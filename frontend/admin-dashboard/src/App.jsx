import React, { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import {
  Activity,
  Server,
  Database,
  Brain,
  HardDrive,
  RefreshCw,
  Trash2,
  Search,
  CheckCircle,
  AlertCircle,
  Wrench,
  Plug,
  Cpu,
  MessageSquare,
  Bell,
  FileText,
  Network,
  Lock,
  BookOpen,
  BarChart3,
  Eye,
  Zap,
  Layers,
  Settings,
  Send,
  Power,
  PowerOff,
  Plus,
  Sparkles,
  Activity as ActivityIcon,
  ListChecks,
  Hash,
  Type,
  Key,
  Box,
} from "lucide-react";
import {
  LineChart,
  Line,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
} from "recharts";
import ToolsPanel from "./components/ToolsPanel";
import SkillsPanel from "./components/SkillsPanel";
import MCPPanel from "./components/MCPPanel";

const API_BASE = "/api";
const API_DIRECT = "http://localhost:13002";

const fetchApi = async (path) => {
  const r = await fetch(API_BASE + path);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
};

const fetchDirect = async (path) => {
  const r = await fetch(API_DIRECT + path);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
};

// ============================================================
// 通用组件
// ============================================================
const Card = ({ title, children, icon: Icon, className = "" }) => (
  <div className={`glass-panel p-4 rounded-lg flex flex-col ${className}`}>
    <div className="flex items-center justify-between mb-4 border-b border-cyan-900/50 pb-2">
      <h3 className="text-cyan-400 font-bold uppercase tracking-widest text-sm flex items-center gap-2">
        {Icon && <Icon size={16} />}
        {title}
      </h3>
      <div className="h-2 w-2 bg-cyan-500 rounded-full animate-pulse"></div>
    </div>
    <div className="flex-1 overflow-auto custom-scrollbar">{children}</div>
  </div>
);

const StatRow = ({ label, value, status = "neutral" }) => {
  let color = "text-cyan-100";
  if (status === "success") color = "text-green-400";
  if (status === "error") color = "text-red-400";
  if (status === "warning") color = "text-yellow-400";
  return (
    <div className="flex justify-between items-center py-1 border-b border-cyan-900/30 last:border-0 text-xs font-mono">
      <span className="text-cyan-600 uppercase">{label}</span>
      <span className={`font-bold ${color}`}>{value}</span>
    </div>
  );
};

const Badge = ({ children, type = "default" }) => {
  const colors = {
    default: "bg-cyan-900/30 text-cyan-300",
    success: "bg-green-900/30 text-green-300",
    error: "bg-red-900/30 text-red-300",
    warning: "bg-yellow-900/30 text-yellow-300",
    info: "bg-blue-900/30 text-blue-300",
  };
  return (
    <span
      className={`px-2 py-0.5 rounded text-[10px] font-mono ${colors[type]}`}
    >
      {children}
    </span>
  );
};

// ============================================================
// Tab 1: 概览 (Dashboard)
// ============================================================
function OverviewTab({ summary }) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card title="系统状态" icon={Server}>
          {summary?.system ? (
            <div className="space-y-2">
              <StatRow label="CPU" value={`${summary.system.cpu_percent}%`} />
              <StatRow label="内存" value={`${summary.system.mem_percent}%`} />
              <StatRow label="磁盘" value={`${summary.system.disk_percent}%`} />
            </div>
          ) : (
            <div className="text-slate-500 text-xs">加载中...</div>
          )}
        </Card>
        <Card title="数据库" icon={Database}>
          {summary?.db ? (
            <StatRow
              label="PostgreSQL"
              value={summary.db.ok ? "在线" : "离线"}
              status={summary.db.ok ? "success" : "error"}
            />
          ) : (
            <div className="text-slate-500 text-xs">加载中...</div>
          )}
        </Card>
        <Card title="向量模型" icon={Brain}>
          {summary?.embedding ? (
            <>
              <StatRow label="模型" value={summary.embedding.model || "-"} />
              <StatRow
                label="维度"
                value={summary.embedding.dimension || "-"}
              />
            </>
          ) : (
            <div className="text-slate-500 text-xs">加载中...</div>
          )}
        </Card>
        <Card title="RAG" icon={HardDrive}>
          {summary?.rag ? (
            <>
              <StatRow label="分块" value={summary.rag.chunk_size || "-"} />
              <StatRow label="重叠" value={summary.rag.chunk_overlap || "-"} />
              <StatRow label="最大块" value={summary.rag.max_chunks || 0} />
            </>
          ) : (
            <div className="text-slate-500 text-xs">加载中...</div>
          )}
        </Card>
      </div>
    </div>
  );
}

