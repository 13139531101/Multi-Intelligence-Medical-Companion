import React, { useState, useRef, useEffect } from "react";
import {
  Box,
  Paper,
  TextField,
  Button,
  Typography,
  List,
  ListItem,
  Avatar,
  Chip,
  CircularProgress,
  Alert,
  Divider,
  Fab,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Collapse,
} from "@mui/material";
import {
  Send as SendIcon,
  SmartToy as BotIcon,
  Person as PersonIcon,
  Close as CloseIcon,
  ExpandLess,
  ExpandMore,
  Assistant as AssistantIcon,
} from "@mui/icons-material";
// 改为使用 HostAgent 会话API，而不是智能路由
import {
  createConversation,
  sendMessage as sendMessageApi,
  queryEvents,
  getProcessingMessages,
} from "../api/api";

const AgentAssistant = ({
  agentType = "default",
  contextPrompt = "",
  suggestions = [],
  position = "bottom-right",
  size = "medium",
}) => {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [conversationId, setConversationId] = useState(null);
  const [pollingIntervalId, setPollingIntervalId] = useState(null);
  const messagesEndRef = useRef(null);
  const processedEventIds = useRef(new Set());
  const lastPendingStatusRef = useRef({});

  // 智能体配置映射
  const agentConfigs = {
    health_records: {
      name: "健康档案管理员",
      color: "#4CAF50",
      defaultPrompt: "我需要关于健康档案管理的帮助",
      suggestions: [
        "如何添加新的健康记录？",
        "查看我的病史记录",
        "更新我的健康档案信息",
        "导出我的健康数据",
      ],
    },
    consultation: {
      name: "健康顾问",
      color: "#2196F3",
      defaultPrompt: "我需要健康咨询和建议",
      suggestions: [
        "分析我的症状",
        "提供健康建议",
        "解释检查结果",
        "推荐治疗方案",
      ],
    },
    medication: {
      name: "用药提醒助手",
      color: "#FF9800",
      defaultPrompt: "我需要用药管理方面的帮助",
      suggestions: [
        "设置用药提醒",
        "管理药物清单",
        "检查药物相互作用",
        "用药时间安排",
      ],
    },
    summary: {
      name: "就诊摘要生成器",
      color: "#9C27B0",
      defaultPrompt: "我需要生成的就诊摘要或解析医疗文档",
      suggestions: [
        "生成的就诊摘要",
        "解析医疗报告",
        "整理检查结果",
        "创建健康总结",
      ],
    },
    default: {
      name: "智能助手",
      color: "#757575",
      defaultPrompt: "我需要帮助",
      suggestions: [
        "健康档案管理",
        "医疗咨询建议",
        "用药提醒设置",
        "就诊摘要生成",
      ],
    },
  };

  const currentAgent = agentConfigs[agentType] || agentConfigs.default;
  const finalSuggestions =
    suggestions.length > 0 ? suggestions : currentAgent.suggestions;

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 组件卸载时清理轮询
  useEffect(() => {
    return () => {
      if (pollingIntervalId) clearInterval(pollingIntervalId);
    };
  }, [pollingIntervalId]);

  // 将事件转成对话消息（仅文本展示）
  const formatEventToMessage = (event, conversationId) => {
    let text = "";
    try {
      if (event?.content?.parts && Array.isArray(event.content.parts)) {
        text = event.content.parts
          .map((p) =>
            p.type === "text"
              ? p.text ?? ""
              : typeof p.data === "string"
              ? p.data
              : JSON.stringify(p.data)
          )
          .join("");
      }
    } catch {
      text = "";
    }

    return {
      id: event.id,
      text,
      sender: event.actor === "user" ? "user" : "bot",
      timestamp: new Date(event.timestamp ?? Date.now()),
    };
  };

  const startPolling = (trackedMessageId, convId) => {
    if (!convId) return;
    if (pollingIntervalId) clearInterval(pollingIntervalId);

    const intervalId = setInterval(async () => {
      try {
        const events = await queryEvents(convId);
        if (Array.isArray(events) && events.length > 0) {
          const sorted = [...events].sort((a, b) => a.timestamp - b.timestamp);
          const toAppend = [];
          for (const ev of sorted) {
            if (
              ev.id &&
              ev.content?.metadata?.conversation_id === convId &&
              !processedEventIds.current.has(ev.id)
            ) {
              processedEventIds.current.add(ev.id);
              const msg = formatEventToMessage(ev, convId);
              // 只展示非空且为智能体的消息
              if (msg.sender === "bot" && msg.text && msg.text.trim() !== "") {
                toAppend.push(msg);
              }
            }
          }
          if (toAppend.length > 0) {
            setMessages((prev) => [...prev, ...toAppend]);
          }
        }

        // 处理完成判断 & 显示pending状态文本
        const pending = await getProcessingMessages();
        let stillPending = false;
        let statusText = "";
        if (Array.isArray(pending)) {
          for (const entry of pending) {
            if (Array.isArray(entry) && entry.length >= 2) {
              const [mid, text] = entry;
              if (mid === trackedMessageId) {
                stillPending = true;
                statusText = typeof text === "string" ? text : "";
                break;
              }
            }
          }
        }

        // 仅在状态文本变化时追加一条提示，避免重复刷屏
        if (
          statusText &&
          statusText.trim() !== "" &&
          lastPendingStatusRef.current[trackedMessageId] !== statusText
        ) {
          lastPendingStatusRef.current[trackedMessageId] = statusText;
          setMessages((prev) => [
            ...prev,
            {
              id: `pending:${trackedMessageId}:${Date.now()}`,
              text: statusText,
              sender: "bot",
              timestamp: new Date(),
            },
          ]);
        }

        if (!stillPending) {
          clearInterval(intervalId);
          setPollingIntervalId(null);
          setLoading(false);
        }
      } catch (err) {
        // 遇到错误不立即中断，打印日志并结束本轮
        console.error("轮询出错:", err);
      }
    }, 700);

    setPollingIntervalId(intervalId);
  };

  const ensureConversation = async () => {
    if (conversationId) return conversationId;
    const resp = await createConversation();
    const cid = resp?.conversation_id;
    if (!cid) throw new Error("创建会话失败");
    setConversationId(cid);
    return cid;
  };

  const handleSendMessage = async (messageText = inputMessage) => {
    if (!messageText.trim() || loading) return;

    // 构建完整的消息，包含上下文
    const fullMessage = contextPrompt
      ? `${contextPrompt}\n\n用户问题：${messageText}`
      : messageText;

    const userMessage = {
      id: Date.now(),
      text: messageText,
      sender: "user",
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage("");
    setLoading(true);
    setError("");

    try {
      const cid = await ensureConversation();
      // 直连指定智能体：通过 metadata.selected_agent 传入
      const metadata = { conversation_id: cid };
      if (agentType !== "default" && currentAgent?.name) {
        metadata.selected_agent = currentAgent.name;
      }

      const sendResp = await sendMessageApi({
        role: "user",
        parts: [{ type: "text", text: fullMessage }],
        metadata,
      });

      const serverMessageId = sendResp?.message_id;
      if (serverMessageId) {
        startPolling(serverMessageId, cid);
      } else {
        throw new Error("发送失败：无返回 message_id");
      }
    } catch (err) {
      console.error("发送消息失败:", err);
      setError("发送消息失败，请稍后重试");
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now() + 1,
          text: "抱歉，我现在无法处理您的请求，请稍后重试。",
          sender: "bot",
          timestamp: new Date(),
          isError: true,
        },
      ]);
      setLoading(false);
    }
  };

  const handleSuggestionClick = (suggestion) => {
    handleSendMessage(suggestion);
  };

  const handleKeyPress = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const getPositionStyles = () => {
    const baseStyles = {
      position: "fixed",
    };

    switch (position) {
      case "bottom-right":
        return { ...baseStyles, bottom: 24, right: 24 };
      case "bottom-left":
        return { ...baseStyles, bottom: 24, left: 24 };
      case "top-right":
        return { ...baseStyles, top: 24, right: 24 };
      case "top-left":
        return { ...baseStyles, top: 24, left: 24 };
      default:
        return { ...baseStyles, bottom: 24, right: 24 };
    }
  };

  const getSizeConfig = () => {
    switch (size) {
      case "small":
        return { width: 320, height: 400, fabSize: "medium" };
      case "large":
        return { width: 480, height: 600, fabSize: "large" };
      default:
        return { width: 400, height: 500, fabSize: "large" };
    }
  };

  const sizeConfig = getSizeConfig();

  return (
    <>
      {/* 浮动按钮 */}
      <Fab
        color="primary"
        aria-label="智能助手"
        onClick={() => setOpen(true)}
        sx={{
          ...getPositionStyles(),
          zIndex: 1200,
          bgcolor: currentAgent.color,
          "&:hover": {
            bgcolor: currentAgent.color,
            opacity: 0.9,
          },
        }}
        size={sizeConfig.fabSize}
      >
        <AssistantIcon />
      </Fab>

      {/* 助手对话框 */}
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        hideBackdrop
        maxWidth={false}
        PaperProps={{
          sx: {
            width: sizeConfig.width,
            height: sizeConfig.height,
            maxHeight: "90vh",
            position: "fixed",
            zIndex: 1300,
            display: "flex",
            flexDirection: "column",
            ...getPositionStyles(),
            m: 0,
          },
        }}
      >
        <DialogTitle
          sx={{
            bgcolor: currentAgent.color,
            color: "white",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            py: 1,
          }}
        >
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Avatar
              sx={{ bgcolor: "rgba(255,255,255,0.2)", width: 32, height: 32 }}
            >
              <BotIcon fontSize="small" />
            </Avatar>
            <Typography variant="h6">{currentAgent.name}</Typography>
          </Box>
          <Box>
            <IconButton
              size="small"
              onClick={() => setExpanded(!expanded)}
              sx={{ color: "white", mr: 1 }}
            >
              {expanded ? <ExpandLess /> : <ExpandMore />}
            </IconButton>
            <IconButton
              size="small"
              onClick={() => setOpen(false)}
              sx={{ color: "white" }}
            >
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>

        <Box
          sx={{
            display: expanded ? "flex" : "none",
            flex: 1,
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          <DialogContent
            sx={{
              p: 0,
              display: "flex",
              flexDirection: "column",
              flex: 1,
              overflow: "hidden",
            }}
          >
            {/* 消息列表 */}
            <Box sx={{ flex: 1, overflow: "auto", p: 2, minHeight: 0 }}>
              {messages.length === 0 ? (
                <Box sx={{ textAlign: "center", mt: 2 }}>
                  <BotIcon
                    sx={{ fontSize: 48, color: "text.secondary", mb: 2 }}
                  />
                  <Typography
                    variant="body1"
                    color="text.secondary"
                    gutterBottom
                  >
                    您好！我是{currentAgent.name}
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 2 }}
                  >
                    我可以帮助您解决相关问题
                  </Typography>

                  {/* 建议问题 */}
                  <Box
                    sx={{ display: "flex", flexDirection: "column", gap: 1 }}
                  >
                    {finalSuggestions.map((suggestion, index) => (
                      <Chip
                        key={index}
                        label={suggestion}
                        variant="outlined"
                        clickable
                        onClick={() => handleSuggestionClick(suggestion)}
                        size="small"
                      />
                    ))}
                  </Box>
                </Box>
              ) : (
                <List dense>
                  {messages.map((message) => (
                    <ListItem
                      key={message.id}
                      sx={{
                        flexDirection: "column",
                        alignItems:
                          message.sender === "user" ? "flex-end" : "flex-start",
                        mb: 1,
                      }}
                    >
                      <Box
                        sx={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: 1,
                          maxWidth: "90%",
                          flexDirection:
                            message.sender === "user" ? "row-reverse" : "row",
                        }}
                      >
                        <Avatar
                          sx={{
                            bgcolor:
                              message.sender === "user"
                                ? "primary.main"
                                : currentAgent.color,
                            width: 24,
                            height: 24,
                          }}
                        >
                          {message.sender === "user" ? (
                            <PersonIcon fontSize="small" />
                          ) : (
                            <BotIcon fontSize="small" />
                          )}
                        </Avatar>

                        <Paper
                          elevation={1}
                          sx={{
                            p: 1.5,
                            bgcolor:
                              message.sender === "user"
                                ? "primary.main"
                                : message.isError
                                ? "error.light"
                                : "grey.100",
                            color:
                              message.sender === "user" || message.isError
                                ? "white"
                                : "text.primary",
                          }}
                        >
                          <Typography
                            variant="body2"
                            sx={{ whiteSpace: "pre-wrap" }}
                          >
                            {message.text}
                          </Typography>
                          <Typography
                            variant="caption"
                            sx={{
                              display: "block",
                              mt: 0.5,
                              opacity: 0.7,
                            }}
                          >
                            {message.timestamp.toLocaleTimeString()}
                          </Typography>
                        </Paper>
                      </Box>
                    </ListItem>
                  ))}

                  {loading && (
                    <ListItem sx={{ justifyContent: "center" }}>
                      <Box
                        sx={{ display: "flex", alignItems: "center", gap: 1 }}
                      >
                        <CircularProgress size={16} />
                        <Typography variant="body2" color="text.secondary">
                          思考中...
                        </Typography>
                      </Box>
                    </ListItem>
                  )}
                </List>
              )}
              <div ref={messagesEndRef} />
            </Box>

            <Divider />

            {/* 错误提示 */}
            {error && (
              <Alert severity="error" sx={{ m: 1 }}>
                {error}
              </Alert>
            )}

            {/* 输入区域 */}
            <Box sx={{ p: 2 }}>
              <Box sx={{ display: "flex", gap: 1 }}>
                <TextField
                  fullWidth
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="输入您的问题..."
                  disabled={loading}
                  variant="outlined"
                  size="small"
                />
                <Button
                  variant="contained"
                  onClick={() => handleSendMessage()}
                  disabled={!inputMessage.trim() || loading}
                  sx={{ minWidth: "auto", px: 2 }}
                  size="small"
                >
                  {loading ? (
                    <CircularProgress size={16} color="inherit" />
                  ) : (
                    <SendIcon fontSize="small" />
                  )}
                </Button>
              </Box>
            </Box>
          </DialogContent>
        </Box>
      </Dialog>
    </>
  );
};

export default AgentAssistant;
