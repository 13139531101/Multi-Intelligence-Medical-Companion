// 阶段48-22 v23: Today First 首页 — 第一眼回答"今天我要做什么"
// 设计原则: 今天/已做/明天/上周, 其他挪走. 情绪藏在数字里, 不评判.
// 阶段48-27: AI 控制页面组件 — 支持 PAGE_UPDATE 指令控制页面显示
import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Container,
  Paper,
  Typography,
  Button,
  Stack,
  Chip,
  Divider,
  CircularProgress,
  Collapse,
  IconButton,
} from "@mui/material";
import {
  Check,
  Close,
  ExpandMore,
  ChevronRight,
  Notifications,
  Medication,
  History,
  Edit,
  Assignment,
  SmartToy,
} from "@mui/icons-material";
import { useAuth } from "../contexts/AuthContext";
import {
  getMedicationReminders,
  markReminderTaken,
  getMedicationsHistory,
} from "../api/healthApi";
import { usePageUpdater } from "../components/usePageUpdater";

// 把今天分成早/中/晚三段
const PERIODS = [
  { key: "morning", label: "早上", time: "08:00", color: "#FFA726" },
  { key: "noon", label: "中午", time: "12:30", color: "#42A5F5" },
  { key: "evening", label: "晚上", time: "20:00", color: "#7E57C2" },
];

// 格式化今天日期: "7月25日 周五"
const formatToday = () => {
  const d = new Date();
  const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  return `${d.getMonth() + 1}月${d.getDate()}日 ${weekdays[d.getDay()]}`;
};

// 友好时段问候
const greeting = () => {
  const h = new Date().getHours();
  if (h < 11) return "早上好";
  if (h < 17) return "中午好";
  return "晚上好";
};

