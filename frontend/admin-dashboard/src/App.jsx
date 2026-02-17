import React, { useState, useEffect, useCallback } from "react";
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
} from "lucide-react";
import {
  LineChart,
  Line,
  ResponsiveContainer,
} from "recharts";

// API Base URL (proxied via Vite in dev, Nginx in prod)
const API_BASE = "/api";

const DashboardCard = ({ title, children, icon: Icon, className = "" }) => (
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

function App() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  // Default to 'admin123' if not set, to match docker-compose default
  const [adminToken, setAdminToken] = useState(
    localStorage.getItem("adminToken") || "admin123",
  );

  // RAG Search State
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);

  // Mock Chart Data
  const [chartData] = useState([
    { name: "00:00", cpu: 10, mem: 20 },
    { name: "04:00", cpu: 15, mem: 22 },
    { name: "08:00", cpu: 45, mem: 35 },
    { name: "12:00", cpu: 30, mem: 40 },
    { name: "16:00", cpu: 60, mem: 45 },
    { name: "20:00", cpu: 25, mem: 30 },
  ]);

  const headers = adminToken ? { "X-Admin-Token": adminToken } : {};

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE}/admin/monitor/summary`, {
        headers: adminToken ? { "X-Admin-Token": adminToken } : {},
      });
      setSummary(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [adminToken]);

  useEffect(() => {
    fetchSummary();
    const interval = setInterval(fetchSummary, 30000); // Auto refresh every 30s
    return () => clearInterval(interval);
  }, [fetchSummary]);

  const handleSearch = async () => {
    if (!searchQuery) return;
    try {
      const res = await axios.post(
        `${API_BASE}/admin/rag/docs`,
        { q: searchQuery, limit: 10 },
        { headers },
      );
      setSearchResults(res.data.docs || []);
    } catch (err) {
      alert("Search failed: " + err.message);
    }
  };

  const handleDelete = async (docId) => {
    if (!confirm("Are you sure you want to delete this document?")) return;
    try {
      await axios.delete(
        `${API_BASE}/admin/medical-kb/docs/${docId}?global_kb=true`,
        { headers },
      );
      handleSearch(); // Refresh list
    } catch (err) {
      alert("Delete failed: " + err.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 p-6 flex flex-col gap-6 text-sm relative overflow-hidden">
      {/* Background Grid */}
      <div className="absolute inset-0 grid grid-cols-[repeat(20,minmax(0,1fr))] opacity-10 pointer-events-none z-0">
        {[...Array(400)].map((_, i) => (
          <div
            key={i}
            className="border border-cyan-900/20 aspect-square"
          ></div>
        ))}
      </div>

      {/* Header */}
      <header className="flex justify-between items-center z-10 border-b border-cyan-500/30 pb-4">
        <div className="flex items-center gap-3">
          <Activity className="text-cyan-400 animate-pulse" size={24} />
          <h1 className="text-2xl font-bold tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-600">
            PHA{" "}
            <span className="text-white font-mono text-lg">SYSTEM.ADMIN</span>
          </h1>
        </div>
        <div className="flex items-center gap-4">
          <input
            type="password"
            placeholder="ADMIN_TOKEN"
            value={adminToken}
            onChange={(e) => {
              setAdminToken(e.target.value);
              localStorage.setItem("adminToken", e.target.value);
            }}
            className="bg-slate-900/80 border border-cyan-800 text-cyan-100 px-3 py-1 rounded text-xs focus:outline-none focus:border-cyan-500 w-32"
          />
          <button
            onClick={fetchSummary}
            className="p-2 hover:bg-cyan-900/30 rounded-full transition-colors text-cyan-400"
          >
            <RefreshCw size={18} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
      </header>

      {/* Main Grid */}
      <main className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6 z-10 flex-1">
        {/* System Stats */}
        <DashboardCard
          title="SYSTEM METRICS"
          icon={Server}
          className="md:col-span-1 h-64 md:h-auto"
        >
          {summary?.system ? (
            <div className="space-y-3">
              <StatRow
                label="CPU Load"
                value={`${summary.system.cpu_percent}%`}
                status={summary.system.cpu_percent > 80 ? "error" : "success"}
              />
              <StatRow
                label="Memory"
                value={`${summary.system.mem_percent}%`}
              />
              <StatRow label="Disk" value={`${summary.system.disk_percent}%`} />
              <div className="mt-4 pt-4 border-t border-cyan-900/30">
                <div className="text-xs text-cyan-600 mb-1">REAL-TIME LOAD</div>
                <div className="h-24 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={chartData}>
                      <Line
                        type="monotone"
                        dataKey="cpu"
                        stroke="#06b6d4"
                        strokeWidth={2}
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="mem"
                        stroke="#8b5cf6"
                        strokeWidth={2}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          ) : (
            <div className="text-center py-10 text-slate-500">NO DATA LINK</div>
          )}
        </DashboardCard>

        {/* Database & Embedding Status */}
        <DashboardCard
          title="CORE SERVICES"
          icon={Database}
          className="md:col-span-1 h-64 md:h-auto"
        >
          <div className="space-y-4">
            <div className="glass-panel p-3 rounded bg-slate-900/80">
              <div className="flex items-center gap-2 mb-2">
                <Database size={14} className="text-cyan-400" />
                <span className="font-bold text-cyan-100">PostgreSQL</span>
              </div>
              <div className="flex items-center gap-2 text-xs">
                {summary?.db?.ok ? (
                  <CheckCircle size={12} className="text-green-400" />
                ) : (
                  <AlertCircle size={12} className="text-red-400" />
                )}
                <span
                  className={
                    summary?.db?.ok ? "text-green-400" : "text-red-400"
                  }
                >
                  {summary?.db?.ok ? "ONLINE" : "CONNECTION FAILED"}
                </span>
              </div>
              {summary?.db?.error && (
                <div className="text-[10px] text-red-400/80 mt-1 break-all">
                  {summary.db.error}
                </div>
              )}
            </div>

            <div className="glass-panel p-3 rounded bg-slate-900/80">
              <div className="flex items-center gap-2 mb-2">
                <Brain size={14} className="text-purple-400" />
                <span className="font-bold text-purple-100">
                  Embedding Model
                </span>
              </div>
              <StatRow
                label="Model"
                value={summary?.embedding?.model || "N/A"}
              />
              <StatRow
                label="Dim"
                value={summary?.embedding?.dimension || "N/A"}
              />
              <div className="flex items-center gap-2 text-xs mt-2">
                {summary?.embedding?.available ? (
                  <CheckCircle size={12} className="text-green-400" />
                ) : (
                  <AlertCircle size={12} className="text-yellow-400" />
                )}
                <span
                  className={
                    summary?.embedding?.available
                      ? "text-green-400"
                      : "text-yellow-400"
                  }
                >
                  {summary?.embedding?.available ? "READY" : "UNAVAILABLE"}
                </span>
              </div>
            </div>
          </div>
        </DashboardCard>

        {/* RAG Management */}
        <DashboardCard
          title="KNOWLEDGE BASE"
          icon={HardDrive}
          className="md:col-span-2 md:row-span-2"
        >
          <div className="flex gap-2 mb-4">
            <div className="relative flex-1">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="Search medical documents..."
                className="w-full bg-slate-900 border border-cyan-800 rounded px-3 py-2 pl-9 text-cyan-100 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50"
              />
              <Search
                size={14}
                className="absolute left-3 top-3 text-cyan-600"
              />
            </div>
            <button
              onClick={handleSearch}
              className="bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded font-bold tracking-wide transition-colors"
            >
              SCAN
            </button>
          </div>

          <div className="space-y-2 overflow-y-auto max-h-[400px] pr-2 custom-scrollbar">
            {searchResults.length === 0 ? (
              <div className="text-center py-10 text-slate-600 border border-dashed border-slate-800 rounded">
                NO DOCUMENTS FOUND
              </div>
            ) : (
              searchResults.map((doc) => (
                <div
                  key={doc.source_id}
                  className="group flex items-start justify-between p-3 bg-slate-900/40 border border-slate-800 hover:border-cyan-500/50 rounded transition-all"
                >
                  <div>
                    <div className="font-bold text-cyan-200 mb-1">
                      {doc.title || doc.source_id}
                    </div>
                    <div className="text-xs text-slate-400 font-mono">
                      ID: {doc.source_id} | Type: {doc.source_type}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-1 line-clamp-2">
                      {doc.preview}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDelete(doc.source_id)}
                    className="opacity-0 group-hover:opacity-100 p-2 text-red-400 hover:bg-red-900/20 rounded transition-all"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              ))
            )}
          </div>
        </DashboardCard>

        {/* Placeholder for future widgets */}
        <DashboardCard
          title="AGENT STATUS"
          icon={Activity}
          className="md:col-span-1 md:col-start-1 md:col-end-3 h-48"
        >
          <div className="grid grid-cols-2 gap-2 h-full">
            {[
              "Health Advisor",
              "Med Reminder",
              "Visit Summary",
              "Health Records",
            ].map((agent, i) => (
              <div
                key={i}
                className="bg-slate-900/50 border border-slate-800 p-3 rounded flex items-center justify-between"
              >
                <span className="text-xs font-mono text-cyan-300">{agent}</span>
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_5px_#22c55e]"></div>
                  <span className="text-[10px] text-green-500">ACTIVE</span>
                </div>
              </div>
            ))}
          </div>
        </DashboardCard>
      </main>
    </div>
  );
}

export default App;
