// 阶段 RBAC: Tools 管理面板（支持编辑 required_role）
import React, { useState, useEffect, useCallback } from "react";
import { Wrench, Lock, Unlock, RefreshCw, Save, X } from "lucide-react";

const API_BASE = "/api";

function RoleBadge({ role }) {
  const colors = {
    guest: "bg-slate-800 text-slate-300 border-slate-600",
    user: "bg-blue-900/40 text-blue-300 border-blue-700",
    admin: "bg-red-900/40 text-red-300 border-red-700",
  };
  const cls = colors[role] || colors.guest;
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${cls}`}>
      {role}
    </span>
  );
}

function ToolsPanel() {
  const [tools, setTools] = useState([]);
  const [stats, setStats] = useState(null);
  const [filter, setFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(null); // { tool_name, role }
  const [editRole, setEditRole] = useState("guest");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState(null);
  const [token, setToken] = useState(null);

  // Get dev admin token on mount
  useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${API_BASE}/v2/admin/dev-token`, { method: "POST" });
        if (r.ok) {
          const data = await r.json();
          setToken(data.access_token);
        }
      } catch (_) {}
    })();
  }, []);

  const adminFetch = useCallback(async (url, opts = {}) => {
    if (!token) throw new Error("not authenticated");
    return fetch(url, {
      ...opts,
      headers: {
        ...(opts.headers || {}),
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
    });
  }, [token]);

  const load = useCallback(async () => {
    try {
      if (!token) return;
      const r = await adminFetch(`${API_BASE}/v2/admin/tools/permissions`);
      if (!r.ok) throw new Error("unauthorized or error");
      const data = await r.json();
      setTools(data.tools || []);
    } catch (e) {
      // fallback to public endpoint
      try {
        const r2 = await fetch(`${API_BASE}/v2/tools`);
        setTools(r2.ok ? (await r2.json()).tools || [] : []);
      } catch {}
    }
  }, [token, adminFetch]);

  useEffect(() => {
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]);

  const showMsg = (text, type = "info") => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 3000);
  };

  const startEdit = (tool) => {
    setEditing({ tool_name: tool.name });
    setEditRole(tool.effective_role || tool.required_role || "guest");
  };
  const cancelEdit = () => { setEditing(null); setEditRole("guest"); };

  const saveEdit = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      const r = await adminFetch(`${API_BASE}/v2/admin/tools/${editing.tool_name}/permission`, {
        method: "PUT",
        body: JSON.stringify({ role: editRole }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || "save failed");
      }
      showMsg(`✅ ${editing.tool_name} → ${editRole}`, "success");
      setEditing(null);
      load();
    } catch (e) {
      showMsg(`❌ ${e.message}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const resetRole = async (toolName) => {
    try {
      await adminFetch(`${API_BASE}/v2/admin/tools/${toolName}/permission`, { method: "DELETE" });
      showMsg(`♻ ${toolName} 已恢复默认`, "success");
      load();
    } catch (e) {
      showMsg(`❌ ${e.message}`, "error");
    }
  };

  const filtered = tools.filter(t =>
    t.name.toLowerCase().includes(filter.toLowerCase()) ||
    (t.description || "").toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="glass-panel p-4 rounded-lg">
      <div className="flex items-center justify-between mb-4 border-b border-cyan-900/50 pb-2">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm flex items-center gap-2">
          <Wrench size={16} />
          工具权限配置
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-cyan-600 font-mono">{tools.length} 个工具</span>
          <button onClick={load} className="p-1 hover:bg-cyan-900/40 rounded">
            <RefreshCw size={12} className="text-cyan-500" />
          </button>
        </div>
      </div>

      {msg && (
        <div className={`mb-3 px-3 py-2 rounded text-xs font-mono ${
          msg.type === "success" ? "bg-green-900/40 text-green-300 border border-green-800" :
          msg.type === "error" ? "bg-red-900/40 text-red-300 border border-red-800" :
          "bg-cyan-900/40 text-cyan-300 border border-cyan-800"
        }`}>
          {msg.text}
        </div>
      )}

      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="过滤工具名/描述..."
        className="w-full bg-slate-900 border border-cyan-800 rounded px-3 py-2 mb-3 text-cyan-100 focus:border-cyan-400 focus:outline-none font-mono text-xs"
      />

      <div className="overflow-y-auto max-h-[520px] pr-1 custom-scrollbar">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-cyan-600 text-left border-b border-cyan-900/50">
              <th className="pb-2 pr-2">工具</th>
              <th className="pb-2 pr-2">分类</th>
              <th className="pb-2 pr-2">默认角色</th>
              <th className="pb-2 pr-2">当前角色</th>
              <th className="pb-2 pr-2">覆盖</th>
              <th className="pb-2">操作</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t) => {
              const isEditing = editing?.tool_name === t.name;
              return (
                <tr key={t.name} className="border-t border-cyan-900/30 hover:bg-cyan-900/10 transition-colors">
                  <td className="py-2 pr-2">
                    <div className="font-mono text-cyan-200 text-[11px]">{t.name}</div>
                    <div className="text-[9px] text-slate-500 mt-0.5 max-w-[180px] truncate">{t.description}</div>
                  </td>
                  <td className="py-2 pr-2">
                    <span className="px-1.5 py-0.5 bg-slate-800 text-slate-400 rounded text-[10px]">{t.category}</span>
                  </td>
                  <td className="py-2 pr-2">
                    <RoleBadge role={t.default_role} />
                  </td>
                  <td className="py-2 pr-2">
                    {isEditing ? (
                      <select
                        value={editRole}
                        onChange={e => setEditRole(e.target.value)}
                        className="bg-slate-900 border border-cyan-700 rounded px-2 py-1 text-cyan-100 font-mono text-[10px]"
                      >
                        <option value="guest">guest</option>
                        <option value="user">user</option>
                        <option value="admin">admin</option>
                      </select>
                    ) : (
                      <RoleBadge role={t.effective_role || t.required_role} />
                    )}
                  </td>
                  <td className="py-2 pr-2">
                    {t.is_overridden ? (
                      <span className="text-[10px] text-yellow-400">已覆盖</span>
                    ) : (
                      <span className="text-[10px] text-slate-600">—</span>
                    )}
                  </td>
                  <td className="py-2">
                    {isEditing ? (
                      <div className="flex gap-1">
                        <button
                          onClick={saveEdit}
                          disabled={saving}
                          className="flex items-center gap-1 px-2 py-1 bg-green-700 hover:bg-green-600 text-white rounded text-[10px]"
                        >
                          <Save size={10} />{saving ? "..." : "保存"}
                        </button>
                        <button
                          onClick={cancelEdit}
                          className="flex items-center gap-1 px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-[10px]"
                        >
                          <X size={10} />取消
                        </button>
                      </div>
                    ) : (
                      <div className="flex gap-1">
                        <button
                          onClick={() => startEdit(t)}
                          className="px-2 py-1 bg-cyan-900/50 hover:bg-cyan-800 text-cyan-300 rounded text-[10px]"
                        >
                          <Lock size={10} className="inline mr-0.5" />编辑
                        </button>
                        {t.is_overridden && (
                          <button
                            onClick={() => resetRole(t.name)}
                            title="恢复默认角色"
                            className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-400 rounded text-[10px]"
                          >
                            ↺恢复
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="text-center py-10 text-slate-600">无匹配工具</div>
        )}
      </div>
    </div>
  );
}

export default ToolsPanel;
