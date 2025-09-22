import React, { useState, useEffect } from 'react';
import {
  Container,
  Grid,
  Card,
  CardContent,
  CardActions,
  Typography,
  Button,
  Box,
  Avatar,
  Chip,
  LinearProgress,
  Alert
} from '@mui/material';
import {
  FolderOpen,
  Chat,
  Medication,
  Assignment,
  CloudUpload,
  TrendingUp,
  Notifications,
  HealthAndSafety,
  SmartToy
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useRecoilValue } from 'recoil';
import { userState } from '../store/recoilState';
import Header from '../components/HealthHeader';
import AgentAssistant from '../components/AgentAssistant';
import { getHealthData } from '../api/healthApi';
import { useAuth } from '../contexts/AuthContext';

const Dashboard = () => {
  const [healthSummary, setHealthSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const recoilUser = useRecoilValue(userState);
  const { user: authUser, isAuthenticated } = useAuth();
  const user = authUser || recoilUser;
  const navigate = useNavigate();

  // 如果未认证，跳转到登录页
  useEffect(() => {
    if (!isAuthenticated && !localStorage.getItem('token')) {
      navigate('/login');
    }
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    const fetchHealthSummary = async () => {
      try {
        const summary = await getHealthData();
        setHealthSummary(summary);
      } catch (error) {
        console.error('获取健康摘要失败:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchHealthSummary();
  }, []);

  const quickActions = [
    {
      title: '健康档案',
      description: '管理您的医疗记录和健康档案',
      icon: <FolderOpen sx={{ fontSize: 40 }} />,
      color: '#2196F3',
      path: '/health-records',
      count: healthSummary?.recordsCount || 0
    },
    {
      title: '健康咨询',
      description: '与AI健康顾问进行智能对话',
      icon: <Chat sx={{ fontSize: 40 }} />,
      color: '#4CAF50',
      path: '/consultation',
      count: healthSummary?.consultationsCount || 0
    },
    {
      title: '用药管理',
      description: '管理药物和设置用药提醒',
      icon: <Medication sx={{ fontSize: 40 }} />,
      color: '#FF9800',
      path: '/medication',
      count: healthSummary?.medicationsCount || 0
    },
    {
      title: '就诊摘要',
      description: '生成和管理就诊摘要',
      icon: <Assignment sx={{ fontSize: 40 }} />,
      color: '#9C27B0',
      path: '/summary',
      count: healthSummary?.summariesCount || 0
    },
    {
      title: '智能聊天',
      description: '一句话调用所有健康智能体',
      icon: <SmartToy sx={{ fontSize: 40 }} />,
      color: '#E91E63',
      path: '/smart-chat',
      count: '新功能'
    }
  ];

  const recentActivities = [
    {
      type: 'upload',
      title: '上传了新的检查报告',
      time: '2小时前',
      icon: <CloudUpload />
    },
    {
      type: 'consultation',
      title: '完成了健康咨询',
      time: '1天前',
      icon: <Chat />
    },
    {
      type: 'medication',
      title: '添加了新的用药提醒',
      time: '2天前',
      icon: <Medication />
    }
  ];

  if (loading) {
    return (
      <Box sx={{ width: '100%', mt: 2 }}>
        <LinearProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ flexGrow: 1, bgcolor: '#f5f5f5', minHeight: '100vh' }}>
      <Header />
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
        {/* 欢迎区域 */}
        <Box sx={{ mb: 4 }}>
          <Grid container spacing={3} alignItems="center">
            <Grid item>
              <Avatar
                sx={{
                  width: 80,
                  height: 80,
                  bgcolor: 'primary.main',
                  fontSize: '2rem'
                }}
              >
                {user?.username?.charAt(0)?.toUpperCase() || 'U'}
              </Avatar>
            </Grid>
            <Grid item xs>
              <Typography variant="h4" gutterBottom>
                欢迎回来，{user?.username || '用户'}！
              </Typography>
              <Typography variant="body1" color="text.secondary">
                今天是管理您健康的好日子
              </Typography>
              <Box sx={{ mt: 1 }}>
                <Chip
                  icon={<HealthAndSafety />}
                  label="健康状态良好"
                  color="success"
                  variant="outlined"
                />
              </Box>
            </Grid>
          </Grid>
        </Box>

        {/* 健康提醒 */}
        {healthSummary?.hasReminders && (
          <Alert
            severity="info"
            sx={{ mb: 3 }}
            icon={<Notifications />}
          >
            您有 {healthSummary.remindersCount} 个待处理的健康提醒
          </Alert>
        )}

        {/* 快速操作 */}
        <Typography variant="h5" gutterBottom sx={{ mb: 3 }}>
          快速操作
        </Typography>
        <Grid container spacing={3} sx={{ mb: 4 }}>
          {quickActions.map((action, index) => (
            <Grid item xs={12} sm={6} md={3} key={index}>
              <Card
                sx={{
                  height: '100%',
                  cursor: 'pointer',
                  transition: 'transform 0.2s, box-shadow 0.2s',
                  '&:hover': {
                    transform: 'translateY(-4px)',
                    boxShadow: 4
                  }
                }}
                onClick={() => navigate(action.path)}
              >
                <CardContent sx={{ textAlign: 'center', pb: 1 }}>
                  <Box
                    sx={{
                      color: action.color,
                      mb: 2
                    }}
                  >
                    {action.icon}
                  </Box>
                  <Typography variant="h6" gutterBottom>
                    {action.title}
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                    {action.description}
                  </Typography>
                  <Chip
                    label={`${action.count} 项`}
                    size="small"
                    sx={{ bgcolor: action.color, color: 'white' }}
                  />
                </CardContent>
                <CardActions sx={{ justifyContent: 'center', pt: 0 }}>
                  <Button size="small" sx={{ color: action.color }}>
                    进入
                  </Button>
                </CardActions>
              </Card>
            </Grid>
          ))}
        </Grid>

        {/* 最近活动和健康趋势 */}
        <Grid container spacing={3}>
          {/* 最近活动 */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  最近活动
                </Typography>
                {recentActivities.map((activity, index) => (
                  <Box
                    key={index}
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      mb: 2,
                      p: 1,
                      borderRadius: 1,
                      bgcolor: 'grey.50'
                    }}
                  >
                    <Avatar sx={{ mr: 2, bgcolor: 'primary.main' }}>
                      {activity.icon}
                    </Avatar>
                    <Box sx={{ flexGrow: 1 }}>
                      <Typography variant="body2">
                        {activity.title}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {activity.time}
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </CardContent>
              <CardActions>
                <Button size="small" onClick={() => navigate('/activity')}>
                  查看全部
                </Button>
              </CardActions>
            </Card>
          </Grid>

          {/* 健康趋势 */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  健康趋势
                </Typography>
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <TrendingUp sx={{ fontSize: 60, color: 'success.main', mb: 2 }} />
                  <Typography variant="body1" color="text.secondary">
                    您的健康数据正在稳步改善
                  </Typography>
                  <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                    基于最近30天的数据分析
                  </Typography>
                </Box>
              </CardContent>
              <CardActions>
                <Button size="small" onClick={() => navigate('/trends')}>
                  详细分析
                </Button>
              </CardActions>
            </Card>
          </Grid>
        </Grid>
      </Container>
      
      {/* 智能助手 */}
      <AgentAssistant 
        agentType="default"
        contextPrompt="当前用户正在查看仪表板页面，可以提供关于健康数据概览、功能导航、系统使用等方面的帮助。"
        position="bottom-right"
        size="medium"
      />
    </Box>
  );
};

export default Dashboard;