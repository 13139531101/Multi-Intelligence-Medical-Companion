// 阶段41-3: MCP 管理面板（增删改 + SSE 实时可视化）
import React, { useState, useEffect, useRef } from "react";
import { Plug, Plus, Trash2, Power, PowerOff, Activity, RefreshCw } from "lucide-react";
import axios from "axios";

const API_BASE = "/api";

const DEFAULT_MCPS = new Set([
  "health_records_mcp", "visit_summary_mcp",
  "medication_reminder_mcp", "health_advisor_mcp",
]);

function MCPPanel() {
  const [servers, setServers] = useState([]);
  const [filter, setFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    name: "", url: "", type: "http", display_name: "", description: "",
  });
  const [activeCalls, setActiveCalls] = useState([]);
  const [callHistory, setCallHistory] = useState([]);
  const [eventSource, setEventSource] = useState(null);
  const streamRef = useRef(null);

  const load = async () => {
    try {
      const r = await axios.get(`${API_BASE}/v2/registry/mcp/servers`);
      setServers(r.data.servers || []);
    } catch (err) {
      console.error(err);
    }
  };

  const loadActive = async () => {
    try {
      const r = await axios.get(`${API_BASE}/v2/mcp/calls/active`);
      setActiveCalls(r.data.active || []);
    } catch (err) { /* ignore */ }
  };

  const loadHistory = async () => {
    try {
      const r = await axios.get(`${API_BASE}/v2/mcp/calls/history?limit=20`);
      setCallHistory(r.data.history || []);
    } catch (err) { /* ignore */ }
  };

  useEffect(() => {
    load();
    loadActive();
    loadHistory();
    const t = setInterval(() => {
      load();
      loadActive();
      loadHistory();
    }, 5000);
    return () => clearInterval(t);
  }, []);

  const toggle = async (srv, enable) => {
    const path = enable ? "enable" : "disable";
    await axios.post(`${API_BASE}/v2/registry/mcp/servers/${srv.name}/${path}`);
    load();
  };

  const remove = async (srv) => {
    if (!confirm(`确认删除 MCP "${srv.display_name}"?`)) return;
    try {
      await axios.delete(`${API_BASE}/v2/registry/mcp/servers/${srv.name}`);
      load();
    } catch (err) {
      alert("删除失败: " + (err.response?.data?.error || err.message));
    }
  };

  const create = async () => {
    if (!createForm.name || !createForm.url) {
      alert("name 和 url 不能为空");
      return;
    }
    try {
      await axios.post(`${API_BASE}/v2/registry/mcp/servers`, createForm);
      setShowCreate(false);
      setCreateForm({ name: "", url: "", type: "http", display_name: "", description: "" });
      load();
    } catch (err) {
      alert("创建失败: " + (err.response?.data?.error || err.message));
    }
  };

  const healthCheck = async (srv) => {
    await axios.post(`${API_BASE}/v2/registry/mcp/servers/${srv.name}/health`);
    load();
  };

  const testCall = async (srv) => {
    try {
      await axios.post(`${API_BASE}/v2/mcp/call/${srv.name}`, {
        method: "test", args: { from: "admin-dashboard" },
      });
      setTimeout(loadHistory, 500);
    } catch (err) {
      alert("调用失败: " + err.message);
    }
  };

  // SSE 可视化
  const startStream = () => {
    if (eventSource) return;
    const es = new EventSource(`${API_BASE}/v2/mcp/visualize/stream`);
    es.addEventListener('call_start', (e) => {
      const d = JSON.parse(e.data);
      addLog('▶ START', d);
      setActiveCalls(prev => [...prev, d]);
    });
    es.addEventListener('call_end', (e) => {
      const d = JSON.parse(e.data);
      addLog(d.success ? '✅ END' : '❌ END', d);
      setActiveCalls(prev => prev.filter(c => c.call_id !== d.call_id));
      setCallHistory(prev => [d, ...prev].slice(0, 20));
    });
    es.onerror = () => {
      addLog('⚠ ERROR', { msg: 'SSE 断开' });
      es.close();
      setEventSource(null);
    };
    setEventSource(es);
  };
  const stopStream = () => {
    if (eventSource) { eventSource.close(); setEventSource(null); }
  };
  const addLog = (type, d) => {
    if (!streamRef.current) return;
    const div = document.createElement('div');
    div.className = `text-[10px] font-mono ${type.includes('END') ? (d.success ? 'text-green-400' : 'text-red-400') : 'text-cyan-300'}`;
    div.textContent = `[${new Date().toLocaleTimeString()}] ${type} ${d.mcp_name || ''}.${d.method || ''} (${d.call_id || ''}) ${d.duration_str || ''}`;
    streamRef.current.appendChild(div);
    streamRef.current.scrollTop = streamRef.current.scrollHeight;
  };

  const filtered = servers.filter(s =>
    s.name.toLowerCase().includes(filter.toLowerCase()) ||
    (s.display_name || '').toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="space-y-4">
      {/* 注册表单 */}
      <div className="glass-panel p-4 rounded-lg">
        <div className="flex items-center justify-between mb-3 border-b border-cyan-900/50 pb-2">
          <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm flex items-center gap-2">
            <Plug size={16} />
            MCP Servers (本地 + 远程)
          </h3>
          <span className="flex items-center gap-2">
            <span className="text-xs text-cyan-600 font-mono">
              {servers.length} 个 | {servers.filter(s => s.health_ok).length} 健康
            </span>
            <button
              onClick={() => setShowCreate(!showCreate)}
              className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs font-mono flex items-center gap-1"
            >
              <Plus size={12} /> 注册远程
            </button>
          </span>
        </div>

        {showCreate && (
          <div className="bg-slate-900/80 p-3 rounded border border-cyan-700/50 mb-3">
            <div className="grid grid-cols-2 gap-2">
              <input value={createForm.name} onChange={e => setCreateForm({...createForm, name: e.target.value})}
                placeholder="name" className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
              <select value={createForm.type} onChange={e => setCreateForm({...createForm, type: e.target.value})}
                className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs">
                <option value="http">HTTP (JSON-RPC)</option>
                <option value="sse">SSE</option>
              </select>
              <input value={createForm.url} onChange={e => setCreateForm({...createForm, url: e.target.value})}
                placeholder="https://example.com" className="md:col-span-2 bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
              <input value={createForm.display_name} onChange={e => setCreateForm({...createForm, display_name: e.target.value})}
                placeholder="显示名" className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
              <input value={createForm.description} onChange={e => setCreateForm({...createForm, description: e.target.value})}
                placeholder="描述" className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
            </div>
            <div className="flex justify-end gap-2 mt-2">
              <button onClick={() => setShowCreate(false)} className="px-3 py-1 text-xs text-slate-400">取消</button>
              <button onClick={create} className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs font-mono">注册</button>
            </div>
          </div>
        )}

        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="过滤 MCP..."
          className="w-full bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 focus:border-cyan-400 focus:outline-none font-mono text-xs"
        />
      </div>

      {/* MCP 列表 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {filtered.map(s => {
          const isDefault = DEFAULT_MCPS.has(s.name);
          return (
            <div key={s.name} className={`p-3 rounded border ${s.health_ok ? 'border-slate-800 bg-slate-900/40' : 'border-red-900/50 bg-red-900/10'}`}>
              <div className="flex items-start justify-between mb-1">
                <div>
                  <div className="font-bold text-cyan-200 font-mono text-sm flex items-center gap-2">
                    <span>{s.icon || '🔌'}</span>
                    {s.display_name}
                    {isDefault && <span className="text-[10px] text-yellow-500">🔒 默认</span>}
                  </div>
                  <div className="text-[10px] text-cyan-600 font-mono mt-1">
                    {s.name} | {s.type} | {s.url || s.command}
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className={`px-2 py-0.5 text-[10px] rounded font-mono ${
                    s.status === 'connected' ? 'bg-green-900/30 text-green-300' :
                    s.status === 'failed' ? 'bg-red-900/30 text-red-300' :
                    s.status === 'disabled' ? 'bg-slate-700 text-slate-400' :
                    'bg-yellow-900/30 text-yellow-300'
                  }`}>{s.status}</span>
                </div>
              </div>
              <div className="flex items-center gap-3 mt-2 text-[10px] text-cyan-600 font-mono">
                <span>📞 {s.call_count}</span>
                <span>❌ {s.error_count} ({(s.error_rate || 0).toFixed(1)}%)</span>
                <span>🔧 {(s.tools || []).length} 工具</span>
              </div>
              <div className="flex gap-1 mt-2 opacity-60 hover:opacity-100">
                <button onClick={() => testCall(s)} className="px-2 py-1 text-[10px] bg-cyan-900/30 text-cyan-300 rounded font-mono">测试调用</button>
                {s.type !== 'local' && (
                  <button onClick={() => healthCheck(s)} className="px-2 py-1 text-[10px] bg-purple-900/30 text-purple-300 rounded font-mono">健康检查</button>
                )}
                <button onClick={() => toggle(s, s.status === 'disabled')} className="px-2 py-1 text-[10px] bg-slate-700 text-slate-300 rounded font-mono">
                  {s.status === 'disabled' ? '启用' : '禁用'}
                </button>
                {!isDefault && (
                  <button onClick={() => remove(s)} className="px-2 py-1 text-[10px] bg-red-900/30 text-red-300 rounded font-mono">删除</button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* SSE 可视化 */}
      <div className="glass-panel p-4 rounded-lg">
        <div className="flex items-center justify-between mb-2 border-b border-cyan-900/50 pb-2">
          <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm flex items-center gap-2">
            <Activity size={16} />
            MCP 调用流 (SSE 实时)
          </h3>
          <div className="flex gap-2">
            {!eventSource ? (
              <button onClick={startStream} className="bg-green-600 hover:bg-green-500 text-white px-3 py-1 rounded text-xs font-mono">▶ 开始</button>
            ) : (
              <button onClick={stopStream} className="bg-red-600 hover:bg-red-500 text-white px-3 py-1 rounded text-xs font-mono">⏸ 停止</button>
            )}
            <button onClick={loadHistory} className="bg-cyan-900/30 text-cyan-300 px-3 py-1 rounded text-xs font-mono">↻ 历史</button>
          </div>
        </div>
        <div ref={streamRef} className="bg-black/40 border border-cyan-900/30 rounded p-2 h-32 overflow-y-auto custom-scrollbar font-mono">
          <span className="text-[10px] text-cyan-600">点击"开始"启动 SSE...</span>
        </div>

        <h4 className="text-cyan-400 text-xs font-mono mt-3 mb-1">活跃调用 ({activeCalls.length})</h4>
        <div className="flex flex-wrap gap-1">
          {activeCalls.length === 0 ? <span className="text-[10px] text-cyan-600">无</span> :
            activeCalls.map(c => (
              <span key={c.call_id} className="px-2 py-1 bg-cyan-900/30 text-cyan-300 text-[10px] rounded font-mono animate-pulse">
                {c.mcp_name}.{c.method} ({c.call_id})
              </span>
            ))
          }
        </div>

        <h4 className="text-cyan-400 text-xs font-mono mt-3 mb-1">最近调用</h4>
        <div className="space-y-1 max-h-40 overflow-y-auto custom-scrollbar">
          {callHistory.length === 0 ? <span className="text-[10px] text-cyan-600">无历史</span> :
            callHistory.map(c => (
              <div key={c.call_id} className={`text-[10px] font-mono px-2 py-1 rounded ${c.success ? 'text-green-300 bg-green-900/10' : 'text-red-300 bg-red-900/10'}`}>
                [{new Date(c.started_at * 1000).toLocaleTimeString()}] {c.mcp_name}.{c.method} → {c.duration_str}
              </div>
            ))
          }
        </div>
      </div>
    </div>
  );
}

export default MCPPanel;