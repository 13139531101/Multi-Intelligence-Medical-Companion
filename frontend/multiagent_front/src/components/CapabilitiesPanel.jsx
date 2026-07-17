// 阶段41-3 业务端: 显示可用 Tools / Skills / MCPs
import React, { useState, useEffect } from "react";
import { Wrench, Brain, Plug, RefreshCw } from "lucide-react";

const SERVER_URL = import.meta.env.VITE_HOSTAGENT_API || 'http://127.0.0.1:13002';

export default function CapabilitiesPanel() {
  const [tools, setTools] = useState([]);
  const [skills, setSkills] = useState([]);
  const [mcps, setMcps] = useState([]);
  const [activeTab, setActiveTab] = useState("tools");
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [t, s, m] = await Promise.all([
        fetch(`${SERVER_URL}/v2/tools`).then(r => r.json()),
        fetch(`${SERVER_URL}/v2/registry/skills`).then(r => r.json()),
        fetch(`${SERVER_URL}/v2/registry/mcp/servers`).then(r => r.json()),
      ]);
      setTools(t.tools || []);
      setSkills((s.skills || []).filter(x => x.enabled));
      setMcps((m.servers || []).filter(x => x.status !== 'disabled'));
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="bg-white rounded-lg shadow p-4 max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-800">🛠️ 系统能力</h2>
        <button
          onClick={load}
          className="flex items-center gap-1 px-3 py-1 bg-gray-100 rounded hover:bg-gray-200 text-sm"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          刷新
        </button>
      </div>

      <div className="flex gap-2 mb-4 border-b">
        {[
          { key: "tools", label: `工具 (${tools.length})`, icon: Wrench },
          { key: "skills", label: `Skills (${skills.length})`, icon: Brain },
          { key: "mcps", label: `MCPs (${mcps.length})`, icon: Plug },
        ].map(t => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setActiveTab(t.key)}
              className={`px-4 py-2 flex items-center gap-2 border-b-2 transition-colors ${
                activeTab === t.key
                  ? "border-blue-500 text-blue-600"
                  : "border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              <Icon size={16} /> {t.label}
            </button>
          );
        })}
      </div>

      {/* Tools（只读 - 内置） */}
      {activeTab === "tools" && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500 mb-2">
            🔒 工具是内置的，仅可查看统计，不能修改
          </p>
          {tools.map(t => (
            <div key={t.name} className="p-3 border border-gray-200 rounded hover:border-blue-300">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-mono font-semibold text-sm text-gray-800">🔧 {t.name}</div>
                  <div className="text-xs text-gray-600 mt-1">{t.description}</div>
                </div>
                <span className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded">
                  {t.category}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                <span>📞 {t.stats?.call_count || 0} 调用</span>
                <span>❌ {t.stats?.error_count || 0} 错</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Skills */}
      {activeTab === "skills" && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500 mb-2">
            ✨ Skills 是由系统自动匹配的，当你说的话包含相关关键词时会自动启用
          </p>
          {skills.map(s => (
            <div key={s.name} className={`p-3 border rounded ${s.enabled ? 'border-gray-200 hover:border-blue-300' : 'border-gray-100 opacity-50'}`}>
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-semibold text-sm text-gray-800">
                    <span className="mr-2">{s.icon}</span>
                    {s.display_name}
                    {s.enabled && <span className="ml-2 text-[10px] text-green-600">●启用</span>}
                  </div>
                  <div className="text-xs text-gray-600 mt-1">{s.description}</div>
                </div>
                <span className="px-2 py-0.5 bg-purple-50 text-purple-700 text-xs rounded">
                  P{s.priority}
                </span>
              </div>
              <div className="flex flex-wrap gap-1 mt-2">
                {(s.tools || []).map(t => (
                  <span key={t} className="px-1.5 py-0.5 bg-gray-100 text-gray-700 text-[10px] rounded font-mono">
                    🔧 {t}
                  </span>
                ))}
              </div>
              <div className="text-[10px] text-gray-400 mt-2">
                触发: {(s.keywords || []).slice(0, 5).join(", ")}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* MCPs */}
      {activeTab === "mcps" && (
        <div className="space-y-2">
          <p className="text-xs text-gray-500 mb-2">
            🔌 MCP 是 Model Context Protocol 工具（本地 + 远程）
          </p>
          {mcps.map(m => (
            <div key={m.name} className="p-3 border border-gray-200 rounded hover:border-blue-300">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-semibold text-sm text-gray-800">
                    <span className="mr-2">{m.icon}</span>
                    {m.display_name}
                  </div>
                  <div className="text-[10px] text-gray-500 font-mono mt-1">
                    {m.name} | {m.type} {m.url ? `| ${m.url}` : ""}
                  </div>
                  <div className="text-xs text-gray-600 mt-1">{m.description}</div>
                </div>
                <span className={`px-2 py-0.5 text-xs rounded ${
                  m.status === 'connected' ? 'bg-green-50 text-green-700' :
                  m.status === 'failed' ? 'bg-red-50 text-red-700' :
                  'bg-gray-100 text-gray-700'
                }`}>
                  {m.status === 'connected' ? '●' : '○'} {m.status}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
                <span>🔧 {(m.tools || []).length} 工具</span>
                <span>📞 {m.call_count} 调用</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}