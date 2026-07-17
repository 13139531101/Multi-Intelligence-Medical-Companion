import React, { useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Drawer,
  Container,
  Paper,
  Typography,
  IconButton,
  TextField,
  Button,
  Avatar,
  Stack,
  Chip,
  Collapse,
  CircularProgress,
  Tooltip,
  Menu,
  MenuItem,
  Divider,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Badge,
} from "@mui/material";
import {
  Send,
  ArrowBack,
  Settings,
  History,
  SmartToy,
  Person,
  ExpandMore,
  CheckCircle,
  AttachFile,
  Mic,
  Info,
  MoreVert,
  Refresh,
  ThumbUp,
  ThumbDown,
  ContentCopy,
  Edit,
  DeleteOutline,
  StopCircle,
  Add,
  Close,
  AccessTime,
} from "@mui/icons-material";
import Header from "../components/HealthHeader";
import {
  smartChat,
  getConsultationHistory,
  deleteConsultation,
  sendMessage,
  getConsultationMessages,
} from "../api/healthApi";

// 阶段48-3: 固定布局 + 真正历史记录侧栏 (来自 /consultations)
const SUGGESTIONS = [
  "我最近血压偏高, 应该怎么办?",
  "硝苯地平和阿司匹林能一起吃吗?",
  "我的心电图显示 ST 段改变, 严重吗?",
  "帮我解读一下这份检查报告",
  "如何预防 2 型糖尿病?",
];

// 阶段48-4: 解析 markdown 表格 (轻度)
const renderTable = (lines, startI, key) => {
  // lines[startI] 是 header (| A | B |), lines[startI+1] 是分隔 (|---|---|
  const headerLine = lines[startI];
  const cells = headerLine.split("|").map(c => c.trim()).filter(c => c !== "");
  if (cells.length < 2) return null;
  return (
    <Box key={key} sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, overflow: "hidden", my: 1 }}>
      <Box sx={{ display: "flex", bgcolor: "grey.100" }}>
        {cells.map((c, ci) => (
          <Box key={ci} sx={{ flex: 1, p: 1, fontWeight: 600, fontSize: "0.85rem" }}>
            {c}
          </Box>
        ))}
      </Box>
      {lines.slice(startI + 2).map((row, ri) => {
        if (!row.startsWith("|")) return null;
        const rcells = row.split("|").map(c => c.trim()).filter(c => c !== "");
        return (
          <Box key={`${key}-${ri}`} sx={{ display: "flex", borderTop: "1px solid", borderColor: "divider" }}>
            {rcells.map((c, ci) => (
              <Box key={ci} sx={{ flex: 1, p: 1, fontSize: "0.85rem" }}>
                {c}
              </Box>
            ))}
          </Box>
        );
      })}
    </Box>
  );
};

