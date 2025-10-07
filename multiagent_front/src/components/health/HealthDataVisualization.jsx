import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Paper,
  Grid,
  Card,
  CardContent,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Alert,
  Skeleton,
  Chip,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider
} from '@mui/material';
import {
  TrendingUp as TrendingUpIcon,
  TrendingDown as TrendingDownIcon,
  Timeline as TimelineIcon,
  Assessment as AssessmentIcon,
  Favorite as FavoriteIcon,
  MonitorHeart as MonitorHeartIcon,
  LocalHospital as LocalHospitalIcon
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area
} from 'recharts';
import { healthRecordsApi } from '../../api/healthRecordsApi';

const HealthDataVisualization = ({ apiAlive }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState('6months');
  const [dataType, setDataType] = useState('all');
  
  // 图表数据
  const [trendData, setTrendData] = useState([]);
  const [categoryData, setCategoryData] = useState([]);
  const [summaryStats, setSummaryStats] = useState({});
  const [recentRecords, setRecentRecords] = useState([]);

  // 时间范围选项
  const timeRangeOptions = [
    { value: '1month', label: '最近1个月' },
    { value: '3months', label: '最近3个月' },
    { value: '6months', label: '最近6个月' },
    { value: '1year', label: '最近1年' },
    { value: 'all', label: '全部时间' }
  ];

  // 数据类型选项
  const dataTypeOptions = [
    { value: 'all', label: '全部数据' },
    { value: 'vital_signs', label: '生命体征' },
    { value: 'lab_result', label: '化验结果' },
    { value: 'medication', label: '用药记录' },
    { value: 'medical_report', label: '体检报告' }
  ];

  // 图表颜色配置
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8', '#82CA9D'];

  useEffect(() => {
    if (apiAlive) {
      fetchVisualizationData();
    } else {
      setLoading(false);
    }
  }, [apiAlive, timeRange, dataType]);

  const fetchVisualizationData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const params = {
        timeRange,
        dataType: dataType !== 'all' ? dataType : undefined
      };
      
      const response = await healthRecordsApi.getVisualizationData(params);
      const data = response.data;
      
      setTrendData(data.trendData || []);
      setCategoryData(data.categoryData || []);
      setSummaryStats(data.summaryStats || {});
      setRecentRecords(data.recentRecords || []);
      
    } catch (err) {
      setError('获取可视化数据失败: ' + (err.message || '未知错误'));
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleDateString('zh-CN', {
      month: 'short',
      day: 'numeric'
    });
  };

  const getRecordTypeIcon = (type) => {
    switch (type) {
      case 'vital_signs':
        return <MonitorHeartIcon />;
      case 'lab_result':
        return <AssessmentIcon />;
      case 'medication':
        return <LocalHospitalIcon />;
      default:
        return <FavoriteIcon />;
    }
  };

  const getRecordTypeLabel = (type) => {
    const typeMap = {
      'medical_report': '体检报告',
      'prescription': '处方单',
      'lab_result': '化验结果',
      'imaging': '影像检查',
      'diagnosis': '诊断记录',
      'surgery': '手术记录',
      'vaccination': '疫苗接种',
      'allergy': '过敏记录',
      'medication': '用药记录',
      'vital_signs': '生命体征',
      'other': '其他'
    };
    return typeMap[type] || type;
  };

  const getTrendIcon = (trend) => {
    if (trend > 0) {
      return <TrendingUpIcon color="success" />;
    } else if (trend < 0) {
      return <TrendingDownIcon color="error" />;
    } else {
      return <TimelineIcon color="info" />;
    }
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
            <InputLabel>时间范围</InputLabel>
            <Select
              value={timeRange}
              label="时间范围"
              onChange={(e) => setTimeRange(e.target.value)}
            >
              {timeRangeOptions.map(option => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} md={6}>
          <FormControl fullWidth>
            <InputLabel>数据类型</InputLabel>
            <Select
              value={dataType}
              label="数据类型"
              onChange={(e) => setDataType(e.target.value)}
            >
              {dataTypeOptions.map(option => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
      </Grid>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Grid container spacing={3}>
          {[...Array(6)].map((_, index) => (
            <Grid item xs={12} md={6} lg={4} key={index}>
              <Card>
                <CardContent>
                  <Skeleton variant="text" width="60%" height={32} />
                  <Skeleton variant="rectangular" width="100%" height={200} sx={{ mt: 2 }} />
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      ) : (
        <Grid container spacing={3}>
          {/* 统计概览 */}
          <Grid item xs={12}>
            <Typography variant="h6" gutterBottom>
              数据概览
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6} md={3}>
                <Card>
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="primary">
                      {summaryStats.totalRecords || 0}
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      总记录数
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card>
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="success.main">
                      {summaryStats.thisMonthRecords || 0}
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      本月新增
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card>
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4" color="warning.main">
                      {summaryStats.criticalRecords || 0}
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                      重要记录
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} sm={6} md={3}>
                <Card>
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', mb: 1 }}>
                      {getTrendIcon(summaryStats.trend || 0)}
                      <Typography variant="h4" sx={{ ml: 1 }}>
                        {Math.abs(summaryStats.trend || 0).toFixed(1)}%
                      </Typography>
                    </Box>
                    <Typography variant="body2" color="textSecondary">
                      增长趋势
                    </Typography>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          </Grid>

          {/* 时间趋势图 */}
          <Grid item xs={12} lg={8}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  记录趋势
                </Typography>
                {trendData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <AreaChart data={trendData}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis 
                        dataKey="date" 
                        tickFormatter={formatDate}
                      />
                      <YAxis />
                      <Tooltip 
                        labelFormatter={(value) => `日期: ${formatDate(value)}`}
                        formatter={(value, name) => [value, '记录数量']}
                      />
                      <Area 
                        type="monotone" 
                        dataKey="count" 
                        stroke="#8884d8" 
                        fill="#8884d8" 
                        fillOpacity={0.3}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <Box sx={{ textAlign: 'center', py: 4 }}>
                    <Typography variant="body2" color="textSecondary">
                      暂无趋势数据
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* 记录类型分布 */}
          <Grid item xs={12} lg={4}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  记录类型分布
                </Typography>
                {categoryData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={300}>
                    <PieChart>
                      <Pie
                        data={categoryData}
                        cx="50%"
                        cy="50%"
                        labelLine={false}
                        label={({ name, percent }) => `${getRecordTypeLabel(name)} ${(percent * 100).toFixed(0)}%`}
                        outerRadius={80}
                        fill="#8884d8"
                        dataKey="value"
                      >
                        {categoryData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value, name) => [value, getRecordTypeLabel(name)]} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <Box sx={{ textAlign: 'center', py: 4 }}>
                    <Typography variant="body2" color="textSecondary">
                      暂无分类数据
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* 最近记录 */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  最近记录
                </Typography>
                {recentRecords.length > 0 ? (
                  <List>
                    {recentRecords.slice(0, 5).map((record, index) => (
                      <React.Fragment key={record.id}>
                        <ListItem>
                          <ListItemIcon>
                            {getRecordTypeIcon(record.record_type)}
                          </ListItemIcon>
                          <ListItemText
                            primary={record.title || record.summary || '无标题'}
                            secondary={
                              <Box>
                                <Typography variant="caption" display="block">
                                  {getRecordTypeLabel(record.record_type)} • {formatDate(record.created_at)}
                                </Typography>
                                {record.tags && record.tags.length > 0 && (
                                  <Box sx={{ mt: 0.5 }}>
                                    {record.tags.slice(0, 2).map((tag, tagIndex) => (
                                      <Chip 
                                        key={tagIndex} 
                                        label={tag} 
                                        size="small" 
                                        variant="outlined"
                                        sx={{ mr: 0.5, fontSize: '0.7rem', height: 20 }}
                                      />
                                    ))}
                                  </Box>
                                )}
                              </Box>
                            }
                          />
                        </ListItem>
                        {index < Math.min(recentRecords.length, 5) - 1 && <Divider />}
                      </React.Fragment>
                    ))}
                  </List>
                ) : (
                  <Box sx={{ textAlign: 'center', py: 4 }}>
                    <Typography variant="body2" color="textSecondary">
                      暂无最近记录
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* 重要性分布 */}
          <Grid item xs={12} md={6}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  重要性分布
                </Typography>
                {summaryStats.importanceDistribution ? (
                  <ResponsiveContainer width="100%" height={250}>
                    <BarChart data={[
                      { name: '低', value: summaryStats.importanceDistribution.low || 0, fill: '#4CAF50' },
                      { name: '中', value: summaryStats.importanceDistribution.medium || 0, fill: '#2196F3' },
                      { name: '高', value: summaryStats.importanceDistribution.high || 0, fill: '#FF9800' },
                      { name: '紧急', value: summaryStats.importanceDistribution.critical || 0, fill: '#F44336' }
                    ]}>
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis dataKey="name" />
                      <YAxis />
                      <Tooltip />
                      <Bar dataKey="value" />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <Box sx={{ textAlign: 'center', py: 4 }}>
                    <Typography variant="body2" color="textSecondary">
                      暂无重要性数据
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  );
};

export default HealthDataVisualization;
