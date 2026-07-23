import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Container,
  Grid,
  Card,
  CardContent,
  Typography,
  Button,
  Chip,
  Stack,
  IconButton,
  LinearProgress,
  Paper,
  Avatar,
  Divider,
  Alert,
  CircularProgress,
  Skeleton,
  Drawer,
  TextField,
  Tooltip,
  Badge,
  InputAdornment,
} from "@mui/material";
import {
  FavoriteBorder,
  Medication,
  Description,
  Assignment,
  CloudUpload,
  EditNote,
  Insights,
  AccessTime,
  LocalHospital,
  Science,
  Warning,
  NotificationsNone,
  Person,
  Add,
  ChevronRight,
  AutoAwesome,
  Refresh,
  EventAvailable,
  Timeline,
  Send,
  SmartToy,
  Psychology,
  Bolt,
  Chat,
  HealthAndSafety,
  AssignmentTurnedIn,
  Healing,
  MenuBook,
  Close,
  History,
  MessageOutlined,
  Dashboard as DashboardIcon,
} from "@mui/icons-material";
import {
  getHealthRecords,
  getMedicationReminders,
  getHealthTrends,
  getConsultationHistory,
  smartChat,
} from "../api/healthApi";
import { useAuth } from "../contexts/AuthContext";
import Header from "../components/HealthHeader";
import AgentQuickFab from "../components/AgentQuickFab";
import { buildHealthTrend } from "../utils/healthMetrics";
import ReactMarkdown from "react-markdown";

// 阶段48-6: Dashboard = 智能体中心 (Agent Hub)
// 4 个智能体: health_advisor / health_records / medication_reminder / visit_summary
const AGENTS = [
  {
    id: "health_advisor",
    name: "健康顾问",
    en: "health_advisor",
    desc: "综合问诊、用药咨询、健康建议",
    icon: SmartToy,
    color: "#1565C0",
    bgColor: "#E3F2FD",
    path: "/v2/chat",
    keywords: ["问诊", "咨询", "建议"],
  },
  {
    id: "health_records",
    name: "档案管理",
    en: "health_records",
    desc: "上传检查报告, 自动识别内容, 整理档案",
    icon: Description,
    color: "#00897B",
    bgColor: "#E0F2F1",
    path: "/v2/health-records",
    keywords: ["报告", "档案", "上传"],
  },
  {
    id: "medication_reminder",
    name: "用药提醒",
    en: "medication_reminder",
    desc: "每日服药、定时提醒、依从性追踪",
    icon: Medication,
    color: "#7B1FA2",
    bgColor: "#F3E5F5",
    path: "/v2/medication",
    keywords: ["服药", "提醒", "药品"],
  },
  {
    id: "visit_summary",
    name: "就诊摘要",
    en: "visit_summary",
    desc: "AI 自动汇总病史、医嘱、随访",
    icon: Assignment,
    color: "#E65100",
    bgColor: "#FFF3E0",
    path: "/summary",
    keywords: ["就诊", "摘要"],
  },
];

