// 阶段48-22 v2: HealthRecordForm — 创建健康档案时显式挂附件
//
// 流程:
//   1. 填表 (title, type, date, hospital, importance, summary...)
//   2. 在 "附件" 一栏可手动上传 (HealthUploader) — 拿到 file_id
//   3. 选择要挂的 file_ids (多选卡片)
//   4. 提交:
//        a) 直接复用已有的 health_records POST (api/health-records) — 不行 (proxy 500)
//        b) Fallback: 走我们的 v2 attach: 先上传到 uploaded_files,
//           然后 V2 INSERT via api service / dashboard service
//      本组件提供 v3: POST 一步包了所有 — 调一个新 endpoint
//
// 实际流程 (v3 简化版):
//   - 上传文件 (HealthUploader) → file_ids[]
//   - 点击 "创建档案并挂附件" → POST /api/v2/create-record-and-attach
//     (下一阶段会加) 现在先调两步:  POST → insert file_ids into metadata via /api/v2-attach/{rid}/attach-files

import React, { useState, useEffect, useCallback } from "react";
import {
  Box, Button, Card, CardContent, Chip, FormControl, Grid, IconButton,
  InputLabel, MenuItem, Select, Stack, TextField, Typography,
  Alert, LinearProgress,
} from "@mui/material";
import {
  Save as SaveIcon, Close as CloseIcon, AttachFile as AttachFileIcon,
  Refresh as RefreshIcon,
} from "@mui/icons-material";
import HealthUploader from "./HealthUploader";

const API_BASE = (import.meta?.env?.VITE_API_BASE) || "http://localhost:13002";

const RECORD_TYPES = [
  { value: "lab_report", label: "化验报告" },
  { value: "imaging", label: "影像 (B超/CT/MRI/X光)" },
  { value: "prescription", label: "处方" },
  { value: "visit", label: "就诊记录" },
  { value: "vaccination", label: "疫苗" },
  { value: "other", label: "其他" },
];

const IMPORTANCE = ["low", "medium", "high"];

