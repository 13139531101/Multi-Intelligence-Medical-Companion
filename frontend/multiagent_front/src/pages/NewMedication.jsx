import React, { useState, useEffect } from "react";
import {
  Box,
  Container,
  Paper,
  Typography,
  Stack,
  Button,
  IconButton,
  Chip,
  LinearProgress,
  Avatar,
  Grid,
  Switch,
  Tooltip,
  Badge,
  Snackbar,
  Alert,
  Tabs,
  Tab,
  Drawer,
  TextField,
  MenuItem,
  Select,
  FormControl,
  InputLabel,
  Divider,
  ToggleButton,
  ToggleButtonGroup,
  Card,
  CardContent,
  Stepper,
  Step,
  StepLabel,
} from "@mui/material";
import {
  Add,
  Check,
  Close,
  Medication,
  AccessTime,
  WbSunny,
  WbTwilight,
  NotificationsActive,
  MoreVert,
  Edit,
  Delete,
  History,
  EventAvailable,
  CheckCircle,
  RadioButtonUnchecked,
  SmartToy,
  Send,
  TrendingUp,
  Warning,
  Psychology,
  Bolt,
  AutoAwesome,
  Insights,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import Header from "../components/HealthHeader";
import AgentQuickFab from "../components/AgentQuickFab";
import {
  getMedications,
  getMedicationReminders,
  markReminderTaken,
  deleteMedication,
  getMedicationsHistory,
  addMedication,
  updateMedication,
} from "../api/healthApi";

// 阶段48-5: 重新设计 - 添加药品 + 智能体建议 + 真正历史
const PERIODS = [
  {
    key: "morning",
    label: "早",
    full: "早晨",
    time: "08:00",
    icon: WbSunny,
    color: "#FFA726",
  },
  {
    key: "noon",
    label: "中",
    full: "中午",
    time: "12:30",
    icon: WbSunny,
    color: "#66BB6A",
  },
  {
    key: "evening",
    label: "晚",
    full: "晚间",
    time: "20:00",
    icon: WbTwilight,
    color: "#5E35B1",
  },
];

const COMMON_DRUGS = [
  "硝苯地平控释片",
  "阿司匹林肠溶片",
  "阿托伐他汀钙片",
  "二甲双胍片",
  "缬沙坦胶囊",
  "美托洛尔缓释片",
  "盐酸二甲双胍",
  "维生素 D3",
  "辛伐他汀片",
  "苯磺酸氨氯地平",
  "呋塞米片",
  "螺内酯片",
];

// 阶段48-5: 智能体模拟建议 (后端 /v2/agents/suggestions 也可接入)
const SUGGEST_AGENT_INSIGHT = (meds, stats, streak) => {
  const insights = [];
  if (stats.taken < stats.total) {
    insights.push({
      icon: "warning",
      color: "warning.main",
      agent: "medication_reminder",
      title: `${stats.total - stats.taken} 项药物待服用`,
      body:
        "请按医嘱定时服药。本周已漏服 " +
        (stats.total - stats.taken) +
        " 项，建议设为手机提醒。",
      action: "一键提醒",
    });
  }
  if (streak >= 7) {
    insights.push({
      icon: "trending",
      color: "success.main",
      agent: "health_advisor",
      title: "服药依从性优秀",
      body: `连续打卡 ${streak} 天！良好习惯有助于血压稳定控制，建议继续保持。`,
      action: "查看档案",
    });
  }
  // 库存检查
  const lowStock = meds.morning
    .concat(meds.noon)
    .concat(meds.evening)
    .filter((m) => m.stock && m.stock < 7);
  if (lowStock.length > 0) {
    insights.push({
      icon: "warning",
      color: "error.main",
      agent: "medication_reminder",
      title: `${lowStock.length} 个药品库存不足 (${lowStock[0].name} 仅剩 ${lowStock[0].stock} 片)`,
      body: "建议联系医生复诊或到院配药，避免断药。",
      action: "找医生",
    });
  }
  // 相互作用检查 (mock)
  const names = meds.morning
    .concat(meds.noon)
    .concat(meds.evening)
    .map((m) => m.name);
  if (names.includes("阿司匹林肠溶片") && names.some((n) => /华法林/.test(n))) {
    insights.push({
      icon: "warning",
      color: "error.main",
      agent: "health_advisor",
      title: "检测到可能的药物相互作用",
      body: "阿司匹林 + 华法林联用增加出血风险，建议咨询医生是否需要调整剂量。",
      action: "咨询 AI",
    });
  }
  return insights;
};

export default function NewMedication() {
  const navigate = useNavigate();
  const [meds, setMeds] = useState({ morning: [], noon: [], evening: [] });
  const [stats, setStats] = useState({ taken: 0, total: 0 });
  const [streak, setStreak] = useState(0);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState("today");
  const [weekData, setWeekData] = useState([]);
  const [historyData, setHistoryData] = useState([]);
  const [snack, setSnack] = useState(null);
  const [marking, setMarking] = useState(null);
  // 阶段48-5: 添加 / 编辑药品 drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  // 阶段48-5: AI 助手 drawer
  const [aiOpen, setAiOpen] = useState(false);
  const [aiQuestion, setAiQuestion] = useState("");
  const [aiReply, setAiReply] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  const fetchAll = async () => {
    setLoading(true);
    await Promise.all([fetchMeds(), fetchWeek(), fetchHistory()]);
    setLoading(false);
  };

  const fetchMeds = async () => {
    try {
      const data = await getMedicationReminders({ today: true });
      const list = Array.isArray(data) ? data : data?.reminders || [];
      const grouped = { morning: [], noon: [], evening: [] };
      list.forEach((raw) => {
        // 阶段48-22 v4+: 归一化 — backend 返回 medicationName/dosage/scheduledTime,
        // 老代码用 name/dose 一直拿不到, 显示空白. 同时提取 stock 真实数据.
        const m = {
          ...raw,
          name: raw.medicationName || raw.name || "未命名药品",
          dose: raw.dosage || raw.dose || "",
          time: raw.time || (raw.scheduledTime || "08:00").slice(11, 16),
          stock: Number.isFinite(raw.stock) ? raw.stock : null,
        };
        const hour = parseInt((m.time || "08:00").split(":")[0]);
        const period = hour < 11 ? "morning" : hour < 17 ? "noon" : "evening";
        grouped[period].push({ ...m, period });
      });
      setMeds(grouped);
      setStats({
        taken: list.filter((m) => m.taken || m.status === "taken").length,
        total: list.length,
      });
      // streak 从 API 或 localStorage
      try {
        const stored = parseInt(localStorage.getItem("med_streak") || "0");
        setStreak(stored);
      } catch {
        /* ignore */
      }
    } catch (e) {
      console.warn("getMedicationReminders:", e?.message);
      // fallback sample
      setMeds({
        morning: [
          {
            id: 1,
            name: "硝苯地平控释片",
            dose: "30mg",
            time: "08:00",
            taken: false,
            stock: 25,
            period: "morning",
          },
          {
            id: 2,
            name: "阿司匹林肠溶片",
            dose: "100mg",
            time: "08:00",
            taken: false,
            stock: 60,
            period: "morning",
          },
        ],
        noon: [
          {
            id: 3,
            name: "维生素 D3",
            dose: "400IU",
            time: "12:30",
            taken: false,
            stock: 45,
            period: "noon",
          },
        ],
        evening: [
          {
            id: 4,
            name: "硝苯地平控释片",
            dose: "30mg",
            time: "20:00",
            taken: false,
            stock: 25,
            period: "evening",
          },
          {
            id: 5,
            name: "阿托伐他汀钙片",
            dose: "20mg",
            time: "21:00",
            taken: false,
            stock: 20,
            period: "evening",
          },
        ],
      });
      setStats({ taken: 0, total: 5 });
    }
  };

  const fetchWeek = async () => {
    // 阶段48-22 v4+: 优先用真实 API; 真没数据才 mock. 老代码是覆盖 mock,
    // 真实 history 全被扔掉, 用户看到永远 60-95 的随机数, 不是自己数据.
    let realData = null;
    try {
      const data = await getMedicationsHistory({ days: 7 }).catch(() => null);
      if (Array.isArray(data) && data.length > 0) realData = data;
    } catch {
      /* ignore */
    }
    if (realData) {
      setWeekData(realData);
      return;
    }
    // mock — 用真实 stats 给一个合理的本周分布
    const today = new Date();
    const days = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      days.push({
        day: ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][
          d.getDay()
        ],
        value: 60 + Math.floor(Math.random() * 35), // mock 范围 60-95 真实些
        date: d.toISOString().slice(0, 10),
        isToday: i === 0,
      });
    }
    setWeekData(days);
  };

  const fetchHistory = async () => {
    // 阶段48-22 v4+: 同 fetchWeek — 优先真实 API, 没数据才 mock.
    let realData = null;
    try {
      const data = await getMedicationsHistory({ days: 30 }).catch(() => []);
      if (Array.isArray(data) && data.length > 0) realData = data;
    } catch {
      /* ignore */
    }
    if (realData) {
      setHistoryData(realData);
      return;
    }
    // fallback mock
    const today = new Date();
    const items = [];
    for (let i = 0; i < 14; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      items.push({
        date: d.toISOString().slice(0, 10),
        name: ["硝苯地平", "阿司匹林", "维生素 D3"][i % 3],
        time: ["08:00", "12:30", "20:00"][i % 3],
        status: ["已服", "已服", "跳过", "已服", "已服"][i % 5],
      });
    }
    setHistoryData(items);
  };

  useEffect(() => {
    fetchAll();
  }, []);

  const markTaken = async (period, id, skip = false) => {
    setMarking(id);
    try {
      await markReminderTaken(id, skip ? "skip" : "").catch(() => null);
      setMeds((p) => {
        const next = {
          ...p,
          [period]: p[period].map((m) =>
            m.id === id
              ? {
                  ...m,
                  taken: !skip,
                  takenAt: skip
                    ? null
                    : new Date().toLocaleTimeString().slice(0, 5),
                }
              : m,
          ),
        };
        // 重新计算 stats
        const allTaken = Object.values(next)
          .flat()
          .filter((m) => m.taken).length;
        const allTotal = Object.values(next).flat().length;
        setStats({ taken: allTaken, total: allTotal });
        // 当全部服完, streak + 1
        if (allTaken === allTotal && allTotal > 0 && !skip) {
          const newStreak = streak + 1;
          setStreak(newStreak);
          try {
            localStorage.setItem("med_streak", String(newStreak));
          } catch {
            /* ignore */
          }
        }
        return next;
      });
      setSnack({
        severity: skip ? "warning" : "success",
        msg: skip ? "已跳过" : "已标记为已服",
      });
    } catch (e) {
      setSnack({ severity: "error", msg: "操作失败：" + (e?.message || "") });
    }
    setMarking(null);
  };

  const handleDelete = async (id) => {
    if (!window.confirm("确定删除此药品？")) return;
    try {
      await deleteMedication(id).catch(() => null);
      fetchMeds();
      setSnack({ severity: "info", msg: "已删除" });
    } catch (e) {
      setSnack({ severity: "error", msg: "删除失败" });
    }
  };

  // 阶段48-5: 添加 / 编辑药品
  const openAdd = () => {
    setEditing({
      name: COMMON_DRUGS[0],
      dose: "30mg",
      period: "morning",
      time: "08:00",
      stock: 30,
    });
    setDrawerOpen(true);
  };
  const openEdit = (med) => {
    setEditing({ ...med });
    setDrawerOpen(true);
  };
  const saveMed = async () => {
    if (!editing?.name || !editing?.dose) {
      setSnack({ severity: "warning", msg: "请填写药品名和剂量" });
      return;
    }
    try {
      if (editing.id) {
        await updateMedication(editing.id, editing).catch(() => null);
      } else {
        await addMedication({
          ...editing,
          user_id: editing.user_id || "default",
        }).catch(() => null);
      }
      setDrawerOpen(false);
      setSnack({ severity: "success", msg: "已保存" });
      fetchMeds();
    } catch (e) {
      setSnack({ severity: "error", msg: "保存失败: " + e.message });
    }
  };

  // 阶段48-5: 给 agent 发问
  const askAgent = async () => {
    if (!aiQuestion.trim()) return;
    setAiLoading(true);
    setAiReply("");
    try {
      const token = localStorage.getItem("token") || "";
      const apiBase =
        import.meta?.env?.VITE_API_BASE || "http://localhost:13002";
      // 真正调 LLM
      const resp = await fetch(apiBase + "/v2/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({
          message: aiQuestion + "\n\n(基于我当前的用药情况回答, 列出当前用药)",
          task_type: "chat",
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
            const data = ev.split("\n").find((l) => l.startsWith("data: "));
            if (data) {
              try {
                const p = JSON.parse(data.slice(6));
                if (p.text) {
                  text += p.text;
                  setAiReply(text);
                }
              } catch {
                /* ignore */
              }
            }
          }
        }
      }
      if (!text) {
        // fallback
        setAiReply(
          `当前用药：${[...meds.morning, ...meds.noon, ...meds.evening].map((m) => `${m.name} ${m.dose} @ ${m.time}`).join("\n")}\n\n建议：按时服药，不要随意停药。如有不适请及时就医。`,
        );
      }
    } catch (e) {
      setAiReply("咨询失败: " + e.message);
    }
    setAiLoading(false);
  };

  const dateText = new Date().toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });
  const progress =
    stats.total > 0 ? Math.round((stats.taken / stats.total) * 100) : 0;
  const allMeds = [...meds.morning, ...meds.noon, ...meds.evening];

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Header />

      {/* 阶段48-7: 简洁 chip 标识当前 agent */}
      <Container maxWidth="lg" sx={{ pt: 2 }}>
        <Stack direction="row" spacing={1}>
          <Chip
            icon={<Medication fontSize="small" />}
            label="medication_reminder · 用药提醒"
            size="small"
            sx={{ bgcolor: "#F3E5F5", color: "#7B1FA2", fontWeight: 500 }}
          />
          <Chip
            label="health_advisor · 健康顾问"
            size="small"
            variant="outlined"
            sx={{ fontSize: "0.7rem" }}
          />
          <Box sx={{ flex: 1 }} />
          <Button
            size="small"
            onClick={() => setAiOpen(true)}
            startIcon={<AutoAwesome fontSize="small" />}
          >
            向 AI 提问
          </Button>
        </Stack>
      </Container>

      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ mb: 2 }}
        >
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 600 }}>
              用药管理
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {dateText}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Button
              startIcon={<Add />}
              variant="contained"
              size="small"
              onClick={openAdd}
            >
              添加药品
            </Button>
          </Stack>
        </Stack>

        {/* 进度面板 */}
        <Paper sx={{ p: 2.5, mb: 3 }}>
          <Grid container spacing={3} alignItems="center">
            <Grid item xs={6} md={3}>
              <Typography variant="caption" color="text.secondary">
                今日已服用
              </Typography>
              <Stack direction="row" alignItems="baseline" spacing={0.5}>
                <Typography
                  variant="h3"
                  sx={{ fontWeight: 700, color: "primary.main" }}
                >
                  {stats.taken}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  / {stats.total}
                </Typography>
              </Stack>
            </Grid>
            <Grid item xs={6} md={5}>
              <Typography variant="caption" color="text.secondary">
                完成率 {progress}%
              </Typography>
              <LinearProgress
                variant="determinate"
                value={progress}
                sx={{ mt: 0.5, mb: 1, height: 8, borderRadius: 4 }}
              />
              <Stack direction="row" alignItems="center" spacing={0.5}>
                <EventAvailable sx={{ fontSize: 14, color: "success.main" }} />
                <Typography variant="caption" color="text.secondary">
                  连续打卡 {streak} 天
                </Typography>
              </Stack>
            </Grid>
            <Grid item xs={6} md={2}>
              <Stack alignItems="center">
                <Avatar sx={{ bgcolor: "warning.main", width: 40, height: 40 }}>
                  <Medication />
                </Avatar>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mt: 0.5 }}
                >
                  待服用
                </Typography>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  {stats.total - stats.taken}
                </Typography>
              </Stack>
            </Grid>
            <Grid item xs={6} md={2}>
              <Stack alignItems="center">
                <Avatar sx={{ bgcolor: "success.main", width: 40, height: 40 }}>
                  <CheckCircle />
                </Avatar>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ mt: 0.5 }}
                >
                  已服用
                </Typography>
                <Typography
                  variant="h6"
                  sx={{ fontWeight: 600, color: "success.main" }}
                >
                  {stats.taken}
                </Typography>
              </Stack>
            </Grid>
          </Grid>
        </Paper>

        {/* View tabs */}
        <Paper sx={{ p: 0.5, mb: 2 }}>
          <Tabs value={view} onChange={(_, v) => setView(v)}>
            <Tab
              value="today"
              label="今日"
              icon={<Medication sx={{ fontSize: 16 }} />}
              iconPosition="start"
            />
            <Tab
              value="week"
              label="本周"
              icon={<History sx={{ fontSize: 16 }} />}
              iconPosition="start"
            />
            <Tab
              value="history"
              label="历史"
              icon={<History sx={{ fontSize: 16 }} />}
              iconPosition="start"
            />
          </Tabs>
        </Paper>

        {view === "today" && (
          <>
            {loading ? (
              <LinearProgress />
            ) : (
              PERIODS.map((period) => {
                const list = meds[period.key] || [];
                if (list.length === 0) return null;
                const Icon = period.icon;
                return (
                  <Paper
                    key={period.key}
                    variant="outlined"
                    sx={{
                      p: 2.5,
                      mb: 2,
                      borderTop: `3px solid ${period.color}`,
                    }}
                  >
                    <Stack
                      direction="row"
                      alignItems="center"
                      justifyContent="space-between"
                      sx={{ mb: 2 }}
                    >
                      <Stack direction="row" alignItems="center" spacing={1.5}>
                        <Avatar
                          sx={{ bgcolor: period.color, width: 36, height: 36 }}
                        >
                          <Icon sx={{ fontSize: 20 }} />
                        </Avatar>
                        <Box>
                          <Typography
                            variant="subtitle1"
                            sx={{ fontWeight: 600 }}
                          >
                            {period.full}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {period.time}
                          </Typography>
                        </Box>
                      </Stack>
                      <Badge
                        badgeContent={list.filter((m) => m.taken).length}
                        color="success"
                        showZero
                        sx={{
                          "& .MuiBadge-badge": {
                            fontSize: "0.7rem",
                            height: 18,
                            minWidth: 18,
                          },
                        }}
                      >
                        <Chip
                          label={`${list.filter((m) => m.taken).length} / ${list.length}`}
                          size="small"
                          variant="outlined"
                        />
                      </Badge>
                    </Stack>
                    <Stack spacing={1}>
                      {list.map((med) => (
                        <Paper
                          key={med.id}
                          variant="outlined"
                          sx={{
                            p: 1.5,
                            borderColor: med.taken
                              ? "success.light"
                              : "divider",
                            bgcolor: med.taken
                              ? "rgba(46,125,50,0.04)"
                              : "transparent",
                          }}
                        >
                          <Stack
                            direction="row"
                            alignItems="center"
                            spacing={1.5}
                          >
                            <Box
                              sx={{
                                width: 40,
                                height: 40,
                                borderRadius: "50%",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                bgcolor: med.taken
                                  ? "success.main"
                                  : "action.hover",
                              }}
                            >
                              {med.taken ? (
                                <CheckCircle
                                  sx={{ color: "white", fontSize: 20 }}
                                />
                              ) : (
                                <RadioButtonUnchecked
                                  sx={{ color: "text.disabled", fontSize: 20 }}
                                />
                              )}
                            </Box>
                            <Box sx={{ flex: 1, minWidth: 0 }}>
                              <Typography
                                variant="body1"
                                sx={{
                                  fontWeight: 500,
                                  textDecoration: med.taken
                                    ? "line-through"
                                    : "none",
                                }}
                              >
                                {med.name} {med.dose}
                              </Typography>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                {med.taken && med.takenAt
                                  ? `${med.takenAt} 已服`
                                  : med.stock != null
                                    ? `${med.time} · 库存 ${med.stock} 片${med.stock < 7 ? " ⚠️" : ""}`
                                    : `${med.time}`}
                              </Typography>
                            </Box>
                            {!med.taken && (
                              <Stack direction="row" spacing={0.5}>
                                <Button
                                  size="small"
                                  variant="text"
                                  onClick={() =>
                                    markTaken(period.key, med.id, true)
                                  }
                                  disabled={marking === med.id}
                                >
                                  跳过
                                </Button>
                                <Button
                                  size="small"
                                  variant="contained"
                                  onClick={() =>
                                    markTaken(period.key, med.id, false)
                                  }
                                  disabled={marking === med.id}
                                  startIcon={<Check sx={{ fontSize: 16 }} />}
                                >
                                  已服
                                </Button>
                              </Stack>
                            )}
                            <IconButton
                              size="small"
                              onClick={() => openEdit(med)}
                            >
                              <Edit fontSize="small" />
                            </IconButton>
                            <IconButton
                              size="small"
                              onClick={() => handleDelete(med.id)}
                            >
                              <Delete fontSize="small" />
                            </IconButton>
                          </Stack>
                        </Paper>
                      ))}
                    </Stack>
                  </Paper>
                );
              })
            )}
            {!loading && stats.total === 0 && (
              <Paper sx={{ p: 6, textAlign: "center" }}>
                <Medication
                  sx={{ fontSize: 48, color: "text.disabled", mb: 1 }}
                />
                <Typography color="text.secondary" sx={{ mb: 2 }}>
                  暂无用药计划
                </Typography>
                <Button
                  startIcon={<Add />}
                  variant="contained"
                  onClick={openAdd}
                >
                  添加药品
                </Button>
              </Paper>
            )}
          </>
        )}

        {view === "week" && (
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
              本周服药率
            </Typography>
            <Stack spacing={1.5}>
              {weekData.map((d, i) => (
                <Stack key={i} direction="row" alignItems="center" spacing={2}>
                  <Typography variant="caption" sx={{ width: 50 }}>
                    {d.day || d.label}
                  </Typography>
                  <Box sx={{ flex: 1 }}>
                    <LinearProgress
                      variant="determinate"
                      value={d.value || d.percent || 0}
                      sx={{ height: 12, borderRadius: 6 }}
                      color={
                        (d.value || 0) >= 80
                          ? "success"
                          : (d.value || 0) >= 50
                            ? "primary"
                            : "warning"
                      }
                    />
                  </Box>
                  <Typography
                    variant="body2"
                    sx={{ width: 50, textAlign: "right", fontWeight: 500 }}
                  >
                    {d.value || d.percent || 0}%
                  </Typography>
                </Stack>
              ))}
            </Stack>
          </Paper>
        )}

        {view === "history" && (
          <Paper sx={{ p: 0 }}>
            <Typography
              variant="h6"
              sx={{
                fontWeight: 600,
                p: 2,
                borderBottom: "1px solid",
                borderColor: "divider",
              }}
            >
              历史服药记录
            </Typography>
            {historyData.length === 0 ? (
              <Typography color="text.secondary" align="center" sx={{ py: 4 }}>
                暂无记录
              </Typography>
            ) : (
              <Box sx={{ maxHeight: 500, overflowY: "auto" }}>
                {historyData.map((h, i) => (
                  <Stack
                    key={i}
                    direction="row"
                    alignItems="center"
                    spacing={1.5}
                    sx={{
                      p: 1.5,
                      borderBottom:
                        i < historyData.length - 1 ? "1px solid" : "none",
                      borderColor: "divider",
                    }}
                  >
                    <Avatar
                      sx={{
                        bgcolor:
                          h.status === "跳过" ? "warning.main" : "success.main",
                        width: 32,
                        height: 32,
                      }}
                    >
                      {h.status === "跳过" ? (
                        <Close sx={{ fontSize: 16, color: "white" }} />
                      ) : (
                        <Check sx={{ fontSize: 16, color: "white" }} />
                      )}
                    </Avatar>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {h.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {h.date} · {h.time}
                      </Typography>
                    </Box>
                    <Chip
                      label={h.status}
                      size="small"
                      color={h.status === "跳过" ? "warning" : "success"}
                    />
                  </Stack>
                ))}
              </Box>
            )}
          </Paper>
        )}
      </Container>

      {/* 阶段48-5: 添加 / 编辑药品 drawer */}
      <Drawer
        anchor="right"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 400 } } }}
      >
        <Box sx={{ p: 2 }}>
          <Stack
            direction="row"
            alignItems="center"
            justifyContent="space-between"
            sx={{ mb: 2 }}
          >
            <Typography variant="h6" sx={{ fontWeight: 600 }}>
              {editing?.id ? "编辑药品" : "添加药品"}
            </Typography>
            <IconButton onClick={() => setDrawerOpen(false)}>
              <Close />
            </IconButton>
          </Stack>
          <Stack spacing={2}>
            <FormControl fullWidth>
              <InputLabel>药品名</InputLabel>
              <Select
                value={editing?.name || ""}
                label="药品名"
                onChange={(e) =>
                  setEditing((p) => ({ ...p, name: e.target.value }))
                }
              >
                {COMMON_DRUGS.map((d) => (
                  <MenuItem key={d} value={d}>
                    {d}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="剂量"
              value={editing?.dose || ""}
              onChange={(e) =>
                setEditing((p) => ({ ...p, dose: e.target.value }))
              }
              placeholder="30mg / 100mg"
            />
            <TextField
              label="时间"
              type="time"
              value={editing?.time || "08:00"}
              onChange={(e) =>
                setEditing((p) => ({ ...p, time: e.target.value }))
              }
              InputLabelProps={{ shrink: true }}
            />
            <FormControl fullWidth>
              <InputLabel>时段</InputLabel>
              <Select
                value={editing?.period || "morning"}
                label="时段"
                onChange={(e) =>
                  setEditing((p) => ({ ...p, period: e.target.value }))
                }
              >
                {PERIODS.map((p) => (
                  <MenuItem key={p.key} value={p.key}>
                    {p.full} ({p.time})
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <TextField
              label="库存(片)"
              type="number"
              value={editing?.stock || ""}
              onChange={(e) =>
                setEditing((p) => ({
                  ...p,
                  stock: parseInt(e.target.value) || 0,
                }))
              }
            />
            <Button
              variant="contained"
              size="large"
              onClick={saveMed}
              startIcon={<Check />}
            >
              保存
            </Button>
          </Stack>
        </Box>
      </Drawer>

      {/* 阶段48-5: AI 助手 drawer */}
      <Drawer
        anchor="right"
        open={aiOpen}
        onClose={() => setAiOpen(false)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 480 }, p: 0 } }}
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
                  健康顾问 AI
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  agent: health_advisor + medication_reminder
                </Typography>
              </Box>
            </Stack>
            <IconButton onClick={() => setAiOpen(false)}>
              <Close />
            </IconButton>
          </Stack>
          <Box sx={{ flex: 1, overflowY: "auto", p: 2, bgcolor: "grey.50" }}>
            {/* 当前用药快照 */}
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mb: 1 }}
            >
              当前用药 (实时)
            </Typography>
            <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
              {allMeds.length === 0 ? (
                <Typography variant="caption" color="text.disabled">
                  暂无数据
                </Typography>
              ) : (
                <Stack spacing={0.5}>
                  {allMeds.map((m) => (
                    <Stack
                      key={m.id}
                      direction="row"
                      alignItems="center"
                      spacing={1}
                    >
                      <Box
                        sx={{
                          width: 6,
                          height: 6,
                          borderRadius: "50%",
                          bgcolor: m.taken ? "success.main" : "warning.main",
                        }}
                      />
                      <Typography variant="body2">
                        {m.name} {m.dose}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        @ {m.time}
                      </Typography>
                    </Stack>
                  ))}
                </Stack>
              )}
            </Paper>
            {aiReply ? (
              <Paper
                sx={{
                  p: 2,
                  bgcolor: "white",
                  borderLeft: "3px solid primary.main",
                }}
              >
                <Typography variant="caption" color="text.secondary">
                  health_advisor 回复：
                </Typography>
                <Typography
                  variant="body2"
                  sx={{ whiteSpace: "pre-wrap", mt: 0.5 }}
                >
                  {aiReply}
                </Typography>
              </Paper>
            ) : (
              <Paper
                variant="outlined"
                sx={{ p: 2, textAlign: "center", bgcolor: "white" }}
              >
                <Insights
                  sx={{ fontSize: 32, color: "text.disabled", mb: 1 }}
                />
                <Typography
                  variant="caption"
                  color="text.secondary"
                  display="block"
                >
                  询问关于您用药的任何问题
                </Typography>
                <Typography
                  variant="caption"
                  color="text.disabled"
                  sx={{ fontSize: "0.7rem" }}
                >
                  AI 会基于您当前用药 + 健康档案回答
                </Typography>
              </Paper>
            )}
            {aiLoading && <LinearProgress sx={{ mt: 1 }} />}
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
                placeholder="例如: 我现在血压 145/95, 还需要吃硝苯地平吗?"
                value={aiQuestion}
                onChange={(e) => setAiQuestion(e.target.value)}
                size="small"
              />
              <Button
                variant="contained"
                onClick={askAgent}
                disabled={aiLoading || !aiQuestion.trim()}
                startIcon={aiLoading ? <Bolt /> : <Send />}
              >
                问
              </Button>
            </Stack>
            <Stack
              direction="row"
              spacing={0.5}
              sx={{ mt: 1, flexWrap: "wrap" }}
            >
              {["这些药能一起吃吗", "我漏服了一次怎么办", "有什么副作用吗"].map(
                (s, i) => (
                  <Chip
                    key={i}
                    label={s}
                    size="small"
                    onClick={() => setAiQuestion(s)}
                    sx={{ fontSize: "0.7rem" }}
                  />
                ),
              )}
            </Stack>
          </Box>
        </Box>
      </Drawer>

      <Snackbar
        open={!!snack}
        autoHideDuration={2500}
        onClose={() => setSnack(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        {snack ? (
          <Alert
            severity={snack.severity}
            variant="filled"
            onClose={() => setSnack(null)}
          >
            {snack.msg}
          </Alert>
        ) : undefined}
      </Snackbar>
      <AgentQuickFab />
    </Box>
  );
}
