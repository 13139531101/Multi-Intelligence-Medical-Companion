import React, { useState } from "react";
import {
  Box, Drawer, Fab, IconButton, Typography, TextField, Button, Stack,
  Avatar, Paper, Chip, LinearProgress,
} from "@mui/material";
import { SmartToy, Close, Send, Bolt, History } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";

// 阶段48-6: 浮动智能体快速按钮 (FAB)
// 任何页面都能调出 → 调用 /v2/chat/stream → 自动归属到合适的 agent
export default function AgentQuickFab() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [reply, setReply] = useState("");
  const [agent, setAgent] = useState("");
  const [loading, setLoading] = useState(false);
  const [toolCalls, setToolCalls] = useState([]); // [{type, name, args, output}]

  const send = async () => {
    if (!q.trim()) return;
    setLoading(true);
    setReply("");
    setAgent("");
    setToolCalls([]);
    try {
      const token = localStorage.getItem("token") || "";
      const apiBase = (import.meta?.env?.VITE_API_BASE) || "http://localhost:13002";
      const resp = await fetch(apiBase + "/v2/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: token ? `Bearer ${token}` : "" },
        body: JSON.stringify({ message: q, metadata: { from_fab: true } }),
      });
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let text = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";
        for (const ev of events) {
          if (ev.includes('event: chunk')) {
            const m = ev.split('\n').find(l => l.startsWith('data: '));
            if (m) {
              try {
                const p = JSON.parse(m.slice(6));
                if (p.text) { text += p.text; setReply(text); }
              } catch { /* ignore */ }
            }
          } else if (ev.includes('event: routing')) {
            const m = ev.split('\n').find(l => l.startsWith('data: '));
            if (m) {
              try {
                const p = JSON.parse(m.slice(6));
                if (p.agent) setAgent(p.agent);
              } catch { /* ignore */ }
            }
          } else if (ev.includes('event: tool_call')) {
            // 工具调用 chip
            const m = ev.split('\n').find(l => l.startsWith('data: '));
            if (m) {
              try {
                const p = JSON.parse(m.slice(6));
                setToolCalls(tc => [...tc, { type: 'tool_call', name: p.name, args: p.args }]);
              } catch { /* ignore */ }
            }
          } else if (ev.includes('event: tool_result')) {
            // 工具结果 chip
            const m = ev.split('\n').find(l => l.startsWith('data: '));
            if (m) {
              try {
                const p = JSON.parse(m.slice(6));
                setToolCalls(tc => [...tc, { type: 'tool_result', name: p.name, output: p.output }]);
              } catch { /* ignore */ }
            }
          }
        }
      }
    } catch (e) {
      setReply("调用失败: " + e.message);
    }
    setLoading(false);
  };

  const openChat = () => {
    setOpen(false);
    if (q.trim()) navigate(`/v2/chat?q=${encodeURIComponent(q)}`);
    else navigate("/v2/chat");
  };

  return (
    <>
      {/* 浮动按钮 - 智能体快问 */}
      <Fab
        color="primary"
        onClick={() => setOpen(true)}
        sx={{
          position: "fixed",
          bottom: 24, right: 24, zIndex: 1000,
          background: "linear-gradient(135deg, #1565C0, #0D47A1)",
          "&:hover": { background: "linear-gradient(135deg, #1976D2, #1565C0)" },
        }}
      >
        <SmartToy />
      </Fab>

      <Drawer anchor="right" open={open} onClose={() => setOpen(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 460 } } }}>
        <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ p: 2, borderBottom: "1px solid", borderColor: "divider", bgcolor: "primary.main", color: "white" }}>
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Avatar sx={{ bgcolor: "rgba(255,255,255,0.2)", color: "white" }}><Bolt /></Avatar>
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>AI 快速咨询</Typography>
                <Typography variant="caption" sx={{ opacity: 0.9 }}>智能路由至最合适的智能体</Typography>
              </Box>
            </Stack>
            <IconButton onClick={() => setOpen(false)} sx={{ color: "white" }}><Close /></IconButton>
          </Stack>
          <Box sx={{ flex: 1, overflowY: "auto", p: 2, bgcolor: "grey.50" }}>
            {!reply ? (
              <Box sx={{ textAlign: "center", color: "text.disabled", py: 4 }}>
                <SmartToy sx={{ fontSize: 64, mb: 1, color: "primary.main", opacity: 0.5 }} />
                <Typography variant="subtitle2" display="block" sx={{ mt: 1 }}>
                  随时问 AI, 它会找最合适的 agent 处理
                </Typography>
                <Typography variant="caption" sx={{ fontSize: "0.7rem", display: "block", mt: 0.5 }}>
                  基于您当前页面 + 档案
                </Typography>
              </Box>
            ) : (
              <Paper sx={{ p: 2, borderLeft: "3px solid", borderColor: "primary.main" }}>
                {agent && (
                  <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 1 }}>
                    <Chip label={agent} size="small" color="primary" />
                    <Typography variant="caption" color="text.secondary">已响应</Typography>
                  </Stack>
                )}
                {toolCalls.length > 0 && (
                  <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", gap: 0.5, mb: 1 }}>
                    {toolCalls.map((tc, i) => (
                      tc.type === "tool_call" ? (
                        <Chip key={i} size="small" label={"🔧 " + tc.name} sx={{ height: 20, fontSize: "0.65rem", bgcolor: "#FFF3E0", color: "#E65100", fontFamily: "monospace" }} />
                      ) : (
                        <Chip key={i} size="small" label={"📋 " + tc.name} sx={{ height: 20, fontSize: "0.65rem", bgcolor: "#E8F5E9", color: "#2E7D32", fontFamily: "monospace" }} />
                      )
                    ))}
                  </Stack>
                )}
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>{reply}</Typography>
              </Paper>
            )}
            {loading && <LinearProgress sx={{ mt: 1 }} />}
          </Box>
          <Box sx={{ p: 2, borderTop: "1px solid", borderColor: "divider", bgcolor: "white" }}>
            <Stack direction="row" spacing={1} alignItems="flex-end">
              <TextField
                fullWidth multiline maxRows={3} size="small"
                placeholder="例如: 这份报告里的指标偏高需要注意什么?"
                value={q} onChange={e => setQ(e.target.value)}
              />
              <Button variant="contained" size="small" onClick={send}
                disabled={loading || !q.trim()} startIcon={<Send />}>
                问
              </Button>
            </Stack>
            <Stack direction="row" spacing={0.5} sx={{ mt: 1 }}>
              <Button size="small" startIcon={<History />} onClick={openChat}>
                完整对话
              </Button>
            </Stack>
          </Box>
        </Box>
      </Drawer>
    </>
  );
}