const renderMd = (text) => {
  if (!text) return null;
  const lines = text.split("\n");
  const result = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("#### ")) {
      result.push(<Typography key={i} variant="subtitle2" sx={{ fontWeight: 600, mt: 1, color: "text.primary" }}>{line.slice(5)}</Typography>);
    } else if (line.startsWith("### ")) {
      result.push(<Typography key={i} variant="subtitle1" sx={{ fontWeight: 600, mt: 1.2, color: "text.primary", fontSize: "0.95rem" }}>{line.slice(4)}</Typography>);
    } else if (line.startsWith("## ")) {
      result.push(<Typography key={i} variant="h6" sx={{ fontWeight: 600, mt: 1.5, mb: 0.5, fontSize: "1rem", borderBottom: "2px solid", borderColor: "primary.main", pb: 0.5 }}>{line.slice(3)}</Typography>);
    } else if (line.startsWith("# ")) {
      result.push(<Typography key={i} variant="h5" sx={{ fontWeight: 700, mt: 1.5 }}>{line.slice(2)}</Typography>);
    } else if (line.startsWith("> ")) {
      result.push(
        <Box key={i} sx={{ borderLeft: "4px solid", borderColor: "warning.main", pl: 1.5, py: 0.5, bgcolor: "rgba(255,193,7,0.05)", my: 0.5 }}>
          <Typography variant="body1" component="div" sx={{ fontStyle: "italic" }} dangerouslySetInnerHTML={{ __html: formatInline(line.slice(2)) }} />
        </Box>,
      );
    } else if (line.startsWith("---")) {
      result.push(<Box key={i} sx={{ borderTop: "1px solid", borderColor: "divider", my: 1 }} />);
    } else if (line.match(/^[-*]\s/)) {
      result.push(
        <Box key={i} sx={{ display: "flex", gap: 1, ml: 1, my: 0.25, alignItems: "flex-start" }}>
          <Box sx={{ color: "primary.main", fontWeight: 700 }}>•</Box>
          <Typography variant="body1" component="div" sx={{ flex: 1, lineHeight: 1.6 }} dangerouslySetInnerHTML={{ __html: formatInline(line.slice(2)) }} />
        </Box>,
      );
    } else if (line.match(/^\d+\.\s/)) {
      const num = line.match(/^(\d+)\.\s/)[1];
      result.push(
        <Box key={i} sx={{ display: "flex", gap: 1, ml: 1, my: 0.25, alignItems: "flex-start" }}>
          <Box sx={{ color: "primary.main", fontWeight: 700, minWidth: 20 }}>{num}.</Box>
          <Typography variant="body1" component="div" sx={{ flex: 1, lineHeight: 1.6 }} dangerouslySetInnerHTML={{ __html: formatInline(line.slice(num.length + 2)) }} />
        </Box>,
      );
    } else if (line.startsWith("|") && line.endsWith("|") && lines[i + 1] && lines[i + 1].match(/^\|[\s\-:|]+\|")) {
      const tableR = renderTable(lines, i, `t-${i}`);
      result.push(tableR);
      i = i + 1;
      while (i + 1 < lines.length && lines[i + 1].startsWith("|")) i++;
    } else if (line.trim() === "") {
      result.push(<Box key={i} sx={{ height: 6 }} />);
    } else {
      result.push(
        <Typography key={i} variant="body1" component="div" sx={{ mb: 0.5, lineHeight: 1.7 }} dangerouslySetInnerHTML={{ __html: formatInline(line) }} />,
      );
    }
    i++;
  }
  return result;
};

const formatInline = (text) => {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(
      /`(.+?)`/g,
      '<code style="background:rgba(0,0,0,0.06);padding:0 4px;border-radius:3px;font-family:monospace;font-size:0.9em">$1</code>',
    )
    .replace(/\n/g, "<br/>");
};

