import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Paper,
  TextField,
  Button,
  Typography,
  List,
  ListItem,
  ListItemText,
  Avatar,
  Chip,
  CircularProgress,
  Alert,
  Divider,
  Card,
  CardContent,
  Grid
} from '@mui/material';
import {
  Send as SendIcon,
  SmartToy as BotIcon,
  Person as PersonIcon,
  HealthAndSafety as HealthIcon,
  MedicalServices as MedicalIcon,
  Medication as MedicationIcon,
  Assignment as AssignmentIcon
} from '@mui/icons-material';
import { smartChat } from '../api/healthApi';
import { useAuth } from '../contexts/AuthContext';

const AgentChat = () => {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selectedAgent, setSelectedAgent] = useState(null);
  const messagesEndRef = useRef(null);

  // 智能体配置
  const agents = [
    {
      name: '健康档案管理员',
      description: '管理个人健康档案和病史记录',
      icon: <HealthIcon />,
      color: '#4CAF50',
      keywords: ['档案', '病史', '记录', '健康记录', '医疗记录', '病历']
    },
    {
      name: '健康顾问',
      description: '提供个性化健康建议和医疗咨询',
      icon: <MedicalIcon />,
      color: '#2196F3',
      keywords: ['建议', '咨询', '症状', '诊断', '治疗', '健康问题', '医疗建议']
    },
    {
      name: '用药提醒助手',
      description: '管理用药计划和智能提醒',
      icon: <MedicationIcon />,
      color: '#FF9800',
      keywords: ['用药', '药物', '提醒', '服药', '药品']
    },
    {
      name: '就诊摘要生成器',
      description: '生成就诊记录摘要和医疗文档解析',
      icon: <AssignmentIcon />,
      color: '#9C27B0',
      keywords: ['摘要', '总结', '就诊', '报告', '文档', '解析']
    }
  ];

  // 示例问题
  const exampleQuestions = [
    '我想查看我的健康档案',
    '最近有头痛症状，需要一些建议',
    '帮我设置用药提醒',
    '生成我上次就诊的摘要'
  ];

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || loading) return;

    const userMessage = {
      id: Date.now(),
      text: inputMessage,
      sender: 'user',
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputMessage('');
    setLoading(true);
    setError('');

    try {
      const response = await smartChat(inputMessage);
      
      if (response.success) {
        setSelectedAgent(response.selected_agent);
        
        const botMessage = {
          id: Date.now() + 1,
          text: response.message,
          sender: 'bot',
          timestamp: new Date(),
          agent: response.selected_agent,
          conversationId: response.conversation_id,
          messageId: response.message_id
        };
        
        setMessages(prev => [...prev, botMessage]);
      } else {
        throw new Error(response.error || '请求失败');
      }
    } catch (error) {
      console.error('发送消息失败:', error);
      setError('发送消息失败，请稍后重试');
      
      const errorMessage = {
        id: Date.now() + 1,
        text: '抱歉，我现在无法处理您的请求，请稍后重试。',
        sender: 'bot',
        timestamp: new Date(),
        isError: true
      };
      
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleExampleClick = (question) => {
    setInputMessage(question);
  };

  const handleKeyPress = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      handleSendMessage();
    }
  };

  const getAgentInfo = (agentName) => {
    return agents.find(agent => agent.name === agentName);
  };

  return (
    <Box sx={{ height: '100vh', display: 'flex', flexDirection: 'column', p: 2 }}>
      {/* 页面标题 */}
      <Typography variant="h4" gutterBottom sx={{ mb: 3 }}>
        智能健康助手
      </Typography>

      {/* 智能体介绍卡片 */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {agents.map((agent, index) => (
          <Grid item xs={12} sm={6} md={3} key={index}>
            <Card 
              sx={{ 
                height: '100%',
                cursor: 'pointer',
                transition: 'all 0.3s',
                '&:hover': {
                  transform: 'translateY(-2px)',
                  boxShadow: 3
                },
                border: selectedAgent === agent.name ? `2px solid ${agent.color}` : 'none'
              }}
              onClick={() => handleExampleClick(`请${agent.name}帮助我`)}
            >
              <CardContent sx={{ textAlign: 'center' }}>
                <Avatar 
                  sx={{ 
                    bgcolor: agent.color, 
                    width: 48, 
                    height: 48, 
                    mx: 'auto', 
                    mb: 1 
                  }}
                >
                  {agent.icon}
                </Avatar>
                <Typography variant="h6" gutterBottom>
                  {agent.name}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {agent.description}
                </Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* 聊天区域 */}
      <Paper 
        elevation={3} 
        sx={{ 
          flex: 1, 
          display: 'flex', 
          flexDirection: 'column',
          overflow: 'hidden'
        }}
      >
        {/* 消息列表 */}
        <Box sx={{ flex: 1, overflow: 'auto', p: 2 }}>
          {messages.length === 0 ? (
            <Box sx={{ textAlign: 'center', mt: 4 }}>
              <BotIcon sx={{ fontSize: 64, color: 'text.secondary', mb: 2 }} />
              <Typography variant="h6" color="text.secondary" gutterBottom>
                欢迎使用智能健康助手！
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                您可以用自然语言与我们的健康专家智能体交流
              </Typography>
              
              {/* 示例问题 */}
              <Typography variant="subtitle2" sx={{ mb: 2 }}>
                试试这些问题：
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, justifyContent: 'center' }}>
                {exampleQuestions.map((question, index) => (
                  <Chip
                    key={index}
                    label={question}
                    variant="outlined"
                    clickable
                    onClick={() => handleExampleClick(question)}
                    sx={{ mb: 1 }}
                  />
                ))}
              </Box>
            </Box>
          ) : (
            <List>
              {messages.map((message) => {
                const agentInfo = message.agent ? getAgentInfo(message.agent) : null;
                
                return (
                  <ListItem
                    key={message.id}
                    sx={{
                      flexDirection: 'column',
                      alignItems: message.sender === 'user' ? 'flex-end' : 'flex-start',
                      mb: 1
                    }}
                  >
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'flex-start',
                        gap: 1,
                        maxWidth: '80%',
                        flexDirection: message.sender === 'user' ? 'row-reverse' : 'row'
                      }}
                    >
                      <Avatar
                        sx={{
                          bgcolor: message.sender === 'user' 
                            ? 'primary.main' 
                            : agentInfo?.color || 'secondary.main',
                          width: 32,
                          height: 32
                        }}
                      >
                        {message.sender === 'user' ? (
                          <PersonIcon fontSize="small" />
                        ) : (
                          agentInfo?.icon || <BotIcon fontSize="small" />
                        )}
                      </Avatar>
                      
                      <Paper
                        elevation={1}
                        sx={{
                          p: 2,
                          bgcolor: message.sender === 'user' 
                            ? 'primary.main' 
                            : message.isError 
                              ? 'error.light'
                              : 'grey.100',
                          color: message.sender === 'user' || message.isError 
                            ? 'white' 
                            : 'text.primary'
                        }}
                      >
                        {message.agent && (
                          <Chip
                            label={message.agent}
                            size="small"
                            sx={{ mb: 1, bgcolor: 'rgba(255,255,255,0.2)' }}
                          />
                        )}
                        <Typography variant="body1">
                          {message.text}
                        </Typography>
                        <Typography 
                          variant="caption" 
                          sx={{ 
                            display: 'block', 
                            mt: 1, 
                            opacity: 0.7 
                          }}
                        >
                          {message.timestamp.toLocaleTimeString()}
                        </Typography>
                      </Paper>
                    </Box>
                  </ListItem>
                );
              })}
              
              {loading && (
                <ListItem sx={{ justifyContent: 'center' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <CircularProgress size={20} />
                    <Typography variant="body2" color="text.secondary">
                      智能体正在思考...
                    </Typography>
                  </Box>
                </ListItem>
              )}
            </List>
          )}
          <div ref={messagesEndRef} />
        </Box>

        <Divider />

        {/* 错误提示 */}
        {error && (
          <Alert severity="error" sx={{ m: 2 }}>
            {error}
          </Alert>
        )}

        {/* 输入区域 */}
        <Box sx={{ p: 2 }}>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <TextField
              fullWidth
              multiline
              maxRows={4}
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="输入您的健康问题或需求..."
              disabled={loading}
              variant="outlined"
              size="small"
            />
            <Button
              variant="contained"
              onClick={handleSendMessage}
              disabled={!inputMessage.trim() || loading}
              sx={{ minWidth: 'auto', px: 2 }}
            >
              {loading ? (
                <CircularProgress size={20} color="inherit" />
              ) : (
                <SendIcon />
              )}
            </Button>
          </Box>
        </Box>
      </Paper>
    </Box>
  );
};

export default AgentChat;