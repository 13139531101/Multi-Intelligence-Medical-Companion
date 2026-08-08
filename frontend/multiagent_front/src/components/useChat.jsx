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
        case "TEXT_MESSAGE_END":
          // 流结束时一次性渲染完整内容，确保 formatInline 能正确匹配 markdown
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
          curToolCalls = curToolCalls.map((t) =>
            t.name === payload.toolCallName
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
        case "chunk":
          curContent += payload.text || "";
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { content: curContent },
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
          curContent += `\n[错误] ${payload.message}`;
          dispatch({
            type: "aiPatch",
            id: aiId,
            patch: { content: curContent, isStreaming: false },
          });
          return;

        // ===== AI 页面控制指令 =====
        case "PAGE_UPDATE":
          // AI 让页面组件执行操作，如 setData、navigateTo 等
          // payload: { component, action, params, displaySummary }
          if (payload.component && payload.action) {
            console.log(`[useChat] PAGE_UPDATE: ${payload.component}.${payload.action}`, payload.params);
            // 调用组件注册表
            componentRegistry.call(payload.component, payload.action, payload.params);
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
