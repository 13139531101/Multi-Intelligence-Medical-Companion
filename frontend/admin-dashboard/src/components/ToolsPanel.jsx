// 阶段41-3: Tools 管理面板（只读 - 工具是内置的不能修改）
import React, { useState, useEffect } from "react";
import { Wrench, TrendingUp, AlertTriangle, Activity } from "lucide-react";
import axios from "axios";

const API_BASE = "/api";

function ToolsPanel() {
  const [tools, setTools] = useState([]);
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API_BASE}/v2/tools`);
      setTools(r.data.tools || []);
      setStats(r.data.stats || null);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  const filtered = tools.filter(t =>
    t.name.toLowerCase().includes(filter.toLowerCase()) ||
    t.description.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="glass-panel p-4 rounded-lg">
      <div className="flex items-center justify-between mb-4 border-b border-cyan-900/50 pb-2">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm flex items-center gap-2">
          <Wrench size={16} />
          工具列表 (内置, 只读)
        </h3>
        <span className="text-xs text-cyan-600 font-mono">
          {tools.length} 个 @tool
        </span>
      </div>

      {/* 统计 */}
      {stats && (
        <div className="grid grid-cols-3 gap-3 mb-4">
          <div className="bg-slate-900/80 p-3 rounded border border-cyan-900/30">
            <div className="text-xs text-cyan-600 uppercase">总调用</div>
            <div className="text-2xl font-bold text-cyan-100 font-mono">
              {stats.total_calls}
            </div>
          </div>
          <div className="bg-slate-900/80 p-3 rounded border border-cyan-900/30">
            <div className="text-xs text-cyan-600 uppercase">错误数</div>
            <div className="text-2xl font-bold text-red-400 font-mono">
              {stats.total_errors}
            </div>
          </div>
          <div className="bg-slate-900/80 p-3 rounded border border-cyan-900/30">
            <div className="text-xs text-cyan-600 uppercase">错误率</div>
            <div className="text-2xl font-bold text-yellow-400 font-mono">
              {stats.error_rate.toFixed(1)}%
            </div>
          </div>
        </div>
      )}

      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="过滤工具名/描述..."
        className="w-full bg-slate-900 border border-cyan-800 rounded px-3 py-2 mb-3 text-cyan-100 focus:border-cyan-400 focus:outline-none font-mono text-xs"
      />

      <div className="space-y-2 overflow-y-auto max-h-[500px] pr-2 custom-scrollbar">
        {filtered.length === 0 ? (
          <div className="text-center py-10 text-slate-600 border border-dashed border-slate-800 rounded">
            无工具
          </div>
        ) : (
          filtered.map((t) => (
            <div
              key={t.name}
              className="group p-3 bg-slate-900/40 border border-slate-800 hover:border-cyan-500/50 rounded transition-all"
            >
              <div className="flex items-start justify-between mb-1">
                <div>
                  <div className="font-bold text-cyan-200 font-mono text-sm">
                    🔧 {t.name}
                  </div>
                  <div className="text-xs text-slate-400 mt-1">
                    {t.description}
                  </div>
                </div>
                <span className="px-2 py-1 bg-cyan-900/30 text-cyan-300 text-[10px] rounded font-mono">
                  {t.category}
                </span>
              </div>
              <div className="flex items-center gap-4 mt-2 text-[10px] text-cyan-600 font-mono">
                <span>📞 {t.stats?.call_count || 0} 次</span>
                <span>❌ {t.stats?.error_count || 0} 错</span>
                <span>
                  ⏱ {t.stats?.call_count
                    ? Math.round(t.stats.total_latency_ms / t.stats.call_count)
                    : 0}ms
                </span>
                <span className="text-yellow-500">🔒 内置 (只读)</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default ToolsPanel;