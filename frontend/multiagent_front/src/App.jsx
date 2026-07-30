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
import Dashboard from "./pages/Dashboard";
import HealthRecords from "./pages/HealthRecords";
import Consultation from "./pages/Consultation";
import Medication from "./pages/Medication";
import Summary from "./pages/Summary";
import TestChat from "./pages/TestChat";

// 全新设计的核心页面
import NewChat from "./pages/NewChat";
import NewHealthRecords from "./pages/NewHealthRecords";
import NewMedication from "./pages/NewMedication";
import TodayDashboard from "./pages/TodayDashboard";

// 自写 AI 浮窗 (不依赖 CopilotKit, 仅登录后显示)
import ChatPanel from "./components/ChatPanel";
import { ChatProvider } from "./components/useChat.jsx";
import { PageDataProvider } from "./components/PageDataContext.jsx";
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
      <PageDataProvider>
        {user && <ChatPanel />}
        <Router>
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
              path="/health-records"
              element={
                <ProtectedRoute>
                  <HealthRecords />
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
              path="/medication"
              element={
                <ProtectedRoute>
                  <Medication />
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

            {/* 默认重定向 */}
            <Route path="/" element={<Navigate to="/v2/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/v2/dashboard" replace />} />
          </Routes>

          <NotificationSnackbar />
        </Router>
      </PageDataProvider>
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
