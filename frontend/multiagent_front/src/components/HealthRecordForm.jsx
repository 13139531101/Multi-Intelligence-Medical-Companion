// 阶段48-22 v3: HealthRecordForm — 单组件双 kind (health_record + visit_summary)
//
// 设计决策: 不拆成两个独立组件 — 表单 UX 高度相似, 拆了会让用户多一次选组件.
// 单一组件接受 kind prop, 内部按 kind 切换字段集, 提交时调同一个 /api/v2/create-record-and-attach,
// 后端根据 target_table 选择对应 schema.
//
// UX 流程 (不变):
//   1. 选择 "新建什么" — 健康档案 vs 就诊摘要 (顶部 segmented)
//   2. 填表 (按 kind 切换字段)
//   3. 上传附件 / 多选
//   4. 点击 "创建" — 1 步到位的 submit (含 idempotency-key)

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  Grid,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  Alert,
  LinearProgress,
  Divider,
} from "@mui/material";
import {
  Save as SaveIcon,
  Close as CloseIcon,
  AttachFile as AttachFileIcon,
  Refresh as RefreshIcon,
} from "@mui/icons-material";
import HealthUploader from "./HealthUploader";

const API_BASE = import.meta?.env?.VITE_API_BASE || "http://localhost:13002";

const RECORD_TYPES = [
  { value: "lab_report", label: "化验报告" },
  { value: "imaging", label: "影像 (B超/CT/MRI/X光)" },
  { value: "prescription", label: "处方" },
  { value: "visit", label: "就诊记录" },
  { value: "vaccination", label: "疫苗" },
  { value: "other", label: "其他" },
];

const IMPORTANCE = ["low", "medium", "high"];
const PRESCRIPTION_LABEL_HINT =
  '处方 (JSON 数组, 例如 [{"drug":"二甲双胍","dose":"0.5g"}])';

const KIND_META = {
  health_record: {
    label: "健康档案",
    table: "health_records",
    dateField: { key: "record_date", label: "日期" },
    titleHint: "例: 2024-01 体检报告",
  },
  visit_summary: {
    label: "就诊摘要",
    table: "visit_summaries",
    dateField: { key: "visit_date", label: "就诊日期" },
    titleHint: "例: 2024-01-15 协和内分泌门诊",
  },
};

const SUMMARY_MAX = 1000;