export default function TodayDashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();

  // ===== AI 页面控制: 注册组件到 ComponentRegistry =====
  const [aiData, setAiData] = useState(null); // AI 设置的数据
  usePageUpdater('TodayDashboard', {
    // AI 可以调用这些方法来操作页面
    setData: (params) => {
      console.log('[TodayDashboard] AI setData:', params);
      setAiData(params);
    },
    navigateTo: (params) => {
      if (params?.path) navigate(params.path);
    },
    showAlert: (params) => {
      alert(params?.message || '来自 AI 的提示');
    },
  });

  const [todayMeds, setTodayMeds] = useState({
    morning: [],
    noon: [],
    evening: [],
  });
  const [loading, setLoading] = useState(true);
  const [marking, setMarking] = useState(null);
  const [showTomorrow, setShowTomorrow] = useState(false);
  const [showWeek, setShowWeek] = useState(false);
  const [weekHistory, setWeekHistory] = useState([]);

  // 加载今日用药
  const fetchMeds = async () => {
    setLoading(true);
    try {
      const data = await getMedicationReminders({ today: true });
      const list = Array.isArray(data) ? data : data?.reminders || [];
      const grouped = { morning: [], noon: [], evening: [] };
      list.forEach((raw) => {
        const m = {
          ...raw,
          name: raw.medicationName || raw.name || "未命名药品",
          dose: raw.dosage || raw.dose || "",
          time: raw.time || (raw.scheduledTime || "08:00").slice(11, 16),
        };
        const hour = parseInt(m.time.split(":")[0]);
        const period = hour < 11 ? "morning" : hour < 17 ? "noon" : "evening";
        grouped[period].push(m);
      });
      setTodayMeds(grouped);
    } catch (e) {
      console.warn("[Today] getMedicationReminders:", e?.message);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchMeds();
    // 加载过去 7 天服药率 (用于 "上周 X 天按时吃药")
    getMedicationsHistory({ days: 7 })
      .then((rows) => setWeekHistory(rows || []))
      .catch(() => setWeekHistory([]));
  }, []);

  // 标记吃药 / 跳过
  const handleMark = async (med, taken) => {
    setMarking(med.id);
    try {
      await markReminderTaken(med.id, taken ? "" : "skip").catch(() => null);
      // 本地更新
      setTodayMeds((p) => {
        const next = { ...p };
        for (const k of Object.keys(next)) {
          next[k] = next[k].map((m) =>
            m.id === med.id
              ? { ...m, taken, status: taken ? "taken" : "skipped" }
              : m,
          );
        }
        return next;
      });
    } catch (e) {
      console.warn("[Today] mark failed:", e?.message);
    }
    setMarking(null);
  };

  // 找出当前最该吃的那一个 (未服 + 时间最早)
  const allUntaken = [
    ...todayMeds.morning,
    ...todayMeds.noon,
    ...todayMeds.evening,
  ].filter((m) => !m.taken && m.status !== "skipped");

  const hero = allUntaken[0] || null;

  // 今天的进度 (已吃 / 应吃)
  const allToday = [
    ...todayMeds.morning,
    ...todayMeds.noon,
    ...todayMeds.evening,
  ];
  const takenCount = allToday.filter(
    (m) => m.taken || m.status === "taken",
  ).length;
  const skippedCount = allToday.filter((m) => m.status === "skipped").length;
  const totalCount = allToday.length;

  // 上周服药率 — 真数据来自 getMedicationsHistory (按天聚合 taken/total)
  const daysOnTrack = weekHistory.filter(
    (d) => d.date !== new Date().toISOString().slice(0, 10) && d.value >= 80,
  ).length;
  const weekSummary = weekHistory.length
    ? `上周 ${daysOnTrack} 天按时吃药`
    : "服药数据加载中...";

  return (
    <Box sx={{ bgcolor: "#F5F7FA", minHeight: "100vh", pb: 4 }}>
      {/* 顶部: 问候 + 通知 + 头像 */}
      <Paper sx={{ borderRadius: 0, py: 2, px: 3, mb: 2 }} elevation={0}>
        <Stack
          direction="row"
          alignItems="center"
          justifyContent="space-between"
        >
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            {greeting()}, {user?.username || "朋友"}
          </Typography>
          <Stack direction="row" spacing={1}>
            <IconButton>
              <Notifications />
            </IconButton>
            <Box
              sx={{
                width: 36,
                height: 36,
                borderRadius: "50%",
                bgcolor: "primary.main",
                color: "white",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 600,
                cursor: "pointer",
              }}
              onClick={() => navigate("/v2/profile")}
            >
              {(user?.username || "U").charAt(0).toUpperCase()}
            </Box>
          </Stack>
        </Stack>
      </Paper>

      <Container maxWidth="sm">
        {/* 日期 */}
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          今天 · {formatToday()}
        </Typography>

        {/* Hero — 该吃药了 (或没药) */}
        {loading ? (
          <Paper sx={{ p: 4, textAlign: "center", borderRadius: 3 }}>
            <CircularProgress size={32} />
          </Paper>
        ) : hero ? (
          <Paper
            sx={{
              p: 3,
              borderRadius: 3,
              border: "2px solid",
              borderColor: "primary.main",
              bgcolor: "rgba(25, 118, 210, 0.04)",
            }}
          >
            <Stack
              direction="row"
              alignItems="center"
              spacing={1.5}
              sx={{ mb: 1 }}
            >
              <Box
                sx={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  bgcolor: "primary.main",
                  color: "white",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Medication />
              </Box>
              <Box>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  该吃药了
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {hero.time}
                </Typography>
              </Box>
            </Stack>
            <Typography variant="h5" sx={{ fontWeight: 700, mb: 2.5, ml: 1 }}>
              {hero.name} {hero.dose}
            </Typography>
            <Stack direction="row" spacing={1.5}>
              <Button
                fullWidth
                variant="contained"
                size="large"
                startIcon={<Check />}
                disabled={marking === hero.id}
                onClick={() => handleMark(hero, true)}
                sx={{ py: 1.5, fontWeight: 600 }}
              >
                吃了
              </Button>
              <Button
                fullWidth
                variant="outlined"
                size="large"
                startIcon={<Close />}
                disabled={marking === hero.id}
                onClick={() => handleMark(hero, false)}
                sx={{ py: 1.5 }}
              >
                跳过
              </Button>
            </Stack>
          </Paper>
        ) : (
          <Paper sx={{ p: 4, textAlign: "center", borderRadius: 3 }}>
            <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
              {totalCount === 0 ? "今天没安排吃药" : "今天的药都吃完啦"}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {totalCount === 0 ? "去添加药品, 让小助手帮你记着" : "明天见"}
            </Typography>
            {totalCount === 0 && (
              <Button
                variant="contained"
                sx={{ mt: 2 }}
                onClick={() => navigate("/v2/medication")}
              >
                去添加
              </Button>
            )}
          </Paper>
        )}

        {/* ===== AI 页面控制: 显示 AI 返回的数据 ===== */}
        {aiData && (
          <Paper
            sx={{
              mt: 2,
              p: 2.5,
              borderRadius: 3,
              border: "2px solid",
              borderColor: "info.main",
              bgcolor: "rgba(0, 145, 234, 0.08)",
            }}
          >
            <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
              <Box
                sx={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  bgcolor: "info.main",
                  color: "white",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <SmartToy />
              </Box>
              <Box>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  AI 分析结果
                </Typography>
                {aiData.title && (
                  <Typography variant="body2" color="text.secondary">
                    {aiData.title}
                  </Typography>
                )}
              </Box>
            </Stack>
            {/* 根据数据类型渲染 */}
            {aiData.type === 'health_records' && aiData.records && (
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  共 {aiData.records.length} 条记录
                </Typography>
                {aiData.records.slice(0, 3).map((r, i) => (
                  <Chip
                    key={i}
                    label={r.name || r.date || `记录 ${i + 1}`}
                    size="small"
                    sx={{ mr: 0.5, mb: 0.5 }}
                  />
                ))}
                {aiData.records.length > 3 && (
                  <Typography variant="caption" color="text.secondary">
                    ... 还有 {aiData.records.length - 3} 条
                  </Typography>
                )}
              </Box>
            )}
            {aiData.type === 'medications' && aiData.medications && (
              <Box sx={{ mt: 1 }}>
                <Typography variant="body2" sx={{ mb: 1 }}>
                  当前用药 {aiData.medications.length} 种
                </Typography>
                {aiData.medications.map((m, i) => (
                  <Chip
                    key={i}
                    label={`${m.name} ${m.dose || ''}`}
                    size="small"
                    color="primary"
                    sx={{ mr: 0.5, mb: 0.5 }}
                  />
                ))}
              </Box>
            )}
            {aiData.summary && (
              <Typography variant="body2" sx={{ mt: 1 }}>
                {aiData.summary}
              </Typography>
            )}
          </Paper>
        )}

        {/* AI 助手 Hero — 跟吃药同等待遇, 都是核心 */}
        <Paper
          sx={{
            mt: 2,
            p: 2.5,
            borderRadius: 3,
            border: "2px solid",
            borderColor: "secondary.main",
            bgcolor: "rgba(156, 39, 176, 0.04)",
            cursor: "pointer",
          }}
          onClick={() => navigate("/v2/chat")}
        >
          <Stack
            direction="row"
            alignItems="center"
            spacing={1.5}
            sx={{ mb: 1 }}
          >
            <Box
              sx={{
                width: 40,
                height: 40,
                borderRadius: "50%",
                bgcolor: "secondary.main",
                color: "white",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <SmartToy />
            </Box>
            <Box>
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                问问小助手
              </Typography>
              <Typography variant="body2" color="text.secondary">
                报告看不懂? 药咋吃? 想问就问
              </Typography>
            </Box>
          </Stack>
          <Stack
            direction="row"
            spacing={1}
            sx={{ flexWrap: "wrap", gap: 1, mb: 1.5 }}
          >
            <Chip
              label="血压偏高怎么办?"
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                navigate("/v2/chat", { state: { q: "血压偏高怎么办?" } });
              }}
              sx={{ cursor: "pointer" }}
            />
            <Chip
              label="我的报告啥意思?"
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                navigate("/v2/chat", { state: { q: "我的报告啥意思?" } });
              }}
              sx={{ cursor: "pointer" }}
            />
            <Chip
              label="药能一起吃吗?"
              size="small"
              onClick={(e) => {
                e.stopPropagation();
                navigate("/v2/chat", { state: { q: "药能一起吃吗?" } });
              }}
              sx={{ cursor: "pointer" }}
            />
          </Stack>
          <Button
            fullWidth
            variant="contained"
            color="secondary"
            size="large"
            endIcon={<ChevronRight />}
            sx={{ py: 1.5, fontWeight: 600 }}
          >
            去问问 →
          </Button>
        </Paper>

        {/* 今天的清单 */}
        {totalCount > 0 && (
          <Box sx={{ mt: 3 }}>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{ mb: 1, fontWeight: 500 }}
            >
              ─── 今天的清单 ───
            </Typography>
            <Paper sx={{ borderRadius: 3, overflow: "hidden" }}>
              {PERIODS.map((p) => {
                const list = todayMeds[p.key];
                if (!list || list.length === 0) return null;
                return (
                  <Box key={p.key}>
                    <Stack
                      direction="row"
                      alignItems="center"
                      spacing={1.5}
                      sx={{
                        px: 2,
                        py: 1.5,
                        borderLeft: `3px solid ${p.color}`,
                        bgcolor: "rgba(0,0,0,0.02)",
                      }}
                    >
                      <Typography
                        variant="body2"
                        sx={{ fontWeight: 600, color: p.color, width: 50 }}
                      >
                        {p.label}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {p.time}
                      </Typography>
                    </Stack>
                    {list.map((m) => (
                      <Stack
                        key={m.id}
                        direction="row"
                        alignItems="center"
                        spacing={2}
                        sx={{ px: 2, py: 1.25 }}
                      >
                        <Box
                          sx={{
                            width: 28,
                            height: 28,
                            borderRadius: "50%",
                            border: "2px solid",
                            borderColor:
                              m.taken || m.status === "taken"
                                ? "success.main"
                                : m.status === "skipped"
                                  ? "grey.400"
                                  : "grey.300",
                            bgcolor:
                              m.taken || m.status === "taken"
                                ? "success.main"
                                : "transparent",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                          }}
                        >
                          {m.taken || m.status === "taken" ? (
                            <Check sx={{ color: "white", fontSize: 18 }} />
                          ) : m.status === "skipped" ? (
                            <Close sx={{ color: "grey.400", fontSize: 16 }} />
                          ) : null}
                        </Box>
                        <Box sx={{ flex: 1 }}>
                          <Typography
                            variant="body2"
                            sx={{
                              fontWeight: 500,
                              textDecoration:
                                m.taken || m.status !== "pending"
                                  ? "line-through"
                                  : "none",
                              color:
                                m.status === "skipped"
                                  ? "text.disabled"
                                  : "text.primary",
                            }}
                          >
                            {m.name} {m.dose}
                          </Typography>
                          {m.status === "skipped" && (
                            <Typography variant="caption" color="text.disabled">
                              已跳过
                            </Typography>
                          )}
                        </Box>
                      </Stack>
                    ))}
                  </Box>
                );
              })}
            </Paper>

            {/* 数字说话, 不评判 */}
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 1.5, textAlign: "center" }}
            >
              {totalCount > 0 && (
                <>
                  今天吃了 {takenCount} 次
                  {skippedCount > 0 && `, 跳过 ${skippedCount} 次`}
                  {takenCount + skippedCount < totalCount &&
                    `, 还有 ${totalCount - takenCount - skippedCount} 次没吃`}
                </>
              )}
            </Typography>
          </Box>
        )}

        {/* 明天 (折叠) */}
        <Paper
          sx={{
            mt: 3,
            p: 1.5,
            borderRadius: 2,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
          onClick={() => setShowTomorrow(!showTomorrow)}
        >
          <Typography variant="body2" sx={{ fontWeight: 500 }}>
            看看明天
          </Typography>
          <ExpandMore
            sx={{
              transform: showTomorrow ? "rotate(180deg)" : "rotate(0deg)",
              transition: "0.2s",
            }}
          />
        </Paper>
        <Collapse in={showTomorrow}>
          <Paper
            sx={{ mt: 1, p: 2, borderRadius: 2, bgcolor: "rgba(0,0,0,0.02)" }}
          >
            <Typography variant="body2" color="text.secondary">
              明天 7月26日 (周六) — 跟今天一样的药
            </Typography>
          </Paper>
        </Collapse>

        {/* 上周 (折叠) */}
        <Paper
          sx={{
            mt: 1.5,
            p: 1.5,
            borderRadius: 2,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
          onClick={() => setShowWeek(!showWeek)}
        >
          <Typography variant="body2" sx={{ fontWeight: 500 }}>
            上周 ({weekSummary})
          </Typography>
          <ExpandMore
            sx={{
              transform: showWeek ? "rotate(180deg)" : "rotate(0deg)",
              transition: "0.2s",
            }}
          />
        </Paper>
        <Collapse in={showWeek}>
          <Paper
            sx={{ mt: 1, p: 2, borderRadius: 2, bgcolor: "rgba(0,0,0,0.02)" }}
          >
            <Typography variant="body2" color="text.secondary">
              本周服药详情 — 待接入真实历史 API
            </Typography>
          </Paper>
        </Collapse>

        {/* 跳到别的页面 (不在底部, 放内容下方) */}
        <Box sx={{ mt: 4 }}>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mb: 1, fontWeight: 500 }}
          >
            ─── 别的功能 ───
          </Typography>
          <Stack spacing={1.5}>
            <Paper
              sx={{
                p: 2,
                borderRadius: 2,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                cursor: "pointer",
              }}
              onClick={() => navigate("/v2/health-records")}
            >
              <Stack direction="row" alignItems="center" spacing={1.5}>
                <Assignment color="primary" />
                <Typography variant="body1" sx={{ fontWeight: 500 }}>
                  我的报告
                </Typography>
              </Stack>
              <ChevronRight color="action" />
            </Paper>
            <Paper
              sx={{
                p: 2,
                borderRadius: 2,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                cursor: "pointer",
              }}
              onClick={() => navigate("/v2/medication")}
            >
              <Stack direction="row" alignItems="center" spacing={1.5}>
                <Medication color="primary" />
                <Typography variant="body1" sx={{ fontWeight: 500 }}>
                  吃药管理
                </Typography>
              </Stack>
              <ChevronRight color="action" />
            </Paper>
            <Paper
              sx={{
                p: 2,
                borderRadius: 2,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                cursor: "pointer",
              }}
              onClick={() => navigate("/v2/chat")}
            >
              <Stack direction="row" alignItems="center" spacing={1.5}>
                <SmartToy color="primary" />
                <Typography variant="body1" sx={{ fontWeight: 500 }}>
                  问小助手
                </Typography>
              </Stack>
              <ChevronRight color="action" />
            </Paper>
          </Stack>
        </Box>
      </Container>
    </Box>
  );
}
