// 自写 chat store + SSE 流. 不依赖 CopilotKit
// 后端: /api/copilotkit (AG-UI: TEXT_MESSAGE_START / TEXT_MESSAGE_CONTENT /
//        TOOL_CALL_START / TOOL_CALL_RESULT / RUN_FINISHED … 兼容旧版 routing/chunk/done)

import React, {
  createContext,
  useContext,
  useReducer,
  useCallback,
} from "react";
import { componentRegistry } from "./ComponentRegistry";

const initialState = {
  open: false,
  messages: [
    {
      id: "welcome",
      role: "assistant",
      content: "你好, 我是你的健康助手. 可以问用药/报告/健康相关的问题.",
    },
  ],
  isThinking: false,
  pageUpdates: [], // AI 触发的页面更新指令
};

function reducer(state, action) {
  switch (action.type) {
    case "toggle":
      return { ...state, open: !state.open };
    case "open":
      return { ...state, open: true };
    case "close":
      return { ...state, open: false };
    case "clear":
      return { ...initialState };
    case "userMsg":
      return {
        ...state,
        messages: [
          ...state.messages,
          { id: "u_" + Date.now(), role: "user", content: action.text },
          {
            id: action.aiId,
            role: "assistant",
            content: "",
            toolCalls: [],
            isStreaming: true,
          },
        ],
        isThinking: true,
        pageUpdates: [], // 清空上次的页面更新
      };
    case "aiPatch":
      return {
        ...state,
        messages: state.messages.map((m) =>
          m.id === action.id ? { ...m, ...action.patch } : m,
        ),
      };
    case "setThinking":
      return { ...state, isThinking: action.value };
    case "pageUpdate":
      // AI 触发的页面组件更新
      return {
        ...state,
        pageUpdates: [...state.pageUpdates, action.update],
      };
    case "clearPageUpdates":
      return { ...state, pageUpdates: [] };
    default:
      return state;
  }
}

const ChatContext = createContext(null);

