// WS-C: 监控面板 — 实时 QPS / 延迟分位 / 错误率 / 缓存命中率 / 路由分布
import React, { useState, useEffect, useCallback } from "react";
import {
  Activity,
  RefreshCw,
  Zap,
  Clock,
  AlertCircle,
  Database,
  GitBranch,
  Cpu,
  MemoryStick,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

const API_BASE = "/api";
const COLORS = ["#06b6d4", "#8b5cf6", "#f59e0b", "#10b981", "#ef4444", "#3b82f6"];

function MonitoringPanel() {
  const [token, setToken] = useState(null);
  const [overview, setOverview] = useState(null);
  const [cache, setCache] = useState(null);
  const [routing, setRouting] = useState(null);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/v2/admin/dev-token`, { method: "POST" });
        if (r.ok) {
          const d = await r.json();
          setToken(d.access_token);
        }
      } catch (_) {}
    })();
  }, []);

  const adminFetch = useCallback(
    async (url) => {
      if (!token) throw new Error("not authenticated");
      const r = await fetch(url, {
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    },
    [token],
  );

  const publicFetch = useCallback(async (url) => {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }, []);

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [ov, ca, rt] = await Promise.all([
        publicFetch(`${API_BASE}/v2/overview`),
        publicFetch(`${API_BASE}/v2/models/cache/stats`),
        adminFetch(`${API_BASE}/v2/routing/distribution`),
      ]);
      setOverview(ov);
      setCache(ca);
      setRouting(rt);
    } catch (e) {
      showMsg(`加载失败: ${e.message}`, "error");
    } finally {
      setLoading(false);
    }
  }, [token, adminFetch, publicFetch]);

  // 2s 轮询 — 监控需要"动起来"
  useEffect(() => {
    if (!token) return;
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [token, load]);

  const showMsg = (text, type = "success") => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 3000);
  };

  if (!token) {
    return <div className="text-slate-500 text-xs p-4">正在获取 admin token…</div>;
  }
  if (!overview) {
    return <div className="text-slate-500 text-xs p-4">加载监控数据中…</div>;
  }

  const req = overview.requests || {};
  const llm = overview.llm_api || {};
  const sys = overview.system || {};
  const uptime = overview.uptime_sec || 0;
  const qps = req.total && uptime ? (req.total / uptime).toFixed(3) : "0";

  const byAgentData = Object.entries(routing?.by_agent || {}).map(([k, v]) => ({
    name: k,
    value: v,
  }));
  const byLayerData = Object.entries(routing?.by_layer || {}).map(([k, v]) => ({
    name: k,
    count: v,
  }));

  return (
    <div className="space-y-4">
      {msg && (
        <div
          className={`fixed top-4 right-4 z-50 px-4 py-2 rounded text-xs font-mono shadow-lg ${
            msg.type === "error"
              ? "bg-red-900/80 text-red-100 border border-red-700"
              : "bg-green-900/80 text-green-100 border border-green-700"
          }`}
        >
          {msg.text}
        </div>
      )}

      {/* 顶部 */}
      <div className="glass-panel p-3 rounded flex justify-between items-center">
        <div className="flex items-center gap-4 text-xs text-cyan-600 font-mono">
          <Activity size={14} className="text-cyan-400 animate-pulse" />
          <span>实时监控 (2s 轮询)</span>
          <span>Uptime: {Math.floor(uptime / 60)}m {Math.floor(uptime % 60)}s</span>
          <span>QPS (累计平均): {qps}</span>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="bg-cyan-900/40 hover:bg-cyan-900/60 text-cyan-200 px-3 py-1 rounded text-xs font-mono flex items-center gap-1"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> 刷新
        </button>
      </div>

      {/* 卡片 1：请求量 + 错误率 + QPS */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Stat
          icon={<Zap size={14} />}
          label="请求总数"
          value={req.total || 0}
          sub={`window=${req.window_size || 0}`}
          accent="cyan"
        />
        <Stat
          icon={<AlertCircle size={14} />}
          label="错误率"
          value={`${((req.error_rate || 0) * 100).toFixed(2)}%`}
          sub={`errors=${req.errors || 0}`}
          accent={(req.error_rate || 0) > 0.05 ? "red" : "green"}
        />
        <Stat
          icon={<Cpu size={14} />}
          label="LLM 调用"
          value={llm.calls || 0}
          sub={`errors=${llm.errors || 0} / rate=${((llm.error_rate || 0) * 100).toFixed(1)}%`}
          accent="purple"
        />
      </div>

      {/* 卡片 2：延迟分位 */}
      <div className="glass-panel p-4 rounded">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
          <Clock size={14} /> 端到端延迟分位 (秒)
        </h3>
        <div className="grid grid-cols-3 gap-3">
          <Stat label="p50" value={`${(req.latency_p50 || 0).toFixed(2)}s`} accent="cyan" />
          <Stat label="p95" value={`${(req.latency_p95 || 0).toFixed(2)}s`} accent="yellow" />
          <Stat label="p99" value={`${(req.latency_p99 || 0).toFixed(2)}s`} accent="red" />
        </div>
      </div>

      {/* 卡片 3：Cache hit rate + 系统 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="glass-panel p-4 rounded">
          <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
            <Database size={14} /> LLM Cache (semantic)
          </h3>
          {cache ? (
            <div className="space-y-1 text-xs font-mono">
              <Row k="size" v={cache.size ?? "?"} />
              <Row k="hits" v={cache.hits ?? "?"} />
              <Row k="misses" v={cache.misses ?? "?"} />
              <Row
                k="hit rate"
                v={cache.hit_rate != null ? `${(cache.hit_rate * 100).toFixed(1)}%` : "—"}
                accent="green"
              />
              <Row k="ttl_sec" v={cache.ttl_sec ?? "?"} />
            </div>
          ) : (
            <div className="text-slate-500 text-xs">暂无 cache 数据</div>
          )}
        </div>
        <div className="glass-panel p-4 rounded">
          <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
            <MemoryStick size={14} /> 系统资源
          </h3>
          <div className="space-y-1 text-xs font-mono">
            <Row k="CPU" v={`${(sys.cpu_percent || 0).toFixed(1)}%`} />
            <Row k="内存" v={`${(sys.mem_percent || 0).toFixed(1)}%`} />
            <Row k="DB" v={overview.db?.ok ? "OK" : "DOWN"} accent={overview.db?.ok ? "green" : "red"} />
            <Row k="embedding model" v={overview.embedding?.model ?? "?"} />
          </div>
        </div>
      </div>

      {/* 卡片 4：路由分布 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="glass-panel p-4 rounded">
          <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
            <GitBranch size={14} /> 路由分布 (按 agent)
          </h3>
          {byAgentData.length === 0 ? (
            <div className="text-slate-500 text-xs p-4">暂无路由事件</div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={byAgentData}
                  dataKey="value"
                  nameKey="name"
                  outerRadius={70}
                  label={(e) => `${e.name}: ${e.value}`}
                >
                  {byAgentData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
        <div className="glass-panel p-4 rounded">
          <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
            <GitBranch size={14} /> 路由分布 (按 layer)
          </h3>
          {byLayerData.length === 0 ? (
            <div className="text-slate-500 text-xs p-4">暂无 layer 数据</div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={byLayerData}>
                <XAxis dataKey="name" stroke="#67e8f9" fontSize={11} />
                <YAxis stroke="#67e8f9" fontSize={11} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #155e75", fontSize: 11 }} />
                <Bar dataKey="count" fill="#8b5cf6" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* 卡片 5：最近路由事件 */}
      <div className="glass-panel p-4 rounded">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
          最近路由 ({(routing?.recent || []).length} 条)
        </h3>
        <div className="max-h-48 overflow-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-cyan-600 text-left">
                <th>ts</th>
                <th>agent</th>
                <th>layer</th>
                <th>reason</th>
              </tr>
            </thead>
            <tbody>
              {(routing?.recent || []).slice().reverse().map((e, i) => (
                <tr key={i} className="border-t border-cyan-900/30">
                  <td className="py-1 font-mono text-slate-400">
                    {e.ts ? new Date(e.ts * 1000).toLocaleTimeString() : "—"}
                  </td>
                  <td className="font-mono text-cyan-200">{e.agent || "?"}</td>
                  <td className="font-mono text-cyan-100">{e.layer ?? "?"}</td>
                  <td className="text-slate-400 truncate max-w-md">{e.reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Stat({ icon, label, value, sub, accent = "cyan" }) {
  const colorClass = `text-${accent}-400`;
  return (
    <div className="glass-panel p-3 rounded">
      <div className={`${colorClass} text-[10px] font-mono uppercase flex items-center gap-1`}>
        {icon} {label}
      </div>
      <div className={`text-${accent}-200 text-2xl font-mono font-bold mt-1`}>{value}</div>
      {sub && <div className="text-cyan-700 text-[10px] font-mono mt-0.5">{sub}</div>}
    </div>
  );
}

function Row({ k, v, accent = "cyan" }) {
  return (
    <div className="flex justify-between">
      <span className="text-cyan-600">{k}</span>
      <span className={`text-${accent}-200`}>{v}</span>
    </div>
  );
}

export default MonitoringPanel;
