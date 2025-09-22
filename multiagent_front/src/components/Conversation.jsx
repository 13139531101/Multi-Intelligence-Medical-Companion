import React, { useState, useEffect, useRef } from "react";
import { useRecoilValue, useRecoilState } from "recoil";
import {
  currentConversationIdState,
  messagesState,
} from "../store/recoilState";
import ChatBubble from "./ChatBubble";
import FormRenderer from "./FormRenderer";
import * as api from "../api/api";
import { v4 as uuidv4 } from "uuid";
import TextField from "@mui/material/TextField";
import IconButton from "@mui/material/IconButton";
import SendIcon from "@mui/icons-material/Send";
import CircularProgress from "@mui/material/CircularProgress";
import Box from "@mui/material/Box";

const Conversation = () => {
  const conversationId = useRecoilValue(currentConversationIdState);
  const [messages, setMessages] = useRecoilState(messagesState);
  const [inputText, setInputText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [pollingIntervalId, setPollingIntervalId] = useState(null);
  const processedEventIds = useRef(new Set());
  const maxPollingTime = 30000; // 30秒最大轮询时间
  const pollingStartTime = useRef(null);

  console.log("当前会话 ID:", conversationId);
  // 组件卸载或conversationId变化时清理轮询
  useEffect(() => {
    return () => {
      if (pollingIntervalId) {
        clearInterval(pollingIntervalId);
      }
    };
  }, [pollingIntervalId]);

  const formatEventToMessage = (event, currentConversationId) => {
    let contentParts = [];
    if (event.content && event.content.parts) {
      contentParts = event.content.parts.map((part) => {
        if (part.type === "text") {
          return [
            part.text !== null && typeof part.text !== "undefined"
              ? part.text
              : "",
            "text/plain",
          ];
        } else if (part.type === "data") {
          return [part.data, "application/json"];
        }
        return [part.text || JSON.stringify(part.data) || "", "text/plain"];
      });
    }

    return {
      event_id: event.id || uuidv4(),
      message_id: event.content?.metadata?.message_id,
      role: event.actor === "user" ? "user" : event.content?.role || "agent",
      content: contentParts,
      metadata: {
        conversation_id:
          event.content?.metadata?.conversation_id || currentConversationId,
      },
      timestamp: event.timestamp,
      actor: event.actor,
    };
  };

  const startPolling = (trackedMessageId) => {
    if (!conversationId) return;

    if (pollingIntervalId) {
      clearInterval(pollingIntervalId);
    }

    pollingStartTime.current = Date.now();

    const intervalId = setInterval(async () => {
      const elapsedTime = Date.now() - pollingStartTime.current;
      if (elapsedTime > maxPollingTime) {
        console.log(
          `[${(elapsedTime / 1000).toFixed(1)}s] 轮询超时（超过 ${
            maxPollingTime / 1000
          } 秒），停止轮询`
        );
        clearInterval(intervalId);
        setPollingIntervalId(null);
        setIsSending(false);
        return;
      }
      /// 检查消息处理状态
      let activeTrackedIdIsStillPending = false;
      try {
        // 1. 检查 /message/pending
        const pendingResponse = await api.getProcessingMessages();
        console.log("pendingResponse:", pendingResponse);
        if (pendingResponse) {
          activeTrackedIdIsStillPending = pendingResponse.some((item) =>
            item.includes(trackedMessageId)
          );
          console.log(
            `[${(elapsedTime / 1000).toFixed(
              1
            )}s] 轮询: Tracked ID ${trackedMessageId} 是否仍在处理中: ${activeTrackedIdIsStillPending}`
          );
        } else {
          console.log(
            `[${(elapsedTime / 1000).toFixed(
              1
            )}s] 轮询: 无法确定 ${trackedMessageId} 的处理状态，应该是已完成`
          );
        }

        // 2. 查询对应的conversation的所有事件 /events/query
        const eventsResponse = await api.queryEvents(conversationId);
        console.log("eventsResponse:", eventsResponse);
        if (eventsResponse) {
          const newMessagesFromEvents = [];
          let lastEmptyIdMsg = null; // 用于追踪最近一条 message_id 为空的消息
          const sortedEvents = [...eventsResponse].sort(
            (a, b) => a.timestamp - b.timestamp
          );

          for (const event of sortedEvents) {
            if (
              event.id &&
              event.content?.metadata?.conversation_id === conversationId &&
              !processedEventIds.current.has(event.id)
            ) {
              processedEventIds.current.add(event.id);
              const formattedMessage = formatEventToMessage(
                event,
                conversationId
              );
              const hasContent = formattedMessage.content.some(
                (part) =>
                  (typeof part[0] === "string" && part[0].trim() !== "") ||
                  (typeof part[0] === "object" && part[0] !== null)
              );
              if (hasContent) {
                if (formattedMessage.message_id) {
                  // 有 message_id，直接 push
                  newMessagesFromEvents.push(formattedMessage);
                  lastEmptyIdMsg = null; // 重置
                } else {
                  // message_id 为空
                  if (
                    Array.isArray(formattedMessage.content) &&
                    Array.isArray(lastEmptyIdMsg?.content)
                  ) {
                    // 后续空 id，合并 content 到上一条空 id 消息
                    const lastType = lastEmptyIdMsg.content[0][1];
                    const currentType = formattedMessage.content[0][1];
                    // 合并文本（第 0 项），保留相同的类型（第 1 项）
                    const mergedText =
                      lastEmptyIdMsg.content[0][0] +
                      formattedMessage.content[0][0];
                    lastEmptyIdMsg.content[0][0] = mergedText;
                  } else {
                    // 首条空 id，直接 push
                    newMessagesFromEvents.push(formattedMessage);
                  }
                }
              }
            }
          }
          console.log("newMessagesFromEvents: ", newMessagesFromEvents);

          if (newMessagesFromEvents.length > 0) {
            console.log(
              `[${(elapsedTime / 1000).toFixed(1)}s] 获取到 ${
                newMessagesFromEvents.length
              } 条新消息`
            );
            setMessages((prevMessages) => {
              const currentMessageIds = new Set(
                prevMessages.map((m) => m.message_id)
              );
              let newMessages = [...prevMessages]; // 创建数组的浅拷贝

              for (const nm of newMessagesFromEvents) {
                const lastMsg = newMessages[newMessages.length - 1];

                const nmText = nm.content
                  ?.map((p) => p[0])
                  .join("\n")
                  .trim();
                const lastText = lastMsg?.content
                  ?.map((p) => p[0])
                  .join("\n")
                  .trim();
                const lastMsgId = lastMsg?.message_id;
                const nmMsgId = nm.message_id; //这条消息的 message_id

                if (
                  lastMsg &&
                  nm.role === lastMsg.role &&
                  nmText === lastText
                ) {
                  // 创建 lastMsg 的副本并更新 dupCount
                  const updatedLastMsg = {
                    ...lastMsg,
                    dupCount: (lastMsg.dupCount || 1) + 1,
                  };
                  // 替换 newMessages 中的最后一个消息
                  newMessages = [
                    ...newMessages.slice(0, -1), // 保留除最后一个消息外的所有消息
                    updatedLastMsg, // 添加更新后的最后一个消息
                  ];
                } else {
                  // 新消息，正常添加
                  newMessages = [...newMessages, { ...nm, dupCount: 1 }];
                }
              }

              // 收到新消息时，重置轮询开始时间，延长最大轮询时间
              pollingStartTime.current = Date.now();
              console.log("newMessages:", newMessages);
              return newMessages;
            });
          }
        }

        if (!activeTrackedIdIsStillPending) {
          console.log(
            `[${(elapsedTime / 1000).toFixed(
              1
            )}s] Tracked ID ${trackedMessageId} 已完成处理，停止轮询`
          );
          clearInterval(intervalId);
          setPollingIntervalId(null);
          setIsSending(false);
        }
      } catch (error) {
        console.error(`[${(elapsedTime / 1000).toFixed(1)}s] 轮询出错:`, error);
      }
    }, 500); // 每0.5秒轮询一次

    setPollingIntervalId(intervalId);
  };

  const handleSendMessage = async () => {
    if (!conversationId || !inputText.trim()) {
      return;
    }

    setIsSending(true);
    const optimisticLocalId = `optimistic-${uuidv4()}`;
    const messageContentToSend = inputText;
    setInputText("");

    const userMessage = {
      message_id: optimisticLocalId,
      role: "user",
      content: [[messageContentToSend, "text/plain"]],
      metadata: { conversation_id: conversationId },
      timestamp: Date.now() / 1000,
      dupCount: 1, // 重复次数, 默认为1，和上一条重复
    };
    setMessages((prevMessages) => [...prevMessages, userMessage]);

    try {
      const sendMessageResponse = await api.sendMessage({
        role: "user",
        parts: [{ type: "text", text: messageContentToSend }],
        metadata: { conversation_id: conversationId },
      });

      if (sendMessageResponse && sendMessageResponse.message_id) {
        const serverConfirmedMessageId = sendMessageResponse.message_id;
        console.log(
          "消息发送成功，Server Message ID:",
          serverConfirmedMessageId
        );

        setMessages((prevMessages) =>
          prevMessages.filter((msg) => msg.message_id !== optimisticLocalId)
        );
        startPolling(serverConfirmedMessageId);
      } else {
        console.error("发送消息失败: 响应中无 message_id");
        setMessages((prevMessages) =>
          prevMessages.filter((msg) => msg.message_id !== optimisticLocalId)
        );
        setIsSending(false);
      }
    } catch (error) {
      console.error("发送消息出错:", error);
      setMessages((prevMessages) =>
        prevMessages.filter((msg) => msg.message_id !== optimisticLocalId)
      );
      setIsSending(false);
    }
  };

  const handleInputChange = (event) => {
    setInputText(event.target.value);
  };

  const handleKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey && !isSending) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  // 更新后的 Conversation 组件布局
  return (
    <div className="flex flex-col h-full bg-gray-50 dark:bg-gray-900">
      <div className="flex-1 overflow-hidden">
        <div className="h-full overflow-y-auto">
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
            {messages.map((message) => (
              <div key={message.event_id || uuidv4()} className="group">
                {Array.isArray(message.content) &&
                message.content.some((part) => part[1] === "form") ? (
                  <FormRenderer message={message} />
                ) : (
                  <ChatBubble message={message} />
                )}
              </div>
            ))}
            {isSending && (
              <div className="flex justify-center items-center p-4 space-x-2">
                <CircularProgress
                  size={24}
                  className="text-gray-500 dark:text-gray-400"
                />
                <span className="text-gray-500 dark:text-gray-400 text-sm">
                  思考中...
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 输入区域 */}
      <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <div className="max-w-3xl mx-auto px-4 py-4">
          <div className="flex items-end gap-2">
            <TextField
              fullWidth
              multiline
              variant="outlined"
              placeholder="输入消息..."
              value={inputText}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              disabled={isSending || !conversationId}
              sx={{
                "& .MuiOutlinedInput-root": {
                  borderRadius: "1.5rem",
                  padding: "0.75rem 1.5rem",
                  backgroundColor: "rgba(0, 0, 0, 0.02)",
                  "&.Mui-focused": {
                    boxShadow: "0 0 0 2px rgba(59, 130, 246, 0.5)",
                  },
                },
              }}
            />
            <IconButton
              color="primary"
              onClick={handleSendMessage}
              disabled={isSending || !inputText.trim() || !conversationId}
              sx={{
                height: "48px",
                width: "48px",
                backgroundColor: "rgb(59, 130, 246)",
                "&:hover": {
                  backgroundColor: "rgb(37, 99, 235)",
                },
                "&:disabled": {
                  backgroundColor: "rgb(229, 231, 235)",
                },
              }}
            >
              <SendIcon className="text-white" />
            </IconButton>
          </div>
          <p className="text-center text-xs text-gray-500 dark:text-gray-400 mt-2">
            支持 Markdown 语法 • Shift + Enter 换行
          </p>
        </div>
      </div>
    </div>
  );
};

export default Conversation;
