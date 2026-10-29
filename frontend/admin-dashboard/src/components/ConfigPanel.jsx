// WS-D: 运行时配置面板 — Cache threshold / TTL / max_size / Fallback chain / Agent grayscale
import React, { useState, useEffect, useCallback } from "react";
import {
  Settings,
  RefreshCw,
  Save,
  RotateCcw,
  Database,
  Clock,
  Hash,
  Layers,
  Cpu,
  Power,
  PowerOff,
  ArrowUp,
  ArrowDown,
} from "lucide-react";

const API_BASE = "/api";

function ConfigPanel() {
  const [token, setToken] = useState(null);
  const [config, setConfig] = useState(null);
  const [agents, setAgents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [saving, setSaving] = useState(false);

  // 表单本地副本（避免输入抖动触发后端）
  const [ttlInput, setTtlInput] = useState("");
  const [maxSizeInput, setMaxSizeInput] = useState("");
  const [chainInput, setChainInput] = useState([]);
  const [thresholdInput, setThresholdInput] = useState("");

  // 1. 取 admin dev-token
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

  // 2. 加载 config + agents
  const load = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const [c, a] = await Promise.all([
        adminFetch(`${API_BASE}/v2/config/get`).then((r) => r.json()),
        adminFetch(`${API_BASE}/v2/agents/registry`).then((r) => r.json()),
      ]);
      setConfig(c);
      setAgents(a?.agents || a || []);
      // 同步到表单
      setTtlInput(String(c.values?.cache_ttl_sec ?? ""));
      setMaxSizeInput(String(c.values?.cache_max_size ?? ""));
      setThresholdInput(String(c.values?.cache_similarity_threshold ?? "0.85"));
      setChainInput([...(c.values?.fallback_chain || [])]);
    } catch (e) {
      showMsg(`加载失败: ${e.message}`, "error");
    } finally {
      setLoading(false);
    }
  }, [token, adminFetch]);

  useEffect(() => {
    if (token) load();
  }, [token, load]);

  // 3. 保存单个值
  const save = async (key, value) => {
    setSaving(true);
    try {
      const r = await adminFetch(`${API_BASE}/v2/config/update`, {
        method: "POST",
        body: JSON.stringify({ values: { [key]: value } }),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      const data = await r.json();
      showMsg(`已保存 ${key} (v${data.new_versions?.[key]})`, "success");
      load();
    } catch (e) {
      showMsg(`保存失败: ${e.message}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    if (!confirm("重置全部配置到 env 默认值（也会清空 Postgres 中的运行时覆盖）？")) return;
    try {
      const r = await adminFetch(`${API_BASE}/v2/config/reset`, { method: "POST" });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      showMsg("已重置到 env 默认", "success");
      load();
    } catch (e) {
      showMsg(`重置失败: ${e.message}`, "error");
    }
  };

  // Fallback chain 上下移
  const moveChain = (idx, dir) => {
    const arr = [...chainInput];
    const target = idx + dir;
    if (target < 0 || target >= arr.length) return;
    [arr[idx], arr[target]] = [arr[target], arr[idx]];
    setChainInput(arr);
  };

  // Agent grayscale 切换（复用现有 enable/disable）
  const toggleAgent = async (name, enable) => {
    try {
      const r = await fetch(
        `${API_BASE}/v2/agents/registry/${name}/${enable ? "enable" : "disable"}`,
        { method: "POST" },
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      showMsg(`${name} -> ${enable ? "ON" : "OFF"}`, "success");
      load();
    } catch (e) {
      showMsg(`切换失败: ${e.message}`, "error");
    }
  };

  if (!token) {
    return (
      <div className="text-slate-500 text-xs p-4">正在获取 admin token…</div>
    );
  }
  if (!config) {
    return (
      <div className="text-slate-500 text-xs p-4">加载配置中…</div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toast */}
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

      {/* 顶部：版本号 + 重置 */}
      <div className="glass-panel p-3 rounded flex justify-between items-center">
        <div className="text-xs text-cyan-600 font-mono">
          RuntimeConfig 快照 · {Object.keys(config.values || {}).length} keys · 最高版本 v
          {Math.max(0, ...Object.values(config.versions || {}))}
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
            onClick={reset}
            className="bg-red-900/40 hover:bg-red-900/60 text-red-200 px-3 py-1 rounded text-xs font-mono flex items-center gap-1"
          >
            <RotateCcw size={12} /> Reset to env
          </button>
        </div>
      </div>

      {/* Card 1: Cache Threshold */}
      <div className="glass-panel p-4 rounded">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
          <Database size={16} /> Cache Similarity Threshold
        </h3>
        <div className="flex gap-2 items-center">
          <input
            type="number"
            min="0"
            max="1"
            step="0.01"
            value={thresholdInput}
            onChange={(e) => setThresholdInput(e.target.value)}
            className="bg-slate-900 border border-cyan-800 rounded px-3 py-1 text-cyan-100 font-mono text-xs w-32"
          />
          <span className="text-cyan-600 text-xs font-mono">
            (当前 v{config.versions?.cache_similarity_threshold ?? 0}, 范围 0–1)
          </span>
          <button
            onClick={() => save("cache_similarity_threshold", parseFloat(thresholdInput))}
            disabled={saving}
            className="ml-auto bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs font-mono flex items-center gap-1"
          >
            <Save size={12} /> 保存
          </button>
        </div>
      </div>

      {/* Card 2: Cache TTL */}
      <div className="glass-panel p-4 rounded">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
          <Clock size={16} /> Cache TTL (sec)
        </h3>
        <div className="flex gap-2 items-center">
          <input
            type="number"
            min="1"
            value={ttlInput}
            onChange={(e) => setTtlInput(e.target.value)}
            className="bg-slate-900 border border-cyan-800 rounded px-3 py-1 text-cyan-100 font-mono text-xs w-32"
          />
          <span className="text-cyan-600 text-xs font-mono">
            (当前 v{config.versions?.cache_ttl_sec ?? 0}={config.values?.cache_ttl_sec})
          </span>
          <button
            onClick={() => save("cache_ttl_sec", parseInt(ttlInput, 10))}
            disabled={saving}
            className="ml-auto bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs font-mono flex items-center gap-1"
          >
            <Save size={12} /> 保存
          </button>
        </div>
      </div>

      {/* Card 3: Cache Max Size */}
      <div className="glass-panel p-4 rounded">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
          <Hash size={16} /> Cache Max Size
        </h3>
        <div className="flex gap-2 items-center">
          <input
            type="number"
            min="1"
            value={maxSizeInput}
            onChange={(e) => setMaxSizeInput(e.target.value)}
            className="bg-slate-900 border border-cyan-800 rounded px-3 py-1 text-cyan-100 font-mono text-xs w-32"
          />
          <span className="text-cyan-600 text-xs font-mono">
            (当前 v{config.versions?.cache_max_size ?? 0}={config.values?.cache_max_size})
          </span>
          <button
            onClick={() => save("cache_max_size", parseInt(maxSizeInput, 10))}
            disabled={saving}
            className="ml-auto bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs font-mono flex items-center gap-1"
          >
            <Save size={12} /> 保存
          </button>
        </div>
      </div>

      {/* Card 4: Fallback Chain (up/down reorderable) */}
      <div className="glass-panel p-4 rounded">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
          <Layers size={16} /> Fallback Chain
        </h3>
        <div className="space-y-1 mb-2">
          {chainInput.map((p, idx) => (
            <div
              key={p}
              className="flex items-center gap-2 bg-slate-900/40 border border-cyan-900/30 rounded px-2 py-1"
            >
              <span className="text-cyan-600 text-[10px] font-mono w-6">#{idx + 1}</span>
              <span className="text-cyan-200 font-mono text-xs flex-1">{p}</span>
              <button
                onClick={() => moveChain(idx, -1)}
                disabled={idx === 0}
                className="text-cyan-400 hover:text-cyan-200 disabled:opacity-30"
                title="上移"
              >
                <ArrowUp size={12} />
              </button>
              <button
                onClick={() => moveChain(idx, 1)}
                disabled={idx === chainInput.length - 1}
                className="text-cyan-400 hover:text-cyan-200 disabled:opacity-30"
                title="下移"
              >
                <ArrowDown size={12} />
              </button>
            </div>
          ))}
        </div>
        <div className="flex justify-end">
          <button
            onClick={() => save("fallback_chain", chainInput)}
            disabled={saving}
            className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs font-mono flex items-center gap-1"
          >
            <Save size={12} /> 保存顺序
          </button>
        </div>
      </div>

      {/* Card 5: Agent Grayscale（re-uses 现有 enable/disable） */}
      <div className="glass-panel p-4 rounded">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm mb-3 flex items-center gap-2">
          <Cpu size={16} /> Agent Grayscale (enable / disable)
        </h3>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-cyan-600 text-left">
              <th>Name</th>
              <th>Status</th>
              <th>Tools</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((a) => (
              <tr key={a.name} className="border-t border-cyan-900/30">
                <td className="py-1 font-mono text-cyan-200">{a.name}</td>
                <td>
                  {a.enabled ? (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-green-900/30 text-green-300">
                      ON
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-red-900/30 text-red-300">
                      OFF
                    </span>
                  )}
                </td>
                <td className="text-slate-400">{a.tools_count || 0}</td>
                <td>
                  <button
                    onClick={() => toggleAgent(a.name, !a.enabled)}
                    className="text-cyan-300 hover:underline text-xs"
                  >
                    {a.enabled ? (
                      <>
                        <PowerOff size={10} className="inline mr-1" />禁用
                      </>
                    ) : (
                      <>
                        <Power size={10} className="inline mr-1" />启用
                      </>
                    )}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default ConfigPanel;
