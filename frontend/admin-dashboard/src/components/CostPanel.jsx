// WS-B: LLM 成本面板 — 总览 + per-provider + 最近明细 + 定价表
import React, { useState, useEffect, useCallback } from "react";
import {
  DollarSign,
  RefreshCw,
  TrendingUp,
  Layers,
  ListOrdered,
  Tag,
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

function CostPanel() {
  const [token, setToken] = useState(null);
  const [summary, setSummary] = useState(null);
  const [perProvider, setPerProvider] = useState([]);
  const [recent, setRecent] = useState([]);
  const [pricing, setPricing] = useState(null);
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

  const showMsg = (text, type = "success") => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 3000);
  };

  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [s, pp, rc, pr] = await Promise.all([
        adminFetch(`${API_BASE}/v2/cost/summary`),
        adminFetch(`${API_BASE}/v2/cost/per-provider`),
        adminFetch(`${API_BASE}/v2/cost/recent?limit=30`),
        adminFetch(`${API_BASE}/v2/cost/pricing`),
      ]);
      setSummary(s);
      setPerProvider(pp.providers || []);
      setRecent(rc.items || []);
      setPricing(pr);
    } catch (e) {
      showMsg(`加载失败: ${e.message}`, "error");
    } finally {
      setLoading(false);
    }
  }, [token, adminFetch]);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  // 5s 自动刷新（cost 数字可能持续变化）
  useEffect(() => {
    if (!token) return;
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [token, load]);

  if (!token) {
    return <div className="text-slate-500 text-xs p-4">正在获取 admin token…</div>;
  }
  if (!summary) {
    return <div className="text-slate-500 text-xs p-4">加载成本数据中…</div>;
  }

  const total = summary.total_cost_usd || 0;
  const providerChartData = perProvider.map((p) => ({
    name: p.provider,
    cost: p.cost_usd,
    calls: p.calls,
  }));
  const featureChartData = Object.entries(summary.by_feature_usd || {}).map(([k, v]) => ({
    name: k,
    value: v,
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

      {/* 顶部：总成本 + 刷新 */}
      <div className="glass-panel p-3 rounded flex justify-between items-center">
        <div className="flex items-center gap-6 text-xs text-cyan-600 font-mono">
          <span className="flex items-center gap-2">
            <DollarSign size={14} className="text-green-400" />
            累计 LLM 成本：<span className="text-green-300 text-base font-bold">${total.toFixed(4)}</span>
          </span>
          <span>累计 token: {summary.total_tokens?.toLocaleString() ?? 0}</span>
          <span>providers: {summary.providers_tracked}</span>
          <span>数据源: {pricing?.source ?? "?"}</span>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="bg-cyan-900/40 hover:bg-cyan-900/60 text-cyan-200 px-3 py-1 rounded text-xs font-mono flex items-center gap-1"
        >
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> 刷新
        </button>
      </div>

      {/* 卡片 1：按 provider 成本（柱图） */}
      <div className="glass-panel p-4 rounded">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
          <Layers size={14} /> 每 Provider 成本 (USD)
        </h3>
        {providerChartData.length === 0 ? (
          <div className="text-slate-500 text-xs p-4">暂无 LLM 调用数据</div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={providerChartData}>
              <XAxis dataKey="name" stroke="#67e8f9" fontSize={11} />
              <YAxis stroke="#67e8f9" fontSize={11} />
              <Tooltip
                contentStyle={{ background: "#0f172a", border: "1px solid #155e75", fontSize: 11 }}
                formatter={(v) => `$${v.toFixed(4)}`}
              />
              <Bar dataKey="cost" fill="#06b6d4" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* 卡片 2：按 feature 成本（饼图） */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="glass-panel p-4 rounded">
          <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
            <TrendingUp size={14} /> 按 Task Type 拆分
          </h3>
          {featureChartData.length === 0 ? (
            <div className="text-slate-500 text-xs p-4">暂无 feature 计数</div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={featureChartData}
                  dataKey="value"
                  nameKey="name"
                  outerRadius={70}
                  label={(e) => `${e.name}: $${e.value.toFixed(3)}`}
                >
                  {featureChartData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => `$${v.toFixed(4)}`} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* 卡片 3：当前定价表 */}
        <div className="glass-panel p-4 rounded">
          <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
            <Tag size={14} /> 定价常量表 (USD/1k tokens)
          </h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-cyan-600 text-left">
                <th>Provider</th>
                <th>Input</th>
                <th>Output</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(pricing?.providers || {}).map(([k, v]) => (
                <tr key={k} className="border-t border-cyan-900/30">
                  <td className="py-1 font-mono text-cyan-200">{k}</td>
                  <td className="font-mono text-cyan-100">${v.input_per_1k?.toFixed(6)}</td>
                  <td className="font-mono text-cyan-100">${v.output_per_1k?.toFixed(6)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* 卡片 4：最近 30 次调用明细 */}
      <div className="glass-panel p-4 rounded">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
          <ListOrdered size={14} /> 最近 {recent.length} 次调用
        </h3>
        {recent.length === 0 ? (
          <div className="text-slate-500 text-xs p-4">暂无明细（环形缓冲需要真实 LLM 调用触发）</div>
        ) : (
          <div className="max-h-72 overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-slate-900">
                <tr className="text-cyan-600 text-left">
                  <th>ts</th>
                  <th>provider</th>
                  <th>task</th>
                  <th>prompt</th>
                  <th>completion</th>
                  <th>latency</th>
                  <th>USD</th>
                </tr>
              </thead>
              <tbody>
                {recent.slice().reverse().map((c, i) => (
                  <tr key={i} className="border-t border-cyan-900/30">
                    <td className="py-1 font-mono text-slate-400">
                      {new Date(c.ts * 1000).toLocaleTimeString()}
                    </td>
                    <td className="font-mono text-cyan-200">{c.provider}</td>
                    <td className="text-cyan-300">{c.task_type || c.feature}</td>
                    <td className="font-mono text-cyan-100">{c.prompt_tokens}</td>
                    <td className="font-mono text-cyan-100">{c.completion_tokens}</td>
                    <td className="font-mono text-cyan-100">{c.latency_ms?.toFixed(0)}ms</td>
                    <td className="font-mono text-green-300">${c.cost_usd?.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default CostPanel;
