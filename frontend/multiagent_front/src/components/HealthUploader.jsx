// 阶段48-22: HealthUploader — 上传图片/文件, 自动 OCR + attach 到 health_records / visit_summaries
//
// 统一接口 POST /v2/upload/file
//   multipart: file + user_id + domain + purpose + metadata
// 即时返回 file_id, OCR 异步跑 (前端可选轮询 ocr_status)

import React, { useState, useRef, useEffect } from "react";
import {
  Box, Button, CircularProgress, LinearProgress, Chip, Stack, Typography,
  Tooltip, IconButton, Card, CardContent, CardMedia,
} from "@mui/material";
import {
  CloudUpload as CloudUploadIcon,
  Description as FileIcon,
  Image as ImageIcon,
  CheckCircle as CheckIcon,
  Error as ErrorIcon,
  Refresh as RefreshIcon,
  Delete as DeleteIcon,
} from "@mui/icons-material";

const API_BASE = (import.meta?.env?.VITE_API_BASE) || "http://localhost:13002";

const PURPOSE_LABEL = {
  health_record: "健康档案",
  visit_summary: "就诊摘要",
  report: "报告",
  avatar: "头像",
  other: "其他",
};

const ACCEPT = "image/*,application/pdf,text/csv,text/plain";

export default function HealthUploader({
  userId,
  domain = "pha",
  purpose = "health_record",
  purposeLabel,
  onUploaded,
  showList = true,
  max = 20,
}) {
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);
  const [files, setFiles] = useState([]); // [{id, name, ocr, attached, error}]
  const [error, setError] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const getAuth = () => {
    if (typeof window === "undefined") return {};
    const t = window.localStorage.getItem("access_token");
    return t ? { Authorization: `Bearer ${t}` } : {};
  };

  const loadList = async () => {
    if (!showList || !userId) return;
    try {
      const r = await fetch(
        `${API_BASE}/v2/upload/files?user_id=${encodeURIComponent(userId)}&domain=${domain}&purpose=${purpose}&limit=${max}`,
        { headers: getAuth() },
      );
      if (!r.ok) return;
      const data = await r.json();
      setFiles(data || []);
    } catch (e) {
      console.warn("[HealthUploader] list failed:", e);
    }
  };

  useEffect(() => { loadList(); }, [userId, domain, purpose, max]);

  const handleUpload = async (file) => {
    if (!userId) {
      setError("用户未登录");
      return;
    }
    setBusy(true); setError(""); setProgress(0);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("user_id", userId);
      fd.append("domain", domain);
      fd.append("purpose", purpose);
      fd.append("metadata", JSON.stringify({ uploaded_at: new Date().toISOString() }));

      // XMLHttpRequest to get progress
      const xhr = new XMLHttpRequest();
      const promise = new Promise((resolve, reject) => {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) setProgress(Math.round(e.loaded / e.total * 80));
        };
        xhr.onload = () => {
          if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
          else reject(new Error(`HTTP ${xhr.status}: ${xhr.responseText}`));
        };
        xhr.onerror = () => reject(new Error("network error"));
        xhr.open("POST", `${API_BASE}/v2/upload/file`);
        const headers = getAuth();
        for (const k in headers) xhr.setRequestHeader(k, headers[k]);
        xhr.send(fd);
      });

      setProgress(80);
      const res = await promise;
      setProgress(100);

      const newItem = {
        id: res.file_id,
        name: res.original_name,
        size_bytes: res.size_bytes,
        mime_type: res.mime_type,
        ocr_status: res.ocr_status || "pending",
        public_url: res.public_url,
        attached_record_id: res.attached_record_id || null,
        attached_table: res.attached_table || null,
        created_at: new Date().toISOString(),
      };
      setFiles((p) => [newItem, ...p]);
      onUploaded?.(newItem);

      // Poll OCR for up to 15s if pending
      if (res.ocr_status === "pending") {
        pollOcr(newItem.id);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setTimeout(() => { setBusy(false); setProgress(0); }, 600);
    }
  };

  const pollOcr = async (fileId) => {
    for (let i = 0; i < 8; i++) {
      await new Promise((r) => setTimeout(r, 1500));
      try {
        const r = await fetch(`${API_BASE}/v2/upload/file/${fileId}?user_id=${encodeURIComponent(userId)}`, {
          headers: getAuth(),
        });
        if (r.ok) {
          const d = await r.json();
          if (d.ocr_status === "done" || d.ocr_status === "failed" || d.ocr_status === "skipped") {
            setFiles((p) => p.map((f) => f.id === fileId ? {
              ...f,
              ocr_status: d.ocr_status,
              attached_record_id: d.attached_id,
              attached_table: d.attached_table,
              ocr_text: d.ocr_text,
            } : f));
            return;
          }
        }
      } catch (e) {
        console.warn("poll failed", e);
      }
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files || []);
    files.forEach(handleUpload);
  };

  const onSelect = (e) => {
    Array.from(e.target.files || []).forEach(handleUpload);
    e.target.value = "";
  };

  return (
    <Box>
      {/* Drop zone */}
      <Box
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        sx={{
          border: "2px dashed",
          borderColor: dragOver ? "primary.main" : "divider",
          borderRadius: 2,
          p: 3,
          textAlign: "center",
          bgcolor: dragOver ? "action.hover" : "transparent",
          cursor: "pointer",
          transition: "all 0.2s",
        }}
        onClick={() => inputRef.current?.click()}
        data-testid={`uploader-drop-${purpose}`}
      >
        <input
          type="file"
          ref={inputRef}
          multiple
          accept={ACCEPT}
          style={{ display: "none" }}
          onChange={onSelect}
        />
        {busy ? (
          <Box>
            <CircularProgress size={32} />
            <Typography variant="body2" sx={{ mt: 1 }}>
              上传中… {progress}%
            </Typography>
            <LinearProgress variant="determinate" value={progress} sx={{ mt: 1 }} />
          </Box>
        ) : (
          <Box>
            <CloudUploadIcon sx={{ fontSize: 48, color: "primary.main" }} />
            <Typography variant="body1" sx={{ mt: 1 }}>
              点击或拖拽文件到这里上传
            </Typography>
            <Typography variant="caption" color="text.secondary">
              支持 图片 (PNG/JPG) / PDF / CSV · 最大 50MB · 用途: {purposeLabel || PURPOSE_LABEL[purpose]}
            </Typography>
          </Box>
        )}
      </Box>

      {error && (
        <Typography variant="caption" color="error" sx={{ display: "block", mt: 1 }}>
          {error}
        </Typography>
      )}

      {/* File list */}
      {showList && files.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <Typography variant="subtitle2">已上传文件 ({files.length})</Typography>
            <IconButton size="small" onClick={loadList}><RefreshIcon fontSize="small" /></IconButton>
          </Stack>
          <Stack spacing={1}>
            {files.map((f) => (
              <Card key={f.id} variant="outlined" sx={{ display: "flex", alignItems: "center", p: 1 }}>
                <Box sx={{ mr: 1 }}>
                  {f.mime_type?.startsWith("image/") ? <ImageIcon color="primary" /> : <FileIcon color="action" />}
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" sx={{ fontWeight: 500 }} noWrap>
                    {f.name}
                  </Typography>
                  <Stack direction="row" spacing={1} sx={{ mt: 0.5 }} alignItems="center">
                    <Chip
                      size="small"
                      label={`${(f.size_bytes / 1024).toFixed(1)} KB`}
                      sx={{ height: 18, fontSize: "0.65rem" }}
                    />
                    <StatusChip status={f.ocr_status} />
                    {f.attached_table && f.attached_record_id && (
                      <Chip
                        size="small"
                        color="success"
                        label={`→ ${f.attached_table.replace("_", " · ")}`}
                        sx={{ height: 18, fontSize: "0.65rem" }}
                      />
                    )}
                  </Stack>
                </Box>
                {f.public_url && (
                  <Tooltip title="打开">
                    <IconButton size="small" component="a" href={`${API_BASE}${f.public_url}`} target="_blank">
                      <ImageIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
              </Card>
            ))}
          </Stack>
        </Box>
      )}
    </Box>
  );
}

function StatusChip({ status }) {
  const map = {
    pending: { label: "OCR 排队中", color: "default", icon: null },
    running: { label: "OCR 中…", color: "warning", icon: <CircularProgress size={10} /> },
    done: { label: "OCR 完成", color: "success", icon: <CheckIcon sx={{ fontSize: 12 }} /> },
    skipped: { label: "无需 OCR", color: "default", icon: null },
    failed: { label: "OCR 失败", color: "error", icon: <ErrorIcon sx={{ fontSize: 12 }} /> },
  };
  const info = map[status] || map.pending;
  return (
    <Chip
      size="small"
      label={info.label}
      color={info.color}
      icon={info.icon || undefined}
      sx={{ height: 18, fontSize: "0.65rem" }}
    />
  );
}
