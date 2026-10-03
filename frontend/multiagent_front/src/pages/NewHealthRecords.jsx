import React, { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
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
  Snackbar,
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
  InfoOutlined,
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
import { usePageUpdater } from "../components/usePageUpdater";
import { PAGE_COMPONENTS, PAGE_ACTIONS } from "../ai/pageContract";
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
  getParsedOcr,
} from "../api/healthApi";

// 阶段48: 升级 - 加图片预览 + OCR 结果 + 详情抽屉 + 真实上传
// 后端 record_type → 本页分类 tab 的映射。
//
// ⚠️ 这里有两个不同的词表，别混：后端写库用的 record_type（lab_report /
// medical_report / symptom / hospital_record …）跟前端 tab 的 key（diagnosis /
// exam / report / allergy / medication）**从来不是一套**。
//
// 阶段48-29 修：这张表原先只认 diagnosis/examination/exam/report/allergy/
// medication/other，而后端实际在写的是 lab_report / medical_report / symptom
// —— 它们查不到键，全部退到 other，而 other 根本不是 CATEGORIES 的 key。
// 结果库里 26 条档案有 23 条点任何分类 tab 都看不到。下面补上实际在用的键。
const API_TO_TYPE = {
  // —— 原本就有的 ——
  diagnosis: { key: "diagnosis", label: "诊断", color: "#1565C0" },
  examination: { key: "exam", label: "检查", color: "#00897B" },
  exam: { key: "exam", label: "检查", color: "#00897B" },
  report: { key: "report", label: "报告", color: "#7B1FA2" },
  allergy: { key: "allergy", label: "过敏", color: "#C62828" },
  medication: { key: "medication", label: "用药", color: "#ED6C02" },
  other: { key: "other", label: "其他", color: "#5A6776" },
  // —— 阶段48-29 补：后端 record_type 词表（见 _TYPE_ALIASES）——
  lab_report: { key: "exam", label: "检查", color: "#00897B" },
  medical_report: { key: "report", label: "报告", color: "#7B1FA2" },
  symptom: { key: "diagnosis", label: "诊断", color: "#1565C0" },
  prescription: { key: "medication", label: "用药", color: "#ED6C02" },
  hospital_record: { key: "diagnosis", label: "诊断", color: "#1565C0" },
  surgery: { key: "diagnosis", label: "诊断", color: "#1565C0" },
  vaccination: { key: "exam", label: "检查", color: "#00897B" },
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

// 阶段48-22 v6: 详情页 0 tab 顶部的 OCR 摘要区
// 抽取 /parsed, 合并用户手输入 content (若存在)
function OcrSummaryBlock({ detailId, files, metadata, userContent }) {
  const metaFiles = (metadata && metadata._attached_files_meta) || [];
  const showFiles =
    metaFiles.length > 0
      ? metaFiles
      : (Array.isArray(files) ? files : []).map((f) =>
          typeof f === "object"
            ? f
            : { file_id: f, file_name: `附件 ${f.slice(0, 8)}` },
        );
  const firstDone = showFiles.find(
    (f) => (f.ocr_status || "").toLowerCase() === "done" && (f.file_id || f.id),
  );
  const fid = firstDone?.file_id || firstDone?.id;
  const fname = firstDone?.file_name || "";
  const [parsed, setParsed] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!fid) return;
    let alive = true;
    setLoading(true);
    (async () => {
      try {
        let uid = null;
        try {
          const u = JSON.parse(localStorage.getItem("user") || "{}");
          uid = u.user_id || u.id || u.sub || null;
        } catch {}
        if (!uid) uid = metadata?.user_id || null;
        if (!uid) uid = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a";
        const r = await getParsedOcr(fid, uid);
        if (alive) setParsed(r.parsed);
      } catch {
        /* ignore */
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [fid, detailId]);

  // 醒目字段 (跟解析页一致)
  const HIGHLIGHT = new Set([
    "姓名",
    "性别",
    "年龄",
    "床号",
    "临床诊断",
    "病理诊断",
  ]);
  // 关键 fields (从 parsed.fields 抽 4-6 个最值得展示)
  const filled = (parsed?.fields || []).filter((f) => f.filled);
  const keyFields = filled.filter((f) => HIGHLIGHT.has(f.key)).slice(0, 6);

  // 合并逻辑: 用户手输入 content 显示作 '内容摘要', 但不压 raw 文本 (用户从正文 Tab 看结构化版)
  const userContentTrim = (userContent || "").trim();
  const hasUserContent = userContentTrim.length > 0;
  const showOcSummary =
    !loading && parsed && (parsed.summary || keyFields.length > 0);

  // 内容是 OCR 自动写入 (区分: 以 '## 文件名' 开头就是 auto-merge 进来的)
  const isAutoOcrContent =
    userContentTrim.startsWith("## ") &&
    /^## \S+\.\w+\s*\n/.test(userContentTrim);
  const contentTitle = isAutoOcrContent ? "📝 从附件自动识别" : "✍️ 您填写";
  // 摘要预览: 取第一句或前 60 字
  const firstLine = userContentTrim.split("\n")[0].slice(0, 80);
  const secondLine = (userContentTrim.split("\n")[1] || "").slice(0, 80);

  if (!fid && !hasUserContent) {
    // 既没 OCR 也没手填 — 不渲染, 让基础页保持干净
    return null;
  }

  return (
    <Stack spacing={1.5}>
      {/* A. 内容摘要卡片 — 只显示前 80 字 + 跳转按钮, 不压 raw 文本
         raw 文本在正文 Tab 已经渲染成结构化卡片, 这里只是摘要 + 跳转.*/}
      {hasUserContent && (
        <Paper
          variant="outlined"
          sx={{ p: 1.5, borderColor: "secondary.light" }}
        >
          <Stack direction="row" alignItems="flex-start" spacing={1}>
            <Edit color="secondary" fontSize="small" />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 0.5 }}
              >
                <Typography variant="caption" color="text.secondary">
                  {contentTitle} · {userContentTrim.length} 字
                </Typography>
                <Button
                  size="small"
                  variant="text"
                  sx={{
                    minWidth: 0,
                    fontSize: "0.7rem",
                    py: 0,
                    px: 1,
                  }}
                  onClick={() => {
                    const evt = new CustomEvent("v2-healthrecords-jump-tab", {
                      detail: 1,
                    });
                    document.dispatchEvent(evt);
                  }}
                >
                  查看正文 →
                </Button>
              </Stack>
              {/* 只显示前两行摘要, 不展开 raw 文本 */}
              <Typography
                variant="body2"
                color="text.primary"
                sx={{
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {firstLine}
                {secondLine ? ` — ${secondLine}` : ""}
                {userContentTrim.length > 160 ? " …" : ""}
              </Typography>
            </Box>
          </Stack>
        </Paper>
      )}

      {/* B. OCR 解析摘要 */}
      {loading && fid && (
        <Paper variant="outlined" sx={{ p: 1.5, borderColor: "primary.light" }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <CircularProgress size={16} />
            <Typography variant="body2" color="text.secondary">
              加载图片识别内容…
            </Typography>
          </Stack>
        </Paper>
      )}
      {showOcSummary && (
        <Paper variant="outlined" sx={{ p: 1.5, borderColor: "primary.light" }}>
          <Stack spacing={1}>
            <Stack direction="row" alignItems="center" spacing={1}>
              <AutoAwesome color="primary" fontSize="small" />
              <Typography
                variant="subtitle2"
                sx={{ flex: 1, color: "primary.main" }}
              >
                📋 图片识别到的信息
              </Typography>
              {fname && (
                <Chip
                  label={fname}
                  size="small"
                  variant="outlined"
                  sx={{
                    maxWidth: 160,
                    "& .MuiChip-label": { textOverflow: "ellipsis" },
                  }}
                />
              )}
            </Stack>

            {/* 摘要一句话 */}
            {parsed.summary && (
              <Typography
                variant="body2"
                sx={{ fontWeight: 500, color: "primary.dark" }}
              >
                {parsed.summary}
              </Typography>
            )}

            {/* 关键 fields: 姓名/性别/年龄/床号/诊断 */}
            {keyFields.length > 0 && (
              <Grid container spacing={0.75}>
                {keyFields.map((f) => (
                  <Grid item xs={12} sm={6} key={f.key}>
                    <Stack direction="row" spacing={0.5} alignItems="baseline">
                      <Typography
                        variant="caption"
                        sx={{ color: "text.secondary", minWidth: 52 }}
                      >
                        {f.key}
                      </Typography>
                      <Typography
                        variant="body2"
                        sx={{
                          fontWeight: 600,
                          color: "text.primary",
                          wordBreak: "break-all",
                        }}
                      >
                        {f.value}
                      </Typography>
                    </Stack>
                  </Grid>
                ))}
              </Grid>
            )}
          </Stack>
        </Paper>
      )}

      {/* C. 用户视角: 没有任何 '已识别' 的图片 — 用更友好的非技术提示 */}
      {!fid && (files || []).length > 0 && (
        <Paper
          variant="outlined"
          sx={{
            p: 1,
            display: "flex",
            alignItems: "center",
            gap: 1,
            bgcolor: "grey.50",
            borderStyle: "dashed",
          }}
        >
          <InfoOutlined fontSize="small" color="action" />
          <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
            附件里的图片内容正在后台读取, 读取完后会自动出现在正文里
          </Typography>
        </Paper>
      )}
    </Stack>
  );
}

// 调 /v2/upload/files/{fid}/parsed 拿 {fields, sections, summary}
// 渲染: 顶部 summary chip + 字段网格 (病人信息) + 段落卡片 (病理所见) + 免疫组化 chips
function ParsedView({ detailId, files, metadata }) {
  const metaFiles = (metadata && metadata._attached_files_meta) || [];
  const showFiles =
    metaFiles.length > 0
      ? metaFiles
      : (Array.isArray(files) ? files : []).map((f) =>
          typeof f === "object"
            ? f
            : { file_id: f, file_name: `附件 ${f.slice(0, 8)}` },
        );
  const firstDone = showFiles.find(
    (f) => (f.ocr_status || "").toLowerCase() === "done" && (f.file_id || f.id),
  );
  const fid = firstDone?.file_id || firstDone?.id;
  const [parsed, setParsed] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState("");

  React.useEffect(() => {
    if (!fid) return;
    let alive = true;
    setLoading(true);
    setErr("");
    (async () => {
      try {
        // 拿当前 user_id (从 localStorage / AuthContext)
        let uid = null;
        try {
          const u = JSON.parse(localStorage.getItem("user") || "{}");
          uid = u.user_id || u.id || u.sub || null;
        } catch {}
        if (!uid) {
          // 从 detail metadata 拾取 (如果有 user_id)
          uid = metadata?.user_id || null;
        }
        if (!uid) {
          uid = "user_4e3ef0b3f49d8d4433e0b4420a3bae2a"; // fallback (与 DB 同步)
        }
        const r = await getParsedOcr(fid, uid);
        if (alive) setParsed(r.parsed);
      } catch (e) {
        if (alive) setErr(e?.message || "解析失败");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [fid, detailId]);

  if (!fid) {
    return (
      <Box sx={{ py: 6, textAlign: "center" }}>
        <Description sx={{ fontSize: 48, color: "text.disabled" }} />
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          本档案没有可识别的图片附件
        </Typography>
      </Box>
    );
  }
  if (loading) {
    return (
      <Stack alignItems="center" spacing={1} sx={{ py: 6 }}>
        <CircularProgress size={32} />
        <Typography variant="body2" color="text.secondary">
          正在读取图片中的文字…
        </Typography>
      </Stack>
    );
  }
  if (err) {
    return (
      <Alert severity="error" sx={{ m: 1 }}>
        {err}
      </Alert>
    );
  }
  if (!parsed || parsed.fields.length === 0) {
    return (
      <Alert severity="info" sx={{ m: 1 }}>
        图片内容还在识别中, 识别完成后会自动显示
      </Alert>
    );
  }

  const fields = parsed.fields || [];
  const sections = parsed.sections || [];
  const summary = parsed.summary || "";
  const filledFields = fields.filter((f) => f.filled);
  const emptyFields = fields.filter((f) => !f.filled);

  // 醒目字段 (病人/诊断类)
  const HIGHLIGHT_KEYS = new Set([
    "姓名",
    "性别",
    "年龄",
    "床号",
    "临床诊断",
    "病理诊断",
    "报告状态",
  ]);

  return (
    <Stack spacing={2}>
      {/* 顶部: 摘要 + filename */}
      <Paper variant="outlined" sx={{ p: 1.5, borderColor: "primary.light" }}>
        <Stack direction="row" alignItems="flex-start" spacing={1}>
          <Description color="primary" />
          <Box sx={{ flex: 1 }}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block" }}
            >
              内容摘要
            </Typography>
            <Typography variant="body1" sx={{ fontWeight: 500, mt: 0.5 }}>
              {summary}
            </Typography>
          </Box>
        </Stack>
      </Paper>

      {/* 病人字段 (4-col grid) */}
      {filledFields.length > 0 && (
        <Paper variant="outlined" sx={{ p: 1.5 }}>
          <Typography
            variant="subtitle2"
            sx={{ mb: 1.5, color: "primary.main" }}
          >
            📋 病人信息
          </Typography>
          <Grid container spacing={1.5}>
            {filledFields.map((f) => {
              const isHighlight = HIGHLIGHT_KEYS.has(f.key);
              return (
                <Grid
                  item
                  xs={12}
                  sm={isHighlight ? 12 : 6}
                  md={isHighlight ? 12 : 4}
                  key={f.key}
                >
                  <Paper
                    sx={{
                      p: 1,
                      bgcolor: isHighlight ? "primary.50" : "grey.50",
                      border: isHighlight
                        ? "1px solid"
                        : "1px solid transparent",
                      borderColor: isHighlight
                        ? "primary.light"
                        : "transparent",
                    }}
                  >
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ display: "block" }}
                    >
                      {f.key}
                    </Typography>
                    <Typography
                      variant={isHighlight ? "h6" : "body2"}
                      sx={{
                        fontWeight: isHighlight ? 600 : 400,
                        wordBreak: "break-all",
                        color: isHighlight ? "primary.dark" : "text.primary",
                      }}
                    >
                      {f.value}
                    </Typography>
                  </Paper>
                </Grid>
              );
            })}
          </Grid>
        </Paper>
      )}

      {/* 段落卡片 */}
      {sections.length > 0 && (
        <Stack spacing={1.5}>
          {sections.map((s) => (
            <Paper key={s.title} variant="outlined" sx={{ p: 1.5 }}>
              <Typography
                variant="subtitle2"
                sx={{
                  mb: 1,
                  color: "secondary.main",
                  display: "flex",
                  alignItems: "center",
                  gap: 0.5,
                }}
              >
                📑 {s.title}
                {s.chips && s.chips.length > 0 && (
                  <Chip
                    label={`${s.chips.length} 项`}
                    size="small"
                    sx={{ height: 18, fontSize: "0.7rem", ml: 0.5 }}
                  />
                )}
              </Typography>
              {s.chips && s.chips.length > 0 && (
                <Stack
                  direction="row"
                  spacing={0.5}
                  sx={{
                    flexWrap: "wrap",
                    gap: 0.5,
                    mb: s.paras.length ? 1.5 : 0,
                  }}
                >
                  {s.chips.map((c, i) => {
                    const isPos = /\(\+|\(3\+|\(\+\)$/.test(c);
                    const isNeg = /\(-\)|\(-\)$/.test(c);
                    return (
                      <Chip
                        key={i}
                        label={c}
                        size="small"
                        color={isPos ? "success" : isNeg ? "error" : "default"}
                        variant={isPos || isNeg ? "filled" : "outlined"}
                        sx={{ fontFamily: "monospace", fontWeight: 600 }}
                      />
                    );
                  })}
                </Stack>
              )}
              {s.paras.length > 0 && (
                <Stack spacing={0.5}>
                  {s.paras.map((p, i) => (
                    <Typography
                      key={i}
                      variant="body2"
                      color="text.primary"
                      sx={{
                        lineHeight: 1.7,
                        pl: 1,
                        borderLeft: "2px solid",
                        borderColor: "divider",
                      }}
                    >
                      {p}
                    </Typography>
                  ))}
                </Stack>
              )}
            </Paper>
          ))}
        </Stack>
      )}

      {/* 空字段 (患者没填的) — 浅显提示, 不挨打 */}
      {emptyFields.length > 0 && (
        <Paper variant="outlined" sx={{ p: 1, bgcolor: "grey.50" }}>
          <Typography variant="caption" color="text.secondary">
            报告里没填的字段 ({emptyFields.length}):&nbsp;
            {emptyFields
              .map((f) => f.key)
              .slice(0, 10)
              .join("、")}
            {emptyFields.length > 10 ? "…" : ""}
          </Typography>
        </Paper>
      )}
    </Stack>
  );
}

// AI 草稿的字段归一化。
// 原则与后端 draft_health_record 一致：抽不到就留空，**不猜日期、不编医院名**。
// 日期留空而不是填今天 —— 用户看到一个空日期会去核对，看到"今天"很可能直接提交，
// 把一份去年的报告记成今天的。
const DRAFT_RECORD_TYPES = [
  "lab_report", "imaging", "prescription", "visit", "vaccination", "other",
];
function normalizeDraft(f) {
  return {
    title: f.title || "",
    record_type: DRAFT_RECORD_TYPES.includes(f.record_type)
      ? f.record_type
      : "lab_report",
    record_date: /^\d{4}-\d{2}-\d{2}$/.test(f.record_date || "")
      ? f.record_date
      : "",
    hospital: f.hospital || "",
    doctor: f.doctor || "",
    summary: f.summary || "",
    tags: f.tags || "",
    importance: ["low", "medium", "high"].includes(f.importance)
      ? f.importance
      : "medium",
    content: f.content || "",
  };
}

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
  const [searchParams] = useSearchParams();

  // ===== AI 页面控制 =====
  // AI 说"打开上个月的血常规报告"时，后端会先让 PageRouter 跳到本页，
  // 紧接着发 openRecord。但指令到达的瞬间本组件还没挂载，records 也还没拉，
  // 所以 openRecord 只是把 id 记下来，等数据到位后再真正打开（见下面的 effect）。
  const [pendingRecordId, setPendingRecordId] = useState(null);
  const [toast, setToast] = useState("");
  // AI 填表的草稿字段。null = 没有草稿（用户自己点「新增」）。
  // 注意这里存的**只是表单值**，没有落库 —— 用户点「创建」才真正入库。
  const [aiDraft, setAiDraft] = useState(null);
  // 草稿序号。HealthRecordForm 的 initialRecord 只在 useState 初始化时读一次，
  // 不换 key 的话第二份草稿不会生效（弹窗已经开着，不会重挂载）。
  const [draftSeq, setDraftSeq] = useState(0);

  // 关弹窗时把草稿一并清掉，否则下次用户自己点「新增」会被上一次的 AI 草稿污染
  const closeEditor = useCallback(() => {
    setEditing(null);
    setAiDraft(null);
  }, []);

  usePageUpdater(PAGE_COMPONENTS.HEALTH_RECORDS, {
    [PAGE_ACTIONS.OPEN_RECORD]: (params) => {
      const rid = params?.recordId ?? params?.id;
      if (rid == null) return;
      setPendingRecordId({
        id: rid,
        title: params?.title,
        query: params?.query,
      });
    },
    [PAGE_ACTIONS.SET_FILTER]: (params) => {
      if (params?.type) setTab(params.type);
    },
    [PAGE_ACTIONS.SET_SEARCH]: (params) => {
      setSearch(params?.q || "");
    },
    // AI 口述建档：把抽取好的字段填进「新增档案」表单，交给用户核对。
    // 这里**只填不提交** —— 入库仍要用户自己点「创建」。这是整条链路安全的
    // 地方：AI 无法凭空往档案库里塞东西，最坏情况只是填错几个字段，用户改掉即可。
    [PAGE_ACTIONS.FILL_FORM]: (params) => {
      const f = normalizeDraft(params?.fields || params || {});
      setAiDraft(f);
      setDraftSeq((n) => n + 1);
      setEditing({}); // 无 id → 走 create 模式
    },
  });

  // 页面无关名，4 个页面共用（只暴露 refresh）—— 后端不必知道用户停在哪一页
  usePageUpdater(PAGE_COMPONENTS.CURRENT_PAGE, {
    [PAGE_ACTIONS.REFRESH]: () => {
      fetchRecords();
    },
  });

  // 数据到位后把待打开的记录真正打开。
  // 不依赖注册表队列的时机 —— 那条链路只负责把 id 送进来。
  useEffect(() => {
    if (!pendingRecordId || loading) return;
    const rid = String(pendingRecordId.id);
    const hit = records.find((r) => String(r.id) === rid);
    if (hit) {
      // 必须先清掉筛选，否则这条记录可能被 tab/search 过滤掉、弹窗开了但列表里没有
      setTab("all");
      setSearch("");
      setDetailTab(0);
      setDetail(hit);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } else {
      // 没找到就退化为按标题/关键字过滤，而不是让页面毫无反应
      const kw = pendingRecordId.title || pendingRecordId.query || "";
      setTab("all");
      setSearch(kw);
      setToast(kw ? `未找到该记录，已按「${kw}」过滤` : "未找到该记录");
    }
    setPendingRecordId(null);
  }, [records, loading, pendingRecordId]);

  // 看门狗：拉取卡住时别让 pendingRecordId 永远挂着
  useEffect(() => {
    if (!pendingRecordId) return undefined;
    const t = setTimeout(() => {
      setPendingRecordId(null);
      setToast("档案加载超时，未能打开该记录");
    }, 8000);
    return () => clearTimeout(t);
  }, [pendingRecordId]);

  // 整页刷新后仍能恢复：后端跳转时带的 ?openRecord=<id>
  useEffect(() => {
    const rid = searchParams.get("openRecord");
    if (rid) setPendingRecordId({ id: rid });
  }, [searchParams]);

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

  // 阶段48-22 v6: 让 '查看完整解析' 链接能把 detailTab 跳到 3 (📋 解析)
  useEffect(() => {
    const onJump = (e) => {
      if (typeof e.detail === "number") setDetailTab(e.detail);
    };
    document.addEventListener("v2-healthrecords-jump-tab", onJump);
    return () =>
      document.removeEventListener("v2-healthrecords-jump-tab", onJump);
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
        setInfo(`识别完成: ${okCount}/${totalCount} 个附件识别成功`);
      } else {
        setInfo(`${totalCount} 个附件都没有识别到文字, 检查图片是否清楚`);
      }
    } catch (e) {
      setError(e?.message || "识别失败");
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

        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr 1fr", sm: "repeat(5, 1fr)" },
            gap: 1.5,
            mb: 2,
          }}
        >
          {[
            { label: "诊断", value: stats.diagnosis, color: "#1565C0" },
            { label: "检查", value: stats.exam, color: "#00897B" },
            { label: "报告", value: stats.report, color: "#7B1FA2" },
            { label: "过敏", value: stats.allergy, color: "#C62828" },
            { label: "档案总数", value: stats.total, color: "#5A6776" },
          ].map((s) => (
            <Paper
              key={s.label}
              variant="outlined"
              sx={{
                p: 1.5,
                textAlign: "center",
                borderTop: `3px solid ${s.color}`,
                minHeight: 76,
                display: "flex",
                flexDirection: "column",
                justifyContent: "center",
              }}
            >
              <Typography variant="h5" sx={{ fontWeight: 700 }}>
                {s.value}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {s.label}
              </Typography>
            </Paper>
          ))}
        </Box>

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
                  {/* 阶段48-22 v6: 图片内容识别中显示旋转标识 (在 avatar 右侧) */}
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
                      {r.date ? `${r.date}` : ""}
                      {r.files.length > 0 ? ` · ${r.files.length} 个附件` : ""}
                    </Typography>
                    {/* 阶段48-22 v6: 列表卡片预览 — 用户视角, 优先命中临床诊断/病理诊断 一行
                        之前直接前 140 字是 "病理号: 病人编号: 报告状态: ..." 一堆冒号, 用户读不出主次. */}
                    {(() => {
                      const meta =
                        (r.metadata && r.metadata._attached_files_meta) || [];
                      const firstDone = meta.find(
                        (f) =>
                          (f.ocr_status || "").toLowerCase() === "done" &&
                          (f.ocr_text || "").length > 0,
                      );
                      const extractPreview = (raw) => {
                        if (!raw) return "";
                        // 优先从已知 KV 中抓最有用的那行
                        const PRIORITY_KEYS = [
                          "临床诊断",
                          "病理诊断",
                          "肉眼所见",
                          "镜下所见",
                          "诊断",
                        ];
                        for (const k of PRIORITY_KEYS) {
                          const m = new RegExp(
                            `${k}\\s*[:：]\\s*([^\\n]{2,140})`,
                          ).exec(raw);
                          if (m && m[1].trim().length > 0) {
                            return m[1].trim();
                          }
                        }
                        // 次选: 跳过空值 KV 行, 落到第一个有 value 的 KV
                        const lineWithValue = raw
                          .split(/\n/)
                          .map((l) => l.trim())
                          .find(
                            (l) =>
                              l.includes(":") &&
                              /\S/.test(l.split(":")[1] || ""),
                          );
                        if (lineWithValue) {
                          const idx = lineWithValue.indexOf(":");
                          const v = lineWithValue
                            .slice(idx + 1)
                            .replace(/\s+/g, " ")
                            .trim();
                          if (v.length > 2) return v.slice(0, 120);
                        }
                        // 后备: raw 前 140
                        return raw.replace(/\s+/g, " ").trim().slice(0, 140);
                      };
                      let title = "";
                      let raw = "";
                      if (firstDone) {
                        title = firstDone.file_name || "";
                        raw = firstDone.ocr_text || "";
                      } else if (r.content) {
                        // content 格式: "## filename\n\n{OCR 文本}" — 跳过头部 file 标记
                        raw = r.content.replace(/^## [^\n]+\n+/, "");
                      }
                      const preview = extractPreview(raw);
                      if (!preview) return null;
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
                          title={title}
                        >
                          {preview}
                        </Typography>
                      );
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
        scroll="paper"
        PaperProps={{
          sx: {
            borderRadius: 2,
            maxHeight: "90vh", // 弹窗占屏幕 90%, 留 10% 给遮罩
            display: "flex",
            flexDirection: "column",
          },
        }}
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
                    sx={{
                      minHeight: 36,
                      "& .MuiTab-root": {
                        minHeight: 36,
                        padding: "6px 16px",
                        fontSize: "0.875rem",
                      },
                    }}
                  >
                    {/* 阶段48-22 v6: 用户视角 — 不暴露 OCR/解析术语, 简化到 3 个 tab */}
                    <Tab label="基础信息" />
                    <Tab label={`正文${detail.content ? "" : " (空)"}`} />
                    <Tab label={`附件${fileCount ? ` (${fileCount})` : ""}`} />
                  </Tabs>
                </Box>

                <DialogContent
                  dividers
                  sx={{ flex: 1, overflowY: "auto", p: 3 }}
                >
                  {/* Tab 0: 基础信息 */}
                  {detailTab === 0 && (
                    <Stack spacing={2}>
                      {/* 阶段48-22 v6: 顶部 OCR 智能摘要 — 让用户进弹窗第一眼看到内容
                          即使是用户手输入 content, 也保留用户源作 '您填写' 卡片, 不被覆盖. */}
                      <OcrSummaryBlock
                        detailId={detail.id}
                        files={detail.files || []}
                        metadata={detail.metadata}
                        userContent={detail.content}
                      />

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

                      {/* 阶段48-22 v6: 底部操作提示 — 替代老版本"切到 OCR tab"的过时引导
                         基础页顶部 OcrSummaryBlock 已经包含 OCR 摘要 + 用户填的合并, 这里只显示
                         跟 content 相关的小提示 + 操作按钮 (跳转/编辑). */}
                      <Paper
                        variant="outlined"
                        sx={{
                          p: 1,
                          display: "flex",
                          alignItems: "center",
                          gap: 1,
                          bgcolor: detail.content ? "grey.50" : "warning.50",
                          borderColor: detail.content
                            ? "divider"
                            : "warning.light",
                        }}
                      >
                        {detail.content ? (
                          <Description fontSize="small" color="action" />
                        ) : (
                          <InfoOutlined fontSize="small" color="warning" />
                        )}
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ flex: 1 }}
                        >
                          {detail.content
                            ? `已存档 ${detail.content.length} 字 (顶部和正文 Tab 都能看到内容)`
                            : "没有内容 — 可点 '编辑' 手动填写, 或上传图片"}
                        </Typography>
                        <Button
                          size="small"
                          variant="text"
                          onClick={() => setDetailTab(1)}
                          sx={{ minWidth: 0, fontSize: "0.7rem" }}
                        >
                          查看正文
                        </Button>
                      </Paper>
                    </Stack>
                  )}

                  {/* Tab 1: 正文 — 用户视角: 显示结构化医学报告卡片, 而不是 859 字的纯文本
                       1) 若有图片附件 → 调 /parsed 渲染 ParsedView (字段网格+段落卡片+免疫组化 chips)
                       2) 若只有用户手填 content → 渲染 content 文本
                       3) 都没有 → 显示占位 */}
                  {detailTab === 1 && (
                    <Box>
                      {/* A. 优先: 显示结构化的图片识别 (如果有任何 done 的图片附件) */}
                      {(() => {
                        const metaFiles =
                          (detail.metadata &&
                            detail.metadata._attached_files_meta) ||
                          [];
                        const firstDone = metaFiles.find(
                          (f) =>
                            (f.ocr_status || "").toLowerCase() === "done" &&
                            (f.file_id || f.id),
                        );
                        if (firstDone) {
                          return (
                            <ParsedView
                              detailId={detail.id}
                              files={detail.files || []}
                              metadata={detail.metadata}
                            />
                          );
                        }
                        // B. 次选: 用户手填 content
                        if (detail.content) {
                          return (
                            <Typography
                              variant="body1"
                              sx={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}
                            >
                              {detail.content}
                            </Typography>
                          );
                        }
                        // C. 占位
                        return (
                          <Stack alignItems="center" sx={{ py: 6 }} spacing={1}>
                            <Description
                              sx={{ fontSize: 48, color: "text.disabled" }}
                            />
                            <Typography variant="body2" color="text.secondary">
                              暂无正文
                            </Typography>
                            <Typography variant="caption" color="text.disabled">
                              上传附件后, 图片内容会自动出现在这里
                            </Typography>
                          </Stack>
                        );
                      })()}
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
                  {/* Tab 3: 📋 智能解析 — 阶段48-22 v6
                       调 /v2/upload/files/{id}/parsed 拿结构化 {fields[], sections[], summary}
                       按医学报告样式展示: 病人信息网格 + 临床诊断强调 + 病理所见段 + 免疫组化 chips */}
                  {/* 阶段48-22 v6: detailTab 3 (📋 解析) 和 4 (OCR 原文) 已隐藏 — 用户不应看到
                       OCR 概念. OCR 文本在上传时已自动合入 detail.content (用户进正文 tab 就看到).
                       解析字段 (姓名/年龄/床号/诊断) 在基础信息 tab 顶部 OcrSummaryBlock 里直接展示. */}
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
        onClose={closeEditor}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{editing?.id ? "编辑档案" : "新增档案"}</DialogTitle>
        <DialogContent dividers>
          {/* AI 草稿的提示条。刻意不用 autoHide —— 用户必须意识到"这是 AI 填的、
              还没入库"，点「创建」才是确认。 */}
          {!editing?.id && aiDraft && (
            <Alert severity="info" sx={{ mb: 2 }}>
              AI 已根据你的描述填好下面的字段，请核对后点「创建」入库。
              没有把握的字段 AI 会留空，需要你补充。
            </Alert>
          )}
          {/* 注: 阶段48-22 v3+: 新建 / 编辑 都用 HealthRecordForm (含附件编辑能力) */}
          <HealthRecordForm
            // 换草稿要换 key：initialRecord 只在挂载时读一次，
            // 否则第二份草稿会在已经开着的弹窗里被忽略。
            key={editing?.id || `draft-${draftSeq}`}
            mode={editing?.id ? "edit" : "create"}
            kind="health_record"
            userId={currentUserId}
            recordId={editing?.id}
            initialRecord={editing?.id ? editing : aiDraft}
            onCreated={() => {
              closeEditor();
              fetchRecords();
            }}
            onUpdated={() => {
              closeEditor();
              fetchRecords();
              setDetail(null);
            }}
            onCancel={closeEditor}
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

      {/* AI 跳转失败时的反馈：没找到记录 / 加载超时 */}
      <Snackbar
        open={!!toast}
        autoHideDuration={5000}
        onClose={() => setToast("")}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="warning" onClose={() => setToast("")}>
          {toast}
        </Alert>
      </Snackbar>
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