const QUICK_PROMPTS = [
  { text: "我最近血压偏高怎么办", agent: "health_advisor", color: "#1565C0" },
  {
    text: "帮我上传并解读这份检查报告",
    agent: "health_records",
    color: "#00897B",
  },
  {
    text: "我今天漏服了硝苯地平, 怎么办",
    agent: "medication_reminder",
    color: "#7B1FA2",
  },
  {
    text: "帮我汇总最近 3 个月的病史",
    agent: "visit_summary",
    color: "#E65100",
  },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [stats, setStats] = useState(null);
  const [med, setMed] = useState({ taken: 0, total: 0 });
  const [records, setRecords] = useState({ total: 0 });
  const [trends, setTrends] = useState({ weeks: [], score: 60 });
  const [recentConvs, setRecentConvs] = useState([]);
  const [loading, setLoading] = useState(true);
  // Agent 状态机
  const [activeAgent, setActiveAgent] = useState(null); // 最近被点击的
  // 阶段48-10: 首页嵌入式对话 (替代 Drawer)
  const [quickAskQ, setQuickAskQ] = useState(""); // 当前输入框
  const [quickAskHistory, setQuickAskHistory] = useState([]); // [{id, q, agent, reply, loading, error, time}]
  const [askTarget, setAskTarget] = useState("auto"); // 用户可选 agent 锁定, 默认 auto (host 自动路由)

  const computeScore = (recCount, medTaken, medTotal) => {
    // 阶段48-8: deprecated, 用 utils/healthMetrics.js 的真实算法替代
    const r = Math.min(recCount * 5, 30);
    const m = medTotal > 0 ? (medTaken / medTotal) * 70 : 0;
    return Math.round(r + m);
  };

  const fetchAll = async () => {
    setLoading(true);
    try {
      const tasks = [
        getHealthRecords().catch(() => []),
        getMedicationReminders({ today: true }).catch(() => []),
        getHealthTrends({ days: 30 }).catch(() => null),
        getConsultationHistory({ limit: 4 }).catch(() => []),
      ];
      const [recs, meds, trend, convs] = await Promise.all(tasks);

      const recList = Array.isArray(recs) ? recs : recs?.records || [];
      const medList = Array.isArray(meds) ? meds : meds?.reminders || [];
      const medTaken = medList.filter(
        (m) => m.taken || m.status === "taken",
      ).length;
      const medTotal = medList.length;

      setRecords({ total: recList.length });
      setMed({ taken: medTaken, total: medTotal });

      // 阶段48-8: 用真实算法替换 mock — 先算 trendResult, 因为 setStats 要用
      const trendResult = buildHealthTrend({
        records: recList,
        reminders: medList,
        consultations: Array.isArray(convs) ? convs : [],
      });

      setStats({
        score: trendResult.today.score,
        records: recList.length,
        exams: recList.filter((r) => r.record_type === "examination").length,
        allergies: recList.filter((r) => r.record_type === "allergy").length,
        reports: recList.filter((r) => r.record_type === "report").length,
      });
      // 阶段48-22 v4+: 调试 — 让用户在 console 看到 score 是怎么算出来的
      console.log("[Dashboard] computed:", {
        recCount: recList.length,
        medCount: medList.length,
        medTaken,
        score: trendResult.today.score,
        components: trendResult.today.components,
      });

      // 把 days 转成 weeks 格式 (前端用)
      const weeks = trendResult.days.map((d) => ({
        day: d.label,
        value: d.score ?? trendResult.today.score,
        date: d.date,
      }));

      setTrends({
        weeks,
        score: trendResult.today.score,
        cov: Math.round(trendResult.components.coverage),
        comp: Math.round(trendResult.components.compliance),
        act: Math.round(trendResult.components.activity),
        stab: Math.round(trendResult.components.stability),
        slope: trendResult.trend.slope,
        r: trendResult.trend.r,
        trendLabel: trendResult.trend.label,
        trendColor: trendResult.trend.color,
        historicalN: trendResult.trend.n,
        comparison: trendResult.comparison,
      });
      setRecentConvs(Array.isArray(convs) ? convs.slice(0, 4) : []);
      setLoading(false);
    } catch (e) {
      // 阶段48-22 v4+: 真算法跑失败 (buildHealthTrend 抛错), 兜底:
      // 设一个 0 分占位, 至少不让 "数据收集中" 卡死
      console.error("[Dashboard] fetchAll failed:", e);
      setStats({
        score: 0,
        records: recList?.length || 0,
        exams: 0,
        allergies: 0,
        reports: 0,
      });
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAll();
  }, []);

  // 阶段48-10: 嵌入式对话, 在 history 数组 append 一个 entry
  const handleAskAgent = async (agentId, q) => {
    const userQ = (q || "").trim();
    if (!userQ) return;
    const targetAgent = agentId || askTarget || "auto";

    // 1) push 一条 pending entry
    const entryId = `qk_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    const initialAgent =
      targetAgent === "auto" ? "auto-routing..." : targetAgent;
    const newEntry = {
      id: entryId,
      q: userQ,
      agent: initialAgent,
      reply: "",
      loading: true,
      error: null,
      time: new Date(),
    };
    setQuickAskHistory((h) => [newEntry, ...h].slice(0, 10)); // 保留最近 10 条
    setQuickAskQ("");
    setActiveAgent(initialAgent);

    try {
      const token = localStorage.getItem("token") || "";
      const apiBase =
        import.meta?.env?.VITE_API_BASE || "http://localhost:13002";
      const metadata = { from_dashboard: true };
      if (targetAgent && targetAgent !== "auto") {
        metadata.selected_agent = targetAgent;
      }
      const resp = await fetch(apiBase + "/v2/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({ message: userQ, metadata }),
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
          if (ev.includes("event: chunk")) {
            const m = ev.split("\n").find((l) => l.startsWith("data: "));
            if (m) {
              try {
                const p = JSON.parse(m.slice(6));
                if (p.text) {
                  text += p.text;
                  setQuickAskHistory((h) =>
                    h.map((e) =>
                      e.id === entryId ? { ...e, reply: text } : e,
                    ),
                  );
                }
              } catch {
                /* ignore */
              }
            }
          } else if (ev.includes("event: routing")) {
            const m = ev.split("\n").find((l) => l.startsWith("data: "));
            if (m) {
              try {
                const p = JSON.parse(m.slice(6));
                if (p.agent) {
                  setQuickAskHistory((h) =>
                    h.map((e) =>
                      e.id === entryId ? { ...e, agent: p.agent } : e,
                    ),
                  );
                  setActiveAgent(p.agent);
                }
              } catch {
                /* ignore */
              }
            }
          } else if (ev.includes("event: tool_call")) {
            // 阶段48-11: 工具调用 — 推到 entry 的 steps
            const m = ev.split("\n").find((l) => l.startsWith("data: "));
            if (m) {
              try {
                const p = JSON.parse(m.slice(6));
                setQuickAskHistory((h) =>
                  h.map((e) =>
                    e.id === entryId
                      ? {
                          ...e,
                          steps: [
                            ...(e.steps || []),
                            {
                              type: "tool_call",
                              name: p.name,
                              args: p.args,
                              t: new Date(),
                            },
                          ],
                        }
                      : e,
                  ),
                );
              } catch {
                /* ignore */
              }
            }
          } else if (ev.includes("event: tool_result")) {
            // 阶段48-11: 工具返回结果
            const m = ev.split("\n").find((l) => l.startsWith("data: "));
            if (m) {
              try {
                const p = JSON.parse(m.slice(6));
                setQuickAskHistory((h) =>
                  h.map((e) =>
                    e.id === entryId
                      ? {
                          ...e,
                          steps: [
                            ...(e.steps || []),
                            {
                              type: "tool_result",
                              name: p.name,
                              output: p.output,
                              t: new Date(),
                            },
                          ],
                        }
                      : e,
                  ),
                );
              } catch {
                /* ignore */
              }
            }
          }
        }
      }
      // 标记完成
      setQuickAskHistory((h) =>
        h.map((e) => (e.id === entryId ? { ...e, loading: false } : e)),
      );
    } catch (e) {
      setQuickAskHistory((h) =>
        h.map((entry) =>
          entry.id === entryId
            ? {
                ...entry,
                loading: false,
                error: e.message,
                reply: entry.reply || `调用失败: ${e.message}`,
              }
            : entry,
        ),
      );
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Header />

      <Container maxWidth="lg" sx={{ py: 3 }}>
        {/* 阶段48-10: 首页嵌入式对话面板 - 不是 Drawer, 是 dashboard 一部分 */}
        <Paper
          sx={{
            p: 0,
            mb: 3,
            borderRadius: 2,
            border: "1px solid",
            borderColor: "divider",
            overflow: "hidden",
            boxShadow: 1,
          }}
        >
          {/* 蓝色问候 header */}
          <Box sx={{ bgcolor: "primary.main", color: "white", px: 2.5, py: 2 }}>
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Avatar
                sx={{
                  bgcolor: "white",
                  color: "primary.main",
                  width: 36,
                  height: 36,
                }}
              >
                <SmartToy fontSize="small" />
              </Avatar>
              <Box sx={{ flex: 1 }}>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  你好, {user?.username || "用户"}
                </Typography>
                <Typography variant="caption" sx={{ opacity: 0.9 }}>
                  有任何健康问题, 直接问我 — 我会自动找最合适的 AI 回答
                </Typography>
              </Box>
              {askTarget !== "auto" && (
                <Chip
                  label={`锁定 ${askTarget}`}
                  size="small"
                  onClick={() => setAskTarget("auto")}
                  sx={{
                    bgcolor: "rgba(255,255,255,0.2)",
                    color: "white",
                    cursor: "pointer",
                  }}
                />
              )}
            </Stack>
          </Box>

          {/* 输入栏 (始终在顶部) */}
          <Box
            sx={{
              px: 2,
              py: 1.5,
              bgcolor: "background.paper",
              borderBottom: 1,
              borderColor: "divider",
            }}
          >
            <TextField
              fullWidth
              size="small"
              multiline
              maxRows={3}
              placeholder="我血压 145/95 怎么办?  今天吃什么药?  这份报告什么意思?"
              value={quickAskQ}
              onChange={(e) => setQuickAskQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && quickAskQ.trim()) {
                  e.preventDefault();
                  handleAskAgent("auto", quickAskQ);
                }
              }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <MessageOutlined
                      fontSize="small"
                      sx={{ color: "text.disabled" }}
                    />
                  </InputAdornment>
                ),
                endAdornment: quickAskQ.trim() ? (
                  <InputAdornment position="end">
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={() => handleAskAgent("auto", quickAskQ)}
                      disabled={!quickAskQ.trim()}
                    >
                      <Send fontSize="small" />
                    </IconButton>
                  </InputAdornment>
                ) : null,
                sx: { borderRadius: 2, bgcolor: "grey.50" },
              }}
            />
            {/* 快捷 chip + 清空 */}
            <Stack
              direction="row"
              spacing={0.5}
              sx={{ mt: 1, flexWrap: "wrap", gap: 0.5, alignItems: "center" }}
            >
              <Typography variant="caption" color="text.disabled">
                试试:
              </Typography>
              {["我血压偏高怎么办", "今天吃什么药", "帮我看体检报告"].map(
                (s, i) => (
                  <Chip
                    key={i}
                    label={s}
                    size="small"
                    variant="outlined"
                    onClick={() => handleAskAgent("auto", s)}
                    sx={{ cursor: "pointer", fontSize: "0.7rem", height: 22 }}
                  />
                ),
              )}
              {quickAskHistory.length > 0 && <Box sx={{ flex: 1 }} />}
              {quickAskHistory.length > 0 && (
                <Chip
                  label="清空对话"
                  size="small"
                  onClick={() => setQuickAskHistory([])}
                  sx={{ cursor: "pointer", fontSize: "0.7rem", height: 22 }}
                  variant="outlined"
                  color="default"
                />
              )}
            </Stack>
          </Box>

          {/* 对话历史 (嵌入式, 流式更新) */}
          {quickAskHistory.length > 0 && (
            <Box sx={{ maxHeight: 480, overflowY: "auto" }}>
              {quickAskHistory.map((entry, idx) => (
                <Box
                  key={entry.id}
                  sx={{
                    px: 2.5,
                    py: 2,
                    borderBottom: idx < quickAskHistory.length - 1 ? 1 : 0,
                    borderColor: "divider",
                    bgcolor: idx % 2 === 0 ? "grey.50" : "background.paper",
                  }}
                >
                  {/* 用户问题 */}
                  <Stack direction="row" alignItems="flex-start" spacing={1.5}>
                    <Avatar
                      sx={{ bgcolor: "secondary.main", width: 28, height: 28 }}
                    >
                      <Typography
                        variant="caption"
                        sx={{ color: "white", fontWeight: 600 }}
                      >
                        {(user?.username || "U").charAt(0).toUpperCase()}
                      </Typography>
                    </Avatar>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Stack
                        direction="row"
                        alignItems="center"
                        spacing={1}
                        sx={{ mb: 0.25 }}
                      >
                        <Typography variant="caption" color="text.secondary">
                          你 ·{" "}
                          {entry.time.toLocaleTimeString("zh", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </Typography>
                      </Stack>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {entry.q}
                      </Typography>
                    </Box>
                  </Stack>

                  {/* AI 回答 */}
                  <Stack
                    direction="row"
                    alignItems="flex-start"
                    spacing={1.5}
                    sx={{ mt: 1.5 }}
                  >
                    <Avatar
                      sx={{ bgcolor: "primary.main", width: 28, height: 28 }}
                    >
                      <SmartToy sx={{ fontSize: 16, color: "white" }} />
                    </Avatar>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Stack
                        direction="row"
                        alignItems="center"
                        spacing={1}
                        sx={{ mb: 0.5 }}
                      >
                        <Chip
                          size="small"
                          label={
                            entry.agent === "auto-routing..."
                              ? "routing…"
                              : entry.agent
                          }
                          sx={{
                            height: 18,
                            fontSize: "0.65rem",
                            fontFamily: "monospace",
                            bgcolor:
                              entry.agent === "auto-routing..."
                                ? "warning.light"
                                : "#E3F2FD",
                            color:
                              entry.agent === "auto-routing..."
                                ? "warning.dark"
                                : "#1565C0",
                          }}
                        />
                        {entry.error && (
                          <Chip
                            size="small"
                            label="error"
                            color="error"
                            sx={{ height: 18, fontSize: "0.65rem" }}
                          />
                        )}
                      </Stack>
                      {entry.reply ? (
                        <>
                          {/* 阶段48-11: 工具调用步骤 (chip 列表, 可展开) */}
                          {entry.steps && entry.steps.length > 0 && (
                            <Box sx={{ mb: 1.5 }}>
                              <Stack
                                direction="row"
                                spacing={0.5}
                                sx={{ flexWrap: "wrap", gap: 0.5, mb: 0.5 }}
                              >
                                {entry.steps
                                  .filter((s) => s.type === "tool_call")
                                  .map((s, i) => (
                                    <Chip
                                      key={`tc_${i}`}
                                      size="small"
                                      icon={
                                        <Science
                                          sx={{ fontSize: "0.9rem !important" }}
                                        />
                                      }
                                      label={`🔧 ${s.name}`}
                                      sx={{
                                        height: 20,
                                        fontSize: "0.65rem",
                                        bgcolor: "#FFF3E0",
                                        color: "#E65100",
                                        fontFamily: "monospace",
                                      }}
                                    />
                                  ))}
                              </Stack>
                            </Box>
                          )}
                          {/* 阶段48-11: Markdown 渲染答案 (支持 ##, **, 列表, 表格) */}
                          <Box
                            sx={{
                              color: "text.primary",
                              lineHeight: 1.7,
                              fontSize: "0.875rem",
                              "& h1, & h2, & h3": {
                                fontSize: "1.1rem",
                                fontWeight: 600,
                                mt: 2,
                                mb: 1,
                                color: "primary.main",
                              },
                              "& p": { my: 1 },
                              "& ul, & ol": { pl: 2.5, my: 1 },
                              "& li": { my: 0.5 },
                              "& code": {
                                bgcolor: "grey.100",
                                px: 0.5,
                                borderRadius: 0.5,
                                fontSize: "0.8rem",
                              },
                              "& pre": {
                                bgcolor: "grey.100",
                                p: 1.5,
                                borderRadius: 1,
                                overflow: "auto",
                              },
                              "& blockquote": {
                                borderLeft: "3px solid",
                                borderColor: "warning.main",
                                bgcolor: "warning.light",
                                px: 1.5,
                                py: 0.5,
                                my: 1,
                                color: "warning.dark",
                                fontStyle: "italic",
                              },
                              "& hr": {
                                my: 2,
                                border: 0,
                                borderTop: 1,
                                borderColor: "divider",
                              },
                              "& table": {
                                borderCollapse: "collapse",
                                width: "100%",
                                my: 1,
                              },
                              "& th, & td": {
                                border: "1px solid",
                                borderColor: "divider",
                                px: 1,
                                py: 0.5,
                                fontSize: "0.75rem",
                              },
                              "& th": {
                                bgcolor: "grey.50",
                                fontWeight: 600,
                              },
                            }}
                          >
                            <ReactMarkdown>{entry.reply}</ReactMarkdown>
                            {entry.loading && <span>▍</span>}
                          </Box>
                        </>
                      ) : entry.loading ? (
                        <Stack
                          direction="row"
                          spacing={0.5}
                          sx={{ pt: 0.5, alignItems: "center" }}
                        >
                          <CircularProgress size={12} />
                          <Typography variant="caption" color="text.disabled">
                            思考中…
                          </Typography>
                        </Stack>
                      ) : (
                        <Typography variant="caption" color="text.disabled">
                          (无回复)
                        </Typography>
                      )}
                    </Box>
                  </Stack>
                </Box>
              ))}
            </Box>
          )}

          {/* 无历史时显示空状态 */}
          {quickAskHistory.length === 0 && (
            <Box sx={{ p: 3, textAlign: "center", color: "text.disabled" }}>
              <SmartToy sx={{ fontSize: 36, mb: 1, opacity: 0.4 }} />
              <Typography variant="body2">
                对话将在这里显示 · 试试点击上面的快捷话题
              </Typography>
            </Box>
          )}
        </Paper>

        {/* 阶段48-7: 简洁 4 个 agent 卡片 - 跳转而非自动答 */}
        <Box sx={{ mb: 3 }}>
          <Stack
            direction="row"
            alignItems="center"
            spacing={1}
            sx={{ mb: 1.5 }}
          >
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              4 个智能体
            </Typography>
            <Typography variant="caption" color="text.secondary">
              点击卡片进入
            </Typography>
          </Stack>
          <Grid container spacing={1.5}>
            {AGENTS.map((ag) => {
              const Icon = ag.icon;
              return (
                <Grid item xs={6} md={3} key={ag.id}>
                  <Card
                    sx={{
                      cursor: "pointer",
                      transition: "all 0.15s",
                      border: 1,
                      borderColor: askTarget === ag.en ? ag.color : "divider",
                      bgcolor:
                        askTarget === ag.en ? ag.bgColor : "background.paper",
                      "&:hover": { borderColor: ag.color, boxShadow: 1 },
                    }}
                    onClick={() => {
                      // 阶段48-10: 锁定该 agent, 把推荐示例填入嵌入式对话
                      setAskTarget(ag.en);
                      const example =
                        ag.id === "health_advisor"
                          ? `最近感觉不舒服, ${ag.name.replace(/[^\u4e00-\u9fa5]/g, "")}能帮分析一下吗?`
                          : ag.id === "health_records"
                            ? `帮我看看最近的检查报告有什么需要注意的`
                            : ag.id === "medication_reminder"
                              ? `今天的服药计划是什么? 现在该吃哪种药?`
                              : `生成本次就诊的摘要`;
                      setQuickAskQ(example);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                  >
                    <CardContent sx={{ p: 2, pb: "16px !important" }}>
                      <Stack direction="row" alignItems="center" spacing={1.5}>
                        <Avatar
                          sx={{
                            bgcolor: ag.bgColor,
                            color: ag.color,
                            width: 40,
                            height: 40,
                          }}
                        >
                          <Icon sx={{ fontSize: 20 }} />
                        </Avatar>
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Typography
                            variant="subtitle2"
                            sx={{ fontWeight: 600 }}
                          >
                            {ag.name}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{
                              display: "block",
                              mt: 0.25,
                              fontSize: "0.7rem",
                            }}
                          >
                            {ag.desc.split("、")[0]}
                          </Typography>
                        </Box>
                      </Stack>
                    </CardContent>
                  </Card>
                </Grid>
              );
            })}
          </Grid>
        </Box>

        {/* 数据卡片 (4 cards) */}
        <Box sx={{ mb: 4 }}>
          <Stack
            direction="row"
            alignItems="center"
            spacing={1}
            sx={{ mb: 1.5 }}
          >
            <Insights sx={{ fontSize: 18, color: "primary.main" }} />
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              健康数据概览
            </Typography>
            <IconButton size="small" onClick={fetchAll}>
              <Refresh fontSize="small" />
            </IconButton>
          </Stack>
          <Grid container spacing={1.5}>
            <Grid item xs={6} md={3}>
              <Paper
                variant="outlined"
                sx={{
                  p: 2,
                  cursor: "pointer",
                  "&:hover": { borderColor: "primary.main" },
                }}
                onClick={() => navigate("/v2/health-records")}
              >
                <Stack direction="row" alignItems="center" spacing={1.5}>
                  <Avatar
                    sx={{ bgcolor: "primary.main", width: 44, height: 44 }}
                  >
                    <FavoriteBorder />
                  </Avatar>
                  <Box>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {loading ? (
                        <Skeleton width={40} />
                      ) : (
                        (stats?.records ?? 0)
                      )}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      健康档案
                    </Typography>
                  </Box>
                </Stack>
              </Paper>
            </Grid>
            <Grid item xs={6} md={3}>
              <Paper
                variant="outlined"
                sx={{
                  p: 2,
                  cursor: "pointer",
                  "&:hover": { borderColor: "primary.main" },
                }}
                onClick={() => navigate("/v2/health-records?type=examination")}
              >
                <Stack direction="row" alignItems="center" spacing={1.5}>
                  <Avatar
                    sx={{ bgcolor: "success.main", width: 44, height: 44 }}
                  >
                    <Science />
                  </Avatar>
                  <Box>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {loading ? <Skeleton width={40} /> : (stats?.exams ?? 0)}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      检查报告
                    </Typography>
                  </Box>
                </Stack>
              </Paper>
            </Grid>
            <Grid item xs={6} md={3}>
              <Paper
                variant="outlined"
                sx={{
                  p: 2,
                  cursor: "pointer",
                  "&:hover": { borderColor: "primary.main" },
                }}
                onClick={() => navigate("/v2/medication")}
              >
                <Stack direction="row" alignItems="center" spacing={1.5}>
                  <Avatar
                    sx={{ bgcolor: "warning.main", width: 44, height: 44 }}
                  >
                    <Medication />
                  </Avatar>
                  <Box>
                    <Typography variant="h4" sx={{ fontWeight: 700 }}>
                      {loading ? (
                        <Skeleton width={40} />
                      ) : (
                        `${med.taken}/${med.total}`
                      )}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      今日服药
                    </Typography>
                  </Box>
                </Stack>
              </Paper>
            </Grid>
            <Grid item xs={6} md={3}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Stack direction="row" alignItems="center" spacing={1.5}>
                  <Avatar
                    sx={{ bgcolor: "secondary.main", width: 44, height: 44 }}
                  >
                    <HealthAndSafety />
                  </Avatar>
                  <Box>
                    <Typography
                      variant="h4"
                      sx={{
                        fontWeight: 700,
                        color: Number.isFinite(stats?.score)
                          ? "primary.main"
                          : "text.disabled",
                      }}
                    >
                      {loading ? (
                        <Skeleton width={40} />
                      ) : Number.isFinite(stats?.score) ? (
                        stats.score
                      ) : (
                        "—"
                      )}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      健康评分
                    </Typography>
                  </Box>
                </Stack>
              </Paper>
            </Grid>
          </Grid>
        </Box>

        <Grid container spacing={3}>
          {/* 左侧: 健康评分 + 趋势 */}
          <Grid item xs={12} md={8}>
            <Paper sx={{ p: 3 }}>
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 2 }}
              >
                <Stack direction="row" alignItems="center" spacing={1}>
                  <Timeline sx={{ color: "primary.main" }} />
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    近 7 天健康趋势
                  </Typography>
                </Stack>
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <Chip
                    size="small"
                    label={
                      Number.isFinite(trends.score)
                        ? trends.trendLabel || "稳定"
                        : "记录中"
                    }
                    sx={{
                      bgcolor: Number.isFinite(trends.score)
                        ? trends.trendColor || "info.main"
                        : "grey.300",
                      color: "white",
                      fontWeight: 600,
                    }}
                  />
                  <Chip
                    size="small"
                    label={
                      Number.isFinite(trends.score)
                        ? `健康评分 ${trends.score} / 100`
                        : "健康评分 — / 100"
                    }
                    color={
                      Number.isFinite(trends.score) ? "primary" : "default"
                    }
                    variant="outlined"
                  />
                </Stack>
              </Stack>
              <Box
                sx={{
                  position: "relative",
                  height: 120,
                  display: "flex",
                  alignItems: "flex-end",
                  gap: 1,
                  mt: 2,
                }}
              >
                {trends.weeks.map((w, i) => {
                  const v = w.value;
                  // 阶段48-22 v4+: NaN/undefined 数据用占位符, 不显示 NaN/undefined/0%
                  const hasData = Number.isFinite(v);
                  const safeV = hasData ? v : 0;
                  const color = hasData
                    ? safeV >= 80
                      ? "success.main"
                      : safeV >= 60
                        ? "primary.main"
                        : safeV >= 40
                          ? "warning.main"
                          : "error.main"
                    : "grey.300"; // 没数据用灰色占位
                  return (
                    <Box key={i} sx={{ flex: 1, textAlign: "center" }}>
                      <Typography
                        variant="caption"
                        sx={{
                          fontWeight: 600,
                          color: hasData ? color : "text.disabled",
                        }}
                      >
                        {hasData ? Math.round(safeV) : "—"}
                      </Typography>
                      <Box
                        sx={{
                          height: hasData ? `${Math.max(safeV, 4)}%` : "8%",
                          maxHeight: 100,
                          bgcolor: color,
                          opacity: hasData ? 1 : 0.4,
                          borderRadius: 1,
                          mt: 0.5,
                          transition: "all 0.3s",
                        }}
                      />
                      <Typography
                        variant="caption"
                        sx={{
                          display: "block",
                          mt: 0.5,
                          color: "text.secondary",
                          fontSize: "0.65rem",
                        }}
                      >
                        {w.day}
                      </Typography>
                    </Box>
                  );
                })}
              </Box>
              <Divider sx={{ my: 2 }} />
              <Grid container spacing={2}>
                <Grid item xs={4}>
                  <Stack alignItems="center">
                    <CircularProgress
                      variant="determinate"
                      value={Number.isFinite(stats?.score) ? stats.score : 0}
                      size={60}
                      thickness={6}
                    />
                    <Typography
                      variant="caption"
                      sx={{
                        mt: 1,
                        color: Number.isFinite(stats?.score)
                          ? "text.secondary"
                          : "text.disabled",
                      }}
                    >
                      {Number.isFinite(stats?.score)
                        ? `${stats.score} / 100`
                        : "暂无数据"}
                    </Typography>
                  </Stack>
                </Grid>
                <Grid item xs={8}>
                  {[
                    { key: "cov", label: "档案覆盖" },
                    { key: "comp", label: "服药依从" },
                    { key: "act", label: "活跃度" },
                    { key: "stab", label: "稳定性" },
                  ].map((row) => {
                    const raw = trends[row.key];
                    const hasData = Number.isFinite(raw);
                    return (
                      <Typography
                        key={row.key}
                        variant="body2"
                        color="text.secondary"
                        sx={{ mb: 0.5 }}
                      >
                        • {row.label}:{" "}
                        <strong
                          style={{
                            color: hasData ? "inherit" : "text.disabled",
                          }}
                        >
                          {hasData ? `${raw}%` : "—"}
                        </strong>
                      </Typography>
                    );
                  })}
                  <Typography
                    variant="caption"
                    color="text.disabled"
                    sx={{ display: "block", mt: 1 }}
                  >
                    {Number.isFinite(trends.historicalN) &&
                    trends.historicalN > 0
                      ? `已积累 ${trends.historicalN} 天数据 — ${trends.historicalN < 7 ? "还需要几天历史才能给趋势" : "趋势已稳定"}`
                      : "刚开始记录 — 7 天后才有趋势; 90 天后做置信度评估"}
                  </Typography>
                </Grid>
              </Grid>
            </Paper>
          </Grid>

          {/* 右侧: 最近对话 */}
          <Grid item xs={12} md={4}>
            <Paper sx={{ p: 2.5 }}>
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 1.5 }}
              >
                <Stack direction="row" alignItems="center" spacing={1}>
                  <History sx={{ color: "primary.main", fontSize: 20 }} />
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
                    最近对话
                  </Typography>
                </Stack>
                <Button
                  size="small"
                  endIcon={<ChevronRight />}
                  onClick={() => navigate("/v2/chat")}
                >
                  全部
                </Button>
              </Stack>
              {recentConvs.length === 0 ? (
                <Box
                  sx={{ textAlign: "center", py: 3, color: "text.disabled" }}
                >
                  <SmartToy sx={{ fontSize: 32, mb: 1 }} />
                  <Typography variant="caption" display="block">
                    暂无对话
                  </Typography>
                  <Button
                    size="small"
                    sx={{ mt: 1 }}
                    onClick={() => navigate("/v2/chat")}
                  >
                    开始第一个
                  </Button>
                </Box>
              ) : (
                <Stack spacing={1}>
                  {recentConvs.map((c, i) => (
                    <Paper
                      key={i}
                      variant="outlined"
                      sx={{
                        p: 1.25,
                        cursor: "pointer",
                        transition: "all 0.15s",
                        "&:hover": {
                          borderColor: "primary.main",
                          bgcolor: "rgba(21,101,192,0.02)",
                        },
                      }}
                      onClick={() => navigate("/v2/chat")}
                    >
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: 500,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {(c.question || c.title || "对话").slice(0, 36)}
                      </Typography>
                      <Stack
                        direction="row"
                        alignItems="center"
                        spacing={0.5}
                        sx={{ mt: 0.25 }}
                      >
                        <Typography variant="caption" color="text.secondary">
                          {c.created_at || c.time || ""}
                        </Typography>
                      </Stack>
                    </Paper>
                  ))}
                </Stack>
              )}
            </Paper>
          </Grid>
        </Grid>

        {/* 阶段48-7: 简洁健康评分条 */}
        <Paper sx={{ p: 2.5, mt: 3 }}>
          <Stack direction="row" alignItems="center" spacing={2}>
            <Box sx={{ textAlign: "center", minWidth: 90 }}>
              <Typography variant="caption" color="text.secondary">
                健康评分
              </Typography>
              {Number.isFinite(stats?.score) ? (
                <Typography
                  variant="h3"
                  sx={{
                    fontWeight: 700,
                    color: stats.score >= 70 ? "success.main" : "primary.main",
                    lineHeight: 1,
                  }}
                >
                  {stats.score}
                </Typography>
              ) : (
                <Typography
                  variant="h3"
                  sx={{
                    fontWeight: 700,
                    color: "text.disabled",
                    lineHeight: 1,
                  }}
                >
                  —
                </Typography>
              )}
              <Typography variant="caption" color="text.disabled">
                / 100
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem sx={{ mx: 2 }} />
            <Box sx={{ flex: 1 }}>
              <LinearProgress
                variant="determinate"
                value={Number.isFinite(stats?.score) ? stats.score : 0}
                sx={{ height: 8, borderRadius: 4, mb: 0.5 }}
              />
              <Typography
                variant="caption"
                color="text.disabled"
                sx={{ display: "block", mt: 0.5 }}
              >
                {Number.isFinite(stats?.score)
                  ? `${stats.score} 分 (${stats.score >= 70 ? "良好" : stats.score >= 40 ? "中等" : "待关注"})`
                  : "数据收集中 — 上传档案或服药后立即显示"}
              </Typography>
              <Stack
                direction="row"
                spacing={2}
                sx={{ mt: 1, flexWrap: "wrap", gap: 0.5 }}
              >
                <Typography variant="caption" color="text.secondary">
                  档案 <strong>{records.total}</strong>
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  · 今日服药{" "}
                  <strong>
                    {med.taken}/{med.total}
                  </strong>
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  · 对话 <strong>{recentConvs.length}</strong>
                </Typography>
              </Stack>
            </Box>
          </Stack>
        </Paper>
      </Container>

      {/* 阶段48-10: Drawer 已移除 — 嵌入式对话在 Dashboard 主面板内 */}
      <AgentQuickFab />
    </Box>
  );
}
