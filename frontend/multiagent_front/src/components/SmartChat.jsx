import React, { useState, useRef, useEffect } from "react";
import {
  Box,
  Paper,
  Typography,
  TextField,
  IconButton,
  Card,
  CardContent,
  Grid,
  Chip,
  CircularProgress,
  Container,
  Button,
  Collapse,
} from "@mui/material";
import {
  Send as SendIcon,
  ExpandMore as ExpandMoreIcon,
} from "@mui/icons-material";
import {
  smartChat,
  queryEvents,
  getProcessingMessages,
  SMART_CHAT_URL,
} from "../api/api";
import { v4 as uuidv4 } from "uuid";
import axios from "axios";
import { useNavigate } from "react-router-dom";

const SmartChat = () => {
  const [messages, setMessages] = useState([
    {
      message_id: uuidv4(),
      type: "assistant",
      text: "您好！我是智能健康助手。您可以用自然语言描述您的需求，我会自动为您选择最合适的专业智能体来帮助您。",
      timestamp: new Date(),
      agent: "系统",
      role: "assistant",
      content: [
        [
          "您好！我是智能健康助手。您可以用自然语言描述您的需求，我会自动为您选择最合适的专业智能体来帮助您。",
          "text/plain",
        ],
      ],
    },
  ]);
  const [inputMessage, setInputMessage] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [pollingIntervalId, setPollingIntervalId] = useState(null);
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [isThinkingCollapsed, setIsThinkingCollapsed] = useState({});
  const messagesEndRef = useRef(null);
  const processedEventIds = useRef(new Set());
  const maxPollingTime = 30000; // 30秒最大轮询时间
  const pollingStartTime = useRef(null);
  const navigate = useNavigate();

  // 智能路由API实例
  const smartChatApi = axios.create({
    baseURL: SMART_CHAT_URL,
    timeout: 30000,
    headers: {
      "Content-Type": "application/json",
      ...(typeof window !== "undefined" &&
      window.localStorage &&
      window.localStorage.getItem("access_token")
        ? {
            Authorization: `Bearer ${window.localStorage.getItem(
              "access_token"
            )}`,
          }
        : {}),
    },
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  // 切换思考过程显示
  const toggleThinkingCollapse = (messageId) => {
    setIsThinkingCollapsed((prev) => ({
      ...prev,
      [messageId]: !prev[messageId],
    }));
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 组件卸载时清理轮询
  useEffect(() => {
    return () => {
      if (pollingIntervalId) {
        clearInterval(pollingIntervalId);
      }
    };
  }, [pollingIntervalId]);

  // 格式化事件为消息
  const formatEventToMessage = (event, conversationId) => {
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
      text: contentParts.map((part) => part[0]).join(""),
      metadata: {
        conversation_id:
          event.content?.metadata?.conversation_id || conversationId,
      },
      timestamp: event.timestamp,
      actor: event.actor,
      agent: event.content?.role === "assistant" ? "智能助手" : "系统",
      type: event.actor === "user" ? "user" : "assistant",
    };
  };

  // 开始轮询
  const startPolling = (trackedMessageId, conversationId) => {
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
        setIsLoading(false);
        return;
      }

      try {
        // 查询对话的所有事件
        const eventsResponse = await queryEvents(conversationId);

        if (eventsResponse && eventsResponse.length > 0) {
          const newMessagesFromEvents = [];
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
              if (hasContent && formattedMessage.role !== "user") {
                newMessagesFromEvents.push(formattedMessage);
              }
            }
          }

          if (newMessagesFromEvents.length > 0) {
            console.log(
              `[${(elapsedTime / 1000).toFixed(1)}s] 获取到 ${
                newMessagesFromEvents.length
              } 条新消息`
            );
            setMessages((prevMessages) => {
              let newMessages = [...prevMessages];
              for (const nm of newMessagesFromEvents) {
                const lastMsg = newMessages[newMessages.length - 1];
                const nmText = nm.text?.trim();
                const lastText = lastMsg?.text?.trim();

                if (
                  lastMsg &&
                  nm.role === lastMsg.role &&
                  nmText === lastText
                ) {
                  // 重复消息，更新计数
                  const updatedLastMsg = {
                    ...lastMsg,
                    dupCount: (lastMsg.dupCount || 1) + 1,
                  };
                  newMessages = [...newMessages.slice(0, -1), updatedLastMsg];
                } else {
                  // 新消息，正常添加
                  const newMessage = { ...nm, dupCount: 1 };
                  newMessages = [...newMessages, newMessage];

                  // 如果是智能体消息且包含思考过程，默认收缩
                  if (
                    nm.role === "assistant" &&
                    nm.text &&
                    (nm.text.includes("思考") ||
                      nm.text.includes("分析") ||
                      nm.text.includes("考虑") ||
                      nm.text.includes("推理") ||
                      nm.text.includes("判断") ||
                      nm.text.includes("评估") ||
                      nm.text.match(/\d+\./g))
                  ) {
                    setIsThinkingCollapsed((prev) => ({
                      ...prev,
                      [newMessage.message_id]: true, // 默认收缩
                    }));
                  }
                }
              }
              return newMessages;
            });

            // 收到新消息时，重置轮询开始时间
            pollingStartTime.current = Date.now();
          }
        }

        // 检查是否还有待处理的消息
        const pendingResponse = await getProcessingMessages();
        const activeTrackedIdIsStillPending = pendingResponse?.some?.((item) =>
          item.includes(trackedMessageId)
        );

        if (!activeTrackedIdIsStillPending) {
          console.log(
            `[${(elapsedTime / 1000).toFixed(
              1
            )}s] Tracked ID ${trackedMessageId} 已完成处理，停止轮询`
          );
          clearInterval(intervalId);
          setPollingIntervalId(null);
          setIsLoading(false);
        }
      } catch (error) {
        console.error(`[${(elapsedTime / 1000).toFixed(1)}s] 轮询出错:`, error);
      }
    }, 500); // 每0.5秒轮询一次

    setPollingIntervalId(intervalId);
  };

  const sendMessage = async () => {
    if (!inputMessage.trim() || isLoading) return;

    const userMessage = inputMessage.trim();
    setInputMessage("");
    setIsLoading(true);

    const optimisticLocalId = `optimistic-${uuidv4()}`;

    // 添加用户消息
    const userMsg = {
      message_id: optimisticLocalId,
      type: "user",
      text: userMessage,
      timestamp: new Date(),
      role: "user",
      content: [[userMessage, "text/plain"]],
      dupCount: 1,
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      // 发送消息到智能路由
      const response = await smartChatApi.post("/smart_chat", {
        message: userMessage,
      });

      if (!response.data.success) {
        throw new Error(response.data.error || "发送消息失败");
      }

      const { conversation_id, selected_agent } = response.data;
      setCurrentConversationId(conversation_id);

      console.log(
        "消息发送成功，会话ID:",
        conversation_id,
        "选择的智能体:",
        selected_agent
      );

      // 更新用户消息的ID为服务器返回的ID
      const serverMessageId = response.data.message_id;
      if (serverMessageId) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.message_id === optimisticLocalId
              ? { ...msg, message_id: serverMessageId }
              : msg
          )
        );
      }

      // 开始轮询获取智能体响应
      startPolling(serverMessageId || optimisticLocalId, conversation_id);
    } catch (error) {
      console.error("发送消息失败:", error);

      // 保留用户消息，添加错误消息
      setMessages((prev) => [
        ...prev,
        {
          message_id: uuidv4(),
          type: "assistant",
          text: "网络连接出现问题，请检查智能路由API服务是否正常运行。",
          timestamp: new Date(),
          agent: "系统",
          role: "assistant",
          content: [
            [
              "网络连接出现问题，请检查智能路由API服务是否正常运行。",
              "text/plain",
            ],
          ],
          dupCount: 1,
        },
      ]);

      setIsLoading(false);
    }
  };

  const formatTime = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const handleKeyPress = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  const agentHints = [
    {
      icon: "📋",
      title: "健康档案管理员",
      example: '"查看我的健康档案"',
    },
    {
      icon: "👩‍⚕️",
      title: "健康顾问",
      example: '"我有头痛症状"',
    },
    {
      icon: "💊",
      title: "用药提醒助手",
      example: '"设置用药提醒"',
    },
    {
      icon: "📄",
      title: "就诊摘要生成器",
      example: '"生成就诊摘要"',
    },
  ];

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          mb: 2,
        }}
      >
        <Typography variant="h4">智能健康助手</Typography>
        <Button variant="outlined" onClick={() => navigate("/dashboard")}>
          返回仪表盘
        </Button>
      </Box>
      {/* 标题 */}
      <Box textAlign="center" mb={4}>
        <Typography variant="h4" component="h1" gutterBottom>
          🤖 智能健康助手
        </Typography>
        <Typography variant="subtitle1" color="text.secondary">
          一句话调用所有健康智能体
        </Typography>
      </Box>

      {/* 聊天容器 */}
      <Paper elevation={3} sx={{ mb: 4, borderRadius: 3, overflow: "hidden" }}>
        {/* 消息区域 */}
        <Box
          sx={{
            height: 400,
            overflowY: "auto",
            p: 2,
            bgcolor: "#f8f9fa",
          }}
        >
          {messages.map((message, index) => {
            // 处理消息内容
            let displayText = message.text;
            if (message.content && Array.isArray(message.content)) {
              displayText = message.content
                .filter(([content, type]) => type === "text/plain")
                .map(([content]) => content)
                .join("\n");
            }

            const isUser = message.type === "user" || message.role === "user";

            return (
              <Box
                key={message.message_id || index}
                sx={{
                  display: "flex",
                  justifyContent: isUser ? "flex-end" : "flex-start",
                  mb: 2,
                }}
              >
                <Paper
                  elevation={1}
                  sx={{
                    maxWidth: "70%",
                    p: 1.5,
                    bgcolor: isUser ? "primary.main" : "white",
                    color: isUser ? "white" : "text.primary",
                    borderRadius: 2,
                    borderBottomRightRadius: isUser ? 0.5 : 2,
                    borderBottomLeftRadius: !isUser ? 0.5 : 2,
                  }}
                >
                  {/* 思考过程显示 */}
                  {!isUser &&
                    displayText &&
                    (displayText.includes("思考") ||
                      displayText.includes("分析") ||
                      displayText.includes("考虑") ||
                      displayText.includes("推理") ||
                      displayText.includes("判断") ||
                      displayText.includes("评估") ||
                      displayText.match(/\d+\./g)) && ( // 检测是否有编号列表
                      <Box mb={1}>
                        <Button
                          size="small"
                          onClick={() =>
                            toggleThinkingCollapse(message.message_id || index)
                          }
                          sx={{
                            textTransform: "none",
                            fontSize: "0.75rem",
                            color: "primary.main",
                            p: 0.5,
                            minWidth: "auto",
                          }}
                          endIcon={
                            <ExpandMoreIcon
                              sx={{
                                transform: isThinkingCollapsed[
                                  message.message_id || index
                                ]
                                  ? "rotate(0deg)"
                                  : "rotate(180deg)",
                                transition: "transform 0.2s",
                              }}
                            />
                          }
                        >
                          {isThinkingCollapsed[message.message_id || index]
                            ? "显示思考过程"
                            : "隐藏思考过程"}
                        </Button>
                        <Box
                          sx={{
                            mt: 1,
                            p: 1.5,
                            bgcolor: "grey.100",
                            borderRadius: 1,
                            fontSize: "0.875rem",
                            color: "text.secondary",
                          }}
                        >
                          <Typography
                            variant="body2"
                            sx={{
                              whiteSpace: "pre-wrap",
                              fontSize: "0.875rem",
                            }}
                          >
                            {(() => {
                              const thinkingLines = displayText
                                .split("\n")
                                .filter(
                                  (line) =>
                                    line.includes("思考") ||
                                    line.includes("分析") ||
                                    line.includes("考虑") ||
                                    line.includes("推理") ||
                                    line.includes("判断") ||
                                    line.includes("评估") ||
                                    line.match(/^\d+\./)
                                );

                              if (
                                isThinkingCollapsed[message.message_id || index]
                              ) {
                                // 收缩状态：只显示第一行和最后一行
                                if (thinkingLines.length <= 2) {
                                  return thinkingLines.join("\n");
                                } else {
                                  return (
                                    thinkingLines[0] +
                                    "\n...\n" +
                                    thinkingLines[thinkingLines.length - 1]
                                  );
                                }
                              } else {
                                // 展开状态：显示所有思考过程
                                return thinkingLines.join("\n");
                              }
                            })()}
                          </Typography>
                        </Box>
                      </Box>
                    )}

                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                    {/* 过滤掉思考过程，只显示最终回复 */}
                    {!isUser &&
                    displayText &&
                    (displayText.includes("思考") ||
                      displayText.includes("分析") ||
                      displayText.includes("考虑") ||
                      displayText.includes("推理") ||
                      displayText.includes("判断") ||
                      displayText.includes("评估") ||
                      displayText.match(/\d+\./g))
                      ? displayText
                          .split("\n")
                          .filter(
                            (line) =>
                              !line.includes("思考") &&
                              !line.includes("分析") &&
                              !line.includes("考虑") &&
                              !line.includes("推理") &&
                              !line.includes("判断") &&
                              !line.includes("评估") &&
                              !line.match(/^\d+\./) &&
                              line.trim()
                          )
                          .join("\n")
                      : displayText}
                  </Typography>
                  {message.agent && (
                    <Box mt={1}>
                      <Chip
                        label={message.agent}
                        size="small"
                        sx={{
                          bgcolor: "rgba(25, 118, 210, 0.1)",
                          color: "primary.main",
                          fontSize: "0.75rem",
                        }}
                      />
                    </Box>
                  )}
                  <Typography
                    variant="caption"
                    sx={{
                      display: "block",
                      mt: 0.5,
                      opacity: 0.7,
                      textAlign: "right",
                    }}
                  >
                    {formatTime(message.timestamp)}
                  </Typography>
                </Paper>
              </Box>
            );
          })}

          {isLoading && (
            <Box display="flex" justifyContent="flex-start" mb={2}>
              <Paper
                elevation={1}
                sx={{
                  p: 1.5,
                  bgcolor: "white",
                  borderRadius: 2,
                  borderBottomLeftRadius: 0.5,
                  minWidth: 200,
                }}
              >
                <Box display="flex" alignItems="center" gap={1} mb={1}>
                  <CircularProgress size={16} color="primary" />
                  <Typography
                    variant="body2"
                    color="primary"
                    fontWeight="medium"
                  >
                    🤖 智能路由分析中...
                  </Typography>
                </Box>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: "block" }}
                >
                  正在为您选择最合适的专业智能体
                </Typography>
                <Box sx={{ mt: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    • 分析问题类型
                  </Typography>
                  <br />
                  <Typography variant="caption" color="text.secondary">
                    • 匹配专业智能体
                  </Typography>
                  <br />
                  <Typography variant="caption" color="text.secondary">
                    • 生成专业回复
                  </Typography>
                </Box>
              </Paper>
            </Box>
          )}

          <div ref={messagesEndRef} />
        </Box>

        {/* 输入区域 */}
        <Box
          sx={{ p: 2, bgcolor: "white", borderTop: 1, borderColor: "divider" }}
        >
          <Box display="flex" gap={1} alignItems="center">
            <TextField
              fullWidth
              variant="outlined"
              placeholder="输入您的健康问题，我会为您选择最合适的智能体..."
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={isLoading}
              size="small"
              sx={{
                "& .MuiOutlinedInput-root": {
                  borderRadius: 3,
                },
              }}
            />
            <IconButton
              onClick={sendMessage}
              disabled={isLoading || !inputMessage.trim()}
              color="primary"
              sx={{
                bgcolor: "primary.main",
                color: "white",
                "&:hover": {
                  bgcolor: "primary.dark",
                },
                "&:disabled": {
                  bgcolor: "grey.300",
                },
              }}
            >
              <SendIcon />
            </IconButton>
          </Box>
        </Box>
      </Paper>

      {/* 智能体功能提示 */}
      <Paper elevation={2} sx={{ p: 3, borderRadius: 3 }}>
        <Typography variant="h6" gutterBottom>
          💡 智能体功能提示
        </Typography>
        <Grid container spacing={2}>
          {agentHints.map((hint, index) => (
            <Grid item xs={12} sm={6} md={3} key={index}>
              <Card
                elevation={1}
                sx={{
                  textAlign: "center",
                  p: 2,
                  bgcolor: "#f8f9fa",
                  transition: "transform 0.2s, box-shadow 0.2s",
                  "&:hover": {
                    transform: "translateY(-2px)",
                    boxShadow: 3,
                  },
                }}
              >
                <Typography variant="h4" component="div" mb={1}>
                  {hint.icon}
                </Typography>
                <Typography variant="subtitle2" fontWeight="bold" mb={0.5}>
                  {hint.title}
                </Typography>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  fontStyle="italic"
                >
                  {hint.example}
                </Typography>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Paper>
    </Container>
  );
};

export default SmartChat;
