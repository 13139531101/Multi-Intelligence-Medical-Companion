import React, { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import {
  Activity,
  Server,
  Database,
  Brain,
  HardDrive,
  RefreshCw,
  Trash2,
  Search,
  CheckCircle,
  AlertCircle,
  Wrench,
  Plug,
  Cpu,
} from "lucide-react";
import { LineChart, Line, ResponsiveContainer } from "recharts";
import ToolsPanel from "./components/ToolsPanel";
import SkillsPanel from "./components/SkillsPanel";
import MCPPanel from "./components/MCPPanel";

// API Base URL (proxied via Vite in dev, Nginx in prod)
const API_BASE = "/api";

const DashboardCard = ({ title, children, icon: Icon, className = "" }) => (
  <div className={`glass-panel p-4 rounded-lg flex flex-col ${className}`}>
    <div className="flex items-center justify-between mb-4 border-b border-cyan-900/50 pb-2">
      <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm flex items-center gap-2">
        {Icon && <Icon size={16} />}
        {title}
      </h3>
      <div className="h-2 w-2 bg-cyan-500 rounded-full animate-pulse"></div>
    </div>
    <div className="flex-1 overflow-auto custom-scrollbar">{children}</div>
  </div>
);

const StatRow = ({ label, value, status = "neutral" }) => {
  let color = "text-cyan-100";
  if (status === "success") color = "text-green-400";
  if (status === "error") color = "text-red-400";
  if (status === "warning") color = "text-yellow-400";

  return (
    <div className="flex justify-between items-center py-1 border-b border-cyan-900/30 last:border-0 text-xs font-mono">
      <span className="text-cyan-600 uppercase">{label}</span>
      <span className={`font-bold ${color}`}>{value}</span>
    </div>
  );
};

function App() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [adminToken, setAdminToken] = useState(
    localStorage.getItem("adminToken") || "",
  );
  const [activeTab, setActiveTab] = useState("dashboard"); // dashboard | tools | skills | mcp

  // RAG Search State
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [kbGlobal, setKbGlobal] = useState(true);
  const [kbUserId, setKbUserId] = useState("");
  const [kbSelected, setKbSelected] = useState(null);
  const [kbChunks, setKbChunks] = useState(null);
  const [kbChunksLoading, setKbChunksLoading] = useState(false);

  const [ingestDocId, setIngestDocId] = useState("");
  const [ingestTitle, setIngestTitle] = useState("");
  const [ingestDocType, setIngestDocType] = useState("medical_kb");
  const [ingestContent, setIngestContent] = useState("");
  const [ingestFiles, setIngestFiles] = useState([]);
  const [ingestFileKey, setIngestFileKey] = useState(0);
  const [ingestResult, setIngestResult] = useState(null);
  const [ingestRunning, setIngestRunning] = useState(false);
  const [ingestRunningText, setIngestRunningText] = useState("");

  const [apiImportUrl, setApiImportUrl] = useState("");
  const [apiImportMethod, setApiImportMethod] = useState("GET");
  const [apiImportItemsPath, setApiImportItemsPath] = useState("");
  const [apiImportDocIdField, setApiImportDocIdField] = useState("");
  const [apiImportTitleField, setApiImportTitleField] = useState("title");
  const [apiImportContentField, setApiImportContentField] = useState("content");
  const [apiImportResult, setApiImportResult] = useState(null);

  const [backfillUserId, setBackfillUserId] = useState("");
  const [backfillSourceTypes, setBackfillSourceTypes] = useState(
    "health_records,visit_summaries",
  );
  const [backfillDryRun, setBackfillDryRun] = useState(false);
  const [backfillResult, setBackfillResult] = useState(null);

  // Mock Chart Data
  const [chartData] = useState([
    { name: "00:00", cpu: 10, mem: 20 },
    { name: "04:00", cpu: 15, mem: 22 },
    { name: "08:00", cpu: 45, mem: 35 },
    { name: "12:00", cpu: 30, mem: 40 },
    { name: "16:00", cpu: 60, mem: 45 },
    { name: "20:00", cpu: 25, mem: 30 },
  ]);

  const headers = adminToken ? { "X-Admin-Token": adminToken } : {};

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/admin/monitor/summary`, {
        headers: adminToken ? { "X-Admin-Token": adminToken } : {},
      });
      setSummary(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [adminToken]);

  useEffect(() => {
    fetchSummary();
    const interval = setInterval(fetchSummary, 30000); // Auto refresh every 30s
    return () => clearInterval(interval);
  }, [fetchSummary]);

  const handleSearch = useCallback(
    async ({ silent = false } = {}) => {
      if (!adminToken) {
        if (!silent) alert("请先填写管理员令牌");
        return;
      }
      if (!kbGlobal && !(kbUserId || "").trim()) {
        if (!silent) alert("global_kb=false 时必须填写目标用户ID");
        return;
      }
      try {
        const res = await axios.post(
          `${API_BASE}/admin/rag/docs`,
          {
            q: searchQuery,
            limit: 50,
            user_id: kbGlobal ? "__global__" : (kbUserId || "").trim(),
            source_type: "medical_kb",
          },
          { headers: { "X-Admin-Token": adminToken } },
        );
        setSearchResults(res.data.items || []);
      } catch (err) {
        if (!silent) alert("查询失败：" + err.message);
      }
    },
    [adminToken, kbGlobal, kbUserId, searchQuery],
  );

  const didAutoListRef = useRef(false);
  useEffect(() => {
    if (didAutoListRef.current) return;
    if (!adminToken) return;
    if (!kbGlobal && !(kbUserId || "").trim()) return;
    didAutoListRef.current = true;
    handleSearch({ silent: true });
  }, [adminToken, kbGlobal, kbUserId, handleSearch]);

  const handleDelete = async (docId) => {
    if (!confirm("确认删除这条文档吗？")) return;
    try {
      const qs = new URLSearchParams();
      qs.set("global_kb", kbGlobal ? "true" : "false");
      if (!kbGlobal) qs.set("user_id", kbUserId);
      await axios.delete(
        `${API_BASE}/admin/medical-kb/docs/${docId}?${qs.toString()}`,
        { headers },
      );
      handleSearch(); // Refresh list
    } catch (err) {
      alert("删除失败：" + err.message);
    }
  };

  const handleImport = async () => {
    const title = (ingestTitle || "").trim();
    const content = (ingestContent || "").trim();
    const docType = (ingestDocType || "").trim() || "medical_kb";
    const docId = (ingestDocId || "").trim();
    const files = Array.isArray(ingestFiles) ? ingestFiles : [];
    const hasFiles = files.length > 0;

    if (!kbGlobal && !(kbUserId || "").trim()) {
      alert("global_kb=false 时必须填写目标用户ID");
      return;
    }

    try {
      setIngestResult(null);
      setIngestRunning(false);
      setIngestRunningText("");
      let res;
      if (hasFiles) {
        setIngestRunning(true);
        setIngestRunningText(`后台入库中(0/${files.length})...`);
        const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
        const pollJob = async (jobId) => {
          const maxWaitMs = 10 * 60 * 1000;
          const maxAttempts = Math.max(1, Math.ceil(maxWaitMs / 1000));
          for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
            const jr = await axios.get(
              `${API_BASE}/admin/medical-kb/jobs/${jobId}`,
              { headers },
            );
            const job = jr?.data?.job;
            if (!job) throw new Error("后台任务状态返回为空");
            if (job.status === "succeeded" || job.status === "failed")
              return job;
            await sleep(1000);
          }
          throw new Error("后台任务超时");
        };
        const results = [];
        for (let i = 0; i < files.length; i += 1) {
          setIngestRunningText(`后台入库中(${i + 1}/${files.length})...`);
          const f = files[i];
          const fd = new FormData();
          fd.append("file", f);
          fd.append("global_kb", kbGlobal ? "true" : "false");
          if (!kbGlobal) fd.append("user_id", (kbUserId || "").trim());
          if (docId) fd.append("doc_id", docId);
          if (docType) fd.append("doc_type", docType);
          if (title && files.length === 1) fd.append("title", title);
          try {
            const r = await axios.post(
              `${API_BASE}/admin/medical-kb/upload`,
              fd,
              { headers },
            );
            const jobId = r?.data?.job_id || r?.data?.jobId;
            if (jobId) {
              const idx = results.length;
              results.push({
                success: true,
                filename: f.name,
                job_id: jobId,
                status: "queued",
              });
              const job = await pollJob(jobId);
              if (job.status === "succeeded") {
                results[idx] = {
                  success: true,
                  filename: f.name,
                  job_id: jobId,
                  status: job.status,
                  result: job.result,
                };
              } else {
                const err =
                  job?.error?.detail ||
                  job?.error?.message ||
                  JSON.stringify(job?.error || {});
                results[idx] = {
                  success: false,
                  filename: f.name,
                  job_id: jobId,
                  status: job.status,
                  error: err,
                };
              }
            } else {
              results.push({ success: true, filename: f.name, result: r.data });
            }
          } catch (e) {
            results.push({
              success: false,
              filename: f.name,
              error: e?.message || String(e),
            });
          }
        }
        res = { data: { success: true, files: results } };
      } else {
        if (!title || !content) {
          alert("标题/正文 不能为空（或选择文件上传）");
          return;
        }
        res = await axios.post(
          `${API_BASE}/admin/medical-kb/import`,
          {
            global_kb: kbGlobal,
            user_id: kbGlobal ? undefined : (kbUserId || "").trim(),
            docs: [
              {
                doc_id: docId || undefined,
                doc_type: docType,
                title,
                content,
              },
            ],
          },
          { headers },
        );
      }
      setIngestResult(res.data);
      setIngestDocId("");
      setIngestTitle("");
      setIngestContent("");
      setIngestFiles([]);
      setIngestFileKey((x) => x + 1);
      handleSearch();
    } catch (err) {
      alert("入库失败：" + err.message);
    } finally {
      setIngestRunning(false);
      setIngestRunningText("");
    }
  };

  const handleApiImport = async () => {
    const url = (apiImportUrl || "").trim();
    if (!url) {
      alert("必须填写 API URL");
      return;
    }
    if (!kbGlobal && !(kbUserId || "").trim()) {
      alert("global_kb=false 时必须填写目标用户ID");
      return;
    }

    try {
      setApiImportResult(null);
      const res = await axios.post(
        `${API_BASE}/admin/medical-kb/import-from-api`,
        {
          global_kb: kbGlobal,
          user_id: kbGlobal ? undefined : (kbUserId || "").trim(),
          url,
          method: (apiImportMethod || "GET").trim().toUpperCase(),
          items_path: (apiImportItemsPath || "").trim() || undefined,
          doc_id_field: (apiImportDocIdField || "").trim() || undefined,
          title_field: (apiImportTitleField || "").trim() || undefined,
          content_field: (apiImportContentField || "").trim() || undefined,
          max_items: 100,
          doc_type: (ingestDocType || "").trim() || "medical_kb",
        },
        { headers },
      );
      setApiImportResult(res.data);
      handleSearch();
    } catch (err) {
      alert("一键入库失败：" + err.message);
    }
  };

  const handleBackfill = async () => {
    const uid = (backfillUserId || "").trim();
    if (!uid) {
      alert("必须填写 user_id");
      return;
    }
    const st = (backfillSourceTypes || "")
      .split(/[,\s]+/g)
      .map((x) => x.trim())
      .filter(Boolean);
    if (st.length === 0) {
      alert("必须填写 source_types");
      return;
    }

    try {
      setBackfillResult(null);
      const res = await axios.post(
        `${API_BASE}/admin/rag/backfill`,
        {
          user_id: uid,
          source_types: st,
          dry_run: backfillDryRun,
          limit: 200,
          offset: 0,
        },
        { headers },
      );
      setBackfillResult(res.data);
    } catch (err) {
      alert("回填失败：" + err.message);
    }
  };

  const handleLoadChunks = async (doc) => {
    if (!doc) return;
    try {
      setKbSelected(doc);
      setKbChunks(null);
      setKbChunksLoading(true);
      const res = await axios.post(
        `${API_BASE}/admin/rag/chunks`,
        {
          user_id: doc.user_id,
          source_type: doc.source_type,
          source_id: doc.source_id,
          limit: 50,
          offset: 0,
        },
        { headers },
      );
      setKbChunks(res.data.items || []);
    } catch (err) {
      alert("加载分块失败：" + err.message);
    } finally {
      setKbChunksLoading(false);
    }
  };

  const handleReindexDoc = async (doc) => {
    if (!doc) return;
    try {
      const res = await axios.post(
        `${API_BASE}/admin/rag/reindex`,
        {
          user_id: doc.user_id,
          source_type: doc.source_type,
          source_id: doc.source_id,
        },
        { headers },
      );
      alert(JSON.stringify(res.data, null, 2));
      handleSearch();
    } catch (err) {
      alert("重建索引失败：" + err.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 p-6 flex flex-col gap-6 text-sm relative overflow-hidden">
      {/* Background Grid */}
      <div className="absolute inset-0 grid grid-cols-[repeat(20,minmax(0,1fr))] opacity-10 pointer-events-none z-0">
        {[...Array(400)].map((_, i) => (
          <div
            key={i}
            className="border border-cyan-900/20 aspect-square"
          ></div>
        ))}
      </div>

      {/* Header */}
      <header className="flex justify-between items-center z-10 border-b border-cyan-500/30 pb-4">
        <div className="flex items-center gap-3">
          <Activity className="text-cyan-400 animate-pulse" size={24} />
          <h1 className="text-2xl font-bold tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-600">
            PHA <span className="text-white font-mono text-lg">系统后台</span>
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <input
            type="password"
            placeholder="管理员令牌"
            value={adminToken}
            onChange={(e) => {
              setAdminToken(e.target.value);
              localStorage.setItem("adminToken", e.target.value);
            }}
            className="bg-slate-900/80 border border-cyan-800 text-cyan-100 px-3 py-1 rounded text-xs focus:outline-none focus:border-cyan-500 w-32"
          />
          <button
            onClick={fetchSummary}
            className="p-2 hover:bg-cyan-900/30 rounded-full transition-colors text-cyan-400"
          >
            <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </header>

      {/* Tabs (阶段41-3) */}
      <nav className="flex gap-2 z-10 border-b border-cyan-900/50 pb-2">
        {[
          { key: "dashboard", label: "仪表盘", icon: Activity },
          { key: "tools", label: "工具 (内置)", icon: Wrench },
          { key: "skills", label: "Skills", icon: Brain },
          { key: "mcp", label: "MCP Servers", icon: Plug },
        ].map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 rounded-t font-mono text-sm flex items-center gap-2 transition-all ${
                activeTab === tab.key
                  ? "bg-cyan-900/40 text-cyan-300 border-b-2 border-cyan-400"
                  : "text-cyan-600 hover:text-cyan-300 hover:bg-cyan-900/20"
              }`}
            >
              <Icon size={14} /> {tab.label}
            </button>
          );
        })}
      </nav>

      {/* Main Grid */}
      <main className="z-10 flex-1">
        {activeTab === "dashboard" && (
          <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {/* 原 dashboard 内容 */}
            {/* System Stats */}
            <DashboardCard
              title="系统指标"
              icon={Server}
              className="md:col-span-1 h-64 md:h-auto"
            >
              {summary?.system ? (
                <div className="space-y-3">
                  <StatRow
                    label="CPU"
                    value={`${summary.system.cpu_percent}%`}
                    status={
                      summary.system.cpu_percent > 80 ? "error" : "success"
                    }
                  />
                  <StatRow
                    label="内存"
                    value={`${summary.system.mem_percent}%`}
                  />
                  <StatRow
                    label="磁盘"
                    value={`${summary.system.disk_percent}%`}
                  />
                  <div className="mt-4 pt-4 border-t border-cyan-900/30">
                    <div className="text-xs text-cyan-600 mb-1">实时负载</div>
                    <div className="h-24 w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                          <Line
                            type="monotone"
                            dataKey="cpu"
                            stroke="#06b6d4"
                            strokeWidth={2}
                            dot={false}
                          />
                          <Line
                            type="monotone"
                            dataKey="mem"
                            stroke="#8b5cf6"
                            strokeWidth={2}
                            dot={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-10 text-slate-500">暂无数据</div>
              )}
            </DashboardCard>

            {/* Database & Embedding Status */}
            <DashboardCard
              title="核心服务"
              icon={Database}
              className="md:col-span-1 h-64 md:h-auto"
            >
              <div className="space-y-4">
                <div className="glass-panel p-3 rounded bg-slate-900/80">
                  <div className="flex items-center gap-2 mb-2">
                    <Database size={14} className="text-cyan-400" />
                    <span className="font-bold text-cyan-100">PostgreSQL</span>
                  </div>
                  <div className="flex items-center gap-2 text-xs">
                    {summary?.db?.ok ? (
                      <CheckCircle size={12} className="text-green-400" />
                    ) : (
                      <AlertCircle size={12} className="text-red-400" />
                    )}
                    <span
                      className={
                        summary?.db?.ok ? "text-green-400" : "text-red-400"
                      }
                    >
                      {summary?.db?.ok ? "在线" : "连接失败"}
                    </span>
                  </div>
                  {summary?.db?.error && (
                    <div className="text-[10px] text-red-400/80 mt-1 break-all">
                      {summary.db.error}
                    </div>
                  )}
                </div>

                <div className="glass-panel p-3 rounded bg-slate-900/80">
                  <div className="flex items-center gap-2 mb-2">
                    <Brain size={14} className="text-purple-400" />
                    <span className="font-bold text-purple-100">向量模型</span>
                  </div>
                  <StatRow
                    label="模型"
                    value={summary?.embedding?.model || "未知"}
                  />
                  <StatRow
                    label="维度"
                    value={summary?.embedding?.dimension || "未知"}
                  />
                  <div className="flex items-center gap-2 text-xs mt-2">
                    {summary?.embedding?.available ? (
                      <CheckCircle size={12} className="text-green-400" />
                    ) : (
                      <AlertCircle size={12} className="text-yellow-400" />
                    )}
                    <span
                      className={
                        summary?.embedding?.available
                          ? "text-green-400"
                          : "text-yellow-400"
                      }
                    >
                      {summary?.embedding?.available ? "可用" : "不可用"}
                    </span>
                  </div>
                </div>
              </div>
            </DashboardCard>

            {/* RAG Management */}
            <DashboardCard
              title="知识库"
              icon={HardDrive}
              className="md:col-span-2 md:row-span-2"
            >
              <div className="glass-panel p-3 rounded bg-slate-900/80 mb-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-xs text-cyan-600 uppercase font-mono">
                    RAG 配置
                  </div>
                  <label className="flex items-center gap-2 text-xs text-cyan-200 font-mono">
                    <input
                      type="checkbox"
                      checked={kbGlobal}
                      onChange={(e) => setKbGlobal(e.target.checked)}
                    />
                    全局知识库
                  </label>
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <StatRow
                    label="分块大小"
                    value={summary?.rag?.chunk_size ?? "未知"}
                  />
                  <StatRow
                    label="分块重叠"
                    value={summary?.rag?.chunk_overlap ?? "未知"}
                  />
                  <StatRow
                    label="最大分块数"
                    value={summary?.rag?.max_chunks ?? 0}
                  />
                  <StatRow
                    label="向量维度"
                    value={summary?.rag?.vector_dim ?? "未知"}
                  />
                </div>
                {!kbGlobal && (
                  <div className="mt-3 flex gap-2">
                    <input
                      type="text"
                      value={kbUserId}
                      onChange={(e) => setKbUserId(e.target.value)}
                      placeholder="目标用户ID"
                      className="flex-1 bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                    />
                  </div>
                )}
              </div>

              <div className="glass-panel p-3 rounded bg-slate-900/80 mb-4">
                <div className="text-xs text-cyan-600 uppercase font-mono mb-2">
                  医疗文档入库
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <input
                    type="text"
                    value={ingestDocId}
                    onChange={(e) => setIngestDocId(e.target.value)}
                    placeholder="doc_id（可选，留空自动生成）"
                    className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                  />
                  <input
                    type="text"
                    value={ingestDocType}
                    onChange={(e) => setIngestDocType(e.target.value)}
                    placeholder="doc_type（如 guideline/drug_label）"
                    className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                  />
                  <input
                    type="text"
                    value={ingestTitle}
                    onChange={(e) => setIngestTitle(e.target.value)}
                    placeholder="标题"
                    className="md:col-span-2 bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50"
                  />
                  <textarea
                    value={ingestContent}
                    onChange={(e) => setIngestContent(e.target.value)}
                    placeholder="正文"
                    className="md:col-span-2 bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 min-h-[120px] font-mono text-xs"
                  />
                  <div className="md:col-span-2 flex items-center gap-2">
                    <input
                      key={ingestFileKey}
                      type="file"
                      accept=".pdf,.docx,.txt,.md"
                      multiple
                      onChange={(e) =>
                        setIngestFiles(Array.from(e.target.files || []))
                      }
                      className="flex-1 text-xs text-slate-300 file:bg-slate-800 file:text-cyan-100 file:border-0 file:rounded file:px-3 file:py-2"
                    />
                    {ingestFiles.length > 0 && (
                      <span className="text-[10px] text-slate-400 break-all max-w-[220px]">
                        已选择 {ingestFiles.length} 个文件
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex justify-end mt-2">
                  <button
                    onClick={handleImport}
                    disabled={ingestRunning}
                    className="bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 disabled:cursor-not-allowed text-white px-4 py-2 rounded font-bold tracking-wide transition-colors"
                  >
                    {ingestRunning ? "入库中..." : "入库"}
                  </button>
                </div>
                {ingestRunning && (
                  <div className="text-[10px] text-slate-400 mt-2 font-mono">
                    {ingestRunningText || "后台入库中..."}
                  </div>
                )}
                {ingestResult && (
                  <pre className="text-[10px] text-slate-400 mt-2 whitespace-pre-wrap break-words">
                    {JSON.stringify(ingestResult, null, 2)}
                  </pre>
                )}
              </div>

              <div className="glass-panel p-3 rounded bg-slate-900/80 mb-4">
                <div className="text-xs text-cyan-600 uppercase font-mono mb-2">
                  一键入库（从 API 拉取）
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <input
                    type="text"
                    value={apiImportUrl}
                    onChange={(e) => setApiImportUrl(e.target.value)}
                    placeholder="API URL（返回 JSON）"
                    className="md:col-span-2 bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                  />
                  <select
                    value={apiImportMethod}
                    onChange={(e) => setApiImportMethod(e.target.value)}
                    className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                  >
                    <option value="GET">GET</option>
                    <option value="POST">POST</option>
                  </select>
                  <input
                    type="text"
                    value={apiImportItemsPath}
                    onChange={(e) => setApiImportItemsPath(e.target.value)}
                    placeholder="items_path（可选，如 data.items）"
                    className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                  />
                  <input
                    type="text"
                    value={apiImportDocIdField}
                    onChange={(e) => setApiImportDocIdField(e.target.value)}
                    placeholder="doc_id 字段（可选）"
                    className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                  />
                  <input
                    type="text"
                    value={apiImportTitleField}
                    onChange={(e) => setApiImportTitleField(e.target.value)}
                    placeholder="title 字段（可选）"
                    className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                  />
                  <input
                    type="text"
                    value={apiImportContentField}
                    onChange={(e) => setApiImportContentField(e.target.value)}
                    placeholder="content 字段（可选）"
                    className="md:col-span-2 bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                  />
                </div>
                <div className="flex justify-end mt-2">
                  <button
                    onClick={handleApiImport}
                    className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded font-bold tracking-wide transition-colors"
                  >
                    一键入库
                  </button>
                </div>
                {apiImportResult && (
                  <pre className="text-[10px] text-slate-400 mt-2 whitespace-pre-wrap break-words">
                    {JSON.stringify(apiImportResult, null, 2)}
                  </pre>
                )}
              </div>

              <div className="glass-panel p-3 rounded bg-slate-900/80 mb-4">
                <div className="text-xs text-cyan-600 uppercase font-mono mb-2">
                  用户数据回填
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  <input
                    type="text"
                    value={backfillUserId}
                    onChange={(e) => setBackfillUserId(e.target.value)}
                    placeholder="user_id（目标用户）"
                    className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                  />
                  <input
                    type="text"
                    value={backfillSourceTypes}
                    onChange={(e) => setBackfillSourceTypes(e.target.value)}
                    placeholder="source_types（逗号分隔）"
                    className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50 font-mono text-xs"
                  />
                  <label className="flex items-center gap-2 text-xs text-cyan-200 font-mono">
                    <input
                      type="checkbox"
                      checked={backfillDryRun}
                      onChange={(e) => setBackfillDryRun(e.target.checked)}
                    />
                    仅预演
                  </label>
                  <div className="flex justify-end">
                    <button
                      onClick={handleBackfill}
                      className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded font-bold tracking-wide transition-colors"
                    >
                      回填
                    </button>
                  </div>
                </div>
                {backfillResult && (
                  <pre className="text-[10px] text-slate-400 mt-2 whitespace-pre-wrap break-words">
                    {JSON.stringify(backfillResult, null, 2)}
                  </pre>
                )}
              </div>

              <div className="flex gap-2 mb-4">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                    placeholder="搜索医疗文档（可选）…"
                    className="w-full bg-slate-900 border border-cyan-800 rounded px-3 py-2 pl-9 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50"
                  />
                  <Search
                    size={14}
                    className="absolute left-3 top-3 text-cyan-600"
                  />
                </div>
                <button
                  onClick={handleSearch}
                  className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded font-bold tracking-wide transition-colors"
                >
                  列表
                </button>
              </div>

              <div className="space-y-2 overflow-y-auto max-h-[400px] pr-2 custom-scrollbar">
                {searchResults.length === 0 ? (
                  <div className="text-center py-10 text-slate-600 border border-dashed border-slate-800 rounded">
                    暂无文档
                  </div>
                ) : (
                  searchResults.map((doc) => (
                    <div
                      key={doc.source_id}
                      className="group flex items-start justify-between p-3 bg-slate-900/40 border border-slate-800 hover:border-cyan-500/50 rounded transition-all"
                    >
                      <div>
                        <div className="font-bold text-cyan-200 mb-1">
                          {doc.title || doc.source_id}
                        </div>
                        <div className="text-xs text-slate-400 font-mono">
                          ID: {doc.source_id} | 用户: {doc.user_id} | 类型:{" "}
                          {doc.record_type || doc.source_type} | 分块:{" "}
                          {doc.chunk_count}
                        </div>
                      </div>
                      <div className="opacity-0 group-hover:opacity-100 flex items-center gap-1 transition-all">
                        <button
                          onClick={() => handleLoadChunks(doc)}
                          className="p-2 text-cyan-300 hover:bg-cyan-900/20 rounded transition-all text-xs font-mono"
                        >
                          分块
                        </button>
                        <button
                          onClick={() => handleReindexDoc(doc)}
                          className="p-2 text-purple-300 hover:bg-purple-900/20 rounded transition-all text-xs font-mono"
                        >
                          重建
                        </button>
                        <button
                          onClick={() => handleDelete(doc.source_id)}
                          className="p-2 text-red-400 hover:bg-red-900/20 rounded transition-all"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>

              {kbSelected && (
                <div className="glass-panel p-3 rounded bg-slate-900/80 mt-4">
                  <div className="text-xs text-cyan-600 uppercase font-mono mb-2">
                    分块：{kbSelected.source_id}
                  </div>
                  {kbChunksLoading ? (
                    <div className="text-slate-500 text-xs font-mono">
                      加载中…
                    </div>
                  ) : (
                    <pre className="text-[10px] text-slate-400 whitespace-pre-wrap break-words max-h-[220px] overflow-auto custom-scrollbar">
                      {JSON.stringify(kbChunks, null, 2)}
                    </pre>
                  )}
                </div>
              )}
            </DashboardCard>

            {/* Placeholder for future widgets */}
            <DashboardCard
              title="智能体状态"
              icon={Activity}
              className="md:col-span-1 md:col-start-1 md:col-end-3 h-48"
            >
              <div className="grid grid-cols-2 gap-2 h-full">
                {["健康顾问", "用药提醒", "就诊摘要", "健康档案"].map(
                  (agent, i) => (
                    <div
                      key={i}
                      className="bg-slate-900/50 border border-slate-800 p-3 rounded flex items-center justify-between"
                    >
                      <span className="text-xs font-mono text-cyan-300">
                        {agent}
                      </span>
                      <div className="flex items-center gap-1">
                        <div className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_5px_#22c55e]"></div>
                        <span className="text-[10px] text-green-500">
                          运行中
                        </span>
                      </div>
                    </div>
                  ),
                )}
              </div>
            </DashboardCard>
          </div>
        )}

        {activeTab === "tools" && (
          <div className="grid grid-cols-1 gap-6">
            <ToolsPanel />
          </div>
        )}

        {activeTab === "skills" && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <SkillsPanel />
          </div>
        )}

        {activeTab === "mcp" && (
          <div className="grid grid-cols-1 gap-6">
            <MCPPanel />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
