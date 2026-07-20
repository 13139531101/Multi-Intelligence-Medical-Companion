import React, { useState, useEffect } from "react";
import {
  Box,
  Container,
  Paper,
  Typography,
  Stack,
  Button,
  IconButton,
  TextField,
  InputAdornment,
  Grid,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Divider,
  Tabs,
  Tab,
  ImageList,
  ImageListItem,
  ImageListItemBar,
  Skeleton,
  Alert,
  LinearProgress,
  CircularProgress,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Card,
  CardContent,
  Avatar,
} from "@mui/material";
import {
  Search,
  Add,
  Description,
  Event,
  Image as ImageIcon,
  Close,
  Delete,
  Edit,
  Visibility,
  Download,
  LocalHospital,
  ExpandMore,
  ChevronRight,
  Face,
  Science,
  Warning,
  Medication,
  AutoAwesome,
  Refresh,
  FilterList,
} from "@mui/icons-material";
import Header from "../components/HealthHeader";
import HealthRecordForm from "../components/HealthRecordForm"; // 阶段48-22 v3+
import AgentQuickFab from "../components/AgentQuickFab";
import {
  getHealthRecords,
  createHealthRecord,
  updateHealthRecord,
  deleteHealthRecord,
  getAttachmentUrl,
  getExtractedRecordInfo,
  extractHealthRecord,
} from "../api/healthApi";

// 阶段48: 升级 - 加图片预览 + OCR 结果 + 详情抽屉 + 真实上传
const API_TO_TYPE = {
  diagnosis: { key: "diagnosis", label: "诊断", color: "#1565C0" },
  examination: { key: "exam", label: "检查", color: "#00897B" },
  exam: { key: "exam", label: "检查", color: "#00897B" },
  report: { key: "report", label: "报告", color: "#7B1FA2" },
  allergy: { key: "allergy", label: "过敏", color: "#C62828" },
  medication: { key: "medication", label: "用药", color: "#ED6C02" },
  other: { key: "other", label: "其他", color: "#5A6776" },
};

const CATEGORIES = [
  { key: "all", label: "全部" },
  { key: "diagnosis", label: "诊断" },
  { key: "exam", label: "检查" },
  { key: "report", label: "报告" },
  { key: "allergy", label: "过敏" },
  { key: "medication", label: "用药" },
];

const adaptRecord = (r) => {
  const typeInfo =
    API_TO_TYPE[r.record_type] || API_TO_TYPE[r.type] || API_TO_TYPE.other;
  return {
    id: r.id,
    title: r.title || r.summary || "未命名档案",
    type: typeInfo.key,
    typeLabel: typeInfo.label,
    color: typeInfo.color,
    date: r.record_date || r.date || "",
    hospital: r.hospital || r.metadata?.hospital || "",
    department: r.department || r.metadata?.department || "",
    content: r.description || r.summary || r.content || "",
    files:
      // 阶段48-22 v6: 后端 row_to_health_record 把 metadata._attached_files_meta
      //   注入了一份富信息 (id+name+mime+ocr_status+public_url)
      //   用它最全; 退化 4 道兜底确保历史数据不丢
      r.metadata?._attached_files_meta ||
      r.files ||
      r.file_attachments ||
      r.metadata?.files ||
      r.metadata?.attached_file_ids ||
      [],
    importance: r.importance || "medium",
    tags: r.tags || [],
    metadata: r.metadata || {},
    ocr: r.metadata?.ocr_result || null,
  };
};

// 阶段48-22 v6: OCR tab 用的辅助函数
const fname_default = (fid) =>
  fid ? `附件 ${String(fid).slice(0, 8)}` : "附件";

const ocrStatusLabel = (status) => {
  switch (status) {
    case "done":
      return "✓ 已识别";
    case "running":
      return "识别中";
    case "failed":
      return "失败";
    case "skipped":
      return "跳过";
    case "pending":
      return "待识别";
    default:
      return status || "未知";
  }
};