export default function HealthRecordForm({
  userId,
  kind = "health_record", // 'health_record' | 'visit_summary'
  onCreated,
  onCancel,
  defaultAttachedFileIds = [],
  onKindChange, // (newKind) => void   可选, 让父组件切换时拿到通知
}) {
  const [activeKind, setActiveKind] = useState(kind);
  const [form, setForm] = useState(() => buildInitialForm(activeKind));
  const [attachedFileIds, setAttachedFileIds] = useState(
    defaultAttachedFileIds,
  );
  const [files, setFiles] = useState([]);
  const [uploaderOpen, setUploaderOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  // 阶段48-22 v3: idempotency-key 防双击重复提交
  const idempotencyKey = useMemo(() => crypto.randomUUID(), []); // 一个表单实例对应一个 key

  const meta = KIND_META[activeKind];

  const getAuth = () => {
    if (typeof window === "undefined") return {};
    const t = window.localStorage.getItem("access_token");
    return t ? { Authorization: `Bearer ${t}` } : {};
  };

  const refreshFiles = useCallback(async () => {
    if (!userId) return;
    try {
      const r = await fetch(
        `${API_BASE}/v2/upload/files?user_id=${encodeURIComponent(userId)}&limit=50`,
        { headers: getAuth() },
      );
      if (r.ok) {
        const all = (await r.json()) || [];
        // 只展示目的匹配当前 kind 的文件 (purpose 跟 kind 对齐)
        // 健康档案 ↔ purpose=health_record,  就诊摘要 ↔ purpose=visit_summary
        const expectedPurpose = activeKind;
        setFiles(all.filter((f) => f.purpose === expectedPurpose));
      }
    } catch {}
  }, [userId, activeKind]);

  useEffect(() => {
    refreshFiles();
  }, [refreshFiles]);

  // 切换 kind 时重置表单
  const switchKind = (newKind) => {
    if (newKind === activeKind) return;
    setActiveKind(newKind);
    setForm(buildInitialForm(newKind));
    setAttachedFileIds([]);
    setError("");
    setInfo("");
    onKindChange?.(newKind);
  };

  const toggleAttach = (fid) => {
    setAttachedFileIds((prev) =>
      prev.includes(fid) ? prev.filter((x) => x !== fid) : [...prev, fid],
    );
  };

  const submit = async () => {
    setError("");
    setInfo("");
    if (!form.title.trim()) {
      setError("请填标题");
      return;
    }
    setBusy(true);
    try {
      const payload = {
        target_table: meta.table,
        record: buildRecordPayload(activeKind, form),
        attached_file_ids: attachedFileIds,
      };
      const r = await fetch(
        `${API_BASE}/api/v2/create-record-and-attach?user_id=${encodeURIComponent(userId)}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey, // 防重复
            ...getAuth(),
          },
          body: JSON.stringify(payload),
        },
      );
      if (!r.ok) {
        const t = await r.text();
        throw new Error(
          `one-step create failed: ${r.status} ${t.slice(0, 200)}`,
        );
      }
      const res = await r.json();
      const warn = res.warnings?.length
        ? `  ⚠ ${res.warnings.length} warning(s)`
        : "";
      setInfo(
        `创建成功${warn} — ${meta.label} +${res.attached_count} 附件 (id=${res.record_id.slice(0, 8)}…)`,
      );
      onCreated?.(res, attachedFileIds);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 2 }}>
          <Typography variant="h6">
            新增{activeKind === "visit_summary" ? "就诊摘要" : "健康档案"}
          </Typography>
          <Box sx={{ flex: 1 }} />
          {onCancel && (
            <IconButton size="small" onClick={onCancel}>
              <CloseIcon />
            </IconButton>
          )}
        </Stack>

        {/* Kind switcher */}
        <Box sx={{ mb: 2 }}>
          <ToggleButtonGroup
            value={activeKind}
            exclusive
            onChange={(_, v) => v && switchKind(v)}
            size="small"
          >
            <ToggleButton value="health_record">📋 健康档案</ToggleButton>
            <ToggleButton value="visit_summary">🏥 就诊摘要</ToggleButton>
          </ToggleButtonGroup>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}
        {info && (
          <Alert severity="success" sx={{ mb: 2 }}>
            {info}
          </Alert>
        )}

        {/* 表单字段 — 关键差异: visit_summary 多 4 个临床字段 */}
        <Grid container spacing={2}>
          <Grid item xs={12} sm={8}>
            <TextField
              fullWidth
              size="small"
              label="标题 *"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder={meta.titleHint}
            />
          </Grid>
          <Grid item xs={12} sm={4}>
            {activeKind === "health_record" ? (
              <FormControl fullWidth size="small">
                <InputLabel>类型</InputLabel>
                <Select
                  value={form.record_type}
                  label="类型"
                  onChange={(e) =>
                    setForm({ ...form, record_type: e.target.value })
                  }
                >
                  {RECORD_TYPES.map((t) => (
                    <MenuItem key={t.value} value={t.value}>
                      {t.label}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            ) : (
              <FormControl fullWidth size="small">
                <InputLabel>重要性</InputLabel>
                <Select
                  value={form.importance || "medium"}
                  label="重要性"
                  onChange={(e) =>
                    setForm({ ...form, importance: e.target.value })
                  }
                >
                  {IMPORTANCE.map((v) => (
                    <MenuItem key={v} value={v}>
                      {v}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}
          </Grid>

          <Grid item xs={12} sm={4}>
            <TextField
              fullWidth
              size="small"
              type="date"
              label={meta.dateField.label}
              InputLabelProps={{ shrink: true }}
              value={form[meta.dateField.key]}
              onChange={(e) =>
                setForm({ ...form, [meta.dateField.key]: e.target.value })
              }
            />
          </Grid>
          <Grid item xs={12} sm={4}>
            <TextField
              fullWidth
              size="small"
              label="医院"
              value={form.hospital}
              onChange={(e) => setForm({ ...form, hospital: e.target.value })}
            />
          </Grid>
          <Grid item xs={12} sm={4}>
            <TextField
              fullWidth
              size="small"
              label="医生"
              value={form.doctor}
              onChange={(e) => setForm({ ...form, doctor: e.target.value })}
            />
          </Grid>

          {activeKind === "health_record" && (
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                size="small"
                label="标签 (逗号分隔)"
                value={form.tags}
                onChange={(e) => setForm({ ...form, tags: e.target.value })}
                placeholder="体检, 高血糖"
              />
            </Grid>
          )}
          {activeKind === "health_record" && (
            <Grid item xs={12} sm={6}>
              <FormControl fullWidth size="small">
                <InputLabel>重要性</InputLabel>
                <Select
                  value={form.importance}
                  label="重要性"
                  onChange={(e) =>
                    setForm({ ...form, importance: e.target.value })
                  }
                >
                  {IMPORTANCE.map((v) => (
                    <MenuItem key={v} value={v}>
                      {v}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
          )}

          {/* visit_summary 专属字段 */}
          {activeKind === "visit_summary" && (
            <>
              <Grid item xs={12}>
                <Divider sx={{ my: 0.5 }}>
                  <Chip label="临床字段" size="small" />
                </Divider>
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="主诉"
                  value={form.chief_complaint}
                  onChange={(e) =>
                    setForm({ ...form, chief_complaint: e.target.value })
                  }
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="症状"
                  value={form.symptoms}
                  onChange={(e) =>
                    setForm({ ...form, symptoms: e.target.value })
                  }
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="检查"
                  value={form.examination}
                  onChange={(e) =>
                    setForm({ ...form, examination: e.target.value })
                  }
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="初步诊断"
                  value={form.diagnosis}
                  onChange={(e) =>
                    setForm({ ...form, diagnosis: e.target.value })
                  }
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="治疗方案"
                  value={form.treatment}
                  onChange={(e) =>
                    setForm({ ...form, treatment: e.target.value })
                  }
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="随访"
                  value={form.follow_up}
                  onChange={(e) =>
                    setForm({ ...form, follow_up: e.target.value })
                  }
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  size="small"
                  label={PRESCRIPTION_LABEL_HINT}
                  value={form.prescription}
                  onChange={(e) =>
                    setForm({ ...form, prescription: e.target.value })
                  }
                  multiline
                  rows={2}
                />
              </Grid>
            </>
          )}

          {/* 通用摘要 */}
          <Grid item xs={12}>
            <TextField
              fullWidth
              size="small"
              label="摘要"
              value={form.summary}
              onChange={(e) => setForm({ ...form, summary: e.target.value })}
              multiline
              rows={2}
              inputProps={{ maxLength: SUMMARY_MAX }}
              helperText={`${(form.summary || "").length}/${SUMMARY_MAX}`}
            />
          </Grid>
          <Grid item xs={12}>
            <TextField
              fullWidth
              size="small"
              label="详细 / OCR 文字 / 备注"
              value={form.content || form.notes || ""}
              onChange={(e) =>
                setForm({
                  ...form,
                  ...(activeKind === "health_record"
                    ? { content: e.target.value }
                    : { notes: e.target.value }),
                })
              }
              multiline
              rows={3}
            />
          </Grid>
        </Grid>

        {/* 附件区 */}
        <Box sx={{ mt: 3 }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <AttachFileIcon fontSize="small" />
            <Typography variant="subtitle2">
              附件 ({attachedFileIds.length} / {files.length})
            </Typography>
            <Box sx={{ flex: 1 }} />
            <IconButton
              size="small"
              onClick={refreshFiles}
              title="刷新文件列表"
            >
              <RefreshIcon fontSize="small" />
            </IconButton>
            <Button
              size="small"
              variant={uploaderOpen ? "contained" : "outlined"}
              onClick={() => setUploaderOpen((v) => !v)}
            >
              {uploaderOpen ? "收起上传" : "上传新文件"}
            </Button>
          </Stack>

          {uploaderOpen && (
            <Box
              sx={{
                mb: 2,
                p: 1.5,
                border: "1px dashed",
                borderColor: "divider",
                borderRadius: 1,
              }}
            >
              <HealthUploader
                userId={userId}
                domain="pha"
                purpose={activeKind}
                purposeLabel={KIND_META[activeKind].label}
                showList={false}
                onUploaded={(f) => {
                  setFiles((p) => [f, ...p]);
                  setAttachedFileIds((prev) => [...prev, f.id]);
                }}
              />
            </Box>
          )}

          {files.length === 0 ? (
            <Typography variant="caption" color="text.secondary">
              暂无当前 kind 的已上传文件. 点击"上传新文件"或先用聊天上传几张.
            </Typography>
          ) : (
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {files.map((f) => {
                const picked = attachedFileIds.includes(f.id);
                return (
                  <Chip
                    key={f.id}
                    label={
                      <Box>
                        <Typography
                          variant="caption"
                          sx={{ display: "block", fontWeight: 500 }}
                        >
                          {f.original_name}
                        </Typography>
                        <Typography variant="caption" sx={{ opacity: 0.7 }}>
                          {(f.size_bytes / 1024).toFixed(1)}KB · OCR{" "}
                          {f.ocr_status}
                        </Typography>
                      </Box>
                    }
                    clickable
                    onClick={() => toggleAttach(f.id)}
                    variant={picked ? "filled" : "outlined"}
                    color={picked ? "primary" : "default"}
                    sx={{ height: "auto", "& .MuiChip-label": { py: 0.5 } }}
                  />
                );
              })}
            </Stack>
          )}
        </Box>

        {busy && <LinearProgress sx={{ mt: 2 }} />}

        <Stack
          direction="row"
          spacing={1}
          sx={{ mt: 3 }}
          justifyContent="flex-end"
        >
          {onCancel && (
            <Button onClick={onCancel} disabled={busy}>
              取消
            </Button>
          )}
          <Button
            variant="contained"
            startIcon={<SaveIcon />}
            onClick={submit}
            disabled={busy}
          >
            创建{meta.label}{" "}
            {attachedFileIds.length > 0 && `+${attachedFileIds.length} 附件`}
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}

// ===== Helpers =====
function buildInitialForm(kind) {
  const today = new Date().toISOString().slice(0, 10);
  const base = {
    title: "",
    hospital: "",
    doctor: "",
    summary: "",
  };
  if (kind === "health_record") {
    return {
      ...base,
      record_type: "lab_report",
      record_date: today,
      importance: "medium",
      tags: "",
      content: "",
    };
  }
  // visit_summary
  return {
    ...base,
    visit_date: today,
    chief_complaint: "",
    symptoms: "",
    examination: "",
    diagnosis: "",
    treatment: "",
    prescription: "[]",
    follow_up: "",
    notes: "",
  };
}

function buildRecordPayload(kind, form) {
  if (kind === "health_record") {
    return {
      title: form.title.trim(),
      record_type: form.record_type,
      record_date: form.record_date || null,
      hospital: form.hospital || "",
      doctor: form.doctor || "",
      summary: form.summary || "",
      content: form.content || "",
      importance: form.importance || "medium",
      tags: form.tags
        ? form.tags
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean)
        : [],
    };
  }
  // visit_summary
  return {
    title: form.title.trim(),
    visit_date: form.visit_date || null,
    doctor: form.doctor || "",
    hospital: form.hospital || "",
    chief_complaint: form.chief_complaint || "",
    symptoms: form.symptoms || "",
    examination: form.examination || "",
    diagnosis: form.diagnosis || "",
    treatment: form.treatment || "",
    prescription: form.prescription || "[]",
    follow_up: form.follow_up || "",
    notes: form.notes || "",
  };
}
