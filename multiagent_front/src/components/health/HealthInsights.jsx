import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  Alert,
  Skeleton,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  LinearProgress,
  Avatar,
  IconButton,
  Collapse
} from '@mui/material';
import {
  Psychology as PsychologyIcon,
  TrendingUp as TrendingUpIcon,
  Warning as WarningIcon,
  CheckCircle as CheckCircleIcon,
  Info as InfoIcon,
  Lightbulb as LightbulbIcon,
  Timeline as TimelineIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
  Refresh as RefreshIcon,
  AutoAwesome as AutoAwesomeIcon
} from '@mui/icons-material';
import { healthRecordsApi } from '../../api/healthRecordsApi';

const HealthInsights = ({ apiAlive }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [insights, setInsights] = useState({});
  const [analysisType, setAnalysisType] = useState('comprehensive');
  const [expandedInsight, setExpandedInsight] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // 分析类型选项
  const analysisTypeOptions = [
    { value: 'comprehensive', label: '综合分析' },
    { value: 'trends', label: '趋势分析' },
    { value: 'risks', label: '风险评估' },
    { value: 'recommendations', label: '健康建议' }
  ];

  // 洞察类型配置
  const insightTypeConfig = {
    'trend': {
      icon: <TrendingUpIcon />,
      color: 'primary',
      title: '趋势洞察'
    },
    'warning': {
      icon: <WarningIcon />,
      color: 'warning',
      title: '健康警告'
    },
    'recommendation': {
      icon: <LightbulbIcon />,
      color: 'success',
      title: '健康建议'
    },
    'pattern': {
      icon: <TimelineIcon />,
      color: 'info',
      title: '模式识别'
    },
    'achievement': {
      icon: <CheckCircleIcon />,
      color: 'success',
      title: '健康成就'
    }
  };

  useEffect(() => {
    if (apiAlive) {
      fetchInsights();
    } else {
      setLoading(false);
    }
  }, [apiAlive, analysisType]);

  const fetchInsights = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const params = {
        analysisType,
        includeRecommendations: true,
        includeTrends: true,
        includeRisks: true
      };
      
      const response = await healthRecordsApi.getHealthInsights(params);
      setInsights(response.data || {});
      
    } catch (err) {
      setError('获取健康洞察失败: ' + (err.message || '未知错误'));
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    await fetchInsights();
    setRefreshing(false);
  };

  const toggleExpanded = (insightId) => {
    setExpandedInsight(expandedInsight === insightId ? null : insightId);
  };

  const getInsightConfig = (type) => {
    return insightTypeConfig[type] || {
      icon: <InfoIcon />,
      color: 'default',
      title: '健康洞察'
    };
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'high':
        return 'error';
      case 'medium':
        return 'warning';
      case 'low':
        return 'info';
      default:
        return 'default';
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleDateString('zh-CN');
  };

  const renderInsightCard = (insight, index) => {
    const config = getInsightConfig(insight.type);
    const isExpanded = expandedInsight === insight.id;

    return (
      <Card key={insight.id || index} sx={{ mb: 2 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 2 }}>
            <Avatar sx={{ bgcolor: `${config.color}.main`, mr: 2 }}>
              {config.icon}
            </Avatar>
            <Box sx={{ flexGrow: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Typography variant="h6" component="h3">
                  {insight.title}
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {insight.severity && (
                    <Chip 
                      label={insight.severity === 'high' ? '高' : insight.severity === 'medium' ? '中' : '低'}
                      color={getSeverityColor(insight.severity)}
                      size="small"
                    />
                  )}
                  {insight.confidence && (
                    <Chip 
                      label={`置信度 ${(insight.confidence * 100).toFixed(0)}%`}
                      variant="outlined"
                      size="small"
                    />
                  )}
                  <IconButton 
                    size="small" 
                    onClick={() => toggleExpanded(insight.id)}
                  >
                    {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                  </IconButton>
                </Box>
              </Box>
              
              <Typography variant="body1" sx={{ mt: 1 }}>
                {insight.summary}
              </Typography>
              
              {insight.tags && insight.tags.length > 0 && (
                <Box sx={{ mt: 1, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                  {insight.tags.map((tag, tagIndex) => (
                    <Chip key={tagIndex} label={tag} size="small" variant="outlined" />
                  ))}
                </Box>
              )}
            </Box>
          </Box>
          
          <Collapse in={isExpanded}>
            <Divider sx={{ mb: 2 }} />
            
            {insight.details && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  详细说明
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  {insight.details}
                </Typography>
              </Box>
            )}
            
            {insight.recommendations && insight.recommendations.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  建议措施
                </Typography>
                <List dense>
                  {insight.recommendations.map((rec, recIndex) => (
                    <ListItem key={recIndex}>
                      <ListItemIcon>
                        <LightbulbIcon color="primary" fontSize="small" />
                      </ListItemIcon>
                      <ListItemText primary={rec} />
                    </ListItem>
                  ))}
                </List>
              </Box>
            )}
            
            {insight.relatedRecords && insight.relatedRecords.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  相关记录
                </Typography>
                <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
                  {insight.relatedRecords.map((record, recordIndex) => (
                    <Chip 
                      key={recordIndex}
                      label={record.title || record.summary || '记录'}
                      variant="outlined"
                      size="small"
                      onClick={() => {/* TODO: 跳转到记录详情 */}}
                    />
                  ))}
                </Box>
              </Box>
            )}
            
            {insight.metrics && (
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  相关指标
                </Typography>
                <Grid container spacing={2}>
                  {Object.entries(insight.metrics).map(([key, value]) => (
                    <Grid item xs={6} md={4} key={key}>
                      <Paper sx={{ p: 1, textAlign: 'center' }}>
                        <Typography variant="h6" color="primary">
                          {typeof value === 'number' ? value.toFixed(1) : value}
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                          {key}
                        </Typography>
                      </Paper>
                    </Grid>
                  ))}
                </Grid>
              </Box>
            )}
          </Collapse>
        </CardContent>
      </Card>
    );
  };

  if (!apiAlive) {
    return (
      <Alert severity="warning">
        健康档案管理服务未连接，请检查后端服务状态。
      </Alert>
    );
  }

  return (
    <Box>
      {/* 控制面板 */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} md={6}>
          <FormControl fullWidth>
            <InputLabel>分析类型</InputLabel>
            <Select
              value={analysisType}
              label="分析类型"
              onChange={(e) => setAnalysisType(e.target.value)}
            >
              {analysisTypeOptions.map(option => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} md={6}>
          <Box sx={{ display: 'flex', gap: 1, height: '100%', alignItems: 'center' }}>
            <Button
              variant="outlined"
              startIcon={refreshing ? <AutoAwesomeIcon /> : <RefreshIcon />}
              onClick={handleRefresh}
              disabled={refreshing}
            >
              {refreshing ? '分析中...' : '重新分析'}
            </Button>
          </Box>
        </Grid>
      </Grid>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {refreshing && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="body2" gutterBottom>
            正在进行智能分析...
          </Typography>
          <LinearProgress />
        </Box>
      )}

      {loading ? (
        <Box>
          {[...Array(3)].map((_, index) => (
            <Card key={index} sx={{ mb: 2 }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  <Skeleton variant="circular" width={40} height={40} sx={{ mr: 2 }} />
                  <Box sx={{ flexGrow: 1 }}>
                    <Skeleton variant="text" width="60%" height={32} />
                    <Skeleton variant="text" width="80%" height={24} />
                  </Box>
                </Box>
                <Skeleton variant="rectangular" width="100%" height={60} />
              </CardContent>
            </Card>
          ))}
        </Box>
      ) : (
        <>
          {/* 总体健康评分 */}
          {insights.healthScore && (
            <Card sx={{ mb: 3 }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  <Avatar sx={{ bgcolor: 'primary.main', mr: 2 }}>
                    <PsychologyIcon />
                  </Avatar>
                  <Typography variant="h6">
                    健康评分
                  </Typography>
                </Box>
                
                <Grid container spacing={3}>
                  <Grid item xs={12} md={4}>
                    <Box sx={{ textAlign: 'center' }}>
                      <Typography variant="h2" color="primary" gutterBottom>
                        {insights.healthScore.overall || 0}
                      </Typography>
                      <Typography variant="body1" color="textSecondary">
                        综合评分 (满分100)
                      </Typography>
                    </Box>
                  </Grid>
                  <Grid item xs={12} md={8}>
                    <Box>
                      {insights.healthScore.categories && Object.entries(insights.healthScore.categories).map(([category, score]) => (
                        <Box key={category} sx={{ mb: 2 }}>
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                            <Typography variant="body2">{category}</Typography>
                            <Typography variant="body2">{score}/100</Typography>
                          </Box>
                          <LinearProgress 
                            variant="determinate" 
                            value={score} 
                            sx={{ height: 8, borderRadius: 4 }}
                          />
                        </Box>
                      ))}
                    </Box>
                  </Grid>
                </Grid>
                
                {insights.healthScore.summary && (
                  <Alert severity="info" sx={{ mt: 2 }}>
                    {insights.healthScore.summary}
                  </Alert>
                )}
              </CardContent>
            </Card>
          )}

          {/* 洞察列表 */}
          {insights.insights && insights.insights.length > 0 ? (
            <>
              <Typography variant="h6" gutterBottom>
                智能洞察 ({insights.insights.length})
              </Typography>
              {insights.insights.map((insight, index) => renderInsightCard(insight, index))}
            </>
          ) : (
            <Paper sx={{ p: 4, textAlign: 'center' }}>
              <AutoAwesomeIcon sx={{ fontSize: 48, color: 'grey.400', mb: 2 }} />
              <Typography variant="h6" color="textSecondary" gutterBottom>
                暂无健康洞察
              </Typography>
              <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
                当您有更多健康记录时，我们将为您提供个性化的健康洞察和建议
              </Typography>
              <Button 
                variant="contained" 
                startIcon={<RefreshIcon />}
                onClick={handleRefresh}
              >
                重新分析
              </Button>
            </Paper>
          )}

          {/* 快速建议 */}
          {insights.quickTips && insights.quickTips.length > 0 && (
            <Card sx={{ mt: 3 }}>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  每日健康小贴士
                </Typography>
                <List>
                  {insights.quickTips.map((tip, index) => (
                    <React.Fragment key={index}>
                      <ListItem>
                        <ListItemIcon>
                          <LightbulbIcon color="primary" />
                        </ListItemIcon>
                        <ListItemText 
                          primary={tip.title}
                          secondary={tip.description}
                        />
                      </ListItem>
                      {index < insights.quickTips.length - 1 && <Divider />}
                    </React.Fragment>
                  ))}
                </List>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </Box>
  );
};

export default HealthInsights;
