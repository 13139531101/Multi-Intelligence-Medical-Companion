// 阶段41-3: Skills 管理面板（增删改）
import React, { useState, useEffect } from "react";
import { Brain, Plus, Trash2, Power, PowerOff, Sparkles } from "lucide-react";
import axios from "axios";

const API_BASE = "/api";

const DEFAULT_SKILLS = new Set([
  "health_records", "medication", "vital_signs",
  "visit_booking", "drug_query", "general_chat",
]);

function SkillsPanel() {
  const [skills, setSkills] = useState([]);
  const [filter, setFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    name: "", display_name: "", description: "", category: "custom",
    tools: "", keywords: "", priority: 50, icon: "🆕",
  });
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API_BASE}/v2/registry/skills`);
      setSkills(r.data.skills || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const toggle = async (skill, enable) => {
    const path = enable ? "enable" : "disable";
    await axios.post(`${API_BASE}/v2/registry/skills/${skill.name}/${path}`);
    load();
  };

  const remove = async (skill) => {
    if (!confirm(`确认删除 Skill "${skill.display_name}"?`)) return;
    try {
      await axios.delete(`${API_BASE}/v2/registry/skills/${skill.name}`);
      load();
    } catch (err) {
      alert("删除失败: " + (err.response?.data?.error || err.message));
    }
  };

  const create = async () => {
    if (!createForm.name || !createForm.display_name) {
      alert("name 和 display_name 不能为空");
      return;
    }
    try {
      const body = {
        ...createForm,
        tools: createForm.tools.split(/[,\s]+/).filter(Boolean),
        keywords: createForm.keywords.split(/[,\s]+/).filter(Boolean),
        priority: Number(createForm.priority),
      };
      await axios.post(`${API_BASE}/v2/registry/skills`, body);
      setShowCreate(false);
      setCreateForm({ name: "", display_name: "", description: "", category: "custom", tools: "", keywords: "", priority: 50, icon: "🆕" });
      load();
    } catch (err) {
      alert("创建失败: " + (err.response?.data?.error || err.message));
    }
  };

  const testMatch = async (skill) => {
    const r = await axios.post(`${API_BASE}/v2/skills/match`, {
      text: prompt("输入测试文本：") || "",
    });
    const matched = r.data.matched?.map(s => s.name) || [];
    alert(`匹配的 skills: ${matched.join(", ")}\n\n本 skill: ${skill.name}\n${matched.includes(skill.name) ? "✅ 匹配" : "❌ 不匹配"}`);
  };

  const filtered = skills.filter(s =>
    s.name.toLowerCase().includes(filter.toLowerCase()) ||
    s.display_name.toLowerCase().includes(filter.toLowerCase()) ||
    s.description.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="glass-panel p-4 rounded-lg">
      <div className="flex items-center justify-between mb-4 border-b border-cyan-900/50 pb-2">
        <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm flex items-center gap-2">
          <Brain size={16} />
          Skills 管理 (可增删改)
        </h3>
        <span className="flex items-center gap-2">
          <span className="text-xs text-cyan-600 font-mono">
            {skills.filter(s => s.enabled).length} / {skills.length} 启用
          </span>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs font-mono flex items-center gap-1"
          >
            <Plus size={12} /> 新建
          </button>
        </span>
      </div>

      {/* 创建表单 */}
      {showCreate && (
        <div className="bg-slate-900/80 p-3 rounded border border-cyan-700/50 mb-4">
          <div className="text-xs text-cyan-400 uppercase font-mono mb-2">
            🆕 创建自定义 Skill
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input value={createForm.name} onChange={e => setCreateForm({...createForm, name: e.target.value})}
              placeholder="id (英文，如 nutrition_advice)" className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
            <input value={createForm.display_name} onChange={e => setCreateForm({...createForm, display_name: e.target.value})}
              placeholder="显示名" className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
            <input value={createForm.icon} onChange={e => setCreateForm({...createForm, icon: e.target.value})}
              placeholder="emoji" className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
            <input value={createForm.category} onChange={e => setCreateForm({...createForm, category: e.target.value})}
              placeholder="category" className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
            <input value={createForm.priority} type="number" onChange={e => setCreateForm({...createForm, priority: e.target.value})}
              placeholder="priority (1-100)" className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
            <input value={createForm.tools} onChange={e => setCreateForm({...createForm, tools: e.target.value})}
              placeholder="tools (逗号分隔)" className="bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
            <input value={createForm.keywords} onChange={e => setCreateForm({...createForm, keywords: e.target.value})}
              placeholder="关键词 (逗号分隔)" className="md:col-span-2 bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
            <textarea value={createForm.description} onChange={e => setCreateForm({...createForm, description: e.target.value})}
              placeholder="描述" rows={2} className="md:col-span-2 bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs" />
          </div>
          <div className="flex justify-end gap-2 mt-2">
            <button onClick={() => setShowCreate(false)} className="px-3 py-1 text-xs text-slate-400">取消</button>
            <button onClick={create} className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs font-mono">创建</button>
          </div>
        </div>
      )}

      <input
        type="text"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="过滤 skill..."
        className="w-full bg-slate-900 border border-cyan-800 rounded px-3 py-2 mb-3 text-cyan-100 focus:border-cyan-400 focus:outline-none font-mono text-xs"
      />

      <div className="space-y-2 overflow-y-auto max-h-[500px] pr-2 custom-scrollbar">
        {filtered.length === 0 ? (
          <div className="text-center py-10 text-slate-600 border border-dashed border-slate-800 rounded">
            无 skill
          </div>
        ) : (
          filtered.map((s) => {
            const isDefault = DEFAULT_SKILLS.has(s.name);
            return (
              <div
                key={s.name}
                className={`group p-3 rounded transition-all border ${
                  s.enabled
                    ? "bg-slate-900/40 border-slate-800 hover:border-cyan-500/50"
                    : "bg-slate-900/20 border-slate-800/50 opacity-50"
                }`}
              >
                <div className="flex items-start justify-between mb-1">
                  <div>
                    <div className="font-bold text-cyan-200 font-mono text-sm flex items-center gap-2">
                      <span>{s.icon}</span>
                      {s.display_name}
                      <span className="text-[10px] text-cyan-600">({s.name})</span>
                      {isDefault && <span className="text-[10px] text-yellow-500">🔒 默认</span>}
                      {!s.enabled && <span className="text-[10px] text-red-500">⏸ 已禁用</span>}
                    </div>
                    <div className="text-xs text-slate-400 mt-1">{s.description}</div>
                  </div>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-all">
                    <button onClick={() => testMatch(s)} title="测试匹配" className="p-1 text-purple-300 hover:bg-purple-900/20 rounded">
                      <Sparkles size={14} />
                    </button>
                    <button onClick={() => toggle(s, !s.enabled)} title={s.enabled ? "禁用" : "启用"}
                      className="p-1 text-cyan-300 hover:bg-cyan-900/20 rounded">
                      {s.enabled ? <PowerOff size={14} /> : <Power size={14} />}
                    </button>
                    {!isDefault && (
                      <button onClick={() => remove(s)} title="删除" className="p-1 text-red-400 hover:bg-red-900/20 rounded">
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-1 mt-2">
                  {(s.tools || []).map(t => (
                    <span key={t} className="px-2 py-0.5 bg-blue-900/30 text-blue-300 text-[10px] rounded font-mono">
                      🔧 {t}
                    </span>
                  ))}
                </div>
                <div className="text-[10px] text-cyan-600 font-mono mt-2">
                  关键词: {(s.keywords || []).slice(0, 8).join(", ")} | 优先级: {s.priority}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default SkillsPanel;