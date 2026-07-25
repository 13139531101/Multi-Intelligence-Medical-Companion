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

// 阶段44: 全新设计的 4 个核心页面
import NewChat from "./pages/NewChat";
import NewHealthRecords from "./pages/NewHealthRecords";
import NewMedication from "./pages/NewMedication";
import TodayDashboard from "./pages/TodayDashboard";
// 阶段48-25: CopilotKit — AI 深度融合 (AG-UI 协议)
import { CopilotKit } from "@copilotkit/react-core";
import { CopilotPopup } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";

// 组件
import ProtectedRoute from "./components/ProtectedRoute";
import NotificationSnackbar from "./components/NotificationSnackbar";
import Login from "./components/Login";
import Register from "./components/Register";
import { AuthProvider } from "./contexts/AuthContext";

function App() {
  return (
    <RecoilRoot>
      {/* 阶段48-25: CopilotKit — AI 一直在所有页面都能用 (侧边浮窗) */}
      <CopilotKit runtimeUrl="/api/copilotkit" agent="default">
        {/* 全屏浮窗 — 默认收起, 右上角按钮触发 */}
        <CopilotPopup
          labels={{
            title: "健康小助手",
            initial: "你好, 我是你的健康助手. 可以问用药/报告/健康相关的问题.",
          }}
        />
        <AuthProvider>
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

              {/* 阶段46: 旧路由重定向到新设计页 */}
              <Route
                path="/health-records"
                element={<Navigate to="/v2/health-records" replace />}
              />
              <Route
                path="/medication"
                element={<Navigate to="/v2/medication" replace />}
              />
              <Route
                path="/chat"
                element={<Navigate to="/v2/chat" replace />}
              />

              {/* 阶段44: 全新设计页面 */}
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

              {/* 默认重定向到今天 */}
              <Route path="/" element={<Navigate to="/v2/today" replace />} />

              {/* 404页面 */}
              <Route path="*" element={<Navigate to="/v2/today" replace />} />
            </Routes>

            {/* 全局通知组件 */}
            <NotificationSnackbar />
          </Router>
        </AuthProvider>
      </CopilotKit>
    </RecoilRoot>
  );
}

export default App;
