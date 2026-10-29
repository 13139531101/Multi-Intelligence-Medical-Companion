// WS-A: Agent 评测 Tab —— 5 个 metric family + 重跑按钮
import React, { useState, useEffect, useCallback } from "react";
import {
  ListChecks,
  RefreshCw,
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  GitBranch,
  Wrench,
  ShieldOff,
  Quote,
  Brain,
} from "lucide-react";

const API_BASE = "/api";

function EvalPanel() {
  const [token, setToken] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [jobId, setJobId] = useState(null);
  const [msg, setMsg] = useState(null);

  // 1. 取 admin token
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
    async (url, opts = {}) => {
      if (!token) throw new Error("not authenticated");
      return fetch(url, {
        ...opts,
        headers: {
          ...(opts.headers || {}),
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
      });
    },
    [token],
  );

  const showMsg = (text, type = "success") => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 3000);
  };

  // 2. 加载最新评测结果
  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const r = await adminFetch(`${API_BASE}/v2/eval/latest`);
      if (r.status === 404) {
        setData(null);
        return;
      }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      showMsg(`加载失败: ${e.message}`, "error");
    } finally {
      setLoading(false);
    }
  }, [token, adminFetch]);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  // 3. 启动重跑 + 轮询
  const runRerun = async () => {
    if (running) return;
    setRunning(true);
    try {
      const r = await adminFetch(`${API_BASE}/v2/eval/run`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setJobId(j.job_id);
      showMsg(`评测已启动: ${j.job_id}`, "success");
      // 轮询状态
      const tick = async () => {
        const sr = await adminFetch(`${API_BASE}/v2/eval/status/${j.job_id}`);
        if (sr.ok) {
          const sj = await sr.json();
          if (sj.status === "done" || sj.status === "error") {
            setRunning(false);
            if (sj.status === "done") {
              showMsg(`评测完成 (${sj.elapsed_sec}s)`, "success");
              load();
            } else {
              showMsg(`评测失败: ${sj.error?.slice(0, 80) || "unknown"}`, "error");
            }
            return;
          }
        }
        setTimeout(tick, 3000);
      };
      setTimeout(tick, 2000);
    } catch (e) {
      setRunning(false);
      showMsg(`启动失败: ${e.message}`, "error");
    }
  };

  if (!token) {
    return <div className="text-slate-500 text-xs p-4">正在获取 admin token…</div>;
  }

  const byCat = data?.by_category || {};
  const totalCases = data?.cases ?? 0;
  const passRate = data?.overall_pass_rate ?? 0;

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

      {/* 顶部：状态 + 重跑 */}
      <div className="glass-panel p-3 rounded flex justify-between items-center">
        <div className="text-xs text-cyan-600 font-mono flex items-center gap-3">
          <ListChecks size={14} className="inline" />
          {data ? (
            <>
              最近评测: {data.ran_at} · {totalCases} cases · 整体 pass rate{" "}
              <span className="text-cyan-300">{(passRate * 100).toFixed(1)}%</span>
            </>
          ) : (
            "尚未跑过评测 —— 点右侧「重跑全部」开始"
          )}
          {jobId && running && (
            <span className="text-yellow-300">
              · 任务 {jobId} 跑中…
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={load}
            disabled={loading}
            className="bg-cyan-900/40 hover:bg-cyan-900/60 text-cyan-200 px-3 py-1 rounded text-xs font-mono flex items-center gap-1"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} /> 刷新
          </button>
          <button
            onClick={runRerun}
            disabled={running}
            className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs font-mono flex items-center gap-1 disabled:opacity-50"
          >
            <Play size={12} className={running ? "animate-pulse" : ""} /> {running ? "跑中…" : "重跑全部"}
          </button>
        </div>
      </div>

      {/* 延迟面板（如果存在） */}
      {data?.latency && (
        <div className="glass-panel p-3 rounded">
          <div className="text-cyan-400 text-xs font-bold uppercase tracking-widest mb-2 flex items-center gap-2">
            <Clock size={14} /> 端到端延迟 (用户真实等待)
          </div>
          <div className="grid grid-cols-4 gap-3 text-xs font-mono">
            <Stat label="avg" value={`${data.latency.avg_sec}s`} />
            <Stat label="p50" value={`${data.latency.p50_sec}s`} />
            <Stat label="p95" value={`${data.latency.p95_sec}s`} />
            <Stat label="max" value={`${data.latency.max_sec}s`} />
          </div>
        </div>
      )}

      {/* 5 个 category 卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        <RoutingCard cat={byCat.routing} />
        <ToolCard cat={byCat.tool_selection} />
        <AbstentionCard cat={byCat.abstention} />
        <CitationCard cat={byCat.citation} />
        <MemoryCard cat={byCat.multi_turn_memory} />
      </div>

      {/* per-case 详细列表（折叠在底部） */}
      {data && (
        <details className="glass-panel p-3 rounded">
          <summary className="text-cyan-400 text-xs font-bold uppercase tracking-widest cursor-pointer">
            查看 per-case 明细 ({totalCases} 条)
          </summary>
          <div className="mt-2 max-h-96 overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-cyan-600 text-left">
                  <th>ID</th>
                  <th>Category</th>
                  <th>Expected</th>
                  <th>Actual</th>
                  <th>Pass</th>
                </tr>
              </thead>
              <tbody>
                {Object.values(byCat).flatMap((c) =>
                  (c?.per_case || []).map((p) => (
                    <tr key={p.id} className="border-t border-cyan-900/30">
                      <td className="py-1 font-mono text-cyan-200">{p.id}</td>
                      <td className="text-slate-400">{p.category || "?"}</td>
                      <td className="font-mono text-slate-300">
                        {p.expected ?? p.must_abstain ?? "?"}
                      </td>
                      <td className="font-mono text-slate-300">
                        {p.actual ?? p.actual_tools ?? p.citation_count ?? "?"}
                      </td>
                      <td>
                        {p.pass_top1 || p.pass_topk || p.forbidden_hit?.length === 0 ? (
                          <CheckCircle2 size={12} className="text-green-400" />
                        ) : (
                          <XCircle size={12} className="text-red-400" />
                        )}
                      </td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}

// ============================================================
// 通用小件
// ============================================================
function Stat({ label, value }) {
  return (
    <div className="bg-slate-900/40 border border-cyan-900/30 rounded p-2">
      <div className="text-cyan-600 text-[10px] font-mono uppercase">{label}</div>
      <div className="text-cyan-100 text-sm font-mono">{value}</div>
    </div>
  );
}

function pct(v) {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function MetricCard({ title, icon, children, accent = "cyan" }) {
  return (
    <div className="glass-panel p-3 rounded">
      <div
        className={`text-${accent}-400 text-xs font-bold uppercase tracking-widest mb-2 flex items-center gap-2`}
      >
        {icon} {title}
      </div>
      <div className="space-y-1 text-xs font-mono">{children}</div>
    </div>
  );
}

function RoutingCard({ cat }) {
  if (!cat) return <MetricCard title="路由" icon={<GitBranch size={14} />}>暂无数据</MetricCard>;
  return (
    <MetricCard title="路由" icon={<GitBranch size={14} />}>
      <Row k="cases" v={cat.cases} />
      <Row k="top-1 acc" v={pct(cat.top1_accuracy)} accent="green" />
      <Row k="top-k acc" v={pct(cat.top_k_accuracy)} accent="green" />
      {cat.by_layer && Object.keys(cat.by_layer).length > 0 && (
        <div className="mt-1 pt-1 border-t border-cyan-900/30 text-cyan-600">
          按 layer:
          {Object.entries(cat.by_layer).map(([k, v]) => (
            <div key={k} className="ml-2">
              {k}: {v.correct}/{v.total}
            </div>
          ))}
        </div>
      )}
    </MetricCard>
  );
}

function ToolCard({ cat }) {
  if (!cat) return <MetricCard title="工具选择" icon={<Wrench size={14} />}>暂无数据</MetricCard>;
  return (
    <MetricCard title="工具选择" icon={<Wrench size={14} />}>
      <Row k="cases" v={cat.cases} />
      <Row k="precision" v={pct(cat.tool_precision)} />
      <Row k="recall" v={pct(cat.tool_recall)} />
      <Row k="F1" v={pct(cat.tool_f1)} accent="green" />
      <Row
        k="forbidden 违例"
        v={cat.forbidden_violations}
        accent={cat.forbidden_violations > 0 ? "red" : "green"}
      />
    </MetricCard>
  );
}

function AbstentionCard({ cat }) {
  if (!cat) return <MetricCard title="拒答" icon={<ShieldOff size={14} />}>暂无数据</MetricCard>;
  return (
    <MetricCard title="拒答 / Escalate" icon={<ShieldOff size={14} />}>
      <Row k="cases" v={cat.cases} />
      <Row k="abstain hit rate" v={pct(cat.abstention_rate)} accent="green" />
      <Row
        k="false abstain rate"
        v={pct(cat.false_abstention_rate)}
        accent={cat.false_abstention_rate > 0.1 ? "red" : "green"}
      />
    </MetricCard>
  );
}

function CitationCard({ cat }) {
  if (!cat) return <MetricCard title="引文" icon={<Quote size={14} />}>暂无数据</MetricCard>;
  return (
    <MetricCard title="引文" icon={<Quote size={14} />}>
      <Row k="cases" v={cat.cases} />
      <Row k="recall" v={pct(cat.citation_recall)} />
      <Row k="precision" v={pct(cat.citation_precision)} />
    </MetricCard>
  );
}

function MemoryCard({ cat }) {
  if (!cat) return <MetricCard title="多轮记忆" icon={<Brain size={14} />}>暂无数据</MetricCard>;
  return (
    <MetricCard title="多轮记忆" icon={<Brain size={14} />}>
      <Row k="cases" v={cat.cases} />
      <Row k="hit rate" v={pct(cat.hit_rate)} accent="green" />
    </MetricCard>
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

export default EvalPanel;
