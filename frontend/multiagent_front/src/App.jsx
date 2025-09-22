import React from 'react';
import { RecoilRoot } from 'recoil';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Home from './pages/Home';
import AgentListPage from './pages/AgentListPage';
import StartConversationPage from './pages/StartConversationPage';
import ConversationPage from './pages/ConversationPage';
import EventPage from './pages/EventPage';
import Settings from './pages/Settings';
import TasksPage from './pages/TasksPage';

// 健康助手应用页面
import Dashboard from './pages/Dashboard';
import HealthRecords from './pages/HealthRecords';
import Consultation from './pages/Consultation';
import Medication from './pages/Medication';
import Summary from './pages/Summary';
import AgentChat from './pages/AgentChat';
import TestChat from './pages/TestChat';

// 组件
import ProtectedRoute from './components/ProtectedRoute';
import NotificationSnackbar from './components/NotificationSnackbar';
import SmartChat from './components/SmartChat';
import Login from './components/Login';
import Register from './components/Register';
import { AuthProvider } from './contexts/AuthContext';


const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: 8,
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
        },
      },
    },
  },
});

function App() {
  return (
    <RecoilRoot>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <AuthProvider>
          <Router>
          <Routes>
            {/* 健康助手应用路由 */}
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={
              <ProtectedRoute>
                <Dashboard />
              </ProtectedRoute>
            } />
            <Route path="/health-records" element={
              <ProtectedRoute>
                <HealthRecords />
              </ProtectedRoute>
            } />
            <Route path="/consultation" element={
              <ProtectedRoute>
                <Consultation />
              </ProtectedRoute>
            } />
            <Route path="/medication" element={
              <ProtectedRoute>
                <Medication />
              </ProtectedRoute>
            } />
            <Route path="/summary" element={
              <ProtectedRoute>
                <Summary />
              </ProtectedRoute>
            } />
            <Route path="/smart-chat" element={
              <ProtectedRoute>
                <SmartChat />
              </ProtectedRoute>
            } />
            <Route path="/agent-chat" element={
              <ProtectedRoute>
                <AgentChat />
              </ProtectedRoute>
            } />
            <Route path="/test-chat" element={<TestChat />} />
            <Route path="/register" element={<Register />} />
            
            {/* 原有的多智能体系统路由 */}
            <Route path="/home" element={<Home />} />
            <Route path="/agents" element={<AgentListPage />} />
            <Route path="/start_conversations" element={<StartConversationPage />} />
            <Route path="/conversations" element={<ConversationPage />} />
            <Route path="/events" element={<EventPage />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/tasks" element={<TasksPage />} />
            
            {/* 默认重定向到仪表板 */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            
            {/* 404页面 */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
          
          {/* 全局通知组件 */}
          <NotificationSnackbar />
          </Router>
        </AuthProvider>
      </ThemeProvider>
    </RecoilRoot>
  );
}

export default App;
