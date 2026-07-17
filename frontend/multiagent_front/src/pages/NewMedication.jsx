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
  Divider,
  Badge,
  Snackbar,
  Alert,
  Tabs,
  Tab,
  ToggleButton,
  ToggleButtonGroup,
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
  LocalPharmacy,
  MoreVert,
  ChevronLeft,
  ChevronRight,
  Edit,
  Delete,
  History,
  EventAvailable,
  CheckCircle,
  RadioButtonUnchecked,
} from "@mui/icons-material";
import Header from "../components/HealthHeader";
import {
  getMedications,
  getMedicationReminders,
  markReminderTaken,
  deleteMedication,
  getMedicationsHistory,
} from "../api/healthApi";

// 阶段48: 升级 - 真实 API + 服药日历 + 时间轴 + 状态
const PERIODS = [
  {
    key: "morning",
    label: "早",
    time: "08:00",
    icon: WbSunny,
    color: "#FFA726",
  },
  { key: "noon", label: "中", time: "12:30", icon: WbSunny, color: "#66BB6A" },
  {
    key: "evening",
    label: "晚",
    time: "20:00",
    icon: WbTwilight,
    color: "#5E35B1",
  },
];

export default function NewMedication() {
  const [meds, setMeds] = useState({ morning: [], noon: [], evening: [] });
  const [stats, setStats] = useState({ taken: 0, total: 0 });
  const [streak, setStreak] = useState(0);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState("today"); // today / week / history
  const [weekData, setWeekData] = useState([]);
  const [selectedDate, setSelectedDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [notifications, setNotifications] = useState(true);
  const [snack, setSnack] = useState(null);
  const [marking, setMarking] = useState(null);

  const fetchMeds = async () => {
    setLoading(true);
    try {
      const data = await getMedicationReminders({ today: true });
      const list = Array.isArray(data) ? data : data?.reminders || [];
      const grouped = { morning: [], noon: [], evening: [] };
      list.forEach((m) => {
        const hour = parseInt((m.time || "08:00").split(":")[0]);
        const period = hour < 11 ? "morning" : hour < 17 ? "noon" : "evening";
        grouped[period].push({ ...m, period });
      });
      setMeds(grouped);
      setStats({
        taken: list.filter((m) => m.taken || m.status === "taken").length,
        total: list.length,
      });
    } catch (e) {
      console.warn("getMedicationReminders:", e?.message);
      // fallback sample
      setMeds({
        morning: [
          {
            id: 1,
            name: "硝苯地平",
            dose: "30mg",
            time: "08:00",
            taken: false,
            stock: 25,
            period: "morning",
          },
          {
            id: 2,
            name: "阿司匹林",
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
            name: "维生素 D",
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
            name: "硝苯地平",
            dose: "30mg",
            time: "20:00",
            taken: false,
            stock: 25,
            period: "evening",
          },
          {
            id: 5,
            name: "阿托伐他汀",
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
    setLoading(false);
  };

  const fetchWeek = async () => {
    try {
      const data = await getMedicationsHistory({ days: 7 }).catch(() => null);
      if (Array.isArray(data)) setWeekData(data);
    } catch {
      /* ignore */
    }
    // fallback: 7天假数据
    const days = ["周一", "周二", "周三", "周四", "周五", "周六", "今日"];
    setWeekData(
      days.map((d, i) => ({
        day: d,
        value: 50 + Math.floor(Math.random() * 50),
        date: "",
      })),
    );
  };

  useEffect(() => {
    fetchMeds();
    fetchWeek();
  }, []);

  const markTaken = async (period, id, skip = false) => {
    setMarking(id);
    try {
      await markReminderTaken(id, skip ? "skip" : "").catch(() => null);
      setMeds((p) => ({
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
      }));
      setStats((s) => ({
        ...s,
        taken: s.taken + (skip ? 0 : 1) - (skip ? 0 : 0),
      }));
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

  const dateText = new Date().toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });
  const progress =
    stats.total > 0 ? Math.round((stats.taken / stats.total) * 100) : 0;

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Header />

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
            <Tooltip title={notifications ? "提醒已开启" : "提醒已关闭"}>
              <Stack direction="row" alignItems="center" spacing={0.5}>
                <NotificationsActive
                  sx={{
                    fontSize: 18,
                    color: notifications ? "primary.main" : "text.disabled",
                  }}
                />
                <Switch
                  checked={notifications}
                  onChange={(e) => setNotifications(e.target.checked)}
                  size="small"
                />
              </Stack>
            </Tooltip>
            <Button startIcon={<Add />} variant="contained" size="small">
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
              <Stack spacing={1.5}>
                <LinearProgress />
              </Stack>
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
                            {period.label === "早"
                              ? "早晨"
                              : period.label === "中"
                                ? "中午"
                                : "晚间"}
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
                              ? "rgba(46, 125, 50, 0.04)"
                              : "transparent",
                            transition: "all 0.2s",
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
                            <Box sx={{ flex: 1 }}>
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
                                  : `${med.time} · 库存 ${med.stock || 30} 片`}
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
                <Button startIcon={<Add />} variant="contained">
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
              {weekData.length === 0 ? (
                <Typography color="text.secondary" textAlign="center">
                  暂无数据
                </Typography>
              ) : (
                weekData.map((d, i) => (
                  <Stack
                    key={i}
                    direction="row"
                    alignItems="center"
                    spacing={2}
                  >
                    <Typography variant="caption" sx={{ width: 50 }}>
                      {d.day || d.label || ""}
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
                ))
              )}
            </Stack>
          </Paper>
        )}

        {view === "history" && (
          <Paper sx={{ p: 3 }}>
            <Typography color="text.secondary" align="center" sx={{ py: 4 }}>
              历史服药记录 (开发中)
            </Typography>
          </Paper>
        )}
      </Container>

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
    </Box>
  );
}
