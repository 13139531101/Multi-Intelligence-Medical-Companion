import React from 'react';
import { RecoilRoot } from 'recoil';
import { CssBaseline, ThemeProvider, createTheme } from '@mui/material';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Home from './pages/Home';
import AgentListPage from './pages/AgentListPage';
import StartConversationPage from './pages/StartConversationPage';
import ConversationPage from './pages/ConversationPage';
import EventPage from './pages/EventPage';
import Settings from './pages/Settings';
import TasksPage from './pages/TasksPage';
import HealthRecordsPage from './pages/HealthRecordsPage';
import PhotosPage from './pages/PhotosPage';


const theme = createTheme({
  palette: {
    mode: 'light',
  },
});

function App() {
  return (
    <RecoilRoot>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <Router>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/agents" element={<AgentListPage />} />
            <Route path="/start_conversations" element={<StartConversationPage />} />
            <Route path="/conversations" element={<ConversationPage />} />
            <Route path="/events" element={<EventPage />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/tasks" element={<TasksPage />} />
            <Route path="/health-records" element={<HealthRecordsPage />} />
            <Route path="/photos" element={<PhotosPage />} />
          </Routes>
        </Router>
      </ThemeProvider>
    </RecoilRoot>
  );
}

export default App;
