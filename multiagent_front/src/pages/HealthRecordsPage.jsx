import React, { useState, useEffect } from 'react';
import {
  Box,
  Container,
  Typography,
  Tabs,
  Tab,
  Paper,
  Alert,
  CircularProgress
} from '@mui/material';
import Header from './Header';
import HealthRecordsList from '../components/health/HealthRecordsList';
import HealthRecordsUpload from '../components/health/HealthRecordsUpload';
import HealthDataVisualization from '../components/health/HealthDataVisualization';
import HealthInsights from '../components/health/HealthInsights';
import { checkApiStatus } from '../api/api';

function TabPanel({ children, value, index, ...other }) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`health-tabpanel-${index}`}
      aria-labelledby={`health-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ p: 3 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

function a11yProps(index) {
  return {
    id: `health-tab-${index}`,
    'aria-controls': `health-tabpanel-${index}`,
  };
}

const HealthRecordsPage = () => {
  const [tabValue, setTabValue] = useState(0);
  const [apiAlive, setApiAlive] = useState(true);
  const [loading, setLoading] = useState(true);
  const [showApiAlert, setShowApiAlert] = useState(false);

  useEffect(() => {
    const checkApi = async () => {
      setLoading(true);
      const isAlive = await checkApiStatus();
      setApiAlive(isAlive);
      setShowApiAlert(!isAlive);
      setLoading(false);
    };

    checkApi();
  }, []);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 flex flex-col">
        <Header />
        <Container maxWidth="lg" sx={{ mt: 4, mb: 4, flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <CircularProgress size={60} />
        </Container>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      <Header />

      <Container maxWidth="lg" sx={{ mt: 4, mb: 4, flexGrow: 1 }}>
        {showApiAlert && (
          <Alert severity="error" sx={{ mb: 3 }}>
            <strong>警告!</strong> 健康档案管理服务未启动，请先启动后端服务。
          </Alert>
        )}

        <Paper elevation={3} sx={{ borderRadius: 2 }}>
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Typography variant="h4" component="h1" sx={{ p: 3, pb: 2, fontWeight: 'bold', color: 'primary.main' }}>
              健康档案管理
            </Typography>

            <Tabs
              value={tabValue}
              onChange={handleTabChange}
              aria-label="健康档案管理标签页"
              sx={{ px: 3 }}
            >
              <Tab label="档案列表" {...a11yProps(0)} />
              <Tab label="上传档案" {...a11yProps(1)} />
              <Tab label="数据分析" {...a11yProps(2)} />
              <Tab label="健康洞察" {...a11yProps(3)} />
            </Tabs>
          </Box>

          <TabPanel value={tabValue} index={0}>
            <HealthRecordsList apiAlive={apiAlive} />
          </TabPanel>

          <TabPanel value={tabValue} index={1}>
            <HealthRecordsUpload apiAlive={apiAlive} />
          </TabPanel>

          <TabPanel value={tabValue} index={2}>
            <HealthDataVisualization apiAlive={apiAlive} />
          </TabPanel>

          <TabPanel value={tabValue} index={3}>
            <HealthInsights apiAlive={apiAlive} />
          </TabPanel>
        </Paper>
      </Container>
    </div>
  );
};

export default HealthRecordsPage;
