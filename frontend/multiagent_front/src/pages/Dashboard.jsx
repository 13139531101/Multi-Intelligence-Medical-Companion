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
  Tooltip,
  Divider,
  Avatar,
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
} from "@mui/icons-material";
import {
  getMedicationReminders,
  getConsultationHistory,
} from "../api/healthApi";
import { useAuth } from "../contexts/AuthContext";
import Header from "../components/HealthHeader";

const SECTIONS = [
  { name: "健康档案", path: "/health-records", desc: "病历与检查报告" },
  { name: "用药管理", path: "/medication", desc: "每日提醒与记录" },
  { name: "问医生", path: "/test-chat", desc: "在线咨询" },
  { name: "就诊小结", path: "/summary", desc: "病史与建议" },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [med, setMed] = useState({
    taken: 2,
    total: 5,
    next: "20:00 硝苯地平 30mg",
  });
  const [records, setRecords] = useState({
    total: 12,
    reports: 5,
    allergies: 3,
    exams: 8,
  });
  const [weekScore] = useState([
    { day: "周一", value: 58 },
    { day: "周二", value: 62 },
    { day: "周三", value: 60 },
    { day: "周四", value: 65 },
    { day: "周五", value: 68 },
    { day: "周六", value: 72 },
    { day: "今日", value: 60 },
  ]);

  useEffect(() => {
    (async () => {
      try {
        const m = await getMedicationReminders({ today: true }).catch(
          () => null,
        );
        if (m) setMed(m);
      } catch (e) {
        /* 静默 */
      }
      setLoading(false);
    })();
  }, []);

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Header />

      <Container maxWidth="lg" sx={{ py: 4 }}>
        {loading && <LinearProgress sx={{ mb: 2 }} />}

        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
          sx={{ mb: 4 }}
        >
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 600, mb: 0.5 }}>
              你好，{user?.username || "朋友"}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              7月16日 周三 · 记录健康，管理用药
            </Typography>
          </Box>
          <Tooltip title="通知">
            <IconButton>
              <NotificationsNone />
            </IconButton>
          </Tooltip>
        </Stack>

        <Grid container spacing={2} sx={{ mb: 3 }}>
          <Grid item xs={12} md={6}>
            <Card>
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
                    sx={{ fontWeight: 700, color: "primary.main" }}
                  >
                    60
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    / 100
                  </Typography>
                </Stack>
                <Box sx={{ height: 50 }}>
                  <svg
                    viewBox="0 0 300 50"
                    style={{ width: "100%", height: "100%" }}
                    preserveAspectRatio="none"
                  >
                    <polyline
                      points={weekScore
                        .map(
                          (t, i) =>
                            `${i * 50 + 10},${50 - (t.value / 100) * 40}`,
                        )
                        .join(" ")}
                      fill="none"
                      stroke="#1565C0"
                      strokeWidth="2"
                    />
                  </svg>
                </Box>
                <Typography variant="caption" color="text.secondary">
                  过去 7 天
                </Typography>
              </CardContent>
            </Card>
          </Grid>

          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Stack
                  direction="row"
                  alignItems="center"
                  spacing={1}
                  sx={{ mb: 1.5, color: "text.secondary" }}
                >
                  <Medication sx={{ fontSize: 18 }} />
                  <Typography variant="body2">今日用药</Typography>
                </Stack>
                <Stack
                  direction="row"
                  alignItems="baseline"
                  spacing={1}
                  sx={{ mb: 2 }}
                >
                  <Typography
                    variant="h2"
                    sx={{ fontWeight: 700, color: "secondary.main" }}
                  >
                    {med.taken}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    / {med.total} 已服
                  </Typography>
                </Stack>
                <LinearProgress
                  variant="determinate"
                  value={(med.taken / med.total) * 100}
                  sx={{ mb: 1.5 }}
                />
                <Stack direction="row" alignItems="center" spacing={1}>
                  <AccessTime sx={{ fontSize: 14, color: "text.secondary" }} />
                  <Typography variant="caption" color="text.secondary">
                    下次：{med.next}
                  </Typography>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        <Paper sx={{ p: 2.5, mb: 3 }}>
          <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
            快捷入口
          </Typography>
          <Grid container spacing={1.5}>
            {SECTIONS.map((s) => (
              <Grid item xs={6} md={3} key={s.name}>
                <Paper
                  onClick={() => navigate("/v2" + s.path)}
                  variant="outlined"
                  sx={{
                    p: 2,
                    cursor: "pointer",
                    textAlign: "center",
                    transition: "all 0.15s",
                    "&:hover": {
                      borderColor: "primary.main",
                      bgcolor: "rgba(21, 101, 192, 0.04)",
                    },
                  }}
                >
                  <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                    {s.name}
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block", mt: 0.5 }}
                  >
                    {s.desc}
                  </Typography>
                </Paper>
              </Grid>
            ))}
          </Grid>
        </Paper>

        <Grid container spacing={2}>
          <Grid item xs={12} md={7}>
            <Paper sx={{ p: 2.5 }}>
              <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
                健康档案
              </Typography>
              <Grid container spacing={1.5}>
                {[
                  { label: "病历", value: records.total, icon: <Assignment /> },
                  {
                    label: "检查报告",
                    value: records.reports,
                    icon: <Description />,
                  },
                  {
                    label: "过敏记录",
                    value: records.allergies,
                    icon: <Warning />,
                  },
                  {
                    label: "检查项目",
                    value: records.exams,
                    icon: <Science />,
                  },
                ].map((stat) => (
                  <Grid item xs={6} md={3} key={stat.label}>
                    <Paper
                      variant="outlined"
                      onClick={() => navigate("/v2/health-records")}
                      sx={{
                        p: 1.5,
                        textAlign: "center",
                        cursor: "pointer",
                        "&:hover": { borderColor: "primary.main" },
                      }}
                    >
                      <Avatar
                        sx={{
                          mx: "auto",
                          mb: 1,
                          width: 32,
                          height: 32,
                          bgcolor: "primary.main",
                        }}
                      >
                        {stat.icon}
                      </Avatar>
                      <Typography variant="h5" sx={{ fontWeight: 600 }}>
                        {stat.value}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {stat.label}
                      </Typography>
                    </Paper>
                  </Grid>
                ))}
              </Grid>
            </Paper>
          </Grid>

          <Grid item xs={12} md={5}>
            <Paper sx={{ p: 2.5 }}>
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 2 }}
              >
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  本周服药
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  92%
                </Typography>
              </Stack>
              <Stack spacing={1}>
                {weekScore.slice(0, 7).map((d) => (
                  <Stack
                    key={d.day}
                    direction="row"
                    alignItems="center"
                    spacing={1.5}
                  >
                    <Typography variant="caption" sx={{ width: 40 }}>
                      {d.day}
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={d.value}
                      sx={{ flex: 1 }}
                    />
                    <Typography
                      variant="caption"
                      sx={{ width: 32, textAlign: "right" }}
                    >
                      {d.value}%
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </Paper>
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
}
