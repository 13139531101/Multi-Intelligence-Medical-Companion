// 阶段 RBAC: Users 管理面板 — 用户角色分配
import React, { useState, useEffect, useCallback } from "react";
import { Users as UsersIcon, RefreshCw, Save, Trash2, Plus, X } from "lucide-react";

const API_BASE = "/api";

function RoleBadge({ role }) {
  const colors = {
    guest: "bg-slate-800 text-slate-300 border-slate-600",
    user: "bg-blue-900/40 text-blue-300 border-blue-700",
    admin: "bg-red-900/40 text-red-300 border-red-700",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${colors[role] || colors.guest}`}>
      {role}
    </span>
  );
}

function UsersPanel() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);
  const [editing, setEditing] = useState(null); // user_id
  const [editRole, setEditRole] = useState("user");
  const [saving, setSaving] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [newUser, setNewUser] = useState({ user_id: "", username: "", role: "user" });
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
    if (!token) return;
    setLoading(true);
    try {
      const r = await adminFetch(`${API_BASE}/v2/admin/users`);
      if (!r.ok) throw new Error("unauthorized");
      const data = await r.json();
      setUsers(data.users || []);
    } catch (e) {
      showMsg(`❌ ${e.message}`, "error");
    } finally {
      setLoading(false);
    }
  }, [token, adminFetch]);

  useEffect(() => { load(); }, [load]);

  const showMsg = (text, type = "info") => {
    setMsg({ text, type });
    setTimeout(() => setMsg(null), 3000);
  };

  const startEdit = (user) => {
    setEditing(user.user_id);
    setEditRole(user.role);
  };
  const cancelEdit = () => { setEditing(null); setEditRole("user"); };

  const saveEdit = async (userId) => {
    setSaving(true);
    try {
      const r = await adminFetch(`${API_BASE}/v2/admin/users/${userId}/role`, {
        method: "PUT",
        body: JSON.stringify({ role: editRole }),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || "save failed");
      }
      showMsg(`✅ ${userId} → ${editRole}`, "success");
      setEditing(null);
      load();
    } catch (e) {
      showMsg(`❌ ${e.message}`, "error");
    } finally {
      setSaving(false);
    }
  };

  const deleteUser = async (userId) => {
    if (userId === "admin") { showMsg("❌ 不能删除 admin 用户", "error"); return; }
    if (!confirm(`确认删除用户 ${userId}？`)) return;
    try {
      const r = await adminFetch(`${API_BASE}/v2/admin/users/${userId}`, { method: "DELETE" });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || "delete failed");
      }
      showMsg(`🗑 ${userId} 已删除`, "success");
      load();
    } catch (e) {
      showMsg(`❌ ${e.message}`, "error");
    }
  };

  const addUser = async () => {
    if (!newUser.user_id || !newUser.username) {
      showMsg("❌ user_id 和 username 不能为空", "error");
      return;
    }
    try {
      const r = await adminFetch(`${API_BASE}/v2/admin/users/upsert`, {
        method: "POST",
        body: JSON.stringify(newUser),
      });
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || "upsert failed");
      }
      showMsg(`✅ 用户 ${newUser.user_id} 已创建/更新`, "success");
      setShowAdd(false);
      setNewUser({ user_id: "", username: "", role: "user" });
      load();
    } catch (e) {
      showMsg(`❌ ${e.message}`, "error");
    }
  };

  return (
    <div className="glass-panel p-4 rounded-lg">
      <div className="flex items-center justify-between mb-4 border-b border-cyan-900/50 pb-2">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm flex items-center gap-2">
          <UsersIcon size={16} />
          用户管理 (RBAC)
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-cyan-600 font-mono">{users.length} 个用户</span>
          <button onClick={load} className="p-1 hover:bg-cyan-900/40 rounded">
            <RefreshCw size={12} className={`text-cyan-500 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="flex items-center gap-1 px-2 py-1 bg-cyan-800 hover:bg-cyan-700 text-cyan-100 rounded text-[10px]"
          >
            <Plus size={11} />新增用户
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

      {showAdd && (
        <div className="bg-slate-900/80 border border-cyan-700/50 rounded p-3 mb-4">
          <div className="text-xs text-cyan-500 mb-2 font-bold">新增 / 批量注册用户</div>
          <div className="grid grid-cols-3 gap-2 mb-2">
            <input
              value={newUser.user_id}
              onChange={e => setNewUser({ ...newUser, user_id: e.target.value })}
              placeholder="user_id"
              className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-[11px]"
            />
            <input
              value={newUser.username}
              onChange={e => setNewUser({ ...newUser, username: e.target.value })}
              placeholder="username"
              className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-[11px]"
            />
            <select
              value={newUser.role}
              onChange={e => setNewUser({ ...newUser, role: e.target.value })}
              className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-[11px]"
            >
              <option value="guest">guest</option>
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <div className="flex gap-2">
            <button
              onClick={addUser}
              className="flex items-center gap-1 px-3 py-1 bg-green-700 hover:bg-green-600 text-white rounded text-[11px]"
            >
              <Plus size={11} />确认创建
            </button>
            <button
              onClick={() => { setShowAdd(false); setNewUser({ user_id: "", username: "", role: "user" }); }}
              className="flex items-center gap-1 px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded text-[11px]"
            >
              <X size={11} />取消
            </button>
          </div>
        </div>
      )}

      <div className="overflow-y-auto max-h-[480px] pr-1 custom-scrollbar">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-cyan-600 text-left border-b border-cyan-900/50">
              <th className="pb-2 pr-3">用户ID</th>
              <th className="pb-2 pr-3">用户名</th>
              <th className="pb-2 pr-3">角色</th>
              <th className="pb-2 pr-3">创建时间</th>
              <th className="pb-2 pr-3">更新时间</th>
              <th className="pb-2">操作</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isEditing = editing === u.user_id;
              return (
                <tr key={u.user_id} className="border-t border-cyan-900/30 hover:bg-cyan-900/10 transition-colors">
                  <td className="py-2 pr-3 font-mono text-cyan-200 text-[11px]">{u.user_id}</td>
                  <td className="py-2 pr-3 text-slate-300 text-[11px]">{u.username}</td>
                  <td className="py-2 pr-3">
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
                      <RoleBadge role={u.role} />
                    )}
                  </td>
                  <td className="py-2 pr-3 text-slate-500 text-[10px]">
                    {new Date(u.created_at * 1000).toLocaleString()}
                  </td>
                  <td className="py-2 pr-3 text-slate-500 text-[10px]">
                    {new Date(u.updated_at * 1000).toLocaleString()}
                  </td>
                  <td className="py-2">
                    <div className="flex gap-1">
                      {isEditing ? (
                        <>
                          <button
                            onClick={() => saveEdit(u.user_id)}
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
                        </>
                      ) : (
                        <>
                          <button
                            onClick={() => startEdit(u)}
                            className="px-2 py-1 bg-cyan-900/50 hover:bg-cyan-800 text-cyan-300 rounded text-[10px]"
                          >
                            编辑
                          </button>
                          {u.user_id !== "admin" && (
                            <button
                              onClick={() => deleteUser(u.user_id)}
                              className="px-2 py-1 bg-red-900/30 hover:bg-red-900/50 text-red-400 rounded text-[10px]"
                            >
                              <Trash2 size={10} className="inline" />
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {users.length === 0 && !loading && (
          <div className="text-center py-10 text-slate-600">暂无用户</div>
        )}
      </div>
    </div>
  );
}

export default UsersPanel;
