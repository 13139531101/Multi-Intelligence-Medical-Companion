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
    desc: "检查报告上传、OCR 识别、档案管理",
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
  // 快速问答 drawer
  const [askOpen, setAskOpen] = useState(false);
  const [askQ, setAskQ] = useState("");
  const [quickAskQ, setQuickAskQ] = useState(""); // 阶段48-7: 顶部快捷输入
  const [askTarget, setAskTarget] = useState("health_advisor");
  const [askReply, setAskReply] = useState("");
  const [askLoading, setAskLoading] = useState(false);

  const computeScore = (recCount, medTaken, medTotal) => {
    // 阶段48-8: deprecated, 用 utils/healthMetrics.js 的真实算法替代
    const r = Math.min(recCount * 5, 30);
    const m = medTotal > 0 ? (medTaken / medTotal) * 70 : 0;
    return Math.round(r + m);
  };

  const fetchAll = async () => {
    setLoading(true);
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
    setStats({
      score: trendResult.today.score,
      records: recList.length,
      exams: recList.filter((r) => r.record_type === "examination").length,
      allergies: recList.filter((r) => r.record_type === "allergy").length,
      reports: recList.filter((r) => r.record_type === "report").length,
    });

    // 阶段48-8: 用真实算法替换 mock
    const trendResult = buildHealthTrend({
      records: recList,
      reminders: medList,
      consultations: Array.isArray(convs) ? convs : [],
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
  };

  useEffect(() => {
    fetchAll();
  }, []);

  const handleAskAgent = async (agentId, q) => {
    setAskTarget(agentId || askTarget);
    setAskQ(q || askQ);
    setAskOpen(true);
    setAskReply("");
    if (!q || !q.trim()) return;
    setAskLoading(true);
    try {
      const token = localStorage.getItem("token") || "";
      const apiBase =
        import.meta?.env?.VITE_API_BASE || "http://localhost:13002";
      const resp = await fetch(apiBase + "/v2/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({
          message: q,
          metadata: {
            selected_agent: agentId || askTarget,
            from_dashboard: true,
          },
        }),
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
                  setAskReply(text);
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
                  setActiveAgent(p.agent);
                  setAskTarget(p.agent);
                }
              } catch {
                /* ignore */
              }
            }
          }
        }
      }
    } catch (e) {
      setAskReply("调用失败: " + e.message);
    }
    setAskLoading(false);
  };

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Header />

      <Container maxWidth="lg" sx={{ py: 3 }}>
        {/* 阶段48-7: 简洁问候 + 直接输入 (无按钮自动答) */}
        <Paper
          sx={{
            p: 3,
            mb: 3,
            bgcolor: "primary.main",
            color: "white",
            boxShadow: 1,
          }}
        >
          <Typography variant="h5" sx={{ fontWeight: 600 }}>
            你好, {user?.username || "用户"}
          </Typography>
          <Typography variant="body2" sx={{ opacity: 0.9, mt: 0.5, mb: 2 }}>
            有任何健康问题, 直接在下面输入, 我会找最合适的 AI 帮你
          </Typography>
          <TextField
            fullWidth
            placeholder="例如: 我最近血压偏高, 需要注意什么?"
            value={quickAskQ}
            onChange={(e) => setQuickAskQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && quickAskQ.trim()) {
                navigate("/v2/chat?q=" + encodeURIComponent(quickAskQ));
              }
            }}
            sx={{
              bgcolor: "rgba(255,255,255,0.95)",
              borderRadius: 1,
              "& .MuiInputBase-input": { color: "text.primary", py: 1.25 },
            }}
            InputProps={{
              endAdornment: (
                <Button
                  variant="contained"
                  color="primary"
                  size="small"
                  onClick={() =>
                    quickAskQ.trim() &&
                    navigate("/v2/chat?q=" + encodeURIComponent(quickAskQ))
                  }
                  disabled={!quickAskQ.trim()}
                >
                  提问
                </Button>
              ),
            }}
          />
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
                      borderColor: "divider",
                      "&:hover": { borderColor: ag.color, boxShadow: 1 },
                    }}
                    onClick={() => navigate(ag.path)}
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
                      sx={{ fontWeight: 700, color: "primary.main" }}
                    >
                      {loading ? <Skeleton width={40} /> : (stats?.score ?? 0)}
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
                    label={trends.trendLabel || "稳定"}
                    sx={{
                      bgcolor: trends.trendColor || "info.main",
                      color: "white",
                      fontWeight: 600,
                    }}
                  />
                  <Chip
                    size="small"
                    label={`健康评分 ${trends.score || 0} / 100`}
                    color="primary"
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
                  const color =
                    v >= 80
                      ? "success.main"
                      : v >= 60
                        ? "primary.main"
                        : v >= 40
                          ? "warning.main"
                          : "error.main";
                  return (
                    <Box key={i} sx={{ flex: 1, textAlign: "center" }}>
                      <Typography
                        variant="caption"
                        sx={{ fontWeight: 600, color: color }}
                      >
                        {Math.round(v)}
                      </Typography>
                      <Box
                        sx={{
                          height: `${Math.max(v, 4)}%`,
                          maxHeight: 100,
                          bgcolor: color,
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
                      value={stats?.score || 0}
                      size={60}
                      thickness={6}
                    />
                    <Typography
                      variant="caption"
                      sx={{ mt: 1, color: "text.secondary" }}
                    >
                      综合分
                    </Typography>
                  </Stack>
                </Grid>
                <Grid item xs={8}>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 0.5 }}
                  >
                    • 档案覆盖: <strong>{trends.cov || 0}%</strong>
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 0.5 }}
                  >
                    • 服药依从: <strong>{trends.comp || 0}%</strong>
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 0.5 }}
                  >
                    • 活跃度: <strong>{trends.act || 0}%</strong>
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 0.5 }}
                  >
                    • 稳定性: <strong>{trends.stab || 0}%</strong>
                    {trends.comparison?.significant && (
                      <Chip
                        size="small"
                        label={`t=${trends.comparison.t}`}
                        sx={{ ml: 0.5, height: 16, fontSize: "0.6rem" }}
                      />
                    )}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.disabled"
                    sx={{ display: "block", mt: 1 }}
                  >
                    斜率 {trends.slope} · r={trends.r} · 历史{" "}
                    {trends.historicalN || 0} 天
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
              <Typography
                variant="h3"
                sx={{
                  fontWeight: 700,
                  color:
                    (stats?.score || 0) >= 70 ? "success.main" : "primary.main",
                  lineHeight: 1,
                }}
              >
                {stats?.score || 0}
              </Typography>
              <Typography variant="caption" color="text.disabled">
                / 100
              </Typography>
            </Box>
            <Divider orientation="vertical" flexItem sx={{ mx: 2 }} />
            <Box sx={{ flex: 1 }}>
              <LinearProgress
                variant="determinate"
                value={stats?.score || 0}
                sx={{ height: 8, borderRadius: 4 }}
              />
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

      {/* 阶段48-6: 快速提问 drawer */}
      <Drawer
        anchor="right"
        open={askOpen}
        onClose={() => setAskOpen(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 520 } } }}
      >
        <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            sx={{ p: 2, borderBottom: "1px solid", borderColor: "divider" }}
          >
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <Avatar sx={{ bgcolor: "primary.main" }}>
                <SmartToy />
              </Avatar>
              <Box>
                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                  智能体问答
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  将由 <strong>{askTarget}</strong> 接答
                </Typography>
              </Box>
            </Stack>
            <IconButton onClick={() => setAskOpen(false)}>
              <Close />
            </IconButton>
          </Stack>
          <Box sx={{ p: 2, borderBottom: "1px solid", borderColor: "divider" }}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mb: 1 }}
            >
              选择目标 agent:
            </Typography>
            <Stack
              direction="row"
              spacing={0.5}
              sx={{ flexWrap: "wrap", gap: 0.5 }}
            >
              {AGENTS.map((ag) => (
                <Chip
                  key={ag.id}
                  label={ag.name}
                  size="small"
                  onClick={() => setAskTarget(ag.en)}
                  sx={{
                    bgcolor: askTarget === ag.en ? ag.color : ag.bgColor,
                    color: askTarget === ag.en ? "white" : ag.color,
                    fontWeight: askTarget === ag.en ? 600 : 400,
                  }}
                />
              ))}
            </Stack>
          </Box>
          <Box sx={{ flex: 1, overflowY: "auto", p: 2, bgcolor: "grey.50" }}>
            {askReply ? (
              <Paper
                sx={{
                  p: 2,
                  bgcolor: "white",
                  borderLeft: "3px solid",
                  borderColor: "primary.main",
                }}
              >
                <Typography variant="caption" color="text.secondary">
                  {activeAgent || askTarget} 回复:
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ mt: 0.5, whiteSpace: "pre-wrap" }}
                >
                  {askReply}
                </Typography>
              </Paper>
            ) : (
              <Box sx={{ textAlign: "center", color: "text.disabled", py: 4 }}>
                <SmartToy sx={{ fontSize: 48, mb: 1 }} />
                <Typography variant="caption" display="block">
                  在下方输入你的问题
                </Typography>
                <Typography
                  variant="caption"
                  sx={{ fontSize: "0.7rem", display: "block", mt: 0.5 }}
                >
                  AI 会基于你的档案 + 当前数据回答
                </Typography>
              </Box>
            )}
            {askLoading && <LinearProgress sx={{ mt: 1 }} />}
          </Box>
          <Box
            sx={{
              p: 2,
              borderTop: "1px solid",
              borderColor: "divider",
              bgcolor: "white",
            }}
          >
            <Stack direction="row" spacing={1} alignItems="flex-end">
              <TextField
                fullWidth
                multiline
                maxRows={3}
                placeholder="例如: 我今天血压 145/95, 需要注意什么?"
                value={askQ}
                onChange={(e) => setAskQ(e.target.value)}
                size="small"
              />
              <Button
                variant="contained"
                onClick={() => handleAskAgent(askTarget, askQ)}
                disabled={askLoading || !askQ.trim()}
                startIcon={<Send />}
              >
                问
              </Button>
            </Stack>
            <Stack
              direction="row"
              spacing={0.5}
              sx={{ mt: 1, flexWrap: "wrap", gap: 0.5 }}
            >
              {["血压高了怎么办", "我最近头疼是怎么回事", "如何改善睡眠"].map(
                (s, i) => (
                  <Chip
                    key={i}
                    label={s}
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      setAskQ(s);
                    }}
                    sx={{ fontSize: "0.7rem", height: 22 }}
                  />
                ),
              )}
            </Stack>
          </Box>
        </Box>
      </Drawer>
      <AgentQuickFab />
    </Box>
  );
}
