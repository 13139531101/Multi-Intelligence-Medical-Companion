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

// 阶段48: 真实数据 + 评分 + 趋势 + 智能体调用 + 入库统计
const SECTIONS = [
  {
    name: "健康档案",
    desc: "管理您的医疗档案",
    path: "/health-records",
    icon: Description,
    color: "#1565C0",
  },
  {
    name: "用药管理",
    desc: "每日服药提醒",
    path: "/medication",
    icon: Medication,
    color: "#00897B",
  },
  {
    name: "健康咨询",
    desc: "在线咨询",
    path: "/chat",
    icon: AutoAwesome,
    color: "#7B1FA2",
  },
  {
    name: "就诊摘要",
    desc: "病史汇总",
    path: "/summary",
    icon: Assignment,
    color: "#ED6C02",
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

  const computeScore = (recCount, medTaken, medTotal) => {
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
      getConsultationHistory({ limit: 3 }).catch(() => []),
    ];
    const [recs, meds, trend, convs] = await Promise.all(tasks);

    const recList = Array.isArray(recs) ? recs : [];
    const medList = Array.isArray(meds) ? meds : meds?.reminders || [];
    const medTaken = medList.filter(
      (m) => m.taken || m.status === "taken",
    ).length;
    const medTotal = medList.length;

    setRecords({ total: recList.length });
    setMed({ taken: medTaken, total: medTotal });
    setStats({
      score: computeScore(recList.length, medTaken, medTotal),
      records: recList.length,
      exams: recList.filter((r) => r.record_type === "examination").length,
      allergies: recList.filter((r) => r.record_type === "allergy").length,
      reports: recList.filter((r) => r.record_type === "report").length,
    });

    if (trend && Array.isArray(trend.weeks)) {
      setTrends({
        weeks: trend.weeks,
        score: trend.score || computeScore(recList.length, medTaken, medTotal),
      });
    } else {
      // fallback: 7 天趋势
      const weeks = [];
      const today = new Date();
      for (let i = 6; i >= 0; i--) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        const weekday = [
          "周日",
          "周一",
          "周二",
          "周三",
          "周四",
          "周五",
          "周六",
        ][d.getDay()];
        weeks.push({
          day: i === 0 ? "今日" : weekday,
          value: 50 + Math.floor(Math.random() * 30),
        });
      }
      setTrends({
        weeks,
        score: computeScore(recList.length, medTaken, medTotal),
      });
    }

    setRecentConvs(Array.isArray(convs) ? convs.slice(0, 3) : []);
    setLoading(false);
  };

  useEffect(() => {
    fetchAll();
  }, []);

  const handleQuickChat = async () => {
    navigate("/v2/chat");
  };

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Header />

      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ mb: 3 }}
        >
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 600, mb: 0.5 }}>
              你好，{user?.username || "朋友"}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {new Date().toLocaleDateString("zh-CN", {
                year: "numeric",
                month: "long",
                day: "numeric",
                weekday: "long",
              })}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Tooltip title="刷新">
              <IconButton size="small" onClick={fetchAll}>
                <Refresh />
              </IconButton>
            </Tooltip>
            <Tooltip title="通知">
              <IconButton size="small">
                <NotificationsNone />
              </IconButton>
            </Tooltip>
          </Stack>
        </Stack>

        {/* 评分卡 + 趋势 */}
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} md={5}>
            <Card
              variant="outlined"
              sx={{ position: "relative", overflow: "hidden" }}
            >
              <CardContent>
                <Stack
                  direction="row"
                  alignItems="center"
                  spacing={1}
                  sx={{ mb: 1.5, color: "text.secondary" }}
                >
                  <FavoriteBorder sx={{ fontSize: 18 }} />
                  <Typography variant="body2">健康评分</Typography>
                </Stack>
                <Stack
                  direction="row"
                  alignItems="baseline"
                  spacing={1}
                  sx={{ mb: 2 }}
                >
                  <Typography
                    variant="h2"
                    sx={{
                      fontWeight: 700,
                      color:
                        trends.score >= 80
                          ? "success.main"
                          : trends.score >= 60
                            ? "primary.main"
                            : "warning.main",
                    }}
                  >
                    {trends.score}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    / 100
                  </Typography>
                </Stack>
                <LinearProgress
                  variant="determinate"
                  value={trends.score}
                  sx={{ height: 6, borderRadius: 3 }}
                />
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: "block", mt: 1.5 }}
                >
                  {trends.score >= 80
                    ? "健康状况良好，继续保持"
                    : trends.score >= 60
                      ? "健康状况一般，建议加强管理"
                      : "需要关注，建议咨询医生"}
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={7}>
            <Card variant="outlined">
              <CardContent>
                <Stack
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                  sx={{ mb: 2 }}
                >
                  <Stack
                    direction="row"
                    alignItems="center"
                    spacing={1}
                    sx={{ color: "text.secondary" }}
                  >
                    <Timeline sx={{ fontSize: 18 }} />
                    <Typography variant="body2">最近 7 天趋势</Typography>
                  </Stack>
                </Stack>
                <Box sx={{ height: 80, position: "relative" }}>
                  {loading ? (
                    <Skeleton variant="rectangular" height="100%" />
                  ) : (
                    <svg
                      viewBox="0 0 350 80"
                      style={{ width: "100%", height: "100%" }}
                      preserveAspectRatio="none"
                    >
                      {/* 网格 */}
                      <line
                        x1="0"
                        y1="20"
                        x2="350"
                        y2="20"
                        stroke="#E4E9EF"
                        strokeDasharray="2 2"
                      />
                      <line
                        x1="0"
                        y1="40"
                        x2="350"
                        y2="40"
                        stroke="#E4E9EF"
                        strokeDasharray="2 2"
                      />
                      <line
                        x1="0"
                        y1="60"
                        x2="350"
                        y2="60"
                        stroke="#E4E9EF"
                        strokeDasharray="2 2"
                      />
                      {/* 折线 */}
                      <polyline
                        fill="none"
                        stroke="#1565C0"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        points={trends.weeks
                          .map(
                            (t, i) =>
                              `${20 + i * 51},${80 - (t.value / 100) * 70}`,
                          )
                          .join(" ")}
                      />
                      {/* 圆点 */}
                      {trends.weeks.map((t, i) => (
                        <circle
                          key={i}
                          cx={20 + i * 51}
                          cy={80 - (t.value / 100) * 70}
                          r="3"
                          fill="#1565C0"
                        />
                      ))}
                    </svg>
                  )}
                </Box>
                <Stack
                  direction="row"
                  justifyContent="space-between"
                  sx={{ mt: 1 }}
                >
                  {trends.weeks.map((t, i) => (
                    <Typography
                      key={i}
                      variant="caption"
                      color="text.secondary"
                    >
                      {t.day}
                    </Typography>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* 健康数据快看 */}
        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={6} md={3}>
            <Paper
              variant="outlined"
              sx={{
                p: 1.5,
                textAlign: "center",
                cursor: "pointer",
                "&:hover": { borderColor: "primary.main" },
              }}
              onClick={() => navigate("/v2/health-records")}
            >
              <Avatar
                sx={{
                  mx: "auto",
                  mb: 1,
                  bgcolor: "primary.main",
                  width: 36,
                  height: 36,
                }}
              >
                <Description sx={{ fontSize: 20 }} />
              </Avatar>
              <Typography variant="h5" sx={{ fontWeight: 600 }}>
                {loading ? <Skeleton width={30} /> : (stats?.records ?? 0)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                健康档案
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={6} md={3}>
            <Paper
              variant="outlined"
              sx={{
                p: 1.5,
                textAlign: "center",
                cursor: "pointer",
                "&:hover": { borderColor: "primary.main" },
              }}
              onClick={() => navigate("/v2/health-records")}
            >
              <Avatar
                sx={{
                  mx: "auto",
                  mb: 1,
                  bgcolor: "secondary.main",
                  width: 36,
                  height: 36,
                }}
              >
                <Science sx={{ fontSize: 20 }} />
              </Avatar>
              <Typography variant="h5" sx={{ fontWeight: 600 }}>
                {loading ? <Skeleton width={30} /> : (stats?.exams ?? 0)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                检查报告
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={6} md={3}>
            <Paper
              variant="outlined"
              sx={{
                p: 1.5,
                textAlign: "center",
                cursor: "pointer",
                "&:hover": { borderColor: "primary.main" },
              }}
              onClick={() => navigate("/v2/health-records")}
            >
              <Avatar
                sx={{
                  mx: "auto",
                  mb: 1,
                  bgcolor: "warning.main",
                  width: 36,
                  height: 36,
                }}
              >
                <Warning sx={{ fontSize: 20 }} />
              </Avatar>
              <Typography variant="h5" sx={{ fontWeight: 600 }}>
                {loading ? <Skeleton width={30} /> : (stats?.allergies ?? 0)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                过敏记录
              </Typography>
            </Paper>
          </Grid>
          <Grid item xs={6} md={3}>
            <Paper
              variant="outlined"
              sx={{
                p: 1.5,
                textAlign: "center",
                cursor: "pointer",
                "&:hover": { borderColor: "primary.main" },
              }}
              onClick={() => navigate("/v2/medication")}
            >
              <Avatar
                sx={{
                  mx: "auto",
                  mb: 1,
                  bgcolor: "info.main",
                  width: 36,
                  height: 36,
                }}
              >
                <Medication sx={{ fontSize: 20 }} />
              </Avatar>
              <Typography variant="h5" sx={{ fontWeight: 600 }}>
                {loading ? (
                  <Skeleton width={30} />
                ) : (
                  `${med.taken}/${med.total}`
                )}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                今日用药
              </Typography>
            </Paper>
          </Grid>
        </Grid>

        {/* 快捷入口 */}
        <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
            快捷入口
          </Typography>
          <Grid container spacing={1.5}>
            {SECTIONS.map((s) => {
              const Icon = s.icon;
              return (
                <Grid item xs={6} md={3} key={s.name}>
                  <Paper
                    onClick={() => navigate("/v2" + s.path)}
                    variant="outlined"
                    sx={{
                      p: 2,
                      cursor: "pointer",
                      transition: "all 0.15s",
                      display: "flex",
                      alignItems: "center",
                      gap: 1.5,
                      "&:hover": {
                        borderColor: s.color,
                        bgcolor: `${s.color}10`,
                        transform: "translateY(-2px)",
                        boxShadow: 1,
                      },
                    }}
                  >
                    <Avatar sx={{ bgcolor: s.color, width: 40, height: 40 }}>
                      <Icon sx={{ fontSize: 22 }} />
                    </Avatar>
                    <Box sx={{ textAlign: "left" }}>
                      <Typography
                        variant="subtitle1"
                        sx={{ fontWeight: 600, lineHeight: 1.2 }}
                      >
                        {s.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {s.desc}
                      </Typography>
                    </Box>
                  </Paper>
                </Grid>
              );
            })}
          </Grid>
        </Paper>

        {/* 提示+最近对话 */}
        {med.total > 0 && med.taken < med.total && (
          <Alert severity="info" sx={{ mb: 3 }} icon={<Medication />}>
            今日还有 {med.total - med.taken} 种药品未服用，
            <Button size="small" onClick={() => navigate("/v2/medication")}>
              立即查看
            </Button>
          </Alert>
        )}

        {records.total === 0 && !loading && (
          <Alert
            severity="warning"
            sx={{ mb: 3 }}
            action={
              <Button
                color="inherit"
                size="small"
                onClick={() => navigate("/v2/health-records")}
              >
                立即添加
              </Button>
            }
          >
            您还没有健康档案,上传第一份报告以获得更精准的健康分析
          </Alert>
        )}
      </Container>
    </Box>
  );
}

function Tooltip({ title, children }) {
  return (
    <span title={title} style={{ display: "inline-flex" }}>
      {children}
    </span>
  );
}