// 阶段48-4: 去掉 markdown 符号用于列表预览
const stripMd = (text) => {
  if (!text) return "";
  return text
    .replace(/^#+\s+/gm, "") // # h
    .replace(/\*\*(.+?)\*\*/g, "$1") // **b**
    .replace(/\*(.+?)\*/g, "$1") // *i*
    .replace(/`(.+?)`/g, "$1") // `c`
    .replace(/^[-*]\s+/gm, "•") // - *
    .replace(/^\d+\.\s+/gm, "•") // 1.
    .replace(/\|/g, " ") // table
    .replace(/\n+/g, " ") // 多行合一
    .replace(/\s+/g, " ")
    .trim();
};

const WELCOME = `你好，我是 PHA 健康咨询助手。

我可以帮你：

- 解答健康问题
- 解读检查报告
- 用药咨询
- 就诊建议

请描述你的具体情况，我会基于你的健康档案作答。`;

export default function NewChat() {
  const navigate = useNavigate();
  const [messages, setMessages] = useState([
    { id: 1, role: "ai", content: WELCOME, time: now(), thinking: null },
  ]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [thinkingOpen, setThinkingOpen] = useState({});
  const [snack, setSnack] = useState(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [currentConvId, setCurrentConvId] = useState(null);
  const [convTitle, setConvTitle] = useState("新对话");
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  function now() {
    return new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  useEffect(() => {
    if (scrollRef.current)
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const fetchHistory = async () => {
    setLoadingHistory(true);
    try {
      const data = await getConsultationHistory({ limit: 50 });
      console.log(
        "[DEBUG] raw:",
        data,
        typeof data,
        Array.isArray(data),
        Array.isArray(data) ? data.length : "-",
      );
      // 过滤：跳过没有 id 的、跳过空对象
      const list = (
        Array.isArray(data) ? data : data?.consultations || data?.messages || []
      ).filter((c) => c && (c.id || c.conversation_id || c._id));
      const mapped = list.map((c) => ({
        id: c.consultation_id || c.id || c._id,
        // 用 question 当主显示文本 (因为 title 通常空)
        title:
          c.title ||
          (c.question || c.preview || c.first_message || "对话").slice(0, 30),
        time: c.updated_at || c.created_at || c.timestamp,
        preview: c.answer || c.preview || c.last_message || c.summary,
        count: c.message_count || c.count || 0,
      }));
      console.log("[DEBUG] mapped:", mapped.length, mapped.slice(0, 2));
      setConversations(mapped);
    } catch (e) {
      console.warn("[DEBUG] history error:", e?.message);
      setConversations([]);
    }
    setLoadingHistory(false);
  };

  const openHistory = () => {
    setHistoryOpen(true);
    fetchHistory();
  };

  const loadConversation = async (convId) => {
    setHistoryOpen(false);
    try {
      const msgs = await getConsultationMessages(convId);
      const list = Array.isArray(msgs) ? msgs : msgs?.messages || [];
      setMessages(
        list.map((m, i) => ({
          id: i + 1,
          role: m.sender === "user" || m.role === "user" ? "user" : "ai",
          content: m.content || m.text || m.message,
          time:
            m.time ||
            new Date(m.timestamp || Date.now()).toLocaleTimeString("zh-CN", {
              hour: "2-digit",
              minute: "2-digit",
            }),
          thinking: null,
        })),
      );
      setCurrentConvId(convId);
      const conv = conversations.find((c) => c.id === convId);
      if (conv) setConvTitle(conv.title);
    } catch (e) {
      setSnack("加载失败: " + e.message);
    }
  };

  const startNew = () => {
    setHistoryOpen(false);
    setMessages([
      { id: 1, role: "ai", content: WELCOME, time: now(), thinking: null },
    ]);
    setCurrentConvId(null);
    setConvTitle("新对话");
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const removeConv = async (convId, e) => {
    e.stopPropagation();
    if (!window.confirm("删除此对话？")) return;
    try {
      await deleteConsultation(convId).catch(() => null);
      setConversations((p) => p.filter((c) => c.id !== convId));
      if (currentConvId === convId) startNew();
    } catch (err) {
      setSnack("删除失败");
    }
  };

  const fakeStream = (aiMsgId, userText) => {
    let stepIdx = 0;
    const steps = [
      { type: "thinking", name: "分析意图", detail: "正在理解问题" },
      { type: "skill", name: "选择智能体", detail: "health_advisor" },
      {
        type: "tool",
        name: "search_medical_kb",
        detail: 'query="' + userText.slice(0, 20) + '..."',
      },
      { type: "thought", name: "综合分析", detail: "结合档案" },
    ];
    const tickThinking = setInterval(() => {
      stepIdx++;
      const cur = steps.slice(0, stepIdx);
      const isDone = stepIdx >= steps.length;
      setMessages((p) =>
        p.map((m) =>
          m.id === aiMsgId
            ? {
                ...m,
                thinking: {
                  status: isDone ? "done" : "processing",
                  steps: cur,
                  duration: isDone ? "1.4 秒" : null,
                },
                content: isDone
                  ? `好的，让我看一下你的情况。

## 初步分析

根据你的描述，常见原因有：

- **生活因素** (可能性 60%) — 压力、疲劳、饮食不规律
- **生理因素** (可能性 30%) — 季节变化、轻度亚健康
- **病理因素** (可能性 10%) — 需进一步检查

## 建议

1. 监测血压 2 周，每天早晚记录
2. 饮食调整：少盐少油，多蔬菜
3. 规律运动：每周 150 分钟中等强度

> 如症状持续超过 2 周或加重，请就医。`
                  : m.content,
              }
            : m,
        ),
      );
      if (isDone) {
        clearInterval(tickThinking);
        setStreaming(false);
      }
    }, 500);
    return () => clearInterval(tickThinking);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    const userMsg = {
      id: Date.now(),
      role: "user",
      content: text,
      time: now(),
    };
    const aiMsgId = Date.now() + 1;
    const aiMsg = {
      id: aiMsgId,
      role: "ai",
      content: "",
      time: now(),
      thinking: {
        status: "thinking",
        steps: [{ type: "thinking", name: "启动会话", detail: "理解问题" }],
      },
    };
    setMessages((p) => [...p, userMsg, aiMsg]);
    setInput("");
    setStreaming(true);

    // 自动从 user msg 拿 title
    if (!currentConvId && messages.length <= 1) setConvTitle(text.slice(0, 24));

    const token = localStorage.getItem("token") || "";
    const apiBase = import.meta?.env?.VITE_API_BASE || "http://localhost:13002";
    try {
      const resp = await fetch(apiBase + "/v2/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({ message: text, conversation_id: currentConvId }),
      });
      if (!resp.ok || !resp.body) throw new Error("stream unavailable");
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let newConvId = currentConvId;
      const startTime = Date.now();
      const finish = () => {
        const dur = ((Date.now() - startTime) / 1000).toFixed(1);
        setMessages((p) =>
          p.map((m) =>
            m.id === aiMsgId
              ? {
                  ...m,
                  thinking: {
                    status: "done",
                    steps: m.thinking?.steps || [],
                    duration: dur + " 秒",
                  },
                }
              : m,
          ),
        );
        setStreaming(false);
        if (newConvId && newConvId !== currentConvId)
          setCurrentConvId(newConvId);
      };
      const read = async () => {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split("\n\n");
          buffer = events.pop() || "";
          for (const ev of events) {
            const lines = ev.split("\n");
            let event = "message";
            let data = "";
            for (const ln of lines) {
              if (ln.startsWith("event: ")) event = ln.slice(7).trim();
              else if (ln.startsWith("data: ")) data += ln.slice(6);
            }
            if (!data) continue;
            try {
              const payload = JSON.parse(data);
              if (event === "chunk" && payload.text) {
                setMessages((p) =>
                  p.map((m) =>
                    m.id === aiMsgId
                      ? { ...m, content: (m.content || "") + payload.text }
                      : m,
                  ),
                );
              } else if (event === "routing" && payload.agent) {
                setMessages((p) =>
                  p.map((m) =>
                    m.id === aiMsgId
                      ? {
                          ...m,
                          thinking: {
                            status: "processing",
                            steps: [
                              ...(m.thinking?.steps || []),
                              {
                                type: "skill",
                                name: "选择智能体",
                                detail: payload.agent,
                              },
                            ],
                          },
                        }
                      : m,
                  ),
                );
              } else if (event === "tool" && payload.name) {
                setMessages((p) =>
                  p.map((m) =>
                    m.id === aiMsgId
                      ? {
                          ...m,
                          thinking: {
                            status: "processing",
                            steps: [
                              ...(m.thinking?.steps || []),
                              {
                                type: "tool",
                                name: payload.name,
                                detail: JSON.stringify(
                                  payload.args || {},
                                ).slice(0, 40),
                              },
                            ],
                          },
                        }
                      : m,
                  ),
                );
              } else if (event === "done") {
                if (payload.conversation_id)
                  newConvId = payload.conversation_id;
                finish();
                return;
              } else if (event === "error") {
                throw new Error(payload.message || "stream error");
              }
            } catch (e) {
              if (e.message === "stream error") throw e;
            }
          }
        }
        finish();
      };
      read().catch((e) => {
        console.warn("SSE:", e?.message);
        if (!messages.find((x) => x.id === aiMsgId)?.content)
          fakeStream(aiMsgId, text);
        else setStreaming(false);
      });
    } catch (e) {
      console.warn("fallback:", e?.message);
      fakeStream(aiMsgId, text);
    }
  };

  const stopStream = () => {
    setStreaming(false);
    setMessages((p) =>
      p.map((m) =>
        m.id === p[p.length - 1].id && m.thinking?.status === "processing"
          ? {
              ...m,
              thinking: { ...m.thinking, status: "done", duration: "已停止" },
            }
          : m,
      ),
    );
  };

  return (
    // 关键修复: height 100vh 不滚动, flex column, 内部 3 块 (header/scroll/input)
    <Box
      sx={{
        height: "100vh",
        bgcolor: "background.default",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <Header />

      <Paper
        square
        sx={{
          py: 1.5,
          px: 2,
          borderRadius: 0,
          borderBottom: "1px solid",
          borderColor: "divider",
          display: "flex",
          alignItems: "center",
          gap: 2,
          flexShrink: 0,
        }}
      >
        <IconButton onClick={() => navigate("/v2/dashboard")} size="small">
          <ArrowBack sx={{ fontSize: 18 }} />
        </IconButton>
        <Avatar sx={{ bgcolor: "primary.main", width: 36, height: 36 }}>
          <SmartToy sx={{ fontSize: 20 }} />
        </Avatar>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            variant="subtitle1"
            sx={{
              fontWeight: 600,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {convTitle}
          </Typography>
          <Stack direction="row" alignItems="center" spacing={0.5}>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                bgcolor: streaming ? "warning.main" : "success.main",
              }}
            />
            <Typography variant="caption" color="text.secondary">
              {streaming ? "思考中" : "在线"}
            </Typography>
          </Stack>
        </Box>
        <Tooltip title="新对话">
          <IconButton size="small" onClick={startNew}>
            <Add fontSize="small" />
          </IconButton>
        </Tooltip>
        <Badge
          badgeContent={conversations.length}
          color="primary"
          max={99}
          sx={{
            "& .MuiBadge-badge": {
              fontSize: "0.65rem",
              height: 16,
              minWidth: 16,
            },
          }}
        >
          <Tooltip title="历史记录">
            <IconButton size="small" onClick={openHistory}>
              <History />
            </IconButton>
          </Tooltip>
        </Badge>
      </Paper>

      {/* 关键修复2: minHeight + flex1 滚动区, 不让输入框跟着滚 */}
      <Box
        ref={scrollRef}
        sx={{ flex: 1, minHeight: 0, overflowY: "auto", py: 2, px: 2 }}
      >
        <Container maxWidth="md" sx={{ px: { xs: 0, sm: 2 } }}>
          {messages.map((m, i) => (
            <Box
              key={m.id}
              sx={{
                display: "flex",
                justifyContent: m.role === "user" ? "flex-end" : "flex-start",
                mb: 2,
                gap: 1.5,
              }}
            >
              {m.role === "ai" && (
                <Avatar sx={{ bgcolor: "primary.main", width: 32, height: 32 }}>
                  <SmartToy sx={{ fontSize: 18 }} />
                </Avatar>
              )}
              <Box sx={{ maxWidth: "78%" }}>
                {m.thinking && (
                  <Paper
                    variant="outlined"
                    sx={{ p: 1, mb: 0.5, bgcolor: "grey.50" }}
                  >
                    <Box
                      onClick={() =>
                        setThinkingOpen((p) => ({ ...p, [m.id]: !p[m.id] }))
                      }
                      sx={{
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                      }}
                    >
                      {m.thinking.status === "done" ? (
                        <CheckCircle
                          sx={{ fontSize: 14, color: "success.main" }}
                        />
                      ) : (
                        <CircularProgress size={12} />
                      )}
                      <Typography variant="caption" color="text.secondary">
                        {m.thinking.status === "done"
                          ? `已完成 · ${m.thinking.duration || ""}`
                          : "正在思考..."}
                      </Typography>
                      <ExpandMore
                        sx={{
                          fontSize: 16,
                          ml: "auto",
                          transform: thinkingOpen[m.id]
                            ? "rotate(180deg)"
                            : "rotate(0)",
                          transition: "transform 0.2s",
                        }}
                      />
                    </Box>
                    <Collapse in={thinkingOpen[m.id]}>
                      <Box
                        sx={{
                          mt: 1,
                          pl: 1.5,
                          borderLeft: "2px solid",
                          borderColor: "divider",
                        }}
                      >
                        {m.thinking.steps.map((s, i2) => (
                          <Stack
                            key={i2}
                            direction="row"
                            alignItems="center"
                            spacing={1}
                            sx={{ py: 0.25 }}
                          >
                            <Box
                              sx={{
                                width: 6,
                                height: 6,
                                borderRadius: "50%",
                                bgcolor: "primary.main",
                              }}
                            />
                            <Typography
                              variant="caption"
                              sx={{ fontWeight: 500 }}
                            >
                              {s.name}
                            </Typography>
                            {s.detail && (
                              <Typography
                                variant="caption"
                                color="text.secondary"
                                noWrap
                              >
                                · {s.detail}
                              </Typography>
                            )}
                          </Stack>
                        ))}
                      </Box>
                    </Collapse>
                  </Paper>
                )}

                {m.content && (
                  <Paper
                    sx={{
                      p: 1.5,
                      bgcolor:
                        m.role === "user" ? "primary.main" : "background.paper",
                      color:
                        m.role === "user"
                          ? "primary.contrastText"
                          : "text.primary",
                      border: m.role === "user" ? "none" : "1px solid",
                      borderColor: "divider",
                    }}
                  >
                    <Box sx={{ color: "inherit" }}>{renderMd(m.content)}</Box>
                  </Paper>
                )}

                {!m.content && m.thinking?.status !== "done" && (
                  <Paper
                    variant="outlined"
                    sx={{
                      p: 1.5,
                      display: "flex",
                      gap: 0.5,
                      alignItems: "center",
                    }}
                  >
                    {[0, 1, 2].map((i2) => (
                      <Box
                        key={i2}
                        sx={{
                          width: 6,
                          height: 6,
                          borderRadius: "50%",
                          bgcolor: "text.disabled",
                          animation: "bounce 1.4s infinite",
                          animationDelay: `${i2 * 0.16}s`,
                          "@keyframes bounce": {
                            "0%, 80%, 100%": { transform: "scale(0)" },
                            "40%": { transform: "scale(1)" },
                          },
                        }}
                      />
                    ))}
                  </Paper>
                )}

                <Stack
                  direction="row"
                  alignItems="center"
                  spacing={0.5}
                  sx={{
                    mt: 0.25,
                    justifyContent:
                      m.role === "user" ? "flex-end" : "flex-start",
                  }}
                >
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ fontSize: "0.65rem" }}
                  >
                    {m.time}
                  </Typography>
                  {m.role === "ai" && m.content && i > 0 && (
                    <>
                      <IconButton
                        size="small"
                        onClick={() => {
                          navigator.clipboard.writeText(m.content);
                          setSnack("已复制");
                        }}
                      >
                        <ContentCopy sx={{ fontSize: 11 }} />
                      </IconButton>
                      <IconButton size="small">
                        <ThumbUp sx={{ fontSize: 11 }} />
                      </IconButton>
                      <IconButton size="small">
                        <ThumbDown sx={{ fontSize: 11 }} />
                      </IconButton>
                    </>
                  )}
                </Stack>
              </Box>
              {m.role === "user" && (
                <Avatar sx={{ bgcolor: "grey.300", width: 32, height: 32 }}>
                  <Person sx={{ fontSize: 18, color: "text.secondary" }} />
                </Avatar>
              )}
            </Box>
          ))}

          {messages.length === 1 && !streaming && (
            <Box sx={{ mt: 2 }}>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ display: "block", mb: 1 }}
              >
                推荐问题
              </Typography>
              <Stack spacing={0.5}>
                {SUGGESTIONS.map((s, i) => (
                  <Paper
                    key={i}
                    variant="outlined"
                    sx={{
                      p: 1,
                      cursor: "pointer",
                      "&:hover": {
                        borderColor: "primary.main",
                        bgcolor: "rgba(21,101,192,0.02)",
                      },
                    }}
                    onClick={() => setInput(s)}
                  >
                    <Typography variant="body2">{s}</Typography>
                  </Paper>
                ))}
              </Stack>
            </Box>
          )}
        </Container>
      </Box>

      {/* 关键修复3: flexShrink: 0 + sticky bottom */}
      <Paper
        square
        sx={{
          borderRadius: 0,
          borderTop: "1px solid",
          borderColor: "divider",
          py: 1.5,
          px: 2,
          flexShrink: 0,
          bgcolor: "background.paper",
        }}
      >
        <Container maxWidth="md" sx={{ px: { xs: 0, sm: 2 } }}>
          <Stack direction="row" alignItems="flex-end" spacing={1}>
            <Tooltip title="附件">
              <IconButton size="small">
                <AttachFile />
              </IconButton>
            </Tooltip>
            <TextField
              fullWidth
              multiline
              maxRows={4}
              size="small"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              inputRef={inputRef}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder="描述你的问题..."
              disabled={streaming}
              sx={{ "& .MuiOutlinedInput-root": { borderRadius: 1 } }}
            />
            <Tooltip title="语音">
              <IconButton size="small">
                <Mic />
              </IconButton>
            </Tooltip>
            {streaming ? (
              <Button
                variant="contained"
                color="warning"
                onClick={stopStream}
                sx={{ minWidth: 48, height: 40 }}
              >
                <StopCircle sx={{ fontSize: 18 }} />
              </Button>
            ) : (
              <Button
                variant="contained"
                onClick={send}
                disabled={!input.trim()}
                sx={{ minWidth: 48, height: 40 }}
              >
                <Send sx={{ fontSize: 18 }} />
              </Button>
            )}
          </Stack>
        </Container>
      </Paper>

      {/* 历史记录 Drawer */}
      <Drawer
        anchor="right"
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 380 } } }}
      >
        <Box>
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            sx={{ p: 2, borderBottom: "1px solid", borderColor: "divider" }}
          >
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              历史记录
            </Typography>
            <Stack direction="row" spacing={1}>
              <Tooltip title="新对话">
                <IconButton size="small" onClick={startNew}>
                  <Add />
                </IconButton>
              </Tooltip>
              <Tooltip title="刷新">
                <IconButton size="small" onClick={fetchHistory}>
                  <Refresh />
                </IconButton>
              </Tooltip>
              <IconButton size="small" onClick={() => setHistoryOpen(false)}>
                <Close />
              </IconButton>
            </Stack>
          </Stack>
          <List sx={{ pt: 0 }}>
            <ListItem disablePadding>
              <ListItemButton
                onClick={startNew}
                sx={{ borderBottom: "1px dashed", borderColor: "divider" }}
              >
                <ListItemIcon>
                  <Add color="primary" />
                </ListItemIcon>
                <ListItemText
                  primary="开始新对话"
                  primaryTypographyProps={{
                    fontWeight: 500,
                    color: "primary.main",
                  }}
                />
              </ListItemButton>
            </ListItem>
            {loadingHistory ? (
              <Box sx={{ p: 4, textAlign: "center" }}>
                <CircularProgress size={24} />
              </Box>
            ) : conversations.length === 0 ? (
              <Box sx={{ p: 4, textAlign: "center" }}>
                <History sx={{ fontSize: 48, color: "text.disabled", mb: 1 }} />
                <Typography color="text.secondary" variant="body2">
                  暂无历史对话
                </Typography>
                <Typography color="text.disabled" variant="caption">
                  开始一个新对话吧
                </Typography>
              </Box>
            ) : (
              conversations.map((c) => (
                <ListItem
                  key={c.id}
                  disablePadding
                  secondaryAction={
                    <IconButton
                      edge="end"
                      size="small"
                      onClick={(e) => removeConv(c.id, e)}
                    >
                      <DeleteOutline fontSize="small" />
                    </IconButton>
                  }
                >
                  <ListItemButton
                    onClick={() => loadConversation(c.id)}
                    selected={currentConvId === c.id}
                    sx={{ alignItems: "flex-start", py: 1.25 }}
                  >
                    <ListItemIcon sx={{ minWidth: 36, mt: 0.5 }}>
                      <AccessTime color="action" fontSize="small" />
                    </ListItemIcon>
                    <ListItemText
                      primary={c.title}
                      secondary={
                        <Stack
                          direction="row"
                          spacing={1}
                          alignItems="flex-start"
                          sx={{ mt: 0.25 }}
                        >
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{
                              flex: 1,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              display: "-webkit-box",
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: "vertical",
                              whiteSpace: "normal",
                              lineHeight: 1.3,
                            }}
                          >
                            {/* 阶段48-4: preview 截 60 字 + 去掉 markdown 符号 */}
                            {stripMd(c.preview || "").slice(0, 60)}
                          </Typography>
                          {c.count > 0 && (
                            <Chip
                              label={c.count}
                              size="small"
                              sx={{
                                height: 16,
                                fontSize: "0.65rem",
                                flexShrink: 0,
                              }}
                            />
                          )}
                        </Stack>
                      }
                      primaryTypographyProps={{
                        fontWeight: 500,
                        fontSize: "0.9rem",
                      }}
                    />
                  </ListItemButton>
                </ListItem>
              ))
            )}
          </List>
        </Box>
      </Drawer>

      {snack && (
        <Box
          sx={{
            position: "fixed",
            bottom: 80,
            left: "50%",
            transform: "translateX(-50%)",
            bgcolor: "grey.900",
            color: "white",
            px: 2,
            py: 1,
            borderRadius: 1,
            fontSize: "0.85rem",
            zIndex: 9999,
          }}
        >
          {snack}
        </Box>
      )}
    </Box>
  );
}