export function ChatProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const sendMessage = useCallback(async (text) => {
    const aiId = "a_" + Date.now();
    dispatch({ type: "userMsg", text, aiId });

    const headers = {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    };
    const token = localStorage.getItem("token");
    if (token) headers.Authorization = `Bearer ${token}`;

    let resp;
    try {
      resp = await fetch("/api/copilotkit", {
        method: "POST",
        headers,
        body: JSON.stringify({ message: text }),
      });
    } catch (e) {
      dispatch({
        type: "aiPatch",
        id: aiId,
        patch: { content: `网络错误: ${e.message}`, isStreaming: false },
      });
      dispatch({ type: "setThinking", value: false });
      return;
    }

    if (!resp.ok) {
      dispatch({
        type: "aiPatch",
        id: aiId,
        patch: { content: `HTTP ${resp.status}`, isStreaming: false },
      });
      dispatch({ type: "setThinking", value: false });
      return;
    }

    // SSE 流
    const reader = resp.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buf = "";
    let curContent = "";
    let curToolCalls = [];
    const finish = (err) => {
      if (err) {
        dispatch({
          type: "aiPatch",
          id: aiId,
          patch: {
            content: curContent + `\n[错误] ${err}`,
            isStreaming: false,
          },
        });
      } else {
        dispatch({ type: "aiPatch", id: aiId, patch: { isStreaming: false } });
      }
      dispatch({ type: "setThinking", value: false });
    };

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
          const block = buf.slice(0, idx);
          buf = buf.slice(idx + 2);

          let eventName = "message";
          let dataStr = "";
          for (const line of block.split("\n")) {
            const l = line.trimEnd();
            if (l.startsWith("event:")) eventName = l.slice(6).trim();
            else if (l.startsWith("data:")) dataStr += l.slice(5).trim();
          }
          if (!dataStr) continue;

          let payload = {};
          try {
            payload = JSON.parse(dataStr);
          } catch {
            continue;
          }

          // AG-UI 事件类型可能在 SSE event 行, 也可能在 payload.type 里
          if (eventName === "message" && payload.type) {
            eventName = payload.type;
          }

          handleEvent(eventName, payload);
        }
      }
    } catch (e) {
      finish(e.message);
      return;
    }
    finish();

    // ---- 内部分发 ----
    function handleEvent(eventName, payload) {
      // AG-UI 协议
      switch (eventName) {
        case "RUN_STARTED":
          // 流开始：只标记开始，不要在这里结束流式渲染
          // （此前与 TEXT_MESSAGE_END 共用 case，导致流一开始就把消息置为
          //   isStreaming:false，出现渲染闪烁）
          return;

        case "TEXT_MESSAGE_END":
          // 文本结束：一次性渲染完整内容，确保 markdown 能正确匹配
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { content: curContent, isStreaming: false },
          });
          return;

        case "TOOL_CALL_END":
          return; // 标记位, 无 UI 动作

        case "TEXT_MESSAGE_START":
          curContent = "";
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { content: "", isStreaming: true },
          });
          return;

        case "TEXT_MESSAGE_CONTENT":
          // 流式过程中：累积 content，dispatch 让 Bubble 用 textContent 渲染（无 markdown）
          curContent += payload.delta || "";
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { content: curContent },
          });
          return;

        case "TOOL_CALL_START":
          curToolCalls = [
            ...curToolCalls,
            { id: payload.toolCallId, name: payload.toolCallName },
          ];
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { toolCalls: curToolCalls },
          });
          return;

        case "TOOL_CALL_RESULT":
          // 修复: 此前按 t.name === payload.toolCallName 匹配, 同名工具多次调用
          // 会串味, 且后端早期版本压根不发 toolCallName → 结果永远挂不上。
          // 改用 toolCallId (唯一) 匹配, 名字仅作兜底。
          curToolCalls = curToolCalls.map((t) =>
            (payload.toolCallId && t.id === payload.toolCallId) ||
            (payload.toolCallName && t.name === payload.toolCallName)
              ? { ...t, result: payload.content || "" }
              : t,
          );
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { toolCalls: curToolCalls },
          });
          return;

        case "RUN_FINISHED":
          // 流结束，触发 markdown 渲染
          dispatch({ type: "aiPatch", id: aiId, patch: { isStreaming: false } });
          return; // finish() 兜底

        case "RUN_ERROR":
          curContent += `\n[错误] ${payload.message || "未知错误"}`;
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { content: curContent, isStreaming: false },
          });
          return;

        // 兼容旧版 /v2/chat/stream 事件
        case "routing":
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { agent: payload.agent },
          });
          return;
        case "rag_context":
          // 阶段48-fix: 后端在检索完 Magnetic RAG(多跳+KG+rerank) 与 CRAG(纠错)
          // 后发来检索画像。此前无此分支 → 静默丢弃, 用户看不到"答得有没有依据"。
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: {
              ragContext: {
                chunks: payload.chunks || 0,
                score: payload.score || 0,
                isRelevant: !!payload.is_relevant,
                cragAction: payload.crag_action || "",
                sourceMix: payload.source_mix || "",
              },
            },
          });
          return;
        case "chunk":
          curContent += payload.text || "";
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { content: curContent, isStreaming: false },  // chunk 开始就渲染 markdown
          });
          return;
        case "tool_call":
          curToolCalls = [
            ...curToolCalls,
            { id: payload.id, name: payload.name, args: payload.args },
          ];
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { toolCalls: curToolCalls },
          });
          return;
        case "tool_result":
          curToolCalls = curToolCalls.map((t) =>
            t.id === payload.id ? { ...t, result: payload.content } : t,
          );
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { toolCalls: curToolCalls },
          });
          return;
        case "done":
          return; // finish() 兜底
        case "error":
          // 修复: 后端发的是 {error: ...}, 此前只读 payload.message → 真实错误
          // 永远显示成 "undefined"。
          curContent += `\n[错误] ${payload.error || payload.message || "未知错误"}`;
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { content: curContent, isStreaming: false },
          });
          return;

        // ===== agent 主动澄清 / HITL 中断 =====
        // 修复: 后端 runtime 此前无这两个分支 → clarify 节点的问题永远不显示,
        // 用户只看到一条空回复。现在由 copilotkit_runtime 转发过来。
        case "clarification":
          curContent +=
            (curContent ? "\n\n" : "") + `❓ ${payload.question || "需要补充信息"}`;
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: {
              content: curContent,
              isStreaming: false,
              isClarification: true,
            },
          });
          dispatch({ type: "setThinking", value: false });
          return;

        case "interrupt":
          curContent += (curContent ? "\n\n" : "") + "⏸ 需要你确认后继续";
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: {
              content: curContent,
              isStreaming: false,
              isInterrupt: true,
              interruptData: payload.interrupt_data,
            },
          });
          dispatch({ type: "setThinking", value: false });
          return;

        // ===== AI 页面控制指令 =====
        case "PAGE_UPDATE":
          // AI 让页面组件执行操作，如 setData、navigateTo 等
          // payload: { component, action, params, displaySummary }
          if (payload.component && payload.action) {
            console.log(`[useChat] PAGE_UPDATE: ${payload.component}.${payload.action}`, payload.params);
            // 目标组件此刻可能还没挂载 —— 最典型的是"跳转到某条记录"：
            // 后端先发 navigateTo、紧接着发 openRecord，而这时用户还停在原页面。
            // 注册表会把未挂载的指令**排队**，等组件注册时自动排空。
            // 所以这里不能再像以前那样提前 return，否则队列永远填不进去。
            const r = componentRegistry.call(
              payload.component,
              payload.action,
              payload.params,
            );
            if (r && r.queued) {
              curContent +=
                (curContent ? "\n\n" : "") +
                `_（${payload.component} 将在页面打开后执行）_`;
              dispatch({
                type: "aiPatch",
                id: aiId,
                patch: { content: curContent },
              });
            }
            // 同时记录到 state，让 ChatPanel 显示操作摘要
            dispatch({
              type: "pageUpdate",
              update: {
                component: payload.component,
                action: payload.action,
                params: payload.params,
                summary: payload.displaySummary || `已执行 ${payload.action}`,
              },
            });
          }
          return;

        // AI 返回要显示的内容摘要（用于浮窗展示）
        case "DISPLAY_SUMMARY":
          if (payload.content) {
            curContent += `\n\n📊 ${payload.content}`;
            dispatch({
              type: "aiPatch",
              id: aiId,
              patch: { content: curContent },
            });
          }
          return;

        default:
          return;
      }
    }
  }, []);

  return (
    <ChatContext.Provider value={{ state, dispatch, sendMessage }}>
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  const ctx = useContext(ChatContext);
  if (!ctx) throw new Error("useChat must be used inside <ChatProvider>");
  const { state, dispatch, sendMessage } = ctx;
  return {
    open: state.open,
    messages: state.messages,
    isThinking: state.isThinking,
    pageUpdates: state.pageUpdates,       // AI 触发的页面更新指令
    toggle: () => dispatch({ type: "toggle" }),
    openPanel: () => dispatch({ type: "open" }),
    close: () => dispatch({ type: "close" }),
    sendMessage,
    clearPageUpdates: () => dispatch({ type: "clearPageUpdates" }),
  };
}