// 取最近一次"提取信息"返回的 OCR 文本 (按 fid 索引)
const lastExtractText = (fid, ocrBlock) => {
  if (!ocrBlock || !ocrBlock.files_ocr) return "";
  const m = (ocrBlock.files_ocr || []).find((x) => x.file_id === fid);
  return m?.reextract?.ocr_text || "";
};

export default function NewHealthRecords() {
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  // 阶段48-22 v3+: 单一入口 — 只有 'editing' (走 HealthRecordForm 内嵌的'上传附件')
  const [detail, setDetail] = useState(null);
  const [editing, setEditing] = useState(null);
  const [extracting, setExtracting] = useState({});
  // 阶段48-22 v5: 详情弹窗 Tab 状态 (基础/正文/附件/OCR)
  const [detailTab, setDetailTab] = useState(0);

  // 阶段48-22 v4: 从 AuthContext 写入的 localStorage.user 解 user_id
  //   之前没传, 子组件显示 "用户未登录"
  const currentUserId = (() => {
    if (typeof window === "undefined") return null;
    const raw = window.localStorage.getItem("user");
    if (!raw) return null;
    try {
      const u = JSON.parse(raw);
      return u.user_id || u.id || null;
    } catch {
      return null;
    }
  })();

  const fetchRecords = async () => {
    setLoading(true);
    try {
      const data = await getHealthRecords();
      if (Array.isArray(data)) {
        setRecords(data.map(adaptRecord));
      }
    } catch (e) {
      console.warn("getHealthRecords:", e?.message);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchRecords();
  }, []);

  const handleExtract = async (recordId) => {
    setExtracting((p) => ({ ...p, [recordId]: true }));
    setError("");
    // 阶段48-22 v6: 真实进度 — 在 records 里 mark OCR 进度数字
    const updateProgress = (doneCount, totalCount) => {
      setRecords((p) =>
        p.map((r) =>
          r.id === recordId
            ? {
                ...r,
                ocr_progress: {
                  done: doneCount,
                  total: totalCount,
                  started_at: new Date().toISOString(),
                },
              }
            : r,
        ),
      );
      if (detail?.id === recordId) {
        setDetail((p) =>
          p
            ? {
                ...p,
                ocr_progress: {
                  done: doneCount,
                  total: totalCount,
                  started_at: new Date().toISOString(),
                },
              }
            : p,
        );
      }
    };
    updateProgress(0, 1);
    try {
      // 先看 record 上有几个 image 文件要跑 (用作分母)
      const record = records.find((r) => r.id === recordId);
      const meta = record?.metadata?._attached_files_meta || [];
      const imageCount = meta.filter((f) =>
        (f.file_type || f.mime_type || "").startsWith("image/"),
      ).length;
      updateProgress(0, Math.max(1, imageCount));
      const res = await extractHealthRecord(recordId);
      const metaOut = {
        ok: res.ok,
        full_text: res.full_text,
        files_ocr: res.files_ocr,
        extracted_at: new Date().toISOString(),
      };
      const updateOne = (r) =>
        r.id === recordId
          ? {
              ...r,
              ocr: metaOut,
              metadata: { ...(r.metadata || {}), last_extract: metaOut },
            }
          : r;
      setRecords((p) => p.map(updateOne));
      if (detail?.id === recordId) {
        setDetail((p) => ({ ...p, ocr: metaOut }));
      }
      updateProgress((res.files_ocr || []).length, Math.max(1, imageCount));
      const okCount = (res.files_ocr || []).filter(
        (f) => f.reextract?.ok,
      ).length;
      const totalCount = (res.files_ocr || []).length;
      if (okCount > 0) {
        setInfo(`OCR 完成: ${okCount}/${totalCount} 个附件识别成功`);
      } else {
        setInfo(`OCR: ${totalCount} 个附件均未识别到文字 — 检查图是否清楚`);
      }
    } catch (e) {
      setError(e?.message || "OCR 失败");
      console.warn("OCR extract failed:", e?.message || e);
    } finally {
      setExtracting((p) => {
        const np = { ...p };
        delete np[recordId]; // 用 delete 而非 set false, 避免残留
        return np;
      });
      setRecords((p) =>
        p.map((r) =>
          r.id === recordId ? { ...r, ocr_progress: undefined } : r,
        ),
      );
      if (detail?.id === recordId) {
        setDetail((p) => (p ? { ...p, ocr_progress: undefined } : p));
      }
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("确定要删除此档案？")) return;
    try {
      await deleteHealthRecord(id);
      setRecords((p) => p.filter((r) => r.id !== id));
      setDetail(null);
    } catch (e) {
      alert("删除失败：" + (e?.message || ""));
    }
  };

  const filtered = records.filter((r) => {
    if (tab !== "all" && r.type !== tab) return false;
    if (search) {
      const s = search.toLowerCase();
      return (
        (r.title || "").toLowerCase().includes(s) ||
        (r.content || "").toLowerCase().includes(s) ||
        (r.hospital || "").toLowerCase().includes(s)
      );
    }
    return true;
  });

  const stats = {
    total: records.length,
    diagnosis: records.filter((r) => r.type === "diagnosis").length,
    exam: records.filter((r) => r.type === "exam").length,
    report: records.filter((r) => r.type === "report").length,
    allergy: records.filter((r) => r.type === "allergy").length,
  };

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      <Header />

      {/* 阶段48-7: 简洁 chip 标识当前 agent */}
      <Container maxWidth="lg" sx={{ pt: 2 }}>
        <Chip
          icon={<Description fontSize="small" />}
          label="health_records · 档案管理"
          size="small"
          sx={{ bgcolor: "#E0F2F1", color: "#00897B", fontWeight: 500 }}
        />
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
              健康档案
            </Typography>
            <Typography variant="caption" color="text.secondary">
              共 {stats.total} 条记录
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Button
              startIcon={<Refresh />}
              variant="text"
              size="small"
              onClick={fetchRecords}
            >
              刷新
            </Button>
            <Button
              startIcon={<Add />}
              variant="contained"
              size="small"
              onClick={() => setEditing({})}
            >
              新增档案
            </Button>
          </Stack>
        </Stack>

        <Grid container spacing={1.5} sx={{ mb: 2 }}>
          {[
            { label: "诊断", value: stats.diagnosis, color: "#1565C0" },
            { label: "检查", value: stats.exam, color: "#00897B" },
            { label: "报告", value: stats.report, color: "#7B1FA2" },
            { label: "过敏", value: stats.allergy, color: "#C62828" },
            { label: "档案总数", value: stats.total, color: "#5A6776" },
          ].map((s) => (
            <Grid item xs={6} md key={s.label}>
              <Paper
                variant="outlined"
                sx={{
                  p: 1.5,
                  textAlign: "center",
                  borderTop: `3px solid ${s.color}`,
                }}
              >
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  {s.value}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {s.label}
                </Typography>
              </Paper>
            </Grid>
          ))}
        </Grid>

        <Paper sx={{ p: 1, mb: 2 }}>
          <Stack direction="row" spacing={1} alignItems="center">
            <TextField
              fullWidth
              size="small"
              placeholder="搜索档案 / 医院 / 内容"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search />
                  </InputAdornment>
                ),
              }}
              sx={{ "& .MuiOutlinedInput-root": { borderRadius: 1 } }}
            />
          </Stack>
        </Paper>

        <Paper sx={{ p: 0.5, mb: 2 }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable">
            {CATEGORIES.map((c) => (
              <Tab key={c.key} value={c.key} label={c.label} />
            ))}
          </Tabs>
        </Paper>

        {loading ? (
          <Stack spacing={1}>
            <Skeleton variant="rectangular" height={80} />
            <Skeleton variant="rectangular" height={80} />
          </Stack>
        ) : filtered.length === 0 ? (
          <Paper sx={{ p: 6, textAlign: "center" }}>
            <Description sx={{ fontSize: 48, color: "text.disabled", mb: 1 }} />
            <Typography color="text.secondary" sx={{ mb: 2 }}>
              {search ? "无搜索结果" : "暂无档案"}
            </Typography>
            {!search && (
              <Stack direction="row" spacing={1} justifyContent="center">
                <Button
                  variant="contained"
                  startIcon={<Add />}
                  onClick={() => setEditing({})}
                >
                  新建第一份档案
                </Button>
              </Stack>
            )}
          </Paper>
        ) : (
          <Stack spacing={1}>
            {filtered.map((r) => (
              <Paper
                key={r.id}
                variant="outlined"
                sx={{
                  p: 2,
                  cursor: "pointer",
                  transition: "all 0.15s",
                  borderLeft: `4px solid ${r.color}`,
                  "&:hover": { borderColor: r.color, boxShadow: 1 },
                }}
                onClick={() => {
                  setDetailTab(0);
                  setDetail(r);
                }}
              >
                <Stack direction="row" spacing={2} alignItems="flex-start">
                  <Avatar
                    variant="rounded"
                    sx={{ bgcolor: r.color, width: 44, height: 44 }}
                  >
                    {r.type === "diagnosis" ? (
                      <Face />
                    ) : r.type === "exam" ? (
                      <Science />
                    ) : r.type === "report" ? (
                      <Description />
                    ) : r.type === "allergy" ? (
                      <Warning />
                    ) : r.type === "medication" ? (
                      <Medication />
                    ) : (
                      <Description />
                    )}
                  </Avatar>
                  {/* 阶段48-22 v6: OCR 进行中显示旋转 chip (在 avatar 右侧) */}
                  {extracting[r.id] && (
                    <CircularProgress size={16} sx={{ mt: 0.5, mr: -1 }} />
                  )}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Stack
                      direction="row"
                      alignItems="center"
                      justifyContent="space-between"
                    >
                      <Typography
                        variant="subtitle1"
                        sx={{ fontWeight: 600 }}
                        noWrap
                      >
                        {r.title}
                      </Typography>
                      <Chip
                        label={r.typeLabel}
                        size="small"
                        sx={{
                          bgcolor: r.color,
                          color: "white",
                          height: 20,
                          fontSize: "0.7rem",
                        }}
                      />
                    </Stack>
                    {r.hospital && (
                      <Typography variant="caption" color="text.secondary">
                        {r.hospital}
                        {r.department ? ` · ${r.department}` : ""}
                      </Typography>
                    )}
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ display: "block" }}
                    >
                      {r.date ? `${r.date} · ` : ""}
                      {r.files.length > 0 ? `${r.files.length} 个附件 · ` : ""}
                      {(() => {
                        // 阶段48-22 v6: 把附件级 ocr_status 聚合出"已识别 N/M"
                        const meta =
                          (r.metadata && r.metadata._attached_files_meta) || [];
                        if (meta.length === 0) {
                          return r.ocr ? "已 OCR 提取" : "未提取";
                        }
                        const done = meta.filter(
                          (f) => (f.ocr_status || "").toLowerCase() === "done",
                        ).length;
                        if (done === meta.length)
                          return `OCR 已识别 ${done}/${meta.length}`;
                        if (done > 0)
                          return `OCR 已识别 ${done}/${meta.length}`;
                        return "未提取";
                      })()}
                    </Typography>
                    {/* 阶段48-22 v6: 直接显示第一条 OCR 文本作为卡片预览 — 一眼能看到内容 */}
                    {(() => {
                      const meta =
                        (r.metadata && r.metadata._attached_files_meta) || [];
                      const firstDone = meta.find(
                        (f) =>
                          (f.ocr_status || "").toLowerCase() === "done" &&
                          (f.ocr_text || "").length > 0,
                      );
                      if (firstDone) {
                        const preview = (firstDone.ocr_text || "")
                          .replace(/\s+/g, " ")
                          .trim()
                          .slice(0, 140);
                        return (
                          <Typography
                            variant="body2"
                            color="text.primary"
                            sx={{
                              mt: 0.5,
                              display: "-webkit-box",
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: "vertical",
                              overflow: "hidden",
                              pl: 1,
                              borderLeft: "2px solid",
                              borderColor: "success.light",
                            }}
                            title={`来自附件: ${firstDone.file_name || ""}`}
                          >
                            {preview}
                            {(firstDone.ocr_text || "").length > 140 ? "…" : ""}
                          </Typography>
                        );
                      }
                      return r.content ? (
                        <Typography
                          variant="body2"
                          color="text.primary"
                          sx={{
                            mt: 0.5,
                            display: "-webkit-box",
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                          }}
                        >
                          {r.content}
                        </Typography>
                      ) : null;
                    })()}
                  </Box>
                  <ChevronRight color="action" />
                </Stack>
              </Paper>
            ))}
          </Stack>
        )}
      </Container>

      {/* 阶段48-22 v5: 弹窗(Material Dialog)取代侧边栏(Drawer).
            - 更大尺寸, 中心展示, 一眼看清档案全部内容
            - Tab 分区: 基础信息 / 正文 / 附件 / OCR (避免信息堆在一起)  */}
      <Dialog
        open={!!detail}
        onClose={() => setDetail(null)}
        maxWidth="md"
        fullWidth
        PaperProps={{ sx: { borderRadius: 2 } }}
      >
        {detail &&
          (() => {
            const fileCount = (detail.files || []).length;
            // 阶段48-22 v6: 至少 1 个附件 OCR 已 done 才打 OCR ✓
            const metaFiles =
              (detail.metadata && detail.metadata._attached_files_meta) || [];
            const hasOcr =
              metaFiles.length > 0 &&
              metaFiles.some(
                (f) => (f.ocr_status || "").toLowerCase() === "done",
              );
            return (
              <>
                {/* 顶部 — 类型 chip + 标题 + 关闭 */}
                <DialogTitle sx={{ pb: 1.5 }}>
                  <Stack direction="row" spacing={2} alignItems="center">
                    <Avatar
                      variant="rounded"
                      sx={{ bgcolor: detail.color, width: 56, height: 56 }}
                    >
                      {detail.type === "diagnosis" ? (
                        <Face />
                      ) : detail.type === "exam" ? (
                        <Science />
                      ) : (
                        <Description />
                      )}
                    </Avatar>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="h6" sx={{ fontWeight: 700 }} noWrap>
                        {detail.title}
                      </Typography>
                      <Stack direction="row" spacing={1} sx={{ mt: 0.5 }}>
                        <Chip
                          label={detail.typeLabel}
                          size="small"
                          sx={{ bgcolor: detail.color, color: "white" }}
                        />
                        <Chip
                          label={detail.importance || "medium"}
                          size="small"
                          variant="outlined"
                        />
                        {fileCount > 0 && (
                          <Chip
                            size="small"
                            variant="outlined"
                            label={`📎 ${fileCount} 个附件`}
                          />
                        )}
                      </Stack>
                    </Box>
                    <IconButton onClick={() => setDetail(null)}>
                      <Close />
                    </IconButton>
                  </Stack>
                </DialogTitle>

                {/* 4-区 Tabs — 默认第一区(基础信息) */}
                <Box sx={{ borderBottom: 1, borderColor: "divider", px: 2 }}>
                  <Tabs
                    value={detailTab}
                    onChange={(_, v) => setDetailTab(v)}
                    variant="scrollable"
                    scrollButtons="auto"
                  >
                    <Tab label="基础信息" />
                    <Tab label={`正文${detail.content ? "" : " (空)"}`} />
                    <Tab label={`附件${fileCount ? ` (${fileCount})` : ""}`} />
                    <Tab label={`OCR${hasOcr ? " ✓" : ""}`} />
                  </Tabs>
                </Box>

                <DialogContent dividers sx={{ minHeight: 360 }}>
                  {/* Tab 0: 基础信息 */}
                  {detailTab === 0 && (
                    <Stack spacing={2}>
                      <Grid container spacing={2}>
                        {detail.date && (
                          <Grid item xs={12} sm={6}>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
                              日期
                            </Typography>
                            <Typography variant="body1">
                              {detail.date}
                            </Typography>
                          </Grid>
                        )}
                        {detail.hospital && (
                          <Grid item xs={12} sm={6}>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
                              医院 / 科室
                            </Typography>
                            <Typography variant="body1">
                              {detail.hospital}
                              {detail.department
                                ? ` · ${detail.department}`
                                : ""}
                            </Typography>
                          </Grid>
                        )}
                        <Grid item xs={12} sm={6}>
                          <Typography variant="caption" color="text.secondary">
                            重要性
                          </Typography>
                          <Typography variant="body1">
                            {detail.importance || "medium"}
                          </Typography>
                        </Grid>
                        {detail.tags && detail.tags.length > 0 && (
                          <Grid item xs={12}>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
                              标签
                            </Typography>
                            <Stack
                              direction="row"
                              spacing={0.5}
                              sx={{ flexWrap: "wrap", gap: 0.5, mt: 0.5 }}
                            >
                              {detail.tags.map((t, i) => (
                                <Chip
                                  key={i}
                                  label={t}
                                  size="small"
                                  variant="outlined"
                                />
                              ))}
                            </Stack>
                          </Grid>
                        )}
                      </Grid>

                      {/* 摘要提示 */}
                      <Alert severity="info" variant="outlined">
                        {detail.content
                          ? `本文档有 ${detail.content.length} 字正文, 切到 "正文" tab 阅读`
                          : "本文档暂无正文 — 切到 OCR tab 从附件提取, 或点 编辑 手动填写"}
                      </Alert>
                    </Stack>
                  )}

                  {/* Tab 1: 正文 */}
                  {detailTab === 1 && (
                    <Box>
                      {detail.content ? (
                        <Typography
                          variant="body1"
                          sx={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}
                        >
                          {detail.content}
                        </Typography>
                      ) : (
                        <Stack alignItems="center" sx={{ py: 6 }} spacing={1}>
                          <Description
                            sx={{ fontSize: 48, color: "text.disabled" }}
                          />
                          <Typography variant="body2" color="text.secondary">
                            暂无正文
                          </Typography>
                          <Button
                            startIcon={<AutoAwesome />}
                            onClick={() => handleExtract(detail.id)}
                            disabled={extracting[detail.id]}
                          >
                            从附件 OCR 提取
                          </Button>
                        </Stack>
                      )}
                    </Box>
                  )}

                  {/* Tab 2: 附件 */}
                  {detailTab === 2 && (
                    <Box>
                      {fileCount > 0 ? (
                        <ImageList cols={3} gap={8} sx={{ m: 0 }}>
                          {detail.files.map((f, i) => {
                            const fid =
                              typeof f === "string"
                                ? f
                                : f.file_id || f.id || f;
                            const fname =
                              typeof f === "object"
                                ? f.original_name || f.name || `附件 ${i + 1}`
                                : `附件 ${i + 1}`;
                            return (
                              <ImageListItem
                                key={i}
                                sx={{
                                  border: "1px solid",
                                  borderColor: "divider",
                                  borderRadius: 1,
                                  overflow: "hidden",
                                }}
                              >
                                <img
                                  src={getAttachmentUrl(fid)}
                                  alt={fname}
                                  loading="lazy"
                                  style={{
                                    width: "100%",
                                    height: 160,
                                    objectFit: "cover",
                                  }}
                                  onError={(e) => {
                                    e.target.style.display = "none";
                                  }}
                                />
                                <ImageListItemBar title={fname} />
                              </ImageListItem>
                            );
                          })}
                        </ImageList>
                      ) : (
                        <Stack alignItems="center" sx={{ py: 6 }} spacing={1}>
                          <ImageIcon
                            sx={{ fontSize: 48, color: "text.disabled" }}
                          />
                          <Typography variant="body2" color="text.secondary">
                            暂无附件
                          </Typography>
                        </Stack>
                      )}
                    </Box>
                  )}

                  {/* Tab 3: OCR — 阶段48-22 v6 修复: 直接读 _attached_files_meta
                       老逻辑看 detail.ocr (永远 null, 因为 OCR 文本写 uploaded_files.ocr_text,
                       不写 metadata.ocr_result), 所以 tab 一直空.
                       现在从附件列表里逐个显示状态 + 文本. */}
                  {detailTab === 3 && (
                    <Stack spacing={2}>
                      <Stack
                        direction="row"
                        alignItems="center"
                        justifyContent="space-between"
                      >
                        <Stack
                          direction="row"
                          alignItems="center"
                          spacing={0.5}
                        >
                          <AutoAwesome fontSize="small" color="primary" />
                          <Typography variant="subtitle2">
                            OCR 提取结果
                          </Typography>
                        </Stack>
                        <Button
                          size="small"
                          startIcon={<AutoAwesome />}
                          disabled={!!extracting[detail.id]}
                          onClick={() => {
                            if (extracting[detail.id]) return;
                            handleExtract(detail.id);
                          }}
                        >
                          {extracting[detail.id] ? "提取中..." : "重新提取"}
                        </Button>
                      </Stack>
                      {extracting[detail.id] && (
                        <Stack spacing={0.5}>
                          <LinearProgress />
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{
                              display: "flex",
                              alignItems: "center",
                              gap: 0.5,
                            }}
                          >
                            <CircularProgress size={12} />
                            正在调用 Qwen-VL 识别图片中的文字 (每张图 3-10 秒)
                          </Typography>
                        </Stack>
                      )}

                      {/* 直接展示每个附件的 OCR 文本, 从 uploaded_files (通过 merge 注入 _attached_files_meta) */}
                      {(() => {
                        const fileList = Array.isArray(detail.files)
                          ? detail.files
                          : [];
                        const metaFiles =
                          (detail.metadata &&
                            detail.metadata._attached_files_meta) ||
                          [];
                        // 兼容: detail.files 可能是 dict 数组或字符串数组
                        if (!fileList.length) {
                          return (
                            <Typography variant="body2" color="text.secondary">
                              本档案暂无附件, 无 OCR 内容
                            </Typography>
                          );
                        }
                        const showFiles =
                          metaFiles.length > 0
                            ? metaFiles
                            : fileList.map((f) =>
                                typeof f === "object"
                                  ? f
                                  : {
                                      file_id: f,
                                      file_name: `附件 ${f.slice(0, 8)}`,
                                    },
                              );
                        return (
                          <Stack spacing={1.5}>
                            {showFiles.map((f) => {
                              const fid = f.file_id;
                              const fname = f.file_name || fname_default(fid);
                              const status = (f.ocr_status || "").toLowerCase();
                              const ocrText =
                                f.ocr_text || lastExtractText(fid, detail.ocr);
                              return (
                                <Paper
                                  key={fid}
                                  variant="outlined"
                                  sx={{ p: 1.5 }}
                                >
                                  <Stack
                                    direction="row"
                                    alignItems="center"
                                    spacing={1}
                                    sx={{ mb: ocrText ? 1 : 0 }}
                                  >
                                    <Description fontSize="small" />
                                    <Typography
                                      variant="body2"
                                      sx={{ flex: 1, fontWeight: 600 }}
                                      noWrap
                                    >
                                      {fname}
                                    </Typography>
                                    <Chip
                                      size="small"
                                      label={ocrStatusLabel(status)}
                                      color={
                                        status === "done"
                                          ? "success"
                                          : status === "failed"
                                            ? "error"
                                            : status === "running"
                                              ? "info"
                                              : "default"
                                      }
                                      variant="outlined"
                                    />
                                  </Stack>
                                  {ocrText ? (
                                    <Typography
                                      variant="body2"
                                      sx={{
                                        whiteSpace: "pre-wrap",
                                        lineHeight: 1.6,
                                        maxHeight: 280,
                                        overflow: "auto",
                                        bgcolor: "grey.50",
                                        p: 1.5,
                                        borderRadius: 1,
                                        fontFamily: "monospace",
                                      }}
                                    >
                                      {ocrText}
                                    </Typography>
                                  ) : status !== "running" ? (
                                    <Typography
                                      variant="body2"
                                      color="text.secondary"
                                    >
                                      {status === "failed"
                                        ? "OCR 失败 — 点 '重新提取' 重试"
                                        : status === "skipped"
                                          ? "此附件为非图片/PDF, 无需 OCR"
                                          : "尚未识别 — 点 '重新提取' 启动"}
                                    </Typography>
                                  ) : null}
                                </Paper>
                              );
                            })}
                          </Stack>
                        );
                      })()}
                    </Stack>
                  )}
                </DialogContent>

                <DialogActions sx={{ p: 2 }}>
                  <Button
                    color="error"
                    startIcon={<Delete />}
                    onClick={() => handleDelete(detail.id)}
                  >
                    删除
                  </Button>
                  <Box sx={{ flex: 1 }} />
                  <Button onClick={() => setDetail(null)}>关闭</Button>
                  <Button
                    variant="contained"
                    startIcon={<Edit />}
                    onClick={() => setEditing(detail)}
                  >
                    编辑
                  </Button>
                </DialogActions>
              </>
            );
          })()}
      </Dialog>

      {/* 阶段48-22 v3+: 用 HealthRecordForm 替代老的 document.getElementById 表单 + 上传 Dialog */}
      <Dialog
        open={!!editing}
        onClose={() => setEditing(null)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{editing?.id ? "编辑档案" : "新增档案"}</DialogTitle>
        <DialogContent dividers>
          {/* 注: 阶段48-22 v3+: 新建 / 编辑 都用 HealthRecordForm (含附件编辑能力) */}
          <HealthRecordForm
            mode={editing?.id ? "edit" : "create"}
            kind="health_record"
            userId={currentUserId}
            recordId={editing?.id}
            initialRecord={editing?.id ? editing : null}
            onCreated={() => {
              setEditing(null);
              fetchRecords();
            }}
            onUpdated={() => {
              setEditing(null);
              fetchRecords();
              setDetail(null);
            }}
            onCancel={() => setEditing(null)}
          />
        </DialogContent>
        {editing?.id && (
          <DialogActions>
            <Button onClick={() => setEditing(null)}>取消</Button>
            <Button
              variant="contained"
              onClick={async () => {
                const payload = {
                  title: document.getElementById("edit-title").value,
                  type: document.getElementById("edit-type").value,
                  hospital: document.getElementById("edit-hospital").value,
                  department: document.getElementById("edit-department").value,
                  date: document.getElementById("edit-date").value,
                  description: document.getElementById("edit-content").value,
                };
                try {
                  await updateHealthRecord(editing.id, payload);
                  setEditing(null);
                  fetchRecords();
                } catch (e) {
                  alert("保存失败: " + (e?.message || ""));
                }
              }}
            >
              保存
            </Button>
          </DialogActions>
        )}
      </Dialog>
      <AgentQuickFab />
    </Box>
  );
}

function DetailRow({ icon, label, sub }) {
  return (
    <Stack direction="row" spacing={1.5} alignItems="center">
      <Box sx={{ color: "text.secondary", display: "flex" }}>{icon}</Box>
      <Box>
        <Typography variant="body2">{label}</Typography>
        {sub && (
          <Typography variant="caption" color="text.secondary">
            {sub}
          </Typography>
        )}
      </Box>
    </Stack>
  );
}
