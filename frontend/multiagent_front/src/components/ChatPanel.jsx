import React, { useEffect, useRef, useState } from "react";
// 自写 AI 浮窗: SSE 消费 /api/copilotkit, 不依赖 CopilotKit
import {
  Box,
  Paper,
  IconButton,
  TextField,
  Typography,
  CircularProgress,
  Chip,
  Stack,
  Alert,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import SendIcon from "@mui/icons-material/Send";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import VisibilityIcon from "@mui/icons-material/Visibility";
import { useChat } from "./useChat.jsx";

export default function ChatPanel() {
  const { open, toggle, close, messages, isThinking, sendMessage, pageUpdates } = useChat();
  const [input, setInput] = useState("");
  const listRef = useRef(null);

  // 自动滚到底
  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages]);

  // 提交
  const submit = () => {
    const t = input.trim();
    if (!t || isThinking) return;
    setInput("");
    sendMessage(t);
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <>
      {/* 浮窗触发按钮 (右下角) — 风格参考 CopilotKit 的圆形按钮 */}
      <IconButton
        onClick={toggle}
        sx={{
          position: "fixed",
          right: 24,
          bottom: 24,
          zIndex: 1300,
          width: 56,
          height: 56,
          bgcolor: "primary.main",
          color: "white",
          boxShadow: 6,
          "&:hover": { bgcolor: "primary.dark" },
        }}
        aria-label={open ? "关闭 AI 助手" : "打开 AI 助手"}
      >
        {open ? <CloseIcon /> : <SmartToyIcon />}
      </IconButton>

      {/* 浮窗对话框 (右下角弹出) */}
      {open && (
        <Paper
          elevation={8}
          sx={{
            position: "fixed",
            right: 24,
            bottom: 96,
            zIndex: 1299,
            width: 380,
            height: 560,
            display: "flex",
            flexDirection: "column",
            borderRadius: 2,
            overflow: "hidden",
          }}
        >
          {/* 头部 */}
          <Box
            sx={{
              p: 1.5,
              bgcolor: "primary.main",
              color: "white",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <Stack direction="row" spacing={1} alignItems="center">
              <SmartToyIcon fontSize="small" />
              <Typography variant="subtitle1" fontWeight={600}>
                健康小助手
              </Typography>
            </Stack>
            <IconButton size="small" sx={{ color: "white" }} onClick={close}>
              <CloseIcon fontSize="small" />
            </IconButton>
          </Box>

          {/* 消息列表 */}
          <Box
            ref={listRef}
            sx={{
              flex: 1,
              overflowY: "auto",
              p: 2,
              bgcolor: "grey.50",
            }}
          >
            {/* AI 页面更新提示 */}
            {pageUpdates.map((update, i) => (
              <Alert
                key={i}
                severity="info"
                icon={<VisibilityIcon />}
                sx={{ mb: 1, fontSize: 12 }}
              >
                <strong>页面已更新:</strong> {update.summary}
                <br />
                <Typography variant="caption" color="text.secondary">
                  组件 {update.component} 执行了 {update.action}
                </Typography>
              </Alert>
            ))}
            {messages.map((m) => (
              <Bubble key={m.id} msg={m} />
            ))}
          </Box>

          {/* 输入区 */}
          <Box
            sx={{
              p: 1.5,
              borderTop: 1,
              borderColor: "divider",
              display: "flex",
              gap: 1,
              alignItems: "flex-end",
            }}
          >
            <TextField
              fullWidth
              multiline
              maxRows={4}
              size="small"
              placeholder={isThinking ? "AI 正在思考..." : "问点什么..."}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              disabled={isThinking}
            />
            <IconButton
              color="primary"
              onClick={submit}
              disabled={isThinking || !input.trim()}
            >
              {isThinking ? <CircularProgress size={20} /> : <SendIcon />}
            </IconButton>
          </Box>
        </Paper>
      )}
    </>
  );
}

function Bubble({ msg }) {
  const isUser = msg.role === "user";
  return (
    <Box
      sx={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        mb: 1.2,
      }}
    >
      <Box sx={{ maxWidth: "85%" }}>
        {!isUser && msg.agent && (
          <Chip
            size="small"
            label={`→ ${msg.agent}`}
            sx={{ mb: 0.5, fontSize: 11, height: 20 }}
          />
        )}
        <Box
          sx={{
            p: 1.2,
            borderRadius: 2,
            bgcolor: isUser ? "primary.main" : "background.paper",
            color: isUser ? "white" : "text.primary",
            border: isUser ? "none" : 1,
            borderColor: "divider",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            fontSize: 14,
            lineHeight: 1.5,
          }}
        >
          {msg.content || (msg.isStreaming ? "..." : "")}
        </Box>
        {/* 工具调用展示 */}
        {msg.toolCalls && msg.toolCalls.length > 0 && (
          <Stack spacing={0.5} sx={{ mt: 0.8 }}>
            {msg.toolCalls.map((t, i) => (
              <Box
                key={i}
                sx={{
                  p: 0.8,
                  borderRadius: 1,
                  bgcolor: "grey.100",
                  fontSize: 12,
                  fontFamily: "monospace",
                  border: 1,
                  borderColor: "divider",
                }}
              >
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  🔧 {t.name}
                </Typography>
                {t.result && (
                  <Typography
                    variant="caption"
                    component="div"
                    sx={{ mt: 0.4, color: "text.secondary" }}
                  >
                    → {String(t.result).slice(0, 200)}
                  </Typography>
                )}
              </Box>
            ))}
          </Stack>
        )}
      </Box>
    </Box>
  );
}
