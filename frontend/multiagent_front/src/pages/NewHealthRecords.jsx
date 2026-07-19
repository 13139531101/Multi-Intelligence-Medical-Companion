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
  Drawer,
  Divider,
  Tabs,
  Tab,
  ImageList,
  ImageListItem,
  ImageListItemBar,
  Skeleton,
  Alert,
  LinearProgress,
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
  uploadFile,
  getAttachmentUrl,
  getExtractedRecordInfo,
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
    files: r.files || r.file_attachments || r.metadata?.files || [],
    importance: r.importance || "medium",
    tags: r.tags || [],
    metadata: r.metadata || {},
    ocr: r.metadata?.ocr_result || null,
  };
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
    try {
      const ocr = await getExtractedRecordInfo(recordId);
      setRecords((p) =>
        p.map((r) => (r.id === recordId ? { ...r, ocr: ocr || r.ocr } : r)),
      );
      if (detail?.id === recordId) {
        setDetail((p) => ({ ...p, ocr: ocr || p.ocr }));
      }
    } catch (e) {
      console.warn("OCR extract failed:", e?.message);
    }
    setExtracting((p) => ({ ...p, [recordId]: false }));
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
                onClick={() => setDetail(r)}
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
                      {r.ocr ? "已 OCR 提取" : "未提取"}
                    </Typography>
                    {r.content && (
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
                    )}
                  </Box>
                  <ChevronRight color="action" />
                </Stack>
              </Paper>
            ))}
          </Stack>
        )}
      </Container>

      <Drawer
        anchor="right"
        open={!!detail}
        onClose={() => setDetail(null)}
        PaperProps={{ sx: { width: { xs: "100%", sm: 480 } } }}
      >
        {detail && (
          <Box>
            <Stack
              direction="row"
              alignItems="center"
              justifyContent="space-between"
              sx={{ p: 2, borderBottom: "1px solid", borderColor: "divider" }}
            >
              <Typography variant="h6" sx={{ fontWeight: 600 }} noWrap>
                档案详情
              </Typography>
              <IconButton size="small" onClick={() => setDetail(null)}>
                <Close />
              </IconButton>
            </Stack>
            <Box sx={{ p: 2 }}>
              <Stack
                direction="row"
                spacing={2}
                alignItems="center"
                sx={{ mb: 2 }}
              >
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
                <Box sx={{ flex: 1 }}>
                  <Typography variant="h6" sx={{ fontWeight: 600 }}>
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
                  </Stack>
                </Box>
              </Stack>

              <Stack spacing={1.5} sx={{ mb: 2 }}>
                {detail.hospital && (
                  <DetailRow
                    icon={<LocalHospital fontSize="small" />}
                    label={detail.hospital}
                    sub={detail.department}
                  />
                )}
                {detail.date && (
                  <DetailRow
                    icon={<Event fontSize="small" />}
                    label={detail.date}
                  />
                )}
                {detail.files.length > 0 && (
                  <DetailRow
                    icon={<ImageIcon fontSize="small" />}
                    label={`${detail.files.length} 个附件`}
                  />
                )}
              </Stack>

              {detail.content && (
                <Paper
                  variant="outlined"
                  sx={{ p: 1.5, mb: 2, bgcolor: "grey.50" }}
                >
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block", mb: 0.5 }}
                  >
                    内容
                  </Typography>
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                    {detail.content}
                  </Typography>
                </Paper>
              )}

              {detail.files.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block", mb: 1 }}
                  >
                    附件预览
                  </Typography>
                  <ImageList cols={2} gap={4} sx={{ m: 0 }}>
                    {detail.files.slice(0, 4).map((f, i) => {
                      const fid =
                        typeof f === "string" ? f : f.file_id || f.id || f;
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
                            alt=""
                            loading="lazy"
                            style={{
                              width: "100%",
                              height: 100,
                              objectFit: "cover",
                            }}
                            onError={(e) => {
                              e.target.style.display = "none";
                            }}
                          />
                        </ImageListItem>
                      );
                    })}
                  </ImageList>
                </Box>
              )}

              <Paper variant="outlined" sx={{ p: 1.5, mb: 2 }}>
                <Stack
                  direction="row"
                  alignItems="center"
                  justifyContent="space-between"
                  sx={{ mb: 1 }}
                >
                  <Stack direction="row" alignItems="center" spacing={0.5}>
                    <AutoAwesome fontSize="small" color="primary" />
                    <Typography variant="caption" sx={{ fontWeight: 600 }}>
                      OCR 提取
                    </Typography>
                  </Stack>
                  <Button
                    size="small"
                    startIcon={<AutoAwesome />}
                    disabled={extracting[detail.id]}
                    onClick={() => handleExtract(detail.id)}
                  >
                    {extracting[detail.id]
                      ? "提取中..."
                      : detail.ocr
                        ? "重新提取"
                        : "提取信息"}
                  </Button>
                </Stack>
                {extracting[detail.id] && <LinearProgress sx={{ mb: 1 }} />}
                {detail.ocr ? (
                  <Box sx={{ fontSize: "0.8rem" }}>
                    {Object.entries(detail.ocr)
                      .slice(0, 6)
                      .map(([k, v]) => (
                        <Stack
                          key={k}
                          direction="row"
                          sx={{
                            py: 0.25,
                            borderBottom: "1px dashed",
                            borderColor: "divider",
                          }}
                        >
                          <Typography
                            variant="caption"
                            sx={{ width: 80, color: "text.secondary" }}
                          >
                            {k}
                          </Typography>
                          <Typography variant="caption" sx={{ flex: 1 }}>
                            {typeof v === "object"
                              ? JSON.stringify(v)
                              : String(v)}
                          </Typography>
                        </Stack>
                      ))}
                  </Box>
                ) : (
                  <Typography variant="caption" color="text.secondary">
                    {extracting[detail.id]
                      ? "正在解析..."
                      : "点击提取以识别图片中的关键信息"}
                  </Typography>
                )}
              </Paper>

              {detail.tags && detail.tags.length > 0 && (
                <Stack
                  direction="row"
                  spacing={0.5}
                  sx={{ mb: 2, flexWrap: "wrap", gap: 0.5 }}
                >
                  {detail.tags.map((t, i) => (
                    <Chip key={i} label={t} size="small" variant="outlined" />
                  ))}
                </Stack>
              )}
            </Box>
            <Divider />
            <Stack direction="row" spacing={1} sx={{ p: 2 }}>
              <Button
                fullWidth
                variant="outlined"
                startIcon={<Edit />}
                onClick={() => setEditing(detail)}
              >
                编辑
              </Button>
              <Button
                fullWidth
                variant="outlined"
                color="error"
                startIcon={<Delete />}
                onClick={() => handleDelete(detail.id)}
              >
                删除
              </Button>
            </Stack>
          </Box>
        )}
      </Drawer>

      {/* 阶段48-22 v3+: 用 HealthRecordForm 替代老的 document.getElementById 表单 + 上传 Dialog */}
      <Dialog
        open={!!editing}
        onClose={() => setEditing(null)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          {editing?.id ? "编辑档案" : "新增档案 (含附件上传)"}
        </DialogTitle>
        <DialogContent dividers>
          {/* 注: 编辑模式还在老路径; 新建用 HealthRecordForm 含附件上传 */}
          {editing?.id ? (
            <Stack spacing={2} sx={{ pt: 1 }}>
              <TextField
                label="标题"
                fullWidth
                size="small"
                defaultValue={editing?.title || ""}
                id="edit-title"
              />
              <TextField
                select
                label="类型"
                fullWidth
                size="small"
                SelectProps={{ native: true }}
                defaultValue={editing?.type || "diagnosis"}
                id="edit-type"
              >
                {CATEGORIES.filter((c) => c.key !== "all").map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
              </TextField>
              <TextField
                label="医院"
                fullWidth
                size="small"
                defaultValue={editing?.hospital || ""}
                id="edit-hospital"
              />
              <TextField
                label="科室"
                fullWidth
                size="small"
                defaultValue={editing?.department || ""}
                id="edit-department"
              />
              <TextField
                label="日期"
                type="date"
                fullWidth
                size="small"
                defaultValue={editing?.date || ""}
                id="edit-date"
                InputLabelProps={{ shrink: true }}
              />
              <TextField
                label="内容描述"
                fullWidth
                size="small"
                multiline
                rows={3}
                defaultValue={editing?.content || ""}
                id="edit-content"
              />
            </Stack>
          ) : (
            <HealthRecordForm
              onCreated={() => {
                setEditing(null);
                fetchRecords();
              }}
              onCancel={() => setEditing(null)}
            />
          )}
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