export default function HealthRecordForm({
  userId,
  onCreated,        // (record) => void
  onCancel,
  defaultAttachedFileIds = [],
}) {
  const [form, setForm] = useState({
    title: "",
    record_type: "lab_report",
    record_date: new Date().toISOString().slice(0, 10),
    hospital: "",
    doctor: "",
    summary: "",
    content: "",
    importance: "medium",
    tags: "",
  });
  const [attachedFileIds, setAttachedFileIds] = useState(defaultAttachedFileIds);
  const [files, setFiles] = useState([]); // 完整的 uploaded_files 列表
  const [uploaderOpen, setUploaderOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const getAuth = () => {
    if (typeof window === "undefined") return {};
    const t = window.localStorage.getItem("access_token");
    return t ? { Authorization: `Bearer ${t}` } : {};
  };

  const refreshFiles = useCallback(async () => {
    if (!userId) return;
    try {
      const r = await fetch(
        `${API_BASE}/v2/upload/files?user_id=${encodeURIComponent(userId)}&purpose=health_record&limit=50`,
        { headers: getAuth() },
      );
      if (r.ok) setFiles((await r.json()) || []);
    } catch {}
  }, [userId]);

  useEffect(() => { refreshFiles(); }, [refreshFiles]);

  const toggleAttach = (fid) => {
    setAttachedFileIds((prev) =>
      prev.includes(fid) ? prev.filter((x) => x !== fid) : [...prev, fid],
    );
  };

  const submit = async () => {
    setError(""); setInfo("");
    if (!form.title.trim()) {
      setError("请填标题");
      return;
    }
    setBusy(true);
    try {
      // Step 1: 直接 DB style — POST /api/v2/create-record-and-attach (下一步实现).
      // 这里先两步走:  POST record，然后 attach file_ids
      const payload = {
        title: form.title.trim(),
        record_type: form.record_type,
        record_date: form.record_date || null,
        hospital: form.hospital || "",
        doctor: form.doctor || "",
        summary: form.summary || "",
        content: form.content || "",
        importance: form.importance,
        tags: form.tags ? form.tags.split(",").map((s) => s.trim()).filter(Boolean) : [],
      };

      // NB: /api/health-records 当前会 500 (proxy bug), 这里直接走 DB 一样的 endpoint
      //    我们创建一个 v2 复合端点 — 但现阶段打调试讯号
      const createUrl = `${API_BASE}/api/health-records?user_id=${encodeURIComponent(userId)}`;
      const r = await fetch(createUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuth() },
        body: JSON.stringify(payload),
      });

      if (!r.ok) {
        const t = await r.text();
        throw new Error(`create record failed: ${r.status} ${t.slice(0, 200)}`);
      }
      const rec = await r.json();
      const rid = rec.id;

      // Step 2: attach files
      if (attachedFileIds.length > 0) {
        const r2 = await fetch(
          `${API_BASE}/api/v2-attach/health_records/${rid}/attach-files?user_id=${encodeURIComponent(userId)}`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json", ...getAuth() },
            body: JSON.stringify({ file_ids: attachedFileIds, replace: true }),
          },
        );
        if (!r2.ok) {
          const t = await r2.text();
          throw new Error(`attach files failed: ${r2.status} ${t.slice(0, 200)}`);
        }
      }

      setInfo(`创建成功 (id=${rid.slice(0,8)}…)  +${attachedFileIds.length} 附件`);
      onCreated?.(rec, attachedFileIds);
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
          <Typography variant="h6">新增健康档案</Typography>
          <Box sx={{ flex: 1 }} />
          {onCancel && (
            <IconButton size="small" onClick={onCancel}><CloseIcon /></IconButton>
          )}
        </Stack>

        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        {info && <Alert severity="success" sx={{ mb: 2 }}>{info}</Alert>}

        <Grid container spacing={2}>
          <Grid item xs={12} sm={8}>
            <TextField
              fullWidth size="small" label="标题 *"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="例: 2024-01 体检报告"
            />
          </Grid>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel>类型</InputLabel>
              <Select
                value={form.record_type}
                label="类型"
                onChange={(e) => setForm({ ...form, record_type: e.target.value })}
              >
                {RECORD_TYPES.map((t) => (
                  <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={4}>
            <TextField
              fullWidth size="small" type="date" label="日期"
              InputLabelProps={{ shrink: true }}
              value={form.record_date}
              onChange={(e) => setForm({ ...form, record_date: e.target.value })}
            />
          </Grid>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel>重要性</InputLabel>
              <Select
                value={form.importance}
                label="重要性"
                onChange={(e) => setForm({ ...form, importance: e.target.value })}
              >
                {IMPORTANCE.map((v) => (
                  <MenuItem key={v} value={v}>{v}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>

          <Grid item xs={12} sm={4}>
            <TextField
              fullWidth size="small" label="医院"
              value={form.hospital}
              onChange={(e) => setForm({ ...form, hospital: e.target.value })}
            />
          </Grid>

          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth size="small" label="医生"
              value={form.doctor}
              onChange={(e) => setForm({ ...form, doctor: e.target.value })}
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              fullWidth size="small" label="标签 (逗号分隔)"
              value={form.tags}
              onChange={(e) => setForm({ ...form, tags: e.target.value })}
              placeholder="体检, 高血糖"
            />
          </Grid>

          <Grid item xs={12}>
            <TextField
              fullWidth size="small" label="摘要"
              value={form.summary}
              onChange={(e) => setForm({ ...form, summary: e.target.value })}
              multiline rows={2}
            />
          </Grid>
          <Grid item xs={12}>
            <TextField
              fullWidth size="small" label="详细 (任意 OCR / 抄录内容)"
              value={form.content}
              onChange={(e) => setForm({ ...form, content: e.target.value })}
              multiline rows={3}
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
            <IconButton size="small" onClick={refreshFiles} title="刷新文件列表">
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
            <Box sx={{ mb: 2, p: 1.5, border: "1px dashed", borderColor: "divider", borderRadius: 1 }}>
              <HealthUploader
                userId={userId}
                domain="pha"
                purpose="health_record"
                purposeLabel="健康档案"
                showList={false}
                onUploaded={(f) => {
                  setFiles((p) => [f, ...p]);
                  setAttachedFileIds((prev) => [...prev, f.id]);
                }}
              />
            </Box>
          )}

          {/* 文件多选 */}
          {files.length === 0 ? (
            <Typography variant="caption" color="text.secondary">
              暂无已上传文件. 点击"上传新文件"或先用聊天上传几张.
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
                        <Typography variant="caption" sx={{ display: "block", fontWeight: 500 }}>
                          {f.original_name}
                        </Typography>
                        <Typography variant="caption" sx={{ opacity: 0.7 }}>
                          {(f.size_bytes / 1024).toFixed(1)}KB · OCR {f.ocr_status}
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

        <Stack direction="row" spacing={1} sx={{ mt: 3 }} justifyContent="flex-end">
          {onCancel && <Button onClick={onCancel} disabled={busy}>取消</Button>}
          <Button
            variant="contained"
            startIcon={<SaveIcon />}
            onClick={submit}
            disabled={busy}
          >
            创建档案 {attachedFileIds.length > 0 && `+${attachedFileIds.length} 附件`}
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