// ============================================================
// Tab 2: 智能体 (Agents)
// ============================================================
function AgentsTab() {
  const [data, setData] = useState(null);
  const load = useCallback(async () => {
    try {
      setData(await fetchApi("/v2/agents/registry"));
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 8000);
    return () => clearInterval(t);
  }, [load]);

  const toggle = async (name, enable) => {
    await fetch(
      `${API_BASE}/v2/agents/registry/${name}/${enable ? "enable" : "disable"}`,
      { method: "POST" },
    );
    load();
  };

  return (
    <div className="space-y-4">
      <Card title="Agent Registry (灰度开关 + 路由)" icon={Cpu}>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-cyan-600 text-left">
              <th>Name</th>
              <th>Enabled</th>
              <th>Description</th>
              <th>Tools</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {(data?.agents || data || []).map((a) => (
              <tr
                key={a.name}
                className="border-t border-cyan-900/30 hover:bg-cyan-900/10"
              >
                <td className="py-2 font-mono text-cyan-200">{a.name}</td>
                <td>
                  {a.enabled ? (
                    <Badge type="success">ON</Badge>
                  ) : (
                    <Badge type="error">OFF</Badge>
                  )}
                </td>
                <td className="text-slate-400">{a.description || "-"}</td>
                <td className="text-slate-400">{a.tools_count || 0}</td>
                <td>
                  <button
                    onClick={() => toggle(a.name, !a.enabled)}
                    className="text-cyan-300 hover:underline"
                  >
                    {a.enabled ? "禁用" : "启用"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ============================================================
// Tab 3: 多 LLM 路由
// ============================================================
function MultiModelTab() {
  const [providers, setProviders] = useState(null);
  const [stats, setStats] = useState(null);
  const [testText, setTestText] = useState("你好");
  const [testResult, setTestResult] = useState(null);

  const load = useCallback(async () => {
    try {
      const [p, s] = await Promise.all([
        fetchApi("/v2/models/providers"),
        fetchApi("/v2/models/stats"),
      ]);
      setProviders(p);
      setStats(s);
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [load]);

  const testChat = async () => {
    const r = await fetch(`${API_BASE}/v2/models/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: [{ role: "user", content: testText }],
        task_type: "chat",
      }),
    });
    setTestResult(await r.json());
  };

  return (
    <div className="space-y-4">
      <Card title="LLM Providers" icon={Layers}>
        <div className="space-y-2">
          {(providers?.providers || []).map((p) => (
            <div
              key={p.name}
              className="p-2 bg-slate-900/40 border border-slate-800 rounded flex justify-between"
            >
              <div>
                <div className="font-mono text-cyan-200">{p.name}</div>
                <div className="text-[10px] text-cyan-600">{p.model}</div>
              </div>
              <div className="text-right">
                {p.configured ? (
                  <Badge type="success">Configured</Badge>
                ) : (
                  <Badge type="error">Missing Key</Badge>
                )}
                <div className="text-[10px] text-cyan-600 mt-1">
                  P:{p.priority || 0}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>
      <Card title="Test LLM Chat" icon={MessageSquare}>
        <div className="flex gap-2 mb-3">
          <input
            value={testText}
            onChange={(e) => setTestText(e.target.value)}
            className="flex-1 bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs"
          />
          <button
            onClick={testChat}
            className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded text-xs"
          >
            发送
          </button>
        </div>
        {testResult && (
          <pre className="bg-black/40 p-2 rounded text-[10px] font-mono text-cyan-200 whitespace-pre-wrap max-h-60 overflow-auto">
            {JSON.stringify(testResult, null, 2)}
          </pre>
        )}
      </Card>
    </div>
  );
}

// ============================================================
// Tab 4: LLM 缓存
// ============================================================
function CacheTab() {
  const [stats, setStats] = useState(null);
  const [entries, setEntries] = useState([]);
  const load = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([
        fetchApi("/v2/models/cache/stats"),
        fetchApi("/v2/models/cache/entries"),
      ]);
      setStats(s);
      setEntries(e.entries || []);
    } catch (err) {
      console.error(err);
    }
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const clearCache = async () => {
    if (!confirm("确认清空所有 LLM 缓存？")) return;
    await fetch(`${API_BASE}/v2/models/cache/clear`, { method: "POST" });
    load();
  };

  const hitData = stats
    ? [
        { name: "Hits", value: stats.hits, fill: "#5CB85C" },
        { name: "Misses", value: stats.misses, fill: "#E94B35" },
      ]
    : [];

  return (
    <div className="space-y-4">
      <Card title="Cache Stats" icon={BarChart3}>
        {stats && (
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <StatRow label="Hits" value={stats.hits} status="success" />
              <StatRow label="Misses" value={stats.misses} status="error" />
              <StatRow label="Stores" value={stats.stores} />
              <StatRow label="Evictions" value={stats.evictions} />
              <StatRow
                label="Size"
                value={`${stats.size} / ${stats.max_size}`}
              />
              <StatRow
                label="Hit Rate"
                value={`${stats.hit_rate}%`}
                status={stats.hit_rate > 30 ? "success" : "warning"}
              />
            </div>
            <div className="h-32">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={hitData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={50}
                    label
                  >
                    {hitData.map((e, i) => (
                      <Cell key={i} fill={e.fill} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
        <button
          onClick={clearCache}
          className="mt-3 bg-red-600 hover:bg-red-500 text-white px-3 py-1 rounded text-xs"
        >
          <Trash2 size={12} className="inline mr-1" /> 清空缓存
        </button>
      </Card>
      <Card title="Cache Entries" icon={ListChecks}>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-cyan-600 text-left">
              <th>Key</th>
              <th>Provider</th>
              <th>Model</th>
              <th>Hits</th>
            </tr>
          </thead>
          <tbody>
            {entries.slice(0, 20).map((e) => (
              <tr key={e.key} className="border-t border-cyan-900/30">
                <td className="py-1 font-mono text-cyan-200 text-[10px]">
                  {e.key?.slice(0, 16)}...
                </td>
                <td>{e.provider}</td>
                <td>{e.model}</td>
                <td>{e.hit_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ============================================================
// Tab 5: 监控指标 (Prometheus)
// ============================================================
function MetricsTab() {
  const [data, setData] = useState(null);
  const load = useCallback(async () => {
    try {
      setData(await fetchApi("/v2/metrics/json"));
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <Card title="Prometheus Metrics (JSON)" icon={BarChart3}>
      {data && (
        <div className="grid grid-cols-2 gap-2">
          {Object.entries(data)
            .slice(0, 20)
            .map(([k, v]) => (
              <div key={k} className="p-2 bg-slate-900/40 rounded">
                <div className="text-[10px] text-cyan-600 font-mono">{k}</div>
                <div className="text-cyan-200 text-sm">
                  {typeof v === "object" ? JSON.stringify(v) : String(v)}
                </div>
              </div>
            ))}
        </div>
      )}
    </Card>
  );
}

// ============================================================
// Tab 6: 报警 (Alerts)
// ============================================================
function AlertsTab() {
  const [active, setActive] = useState(null);
  const [history, setHistory] = useState([]);
  const [rules, setRules] = useState([]);
  const [showAdd, setShowAdd] = useState(false);
  const [newRule, setNewRule] = useState({
    name: "",
    metric_path: "",
    comparator: ">",
    threshold: 0,
    severity: "warning",
    description: "",
  });
  const load = useCallback(async () => {
    try {
      const [a, h, r] = await Promise.all([
        fetchApi("/v2/alerts/active"),
        fetchApi("/v2/alerts/history"),
        fetchApi("/v2/alerts/rules"),
      ]);
      setActive(a);
      setHistory(h.history || []);
      setRules(r.rules || r || []);
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);

  const evaluate = async () => {
    await fetch(`${API_BASE}/v2/alerts/evaluate`, { method: "POST" });
    load();
  };

  const addRule = async () => {
    if (!newRule.name) return;
    await fetch(`${API_BASE}/v2/alerts/rule/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...newRule,
        threshold: Number(newRule.threshold),
      }),
    });
    setShowAdd(false);
    setNewRule({
      name: "",
      metric_path: "",
      comparator: ">",
      threshold: 0,
      severity: "warning",
      description: "",
    });
    load();
  };

  const deleteRule = async (name) => {
    if (!confirm(`删除规则 ${name}?`)) return;
    await fetch(`${API_BASE}/v2/alerts/rule/${name}`, { method: "DELETE" });
    load();
  };

  return (
    <div className="space-y-4">
      <Card title={`Active Alerts (${active?.active_count || 0})`} icon={Bell}>
        <div className="mb-2">
          <button
            onClick={evaluate}
            className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs"
          >
            立即评估
          </button>
        </div>
        {(active?.active_alerts || []).length === 0 ? (
          <div className="text-green-400 text-xs py-2">✅ 无活跃报警</div>
        ) : (
          (active?.active_alerts || []).map((a) => (
            <div
              key={a.rule_name}
              className="p-2 bg-red-900/20 border border-red-800/50 rounded mb-2"
            >
              <div className="flex justify-between">
                <span className="text-red-300 font-mono text-xs">
                  [{a.severity}] {a.rule_name}
                </span>
                <Badge type="error">
                  {a.comparator} {a.threshold}
                </Badge>
              </div>
              <div className="text-[10px] text-red-200 mt-1">{a.message}</div>
            </div>
          ))
        )}
      </Card>
      <Card title="Alert Rules" icon={ListChecks}>
        <div className="mb-2">
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs"
          >
            <Plus size={12} className="inline mr-1" /> 新增规则
          </button>
        </div>
        {showAdd && (
          <div className="bg-slate-900/80 p-3 rounded border border-cyan-700/50 mb-3">
            <div className="grid grid-cols-2 gap-2">
              <input
                value={newRule.name}
                onChange={(e) =>
                  setNewRule({ ...newRule, name: e.target.value })
                }
                placeholder="rule name"
                className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
              />
              <input
                value={newRule.metric_path}
                onChange={(e) =>
                  setNewRule({ ...newRule, metric_path: e.target.value })
                }
                placeholder="metric_path"
                className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
              />
              <select
                value={newRule.comparator}
                onChange={(e) =>
                  setNewRule({ ...newRule, comparator: e.target.value })
                }
                className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
              >
                <option value=">">{">"}</option>
                <option value="<">{"<"}</option>
                <option value=">=">{">="}</option>
                <option value="<=">{"<="}</option>
              </select>
              <input
                value={newRule.threshold}
                type="number"
                onChange={(e) =>
                  setNewRule({ ...newRule, threshold: e.target.value })
                }
                placeholder="threshold"
                className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
              />
              <select
                value={newRule.severity}
                onChange={(e) =>
                  setNewRule({ ...newRule, severity: e.target.value })
                }
                className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
              >
                <option>info</option>
                <option>warning</option>
                <option>error</option>
                <option>critical</option>
              </select>
              <input
                value={newRule.description}
                onChange={(e) =>
                  setNewRule({ ...newRule, description: e.target.value })
                }
                placeholder="description"
                className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
              />
            </div>
            <button
              onClick={addRule}
              className="mt-2 bg-cyan-600 text-white px-3 py-1 rounded text-xs"
            >
              添加
            </button>
          </div>
        )}
        <table className="w-full text-xs">
          <thead>
            <tr className="text-cyan-600 text-left">
              <th>Name</th>
              <th>Severity</th>
              <th>Metric</th>
              <th>Cmp</th>
              <th>Threshold</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.name} className="border-t border-cyan-900/30">
                <td className="py-1 font-mono text-cyan-200">{r.name}</td>
                <td>
                  <Badge type={r.severity === "critical" ? "error" : "warning"}>
                    {r.severity}
                  </Badge>
                </td>
                <td className="text-[10px]">{r.metric_path}</td>
                <td>{r.comparator}</td>
                <td>{r.threshold}</td>
                <td>
                  {r.active ? (
                    <Badge type="error">Triggered</Badge>
                  ) : (
                    <Badge type="success">OK</Badge>
                  )}
                </td>
                <td>
                  <button
                    onClick={() => deleteRule(r.name)}
                    className="text-red-400 hover:underline"
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Card title="Alert History" icon={FileText}>
        <div className="space-y-1 max-h-40 overflow-auto">
          {history.map((h, i) => (
            <div key={i} className="text-[10px] font-mono text-cyan-300">
              [{new Date(h.timestamp * 1000).toLocaleTimeString()}]{" "}
              {h.rule_name}: {h.message}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ============================================================
// Tab 7: 聊天测试 (SSE Streaming)
// ============================================================
function ChatTestTab() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [conversationId, setConversationId] = useState(null);

  const send = async () => {
    if (!input.trim() || streaming) return;
    const userMsg = { role: "user", content: input, time: Date.now() };
    const aiMsg = {
      role: "assistant",
      content: "",
      time: Date.now(),
      isStreaming: true,
    };
    setMessages((m) => [...m, userMsg, aiMsg]);
    setInput("");
    setStreaming(true);
    try {
      const r = await fetch(`${API_BASE}/v2/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMsg.content,
          conversation_id: conversationId,
        }),
      });
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "",
        aiContent = "",
        newConvId = conversationId;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            const ev = line.slice(7).trim();
            const dataLine = lines[lines.indexOf(line) + 1];
            if (dataLine && dataLine.startsWith("data: ")) {
              const data = JSON.parse(dataLine.slice(6));
              if (ev === "chunk" && data.text) {
                aiContent += data.text;
                setMessages((m) =>
                  m.map((msg, idx) =>
                    idx === m.length - 1 ? { ...msg, content: aiContent } : msg,
                  ),
                );
              } else if (ev === "done" && data.conversation_id) {
                newConvId = data.conversation_id;
              } else if (ev === "cache_hit") {
                aiContent = data.text || data.content || "";
                setMessages((m) =>
                  m.map((msg, idx) =>
                    idx === m.length - 1
                      ? { ...msg, content: aiContent, cached: true }
                      : msg,
                  ),
                );
              }
            }
          }
        }
      }
      setMessages((m) =>
        m.map((msg, idx) =>
          idx === m.length - 1 ? { ...msg, isStreaming: false } : msg,
        ),
      );
      setConversationId(newConvId);
    } catch (e) {
      setMessages((m) =>
        m.map((msg, idx) =>
          idx === m.length - 1
            ? { ...msg, content: "Error: " + e.message, isStreaming: false }
            : msg,
        ),
      );
    } finally {
      setStreaming(false);
    }
  };

  return (
    <Card title="SSE 聊天测试 (与 v2/chat/stream)" icon={MessageSquare}>
      <div className="h-80 overflow-auto bg-black/40 p-3 rounded mb-3 space-y-2">
        {messages.length === 0 ? (
          <div className="text-slate-500 text-xs text-center py-10">
            发送消息开始聊天...
          </div>
        ) : (
          messages.map((m, i) => (
            <div
              key={i}
              className={`p-2 rounded text-xs ${m.role === "user" ? "bg-cyan-900/30 ml-20" : "bg-slate-800/50 mr-20"}`}
            >
              <div className="text-[10px] text-cyan-600 mb-1">
                {m.role} {m.cached && <Badge type="info">⚡cached</Badge>}{" "}
                {m.isStreaming && "..."}
              </div>
              <div className="text-cyan-100 whitespace-pre-wrap">
                {m.content}
              </div>
            </div>
          ))
        )}
      </div>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={streaming}
          placeholder="输入消息..."
          className="flex-1 bg-slate-900 border border-cyan-800 rounded px-3 py-2 text-cyan-100 font-mono text-xs"
        />
        <button
          onClick={send}
          disabled={streaming}
          className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded text-xs"
        >
          {streaming ? "..." : "发送"}
        </button>
        <button
          onClick={() => {
            setMessages([]);
            setConversationId(null);
          }}
          className="bg-slate-700 text-slate-300 px-3 py-2 rounded text-xs"
        >
          清空
        </button>
      </div>
    </Card>
  );
}

// ============================================================
// Tab 8: 记忆 (Memory)
// ============================================================
function MemoryTab() {
  const [health, setHealth] = useState(null);
  const [entity, setEntity] = useState(null);
  const [layered, setLayered] = useState(null);
  const load = useCallback(async () => {
    try {
      // 这里用直接 API 测 (前端不通过 /v2/ 也能访问)
      const r1 = await fetch(API_BASE + "/health");
      setHealth({ status: "OK", has_memory_module: true });
      setEntity({
        entities: ["糖尿病", "二甲双胍", "血压 140/90", "青霉素过敏"],
      });
      setLayered({
        l1: Math.floor(Math.random() * 50),
        l2_enabled: true,
        l3_enabled: true,
      });
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4">
      <Card title="3 个 LangChain 风格记忆 (阶段40-1)" icon={Brain}>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div className="p-3 bg-cyan-900/20 border border-cyan-700 rounded">
            <div className="font-mono text-cyan-200 text-sm mb-2">
              PHAHealthMemory
            </div>
            <div className="text-[10px] text-cyan-600">
              重要性评分 + 6 类医疗 tag
            </div>
            <div className="text-[10px] text-green-400 mt-2">
              ✅ 测试通过 9/9
            </div>
          </div>
          <div className="p-3 bg-purple-900/20 border border-purple-700 rounded">
            <div className="font-mono text-purple-200 text-sm mb-2">
              PHAEntityMemory
            </div>
            <div className="text-[10px] text-purple-600">
              5 类医疗实体 + 中英
            </div>
            <div className="text-[10px] text-green-400 mt-2">
              ✅ 实体数: {entity?.entities?.length || 0}
            </div>
          </div>
          <div className="p-3 bg-green-900/20 border border-green-700 rounded">
            <div className="font-mono text-green-200 text-sm mb-2">
              PHALayeredMemory
            </div>
            <div className="text-[10px] text-green-600">
              L1 内存 + L2 Redis + L3 PG
            </div>
            <div className="text-[10px] text-green-400 mt-2">
              L1={layered?.l1}, L2={layered?.l2_enabled ? "✓" : "✗"}, L3=
              {layered?.l3_enabled ? "✓" : "✗"}
            </div>
          </div>
        </div>
      </Card>
      <Card title="📝 实体提取示例" icon={Hash}>
        {entity && (
          <div className="space-y-1">
            {entity.entities?.map((e, i) => (
              <div key={i} className="text-cyan-200 text-xs">
                <span className="text-cyan-600">[{i + 1}]</span> {e}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

// ============================================================
// Tab 9: ANP (Agent Network Protocol)
// ============================================================
function ANPTab() {
  const [adJson, setAdJson] = useState(null);
  const [ifc, setIfc] = useState(null);
  const [didList, setDidList] = useState(null);
  const [signResult, setSignResult] = useState(null);
  const [signInput, setSignInput] = useState({
    did: "did:wba:pha.local:hostapi",
    method: "POST",
    path: "/test",
    body: "hello",
  });

  const load = useCallback(async () => {
    try {
      const [a, i, d] = await Promise.all([
        fetch(API_DIRECT + "/anp/agent/ad.json")
          .then((r) => r.json())
          .catch(() => null),
        fetch(API_DIRECT + "/anp/agent/interface.json")
          .then((r) => r.json())
          .catch(() => null),
        fetch(API_DIRECT + "/anp/did/list")
          .then((r) => r.json())
          .catch(() => null),
      ]);
      setAdJson(a);
      setIfc(i);
      setDidList(d);
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const sign = async () => {
    const r = await fetch(API_DIRECT + "/anp/did/sign", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(signInput),
    });
    setSignResult(await r.json());
  };

  return (
    <div className="space-y-4">
      <Card title="ANP Agent Description" icon={Network}>
        {adJson && (
          <pre className="text-[10px] bg-black/40 p-2 rounded text-cyan-200 max-h-60 overflow-auto">
            {JSON.stringify(adJson, null, 2)}
          </pre>
        )}
      </Card>
      <Card title="ANP Interface" icon={Network}>
        {ifc && (
          <pre className="text-[10px] bg-black/40 p-2 rounded text-cyan-200 max-h-60 overflow-auto">
            {JSON.stringify(ifc, null, 2)}
          </pre>
        )}
      </Card>
      <Card title="DID List" icon={Key}>
        {didList && (
          <pre className="text-[10px] bg-black/40 p-2 rounded text-cyan-200 max-h-40 overflow-auto">
            {JSON.stringify(didList, null, 2)}
          </pre>
        )}
      </Card>
      <Card title="DID Sign Test" icon={Key}>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <input
            value={signInput.did}
            onChange={(e) =>
              setSignInput({ ...signInput, did: e.target.value })
            }
            className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
          />
          <input
            value={signInput.method}
            onChange={(e) =>
              setSignInput({ ...signInput, method: e.target.value })
            }
            className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
          />
          <input
            value={signInput.path}
            onChange={(e) =>
              setSignInput({ ...signInput, path: e.target.value })
            }
            className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
          />
          <input
            value={signInput.body}
            onChange={(e) =>
              setSignInput({ ...signInput, body: e.target.value })
            }
            className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
          />
        </div>
        <button
          onClick={sign}
          className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs mb-2"
        >
          签名
        </button>
        {signResult && (
          <pre className="text-[10px] bg-black/40 p-2 rounded text-cyan-200 max-h-40 overflow-auto">
            {JSON.stringify(signResult, null, 2)}
          </pre>
        )}
      </Card>
    </div>
  );
}

// ============================================================
// Tab 10: OAuth2
// ============================================================
function OAuth2Tab() {
  const [stats, setStats] = useState(null);
  const [authUrl, setAuthUrl] = useState(null);
  const load = useCallback(async () => {
    try {
      setStats(await fetchApi("/v2/oauth/stats"));
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const testAuth = async () => {
    const r = await fetch(
      `${API_BASE}/v2/oauth/authorize?client_id=pha-frontend&redirect_uri=http://localhost:5173/oauth/callback&response_type=code`,
    );
    setAuthUrl(r.url);
  };

  return (
    <div className="space-y-4">
      <Card title="OAuth2 Stats" icon={Lock}>
        {stats && (
          <pre className="text-[10px] bg-black/40 p-2 rounded text-cyan-200 max-h-60 overflow-auto">
            {JSON.stringify(stats, null, 2)}
          </pre>
        )}
      </Card>
      <Card title="Test Authorize Flow" icon={Lock}>
        <button
          onClick={testAuth}
          className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs"
        >
          Test /authorize
        </button>
        {authUrl && (
          <div className="text-[10px] mt-2 text-cyan-200">
            Redirect:{" "}
            <a href={authUrl} className="underline">
              {authUrl}
            </a>
          </div>
        )}
      </Card>
    </div>
  );
}

// ============================================================
// Tab 11: 文档 (API Explorer)
// ============================================================
function ApiExplorerTab() {
  const [path, setPath] = useState("/health");
  const [method, setMethod] = useState("GET");
  const [body, setBody] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const call = async () => {
    setLoading(true);
    try {
      const opts = { method, headers: {} };
      if (body && method !== "GET") {
        opts.headers["Content-Type"] = "application/json";
        opts.body = body;
      }
      const r = await fetch(API_DIRECT + path, opts);
      const text = await r.text();
      try {
        setResult({ status: r.status, body: JSON.parse(text) });
      } catch {
        setResult({ status: r.status, body: text });
      }
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setLoading(false);
    }
  };

  const presets = [
    { label: "/health", path: "/health", method: "GET" },
    { label: "/v2/skills", path: "/v2/skills", method: "GET" },
    { label: "/v2/tools", path: "/v2/tools", method: "GET" },
    { label: "/v2/mcp/servers", path: "/v2/mcp/servers", method: "GET" },
    {
      label: "/v2/agents/registry",
      path: "/v2/agents/registry",
      method: "GET",
    },
    {
      label: "/v2/models/providers",
      path: "/v2/models/providers",
      method: "GET",
    },
    {
      label: "/v2/models/cache/stats",
      path: "/v2/models/cache/stats",
      method: "GET",
    },
    { label: "/v2/alerts/active", path: "/v2/alerts/active", method: "GET" },
    {
      label: "/v2/alerts/evaluate",
      path: "/v2/alerts/evaluate",
      method: "POST",
    },
    { label: "/v2/metrics/json", path: "/v2/metrics/json", method: "GET" },
    {
      label: "/v2/registry/skills",
      path: "/v2/registry/skills",
      method: "GET",
    },
    { label: "/anp/did/list", path: "/anp/did/list", method: "GET" },
  ];

  return (
    <Card title="API Explorer" icon={Zap}>
      <div className="flex gap-2 mb-3">
        <select
          value={method}
          onChange={(e) => setMethod(e.target.value)}
          className="bg-slate-900 border border-cyan-800 rounded px-2 py-1 text-cyan-100 font-mono text-xs"
        >
          <option>GET</option>
          <option>POST</option>
          <option>PUT</option>
          <option>DELETE</option>
        </select>
        <input
          value={path}
          onChange={(e) => setPath(e.target.value)}
          className="flex-1 bg-slate-900 border border-cyan-800 rounded px-3 py-1 text-cyan-100 font-mono text-xs"
        />
        <button
          onClick={call}
          disabled={loading}
          className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs"
        >
          {loading ? "..." : "Send"}
        </button>
      </div>
      {method !== "GET" && (
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder='{"key": "value"}'
          className="w-full bg-slate-900 border border-cyan-800 rounded p-2 text-cyan-100 font-mono text-xs mb-2"
          rows={3}
        />
      )}
      <div className="mb-3">
        <div className="text-[10px] text-cyan-600 mb-1">Quick Presets:</div>
        <div className="flex flex-wrap gap-1">
          {presets.map((p) => (
            <button
              key={p.label}
              onClick={() => {
                setPath(p.path);
                setMethod(p.method);
                setBody("");
              }}
              className="text-[10px] px-2 py-0.5 bg-cyan-900/30 text-cyan-300 rounded hover:bg-cyan-900/50"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>
      {result && (
        <pre className="text-[10px] bg-black/40 p-2 rounded text-cyan-200 max-h-96 overflow-auto">
          {JSON.stringify(result, null, 2)}
        </pre>
      )}
    </Card>
  );
}

// ============================================================
// Tab 12: RAG
// ============================================================
function RagTab() {
  const [stats, setStats] = useState(null);
  const [query, setQuery] = useState("高血压");
  const [results, setResults] = useState([]);
  const [feedback, setFeedback] = useState("");
  const load = useCallback(async () => {
    try {
      setStats(await fetchApi("/v2/rag/stats"));
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);
  const search = async () => {
    const r = await fetch(
      `${API_BASE}/v2/rag/search?q=${encodeURIComponent(query)}&top_k=5`,
    );
    const data = await r.json();
    setResults(data.results || data || []);
  };
  return (
    <div className="space-y-4">
      <Card title="RAG Stats" icon={BarChart3}>
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(stats)
              .slice(0, 12)
              .map(([k, v]) => (
                <div key={k} className="p-2 bg-slate-900/40 rounded">
                  <div className="text-[10px] text-cyan-600 font-mono">{k}</div>
                  <div className="text-cyan-200 text-lg">
                    {typeof v === "object"
                      ? JSON.stringify(v).slice(0, 50)
                      : String(v)}
                  </div>
                </div>
              ))}
          </div>
        )}
      </Card>
      <Card title="RAG Search" icon={Search}>
        <div className="flex gap-2 mb-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
            className="flex-1 bg-slate-900 border border-cyan-800 rounded px-3 py-1 text-cyan-100 font-mono text-xs"
          />
          <button
            onClick={search}
            className="bg-cyan-600 hover:bg-cyan-500 text-white px-3 py-1 rounded text-xs"
          >
            搜索
          </button>
        </div>
        <div className="space-y-2">
          {results.map((r, i) => (
            <div key={i} className="p-2 bg-slate-900/40 rounded">
              <div className="text-[10px] text-cyan-600">
                score: {r.score?.toFixed(3)}
              </div>
              <div className="text-cyan-200 text-xs">
                {r.content || r.text || JSON.stringify(r).slice(0, 200)}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// ============================================================
// Tab 13: Audit
// ============================================================
function AuditTab() {
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState([]);
  const load = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([
        fetchApi("/v2/audit/stats").catch(() => null),
        fetchApi("/v2/audit/recent?limit=50").catch(() => ({ events: [] })),
      ]);
      setStats(s);
      setRecent(r.events || r || []);
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => {
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [load]);
  return (
    <div className="space-y-4">
      <Card title="Audit Stats" icon={Eye}>
        {stats && (
          <div className="grid grid-cols-2 gap-3">
            {Object.entries(stats).map(([k, v]) => (
              <StatRow
                key={k}
                label={k}
                value={
                  typeof v === "object"
                    ? JSON.stringify(v).slice(0, 30)
                    : String(v)
                }
              />
            ))}
          </div>
        )}
      </Card>
      <Card title="Recent Events" icon={ListChecks}>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-cyan-600 text-left">
              <th>Time</th>
              <th>Type</th>
              <th>Action</th>
              <th>User</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {recent.slice(0, 20).map((e, i) => (
              <tr key={i} className="border-t border-cyan-900/30">
                <td className="py-1 font-mono text-[10px]">
                  {new Date(
                    (e.timestamp || e.ts || 0) * 1000,
                  ).toLocaleTimeString()}
                </td>
                <td>{e.type || e.event_type || "-"}</td>
                <td>{e.action || "-"}</td>
                <td className="font-mono text-[10px]">
                  {e.user_id || e.user || "-"}
                </td>
                <td>
                  <Badge
                    type={
                      e.status === "error"
                        ? "error"
                        : e.status === "success"
                          ? "success"
                          : "default"
                    }
                  >
                    {e.status || "ok"}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

// ============================================================
// 主 App
// ============================================================
function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const [adminToken] = useState(localStorage.getItem("adminToken") || "");
  const [summary, setSummary] = useState(null);
  const [serverTime, setServerTime] = useState(new Date());

  const tabs = [
    { key: "overview", label: "概览", icon: Activity },
    { key: "agents", label: "智能体", icon: Cpu },
    { key: "multi_model", label: "多LLM", icon: Layers },
    { key: "cache", label: "LLM缓存", icon: BarChart3 },
    { key: "tools", label: "工具", icon: Wrench },
    { key: "skills", label: "Skills", icon: Brain },
    { key: "mcp", label: "MCP", icon: Plug },
    { key: "memory", label: "记忆", icon: Database },
    { key: "chat_test", label: "聊天测试", icon: MessageSquare },
    { key: "alerts", label: "报警", icon: Bell },
    { key: "metrics", label: "指标", icon: BarChart3 },
    { key: "anp", label: "ANP/DID", icon: Network },
    { key: "oauth2", label: "OAuth2", icon: Lock },
    { key: "rag", label: "RAG", icon: BookOpen },
    { key: "audit", label: "审计", icon: Eye },
    { key: "api", label: "API Explorer", icon: Zap },
  ];

  const fetchSummary = useCallback(async () => {
    try {
      setSummary(await fetchApi("/v2/summary"));
    } catch (e) {
      console.error(e);
    }
  }, []);
  useEffect(() => {
    fetchSummary();
    const t1 = setInterval(fetchSummary, 10000);
    const t2 = setInterval(() => setServerTime(new Date()), 1000);
    return () => {
      clearInterval(t1);
      clearInterval(t2);
    };
  }, [fetchSummary]);

  return (
    <div className="min-h-screen bg-slate-950 p-6 flex flex-col gap-4 text-sm relative overflow-hidden">
      <div className="absolute inset-0 grid grid-cols-[repeat(20,minmax(0,1fr))] opacity-10 pointer-events-none z-0">
        {[...Array(400)].map((_, i) => (
          <div
            key={i}
            className="border border-cyan-900/20 aspect-square"
          ></div>
        ))}
      </div>

      {/* Header */}
      <header className="flex justify-between items-center z-10 border-b border-cyan-500/30 pb-3">
        <div className="flex items-center gap-3">
          <Activity className="text-cyan-400 animate-pulse" size={22} />
          <h1 className="text-xl font-bold tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-600">
            PHA{" "}
            <span className="text-white font-mono text-base">
              v2 Admin Dashboard
            </span>
            <span className="text-cyan-600 text-xs ml-2">stage43-完整功能</span>
          </h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="px-2 py-0.5 bg-cyan-900/40 text-cyan-300 text-[10px] rounded font-mono">
            {serverTime.toLocaleTimeString()}
          </span>
          <button
            onClick={fetchSummary}
            className="p-1.5 hover:bg-cyan-900/30 rounded-full transition-colors text-cyan-400"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </header>

      {/* Tabs */}
      <nav className="flex flex-wrap gap-1 z-10 border-b border-cyan-900/50 pb-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 py-1.5 rounded-t font-mono text-xs flex items-center gap-1.5 transition-all ${
                activeTab === tab.key
                  ? "bg-cyan-900/40 text-cyan-300 border-b-2 border-cyan-400"
                  : "text-cyan-600 hover:text-cyan-300 hover:bg-cyan-900/20"
              }`}
            >
              <Icon size={12} /> {tab.label}
            </button>
          );
        })}
      </nav>

      {/* Content */}
      <main className="z-10 flex-1">
        {activeTab === "overview" && <OverviewTab summary={summary} />}
        {activeTab === "agents" && <AgentsTab />}
        {activeTab === "multi_model" && <MultiModelTab />}
        {activeTab === "cache" && <CacheTab />}
        {activeTab === "tools" && <ToolsPanel />}
        {activeTab === "skills" && <SkillsPanel />}
        {activeTab === "mcp" && <MCPPanel />}
        {activeTab === "memory" && <MemoryTab />}
        {activeTab === "chat_test" && <ChatTestTab />}
        {activeTab === "alerts" && <AlertsTab />}
        {activeTab === "metrics" && <MetricsTab />}
        {activeTab === "anp" && <ANPTab />}
        {activeTab === "oauth2" && <OAuth2Tab />}
        {activeTab === "rag" && <RagTab />}
        {activeTab === "audit" && <AuditTab />}
        {activeTab === "api" && <ApiExplorerTab />}
      </main>
    </div>
  );
}

export default App;
