// 阶段44-1: 现代化 Dashboard（深湖蓝+薄荷绿 + 大量留白 + 卡片 + 动效）
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box, Container, Grid, Card, CardContent, Typography, Button, Avatar, Chip,
  Stack, IconButton, LinearProgress, Paper, Divider, Tooltip, Badge,
} from '@mui/material';
import {
  FavoriteOutlined, MedicationOutlined, ChatOutlined, DescriptionOutlined,
  TrendingUp, TrendingDown, NotificationsNoneOutlined, AddOutlined,
  CloudUploadOutlined, EditNoteOutlined, InsightsOutlined, AccessTimeOutlined,
  SmartToyOutlined, HealthAndSafetyOutlined, FolderOpenOutlined,
  EventNoteOutlined, PsychologyOutlined, AssignmentOutlined, SpeedOutlined,
  ArrowForwardIos,
} from '@mui/icons-material';
import { getHealthData, getMedicationReminders, getConsultationHistory } from '../api/healthApi';
import { useAuth } from '../contexts/AuthContext';
import Header from '../components/HealthHeader';

// 4 个 AI 智能体配置
const AGENTS = [
  { name: '健康顾问', icon: '💬', color: '#2D7A8C', desc: '健康问答', path: '/test-chat', bg: 'linear-gradient(135deg, #2D7A8C 0%, #5BA4B5 100%)' },
  { name: '档案管理', icon: '📋', color: '#5EC5B8', desc: '病历 OCR', path: '/health-records', bg: 'linear-gradient(135deg, #5EC5B8 0%, #8DD9CE 100%)' },
  { name: '用药提醒', icon: '💊', color: '#F4A261', desc: '智能提醒', path: '/medication', bg: 'linear-gradient(135deg, #F4A261 0%, #F8C088 100%)' },
  { name: '就诊小结', icon: '📝', color: '#9B6DD7', desc: 'AI 生成', path: '/summary', bg: 'linear-gradient(135deg, #9B6DD7 0%, #B894E0 100%)' },
];

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [healthScore, setHealthScore] = useState(60);
  const [medToday, setMedToday] = useState({ taken: 3, total: 5, next: '20:00' });
  const [records, setRecords] = useState({ total: 12, reports: 5, allergies: 3, exams: 8 });
  const [conversations, setConversations] = useState([]);
  const [trends] = useState([
    { day: '周一', score: 58 }, { day: '周二', score: 62 }, { day: '周三', score: 60 },
    { day: '周四', score: 65 }, { day: '周五', score: 68 }, { day: '周六', score: 72 },
    { day: '今日', score: 60 },
  ]);
  const [tips] = useState([
    { icon: '💧', text: '您昨天饮水偏少，建议每天 1500-2000ml' },
    { icon: '🛌', text: '本周平均睡眠 6.5 小时，建议 7-8 小时' },
    { icon: '🚶', text: '您的本周步数低于平均，多多走动吧' },
  ]);

  useEffect(() => {
    (async () => {
      try {
        const [med, convs] = await Promise.all([
          getMedicationReminders({ today: true }).catch(() => null),
          getConsultationHistory({ limit: 3 }).catch(() => []),
        ]);
        if (med) setMedToday(med);
        if (convs) setConversations(convs);
      } catch (e) { /* 静默 */ }
      setLoading(false);
    })();
  }, []);

  const maxScore = Math.max(...trends.map(t => t.score));

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <Header />

      <Container maxWidth="xl" sx={{ py: 4 }}>
        {loading && <LinearProgress sx={{ mb: 2, borderRadius: 1 }} />}

        {/* 欢迎 + 时间 */}
        <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
          <Box>
            <Typography variant="h3" sx={{ fontWeight: 700, mb: 0.5 }}>
              你好，{user?.username || '朋友'} 👋
            </Typography>
            <Typography variant="body1" color="text.secondary">
              今天感觉怎么样？让我们一起管理健康
            </Typography>
          </Box>
          <Tooltip title="通知">
            <IconButton><Badge badgeContent={3} color="error"><NotificationsNoneOutlined /></Badge></IconButton>
          </Tooltip>
        </Stack>

        {/* 健康数据卡片 (2 大卡) */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          {/* 健康评分 */}
          <Grid item xs={12} md={6}>
            <Card sx={{ background: 'linear-gradient(135deg, #2D7A8C 0%, #5BA4B5 100%)', color: 'white', height: '100%' }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <FavoriteOutlined />
                    <Typography variant="body2" sx={{ opacity: 0.9 }}>健康评分</Typography>
                  </Stack>
                  <Chip
                    icon={<TrendingUp sx={{ fontSize: 14 }} />}
                    label="较昨日 +2"
                    size="small"
                    sx={{ bgcolor: 'rgba(255,255,255,0.2)', color: 'white' }}
                  />
                </Stack>
                <Stack direction="row" alignItems="baseline" spacing={1} sx={{ mb: 2 }}>
                  <Typography variant="h1" sx={{ fontWeight: 800, fontSize: '4rem' }}>{healthScore}</Typography>
                  <Typography variant="h6" sx={{ opacity: 0.8 }}>/ 100</Typography>
                </Stack>
                <Box sx={{ position: 'relative', height: 80 }}>
                  <svg viewBox="0 0 300 80" style={{ width: '100%', height: '100%' }} preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="rgba(255,255,255,0.6)" />
                        <stop offset="100%" stopColor="rgba(255,255,255,0)" />
                      </linearGradient>
                    </defs>
                    <polyline
                      points={trends.map((t, i) => `${i * 50 + 10},${80 - (t.score / 100) * 70}`).join(' ')}
                      fill="none"
                      stroke="white"
                      strokeWidth="2.5"
                    />
                    <polygon
                      points={`10,80 ${trends.map((t, i) => `${i * 50 + 10},${80 - (t.score / 100) * 70}`).join(' ')} 260,80`}
                      fill="url(#trendGrad)"
                    />
                  </svg>
                </Box>
                <Typography variant="caption" sx={{ opacity: 0.7 }}>过去 7 天趋势</Typography>
              </CardContent>
            </Card>
          </Grid>

          {/* 今日用药 */}
          <Grid item xs={12} md={6}>
            <Card sx={{ background: 'linear-gradient(135deg, #F4A261 0%, #F8C088 100%)', color: 'white', height: '100%' }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                  <Stack direction="row" alignItems="center" spacing={1}>
                    <MedicationOutlined />
                    <Typography variant="body2" sx={{ opacity: 0.9 }}>今日用药</Typography>
                  </Stack>
                  <Button
                    size="small"
                    variant="contained"
                    sx={{ bgcolor: 'rgba(255,255,255,0.2)', '&:hover': { bgcolor: 'rgba(255,255,255,0.3)' } }}
                    onClick={() => navigate('/medication')}
                  >
                    详情
                  </Button>
                </Stack>
                <Stack direction="row" alignItems="baseline" spacing={1} sx={{ mb: 2 }}>
                  <Typography variant="h1" sx={{ fontWeight: 800, fontSize: '4rem' }}>
                    {medToday.taken}
                  </Typography>
                  <Typography variant="h6" sx={{ opacity: 0.8 }}>/ {medToday.total} 已服</Typography>
                </Stack>
                <LinearProgress
                  variant="determinate"
                  value={(medToday.taken / medToday.total) * 100}
                  sx={{
                    height: 8,
                    borderRadius: 4,
                    bgcolor: 'rgba(255,255,255,0.2)',
                    mb: 1.5,
                    '& .MuiLinearProgress-bar': { bgcolor: 'white' },
                  }}
                />
                <Stack direction="row" alignItems="center" spacing={1}>
                  <AccessTimeOutlined sx={{ fontSize: 18 }} />
                  <Typography variant="body2" sx={{ opacity: 0.9 }}>
                    下次用药：<strong>{medToday.next}</strong>（硝苯地平 30mg）
                  </Typography>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        </Grid>

        {/* AI 智能体 */}
        <Paper sx={{ p: 3, mb: 3, borderRadius: 4 }}>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
            <Stack direction="row" alignItems="center" spacing={1.5}>
              <SmartToyOutlined sx={{ color: 'primary.main', fontSize: 28 }} />
              <Box>
                <Typography variant="h5" sx={{ fontWeight: 600 }}>AI 智能体</Typography>
                <Typography variant="caption" color="text.secondary">
                  4 个专业助手 · 5 个工具 · 6 个技能 · SSE 实时响应
                </Typography>
              </Box>
            </Stack>
            <Button endIcon={<ArrowForwardIos sx={{ fontSize: 14 }} />} size="small">
              全部
            </Button>
          </Stack>
          <Grid container spacing={2}>
            {AGENTS.map((agent) => (
              <Grid item xs={6} md={3} key={agent.name}>
                <Card
                  onClick={() => navigate(agent.path)}
                  sx={{
                    cursor: 'pointer',
                    background: agent.bg,
                    color: 'white',
                    height: 130,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexDirection: 'column',
                    '&:hover': { transform: 'translateY(-4px) scale(1.02)' },
                  }}
                >
                  <Typography sx={{ fontSize: '2.5rem', mb: 1 }}>{agent.icon}</Typography>
                  <Typography variant="h6" sx={{ fontWeight: 600, color: 'white' }}>{agent.name}</Typography>
                  <Typography variant="caption" sx={{ opacity: 0.9 }}>{agent.desc}</Typography>
                </Card>
              </Grid>
            ))}
          </Grid>
        </Paper>

        {/* 快速操作 + 健康档案概览 */}
        <Grid container spacing={3} sx={{ mb: 3 }}>
          {/* 快速操作 */}
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3, borderRadius: 4, height: '100%' }}>
              <Typography variant="h6" sx={{ fontWeight: 600, mb: 2 }}>
                <SpeedOutlined sx={{ verticalAlign: 'middle', mr: 1, color: 'primary.main' }} />
                快速操作
              </Typography>
              <Grid container spacing={1.5}>
                {[
                  { icon: <CloudUploadOutlined />, label: '上传病历', color: '#2D7A8C', path: '/health-records' },
                  { icon: <ChatOutlined />, label: '问 AI', color: '#5EC5B8', path: '/test-chat' },
                  { icon: <EditNoteOutlined />, label: '记录症状', color: '#F4A261', path: '/test-chat' },
                  { icon: <InsightsOutlined />, label: '健康趋势', color: '#9B6DD7', path: '/dashboard' },
                ].map((act) => (
                  <Grid item xs={6} key={act.label}>
                    <Button
                      fullWidth
                      startIcon={act.icon}
                      onClick={() => navigate(act.path)}
                      sx={{
                        bgcolor: `${act.color}10`,
                        color: act.color,
                        py: 1.5,
                        '&:hover': { bgcolor: `${act.color}20` },
                      }}
                    >
                      {act.label}
                    </Button>
                  </Grid>
                ))}
              </Grid>
            </Paper>
          </Grid>

          {/* 档案统计 */}
          <Grid item xs={12} md={6}>
            <Paper sx={{ p: 3, borderRadius: 4, height: '100%' }}>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  <FolderOpenOutlined sx={{ verticalAlign: 'middle', mr: 1, color: 'primary.main' }} />
                  健康档案
                </Typography>
                <Button size="small" onClick={() => navigate('/health-records')}>
                  查看全部
                </Button>
              </Stack>
              <Grid container spacing={2}>
                {[
                  { label: '病历', value: records.total, color: '#2D7A8C', icon: '📋' },
                  { label: '检查报告', value: records.reports, color: '#5EC5B8', icon: '🩸' },
                  { label: '过敏记录', value: records.allergies, color: '#E76F51', icon: '⚠️' },
                  { label: '检查项目', value: records.exams, color: '#9B6DD7', icon: '🔬' },
                ].map((stat) => (
                  <Grid item xs={6} key={stat.label}>
                    <Box
                      sx={{
                        p: 2,
                        borderRadius: 2,
                        bgcolor: `${stat.color}08`,
                        border: `1px solid ${stat.color}20`,
                      }}
                    >
                      <Typography variant="caption" color="text.secondary">{stat.label}</Typography>
                      <Stack direction="row" alignItems="baseline" justifyContent="space-between">
                        <Typography variant="h4" sx={{ fontWeight: 700, color: stat.color }}>
                          {stat.value}
                        </Typography>
                        <Typography sx={{ fontSize: '1.5rem' }}>{stat.icon}</Typography>
                      </Stack>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </Paper>
          </Grid>
        </Grid>

        {/* AI 智能建议 + 最近对话 */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={7}>
            <Paper sx={{ p: 3, borderRadius: 4, height: '100%' }}>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  <PsychologyOutlined sx={{ verticalAlign: 'middle', mr: 1, color: 'secondary.main' }} />
                  AI 智能建议
                </Typography>
                <Chip label="每天更新" size="small" color="secondary" variant="outlined" />
              </Stack>
              <Stack spacing={2}>
                {tips.map((tip, i) => (
                  <Box
                    key={i}
                    sx={{
                      p: 2,
                      borderRadius: 2,
                      bgcolor: 'background.default',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 2,
                    }}
                  >
                    <Typography sx={{ fontSize: '1.8rem' }}>{tip.icon}</Typography>
                    <Typography variant="body2" sx={{ flex: 1 }}>{tip.text}</Typography>
                  </Box>
                ))}
              </Stack>
            </Paper>
          </Grid>

          <Grid item xs={12} md={5}>
            <Paper sx={{ p: 3, borderRadius: 4, height: '100%' }}>
              <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  <ChatOutlined sx={{ verticalAlign: 'middle', mr: 1, color: 'primary.main' }} />
                  最近对话
                </Typography>
                <Button size="small" onClick={() => navigate('/conversations')}>
                  历史
                </Button>
              </Stack>
              {conversations.length === 0 ? (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <ChatOutlined sx={{ fontSize: 48, color: 'text.disabled', mb: 1 }} />
                  <Typography variant="body2" color="text.secondary">还没有对话</Typography>
                  <Button variant="contained" sx={{ mt: 2 }} onClick={() => navigate('/test-chat')}>
                    开始第一次对话
                  </Button>
                </Box>
              ) : (
                <Stack spacing={1}>
                  {conversations.slice(0, 3).map((c) => (
                    <Box
                      key={c.id || c.conversation_id}
                      onClick={() => navigate('/conversations/' + (c.id || c.conversation_id))}
                      sx={{
                        p: 1.5,
                        borderRadius: 2,
                        cursor: 'pointer',
                        '&:hover': { bgcolor: 'background.default' },
                      }}
                    >
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>{c.title || '新对话'}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(c.updated_at || c.created_at).toLocaleString()}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              )}
            </Paper>
          </Grid>
        </Grid>
      </Container>
    </Box>
  );
}