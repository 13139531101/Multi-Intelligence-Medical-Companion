import React, { useState, useEffect, useRef } from "react";
import {
  Container,
  Box,
  Paper,
  Typography,
  TextField,
  IconButton,
  Avatar,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Chip,
  Button,
  Grid,
  Card,
  CardContent,
  Fab,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Alert,
  CircularProgress,
} from "@mui/material";
import {
  Send,
  SmartToy,
  Person,
  Add,
  History,
  MedicalServices,
  Psychology,
  FitnessCenter,
  Restaurant,
  LocalHospital,
  AttachFile,
  Mic,
  Stop,
  Delete,
} from "@mui/icons-material";
import { useRecoilValue } from "recoil";
import { userState } from "../store/recoilState";
import Header from "../components/HealthHeader";
import AgentAssistant from "../components/AgentAssistant";
import {
  getConsultationHistory,
  createConsultation,
  sendMessage,
  getConsultationMessages,
  deleteConsultation,
} from "../api/healthApi";
import { listRemoteAgents, getAgentCard, sendTaskStreaming } from "../api/api";
import { v4 as uuidv4 } from "uuid";

const Consultation = () => {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [consultations, setConsultations] = useState([]);
  const [currentConsultationId, setCurrentConsultationId] = useState(null);
  // const [openNewDialog, setOpenNewDialog] = useState(false); // Removed
  // const [consultationTitle, setConsultationTitle] = useState(""); // Removed
  // const [consultationType, setConsultationType] = useState("general"); // Removed
  const [isRecording, setIsRecording] = useState(false);
  const aiContentRef = useRef("");
  // 新增：A2A 状态
  const [agentCardState, setAgentCardState] = useState(null);
  const [sessionId, setSessionId] = useState(uuidv4());
  const abortStreamingRef = useRef(null);
  const currentStreamingMessageIdRef = useRef(null);

  const messagesEndRef = useRef(null);
  const user = useRecoilValue(userState);

  const consultationTypes = [
    {
      value: "general",
      label: "一般咨询",
      icon: <MedicalServices />,
      color: "#2196F3",
    },
    {
      value: "mental",
      label: "心理健康",
      icon: <Psychology />,
      color: "#9C27B0",
    },
    {
      value: "fitness",
      label: "运动健身",
      icon: <FitnessCenter />,
      color: "#4CAF50",
    },
    {
      value: "nutrition",
      label: "营养饮食",
      icon: <Restaurant />,
      color: "#FF9800",
    },
    {
      value: "emergency",
      label: "紧急咨询",
      icon: <LocalHospital />,
      color: "#F44336",
    },
  ];

  const quickQuestions = [
    "我最近总是感到疲劳，这可能是什么原因？",
    "如何改善睡眠质量？",
    "适合我的运动方案有哪些？",
    "如何制定健康的饮食计划？",
    "我的体检报告显示什么问题？",
  ];

  useEffect(() => {
    fetchConsultationHistory();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 初始化默认 Agent
  useEffect(() => {
    const initAgent = async () => {
      try {
        const agents = await listRemoteAgents();
        if (Array.isArray(agents) && agents.length > 0) {
          const advisor =
            agents.find((a) => a?.name === "健康顾问") ||
            agents.find((a) => (a?.name || "").includes("顾问")) ||
            agents[0];
          const addr = advisor?.url || advisor?.address || "";
          if (addr) {
            const card = await getAgentCard(addr);
            setAgentCardState(card);
          }
        }
      } catch (e) {
        console.error("初始化智能体失败:", e);
      }
    };
    initAgent();
  }, []);

  // 组件卸载时清理进行中的流式连接
  useEffect(() => {
    return () => {
      if (abortStreamingRef.current) {
        try {
          abortStreamingRef.current();
        } catch (_) {}
        abortStreamingRef.current = null;
        currentStreamingMessageIdRef.current = null;
      }
    };
  }, []);

  // 当 Agent 变化时重置会话与流
  useEffect(() => {
    setSessionId(uuidv4());
    if (abortStreamingRef.current) {
      abortStreamingRef.current();
      abortStreamingRef.current = null;
      currentStreamingMessageIdRef.current = null;
    }
  }, [agentCardState]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleDeleteConsultation = async (e, id) => {
    e.stopPropagation();
    if (window.confirm("确定要删除这条咨询记录吗？")) {
      try {
        await deleteConsultation(id);
        setConsultations((prev) => prev.filter((c) => c.id !== id));
        if (currentConsultationId === id) {
          setCurrentConsultationId(null);
          setMessages([]);
        }
      } catch (error) {
        console.error("删除咨询失败:", error);
        alert("删除失败，请稍后重试");
      }
    }
  };

  const fetchConsultationHistory = async () => {
    try {
      const history = await getConsultationHistory();
      // Transform history to match UI expected format
      const formattedHistory = history.map((item) => ({
        id: item.consultation_id,
        title:
          item.question.length > 20
            ? item.question.substring(0, 20) + "..."
            : item.question,
        type: "general", // Default or derive from tags
        createdAt: item.created_at,
        messages: [
          {
            id: item.consultation_id + "_q",
            type: "user",
            content: item.question,
            timestamp: new Date(item.created_at),
          },
          {
            id: item.consultation_id + "_a",
            type: "ai",
            content: item.answer,
            timestamp: new Date(item.created_at),
          },
        ],
      }));
      setConsultations(formattedHistory);
    } catch (error) {
      console.error("获取咨询历史失败:", error);
    }
  };

  const handleSendMessage = async () => {
    if (!inputMessage.trim()) return;

    let activeConsultationId = currentConsultationId;

    // If no active consultation, create one
    if (!activeConsultationId) {
      activeConsultationId = await handleCreateConsultation();
      if (!activeConsultationId) return;
      try {
        setCurrentConsultationId(activeConsultationId);
        setSessionId(activeConsultationId);
      } catch (_) {}
    }

    if (!agentCardState?.agentEndpointUrl) {
      console.warn("未配置远程智能体或无法读取 agentEndpointUrl");
      return;
    }

    const userMessage = {
      id: Date.now(),
      type: "user",
      content: inputMessage,
      timestamp: new Date(),
    };

    // Save User Message
    try {
      await sendMessage(activeConsultationId, {
        role: "user",
        content: inputMessage,
      });
    } catch (e) {
      console.warn("保存用户消息失败:", e);
    }

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage("");
    setLoading(true);

    // 插入一个正在流式的 AI 消息
    const agentMsgId = Date.now() + 1;
    setMessages((prev) => [
      ...prev,
      {
        id: agentMsgId,
        type: "ai",
        content: "",
        thinking: "",
        showThinking: false,
        timestamp: new Date(),
        isStreaming: true,
      },
    ]);
    currentStreamingMessageIdRef.current = agentMsgId;
    aiContentRef.current = "";

    try {
      const taskId = uuidv4();
      const payload = {
        id: taskId,
        sessionId: activeConsultationId,
        acceptedOutputModes: ["text", "data"],
        message: {
          role: "user",
          parts: [{ type: "text", text: userMessage.content }],
        },
      };

      abortStreamingRef.current = sendTaskStreaming(
        agentCardState.agentEndpointUrl,
        payload,
        // onMessage
        async (evt) => {
          const statusParts = evt?.result?.status?.message?.parts || [];
          if (statusParts.length && currentStreamingMessageIdRef.current) {
            const thinkingText = statusParts
              .filter((p) => p?.type === "text" && p.text)
              .map((p) => p.text)
              .join("");
            if (thinkingText) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === currentStreamingMessageIdRef.current
                    ? { ...m, thinking: (m.thinking || "") + thinkingText }
                    : m
                )
              );
            }
          }

          // 2) 处理 artifact 分片（主要的流式内容）
          const artifact = evt?.result?.artifact;
          if (
            artifact &&
            artifact.parts &&
            currentStreamingMessageIdRef.current
          ) {
            const { parts, append, lastChunk } = artifact;
            parts.forEach((part) => {
              if (part?.type === "text" && typeof part.text === "string") {
                const text = part.text;
                aiContentRef.current = append
                  ? aiContentRef.current + text
                  : text;

                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === currentStreamingMessageIdRef.current
                      ? {
                          ...m,
                          content: append ? (m.content || "") + text : text,
                          isStreaming: !lastChunk,
                        }
                      : m
                  )
                );
              }
            });
          }

          // 2.1) 兼容：如果结果直接放在 result.message.parts，也进行拼接
          const messageParts = evt?.result?.message?.parts || [];
          if (messageParts.length && currentStreamingMessageIdRef.current) {
            const text = messageParts
              .filter((p) => p?.type === "text" && p.text)
              .map((p) => p.text)
              .join("");
            if (text) {
              aiContentRef.current += text;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === currentStreamingMessageIdRef.current
                    ? { ...m, content: (m.content || "") + text }
                    : m
                )
              );
            }
          }

          // 3) 处理最终完成信号
          if (
            evt?.result?.final ||
            evt?.result?.status?.state === "completed"
          ) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === currentStreamingMessageIdRef.current
                  ? { ...m, isStreaming: false }
                  : m
              )
            );
            setLoading(false);

            // Save AI Message
            try {
              await sendMessage(activeConsultationId, {
                role: "ai",
                content: aiContentRef.current,
              });
            } catch (e) {
              console.warn("保存AI消息失败:", e);
            }
          }
        },
        // onError
        (err) => {
          console.error("发送流式任务失败:", err);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === currentStreamingMessageIdRef.current
                ? {
                    ...m,
                    content: "抱歉，AI 回复失败，请稍后重试。",
                    isStreaming: false,
                  }
                : m
            )
          );
          setLoading(false);
          abortStreamingRef.current = null;
          currentStreamingMessageIdRef.current = null;
        },
        // onClose
        () => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === currentStreamingMessageIdRef.current
                ? { ...m, isStreaming: false }
                : m
            )
          );
          setLoading(false);
          abortStreamingRef.current = null;
          currentStreamingMessageIdRef.current = null;
        }
      );
    } catch (error) {
      console.error("发送消息失败:", error);
      const errorMessage = {
        id: Date.now() + 2,
        type: "ai",
        content: "抱歉，我现在无法回复您的消息。请稍后再试。",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      setLoading(false);
    }
  };

  const handleCreateConsultation = async () => {
    const now = new Date();
    const title = `咨询 ${now.toLocaleString()}`;
    const newSessionId = uuidv4();
    const initialMsg = "您好！我是您的AI健康顾问。请问有什么可以帮您？";

    try {
      // 1. Create in DB immediately
      const result = await createConsultation({
        question: title,
        answer: initialMsg,
        session_id: newSessionId,
        tags: [],
      });

      // 2. Construct local object to update UI immediately
      // Assuming result contains the created ID, or we generate one if backend doesn't return consistent ID for 'consultation_id' vs 'id'
      // But getConsultationHistory maps item.consultation_id to id.
      // Let's assume backend generates an ID. If we don't have it, we might need to fetch history.
      // To be safe and simple: fetch history and select the first one (latest).

      await fetchConsultationHistory();

      // We need to set the current consultation to the one we just created.
      // Since fetchConsultationHistory updates state asynchronously, we can't rely on 'consultations' state here immediately.
      // However, we can try to find it or just reload the page? No, that's bad.

      // Better approach: fetchHistory returns the list?
      // In fetchConsultationHistory:
      // const history = await getConsultationHistory();
      // setConsultations(formattedHistory);
      // I should modify fetchConsultationHistory to return the formatted list.

      const history = await getConsultationHistory();
      const formattedHistory = history.map((item) => ({
        id: item.consultation_id,
        title:
          item.question.length > 20
            ? item.question.substring(0, 20) + "..."
            : item.question,
        type: "general",
        createdAt: item.created_at,
        messages: [
          {
            id: item.consultation_id + "_q",
            type: "user",
            content: item.question,
            timestamp: new Date(item.created_at),
          },
          {
            id: item.consultation_id + "_a",
            type: "ai",
            content: item.answer,
            timestamp: new Date(item.created_at),
          },
        ],
      }));

      setConsultations(formattedHistory);

      // Find the one with our session_id if possible, or just the latest
      // The backend sorts by created_at desc usually?
      // Let's assume the new one is the first one or we match by question title
      const newItem = formattedHistory.find(
        (item) =>
          item.title.includes(title) || item.messages[0].content === title
      );

      if (newItem) {
        handleLoadConsultation(newItem);
        setSessionId(newSessionId); // Ensure session ID matches
      }
      return newSessionId;
    } catch (error) {
      console.error("Failed to create consultation:", error);
      return null;
    }
  };

  const handleLoadConsultation = async (consultation) => {
    setCurrentConsultationId(consultation.id);
    setSessionId(consultation.id);
    try {
      const msgs = await getConsultationMessages(consultation.id);
      if (msgs && msgs.length > 0) {
        const uiMsgs = msgs.map((m) => ({
          id: m.id,
          type: m.role,
          content: m.content,
          timestamp: new Date(m.created_at),
        }));
        setMessages(uiMsgs);
      } else {
        setMessages(consultation.messages || []);
      }
    } catch (e) {
      console.error("Failed to load messages:", e);
      setMessages(consultation.messages || []);
    }
  };

  const handleQuickQuestion = (question) => {
    setInputMessage(question);
  };

  const handleFileUpload = (files) => {
    setAttachedFiles((prev) => [...prev, ...files]);
  };

  const removeAttachedFile = (index) => {
    setAttachedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const getTypeInfo = (type) => {
    return (
      consultationTypes.find((t) => t.value === type) || consultationTypes[0]
    );
  };

  return (
    <Box sx={{ flexGrow: 1, bgcolor: "#f5f5f5", minHeight: "100vh" }}>
      <Header />
      <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
        <Grid container spacing={3} sx={{ height: "calc(100vh - 200px)" }}>
          {/* 左侧：咨询历史 */}
          <Grid item xs={12} md={3} sx={{ height: "100%" }}>
            <Paper
              sx={{ height: "100%", display: "flex", flexDirection: "column" }}
            >
              <Box sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
                <Typography variant="h6" gutterBottom>
                  咨询历史
                </Typography>
                <Button
                  fullWidth
                  variant="contained"
                  startIcon={<Add />}
                  onClick={handleCreateConsultation}
                  sx={{ borderRadius: 2 }}
                >
                  新建咨询
                </Button>
              </Box>
              <List sx={{ flexGrow: 1, overflow: "auto" }}>
                {consultations.map((consultation) => {
                  const typeInfo = getTypeInfo(consultation.type);
                  return (
                    <ListItem
                      key={consultation.id}
                      button
                      selected={currentConsultationId === consultation.id}
                      onClick={() => handleLoadConsultation(consultation)}
                      secondaryAction={
                        <IconButton
                          edge="end"
                          aria-label="delete"
                          onClick={(e) =>
                            handleDeleteConsultation(e, consultation.id)
                          }
                          size="small"
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      }
                      sx={{
                        borderRadius: 1,
                        mx: 1,
                        mb: 1,
                        pr: 6,
                        "&.Mui-selected": {
                          bgcolor: "primary.light",
                          color: "primary.contrastText",
                        },
                      }}
                    >
                      <ListItemAvatar>
                        <Avatar
                          sx={{
                            bgcolor: typeInfo.color,
                            width: 32,
                            height: 32,
                          }}
                        >
                          {typeInfo.icon}
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText
                        primary={
                          <Typography variant="body2" noWrap>
                            {consultation.title}
                          </Typography>
                        }
                        secondary={
                          <Typography variant="caption" color="text.secondary">
                            {new Date(
                              consultation.createdAt
                            ).toLocaleDateString()}
                          </Typography>
                        }
                      />
                    </ListItem>
                  );
                })}
              </List>
            </Paper>
          </Grid>

          {/* 中间：聊天区域 */}
          <Grid item xs={12} md={6} sx={{ height: "100%" }}>
            <Paper
              sx={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
                overflow: "hidden", // Ensure paper doesn't grow
              }}
            >
              {/* 聊天头部 */}
              <Box sx={{ p: 2, borderBottom: 1, borderColor: "divider" }}>
                <Typography variant="h6">
                  {currentConsultationId ? "健康咨询" : "选择或创建咨询"}
                </Typography>
                {currentConsultationId && (
                  <Typography variant="body2" color="text.secondary">
                    AI健康顾问为您提供专业建议
                  </Typography>
                )}
              </Box>

              {/* 消息列表 */}
              <Box sx={{ flexGrow: 1, overflow: "auto", p: 1, minHeight: 0 }}>
                {!currentConsultationId ? (
                  <Box sx={{ textAlign: "center", mt: 4 }}>
                    <SmartToy
                      sx={{ fontSize: 80, color: "text.secondary", mb: 2 }}
                    />
                    <Typography
                      variant="h6"
                      color="text.secondary"
                      gutterBottom
                    >
                      开始您的健康咨询
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      选择一个历史咨询或创建新的咨询开始对话
                    </Typography>
                  </Box>
                ) : (
                  <List>
                    {messages.map((message) => (
                      <ListItem
                        key={message.id}
                        sx={{ alignItems: "flex-start" }}
                      >
                        <ListItemAvatar>
                          <Avatar
                            sx={{
                              bgcolor:
                                message.type === "user"
                                  ? "primary.main"
                                  : "secondary.main",
                            }}
                          >
                            {message.type === "user" ? (
                              <Person />
                            ) : (
                              <SmartToy />
                            )}
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText
                          primary={
                            <Box>
                              <Typography
                                variant="body1"
                                sx={{ whiteSpace: "pre-wrap" }}
                              >
                                {message.content}
                              </Typography>
                              {message.files && message.files.length > 0 && (
                                <Box sx={{ mb: 1 }}>
                                  {message.files.map((file, index) => (
                                    <Chip
                                      key={index}
                                      icon={<AttachFile />}
                                      label={file.name}
                                      size="small"
                                      sx={{ mr: 1, mb: 1 }}
                                    />
                                  ))}
                                </Box>
                              )}
                              {message.type === "ai" && message.thinking && (
                                <Box sx={{ mt: 1 }}>
                                  <Button
                                    variant="outlined"
                                    size="small"
                                    onClick={() => {
                                      setMessages((prev) =>
                                        prev.map((m) =>
                                          m.id === message.id
                                            ? {
                                                ...m,
                                                showThinking: !m.showThinking,
                                              }
                                            : m
                                        )
                                      );
                                    }}
                                  >
                                    {message.showThinking
                                      ? "隐藏思考过程"
                                      : "查看思考过程"}
                                  </Button>
                                  {message.showThinking && (
                                    <Paper
                                      sx={{
                                        mt: 1,
                                        p: 1,
                                        bgcolor: "grey.100",
                                        whiteSpace: "pre-wrap",
                                        fontSize: 14,
                                      }}
                                    >
                                      {message.thinking}
                                    </Paper>
                                  )}
                                </Box>
                              )}
                              {message.suggestions && (
                                <Box sx={{ mt: 1 }}>
                                  {message.suggestions.map(
                                    (suggestion, index) => (
                                      <Chip
                                        key={index}
                                        label={suggestion}
                                        size="small"
                                        variant="outlined"
                                        clickable
                                        onClick={() =>
                                          handleQuickQuestion(suggestion)
                                        }
                                        sx={{ mr: 1, mb: 1 }}
                                      />
                                    )
                                  )}
                                </Box>
                              )}
                            </Box>
                          }
                          secondary={
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
                              {new Date(message.timestamp).toLocaleTimeString()}
                            </Typography>
                          }
                        />
                      </ListItem>
                    ))}
                    {loading && (
                      <ListItem>
                        <ListItemAvatar>
                          <Avatar sx={{ bgcolor: "secondary.main" }}>
                            <SmartToy />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText
                          primary={
                            <Box sx={{ display: "flex", alignItems: "center" }}>
                              <CircularProgress size={20} sx={{ mr: 1 }} />
                              <Typography variant="body2">
                                AI正在思考...
                              </Typography>
                            </Box>
                          }
                        />
                      </ListItem>
                    )}
                    <div ref={messagesEndRef} />
                  </List>
                )}
              </Box>

              {/* 输入区域 */}
              {currentConsultationId && (
                <Box sx={{ p: 2, borderTop: 1, borderColor: "divider" }}>
                  <Box sx={{ display: "flex", alignItems: "flex-end", gap: 1 }}>
                    <TextField
                      fullWidth
                      multiline
                      maxRows={4}
                      placeholder="输入您的健康问题..."
                      value={inputMessage}
                      onChange={(e) => setInputMessage(e.target.value)}
                      onKeyPress={(e) => {
                        if (e.key === "Enter" && !e.shiftKey) {
                          e.preventDefault();
                          handleSendMessage();
                        }
                      }}
                    />
                    <IconButton
                      color="primary"
                      onClick={handleSendMessage}
                      disabled={!inputMessage.trim()}
                    >
                      <Send />
                    </IconButton>
                  </Box>
                </Box>
              )}
            </Paper>
          </Grid>

          {/* 右侧：快速问题和建议 */}
          <Grid item xs={12} md={3} sx={{ height: "100%" }}>
            <Box
              sx={{
                display: "flex",
                flexDirection: "column",
                gap: 2,
                height: "100%",
              }}
            >
              {/* 咨询类型 */}
              <Card>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    咨询类型
                  </Typography>
                  <Grid container spacing={1}>
                    {consultationTypes.map((type) => (
                      <Grid item xs={6} key={type.value}>
                        <Button
                          fullWidth
                          variant="outlined"
                          size="small"
                          startIcon={type.icon}
                          onClick={() => {
                            setConsultationType(type.value);
                            setConsultationTitle(type.label);
                            setOpenNewDialog(true);
                          }}
                          sx={{
                            borderColor: type.color,
                            color: type.color,
                            "&:hover": {
                              bgcolor: type.color,
                              color: "white",
                            },
                          }}
                        >
                          {type.label}
                        </Button>
                      </Grid>
                    ))}
                  </Grid>
                </CardContent>
              </Card>

              {/* 快速问题 */}
              <Card sx={{ flexGrow: 1 }}>
                <CardContent>
                  <Typography variant="h6" gutterBottom>
                    常见问题
                  </Typography>
                  <List dense>
                    {quickQuestions.map((question, index) => (
                      <ListItem
                        key={index}
                        button
                        onClick={() => handleQuickQuestion(question)}
                        sx={{ borderRadius: 1, mb: 1 }}
                      >
                        <ListItemText
                          primary={
                            <Typography variant="body2">{question}</Typography>
                          }
                        />
                      </ListItem>
                    ))}
                  </List>
                </CardContent>
              </Card>
            </Box>
          </Grid>
        </Grid>
      </Container>

      {/* 新建咨询对话框 - 已移除 */}

      {/* 智能助手 */}
      <AgentAssistant
        agentType="consultation"
        contextPrompt="当前用户正在使用健康咨询页面，可能需要医疗建议、症状分析、健康指导等方面的帮助。"
        position="bottom-right"
        size="medium"
      />
    </Box>
  );
};

export default Consultation;
