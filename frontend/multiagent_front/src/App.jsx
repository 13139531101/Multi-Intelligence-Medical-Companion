import React from "react";
import { RecoilRoot } from "recoil";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import Home from "./pages/Home";
import AgentListPage from "./pages/AgentListPage";
import StartConversationPage from "./pages/StartConversationPage";
import ConversationPage from "./pages/ConversationPage";
import EventPage from "./pages/EventPage";
import Settings from "./pages/Settings";
import TasksPage from "./pages/TasksPage";

// 健康助手应用页面
// 阶段48-30: 移除了 HealthRecords / Medication 两个 v1 页面的路由与 import。
// 它们此前声明在 /health-records 与 /medication 上, 而这两个路径在文件下方
// 又被声明成 <Navigate to="/v2/...">。React Router 6 是**首次声明生效**,
// 所以那两条重定向永远不可达, 老链接进的是 v1 页面 —— 与"旧路由兼容"的
// 注释意图正好相反。现在按注释意图统一: 老路径一律重定向到 v2。
import Dashboard from "./pages/Dashboard";
import Consultation from "./pages/Consultation";
import Summary from "./pages/Summary";
import TestChat from "./pages/TestChat";

// 全新设计的核心页面
import NewChat from "./pages/NewChat";
import NewHealthRecords from "./pages/NewHealthRecords";
import NewMedication from "./pages/NewMedication";
import TodayDashboard from "./pages/TodayDashboard";

// 自写 AI 浮窗 (不依赖 CopilotKit, 仅登录后显示)
import ChatPanel from "./components/ChatPanel";
// 渲染 null，但挂在 <Router> 内且始终挂载 —— 给 AI 一个可用的跳转出口
import PageRouter from "./components/PageRouter";
import { ChatProvider } from "./components/useChat.jsx";
import { AuthProvider, useAuth } from "./contexts/AuthContext";

// 通用组件
import ProtectedRoute from "./components/ProtectedRoute";
import NotificationSnackbar from "./components/NotificationSnackbar";
import Login from "./components/Login";
import Register from "./components/Register";

function AppShell() {
  const { user } = useAuth();
  return (
    <ChatProvider>
      {user && <ChatPanel />}
      <Router>
        {/* 必须在 <Router> 内部：AI 的跳转指令靠它落地 */}
        <PageRouter />
        <Routes>
          {/* 健康助手应用路由 */}
          <Route path="/login" element={<Login />} />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/consultation"
            element={
              <ProtectedRoute>
                <Consultation />
              </ProtectedRoute>
            }
          />
          <Route
            path="/summary"
            element={
              <ProtectedRoute>
                <Summary />
              </ProtectedRoute>
            }
          />
          <Route path="/test-chat" element={<TestChat />} />
          <Route path="/register" element={<Register />} />

          {/* 全新设计页面 */}
          <Route
            path="/v2/dashboard"
            element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/v2/today"
            element={
              <ProtectedRoute>
                <TodayDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/v2/chat"
            element={
              <ProtectedRoute>
                <NewChat />
              </ProtectedRoute>
            }
          />
          <Route
            path="/v2/health-records"
            element={
              <ProtectedRoute>
                <NewHealthRecords />
              </ProtectedRoute>
            }
          />
          <Route
            path="/v2/medication"
            element={
              <ProtectedRoute>
                <NewMedication />
              </ProtectedRoute>
            }
          />

          {/* 旧路由兼容 */}
          <Route
            path="/health-records"
            element={<Navigate to="/v2/health-records" replace />}
          />
          <Route
            path="/medication"
            element={<Navigate to="/v2/medication" replace />}
          />
          <Route path="/chat" element={<Navigate to="/v2/chat" replace />} />

          {/* 原有的多智能体系统路由 */}
          <Route path="/home" element={<Home />} />
          <Route path="/agents" element={<AgentListPage />} />
          <Route
            path="/start_conversations"
            element={<StartConversationPage />}
          />
          <Route path="/conversations" element={<ConversationPage />} />
          <Route path="/events" element={<EventPage />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/tasks" element={<TasksPage />} />

          {/* 默认重定向 — 落回 /v2/dashboard（主页面）。
              早先之所以落到 /v2/today，是因为当时 TodayDashboard 是唯一注册了
              usePageUpdater 的页面，停在别处 PAGE_UPDATE 会被静默丢弃。
              现在 Dashboard 自己也注册了（含页面无关的 AiInfoCard），
              且注册表带待执行队列，落地页不再受这个约束。 */}
          <Route path="/" element={<Navigate to="/v2/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/v2/dashboard" replace />} />
        </Routes>

        <NotificationSnackbar />
      </Router>
    </ChatProvider>
  );
}

function App() {
  return (
    <RecoilRoot>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </RecoilRoot>
  );
}

export default App;
