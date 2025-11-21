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
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  Avatar,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Alert,
  Tabs,
  Tab,
  Divider,
  LinearProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Paper
} from '@mui/material';
import {
  Add,
  Assignment,
  AutoAwesome,
  Download,
  Share,
  Edit,
  Delete,
  Visibility,
  ExpandMore,
  LocalHospital,
  Person,
  Schedule,
  Description,
  Print,
  Email
} from '@mui/icons-material';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import dayjs from 'dayjs';
import Header from '../components/HealthHeader';
import FileUpload from '../components/FileUpload';
import AgentAssistant from '../components/AgentAssistant';
import { getSummaries, createSummary, updateSummary, deleteSummary, generateAISummary } from '../api/healthApi';

const Summary = () => {
  const [summaries, setSummaries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [openDialog, setOpenDialog] = useState(false);
  const [openAIDialog, setOpenAIDialog] = useState(false);
  const [editingSummary, setEditingSummary] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  const [selectedSummary, setSelectedSummary] = useState(null);

  const [formData, setFormData] = useState({
    title: '',
    visitDate: dayjs(),
    doctor: '',
    hospital: '',
    department: '',
    chiefComplaint: '',
    symptoms: '',
    examination: '',
    diagnosis: '',
    treatment: '',
    prescription: '',
    followUp: '',
    notes: '',
    files: [],
    tests: []
  });

  const [aiFormData, setAiFormData] = useState({
    visitDate: dayjs(),
    doctor: '',
    hospital: '',
    files: [],
    additionalInfo: ''
  });

  const departments = [
    '内科', '外科', '儿科', '妇产科', '眼科', '耳鼻喉科',
    '皮肤科', '神经科', '精神科', '骨科', '泌尿科', '心血管科',
    '呼吸科', '消化科', '内分泌科', '肿瘤科', '急诊科', '其他'
  ];

  useEffect(() => {
    fetchSummaries();
  }, []);

  const fetchSummaries = async () => {
    try {
      const data = await getSummaries();
      setSummaries(data);
    } catch (error) {
      console.error('获取就诊摘要失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    try {
      if (editingSummary) {
        await updateSummary(editingSummary.id, formData);
      } else {
        await createSummary(formData);
      }
      await fetchSummaries();
      handleCloseDialog();
    } catch (error) {
      console.error('保存就诊摘要失败:', error);
    }
  };

  const handleGenerateAISummary = async () => {
    setGenerating(true);
    try {
      const generatedSummary = await generateAISummary(aiFormData);
      
      // 将AI生成的摘要填入表单
      setFormData({
        title: generatedSummary.title || `${aiFormData.doctor} - ${dayjs(aiFormData.visitDate).format('YYYY/MM/DD')}`,
        visitDate: aiFormData.visitDate,
        doctor: aiFormData.doctor,
        hospital: aiFormData.hospital,
        department: generatedSummary.department || '',
        chiefComplaint: generatedSummary.chiefComplaint || '',
        symptoms: generatedSummary.symptoms || '',
        examination: generatedSummary.examination || '',
        diagnosis: generatedSummary.diagnosis || '',
        treatment: generatedSummary.treatment || '',
        prescription: generatedSummary.prescription || '',
        followUp: generatedSummary.followUp || '',
        notes: generatedSummary.notes || '',
        files: aiFormData.files,
        tests: Array.isArray(generatedSummary.tests) ? generatedSummary.tests : []
      });
      
      setOpenAIDialog(false);
      setOpenDialog(true);
    } catch (error) {
      console.error('AI生成摘要失败:', error);
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async (id) => {
    if (window.confirm('确定要删除这个就诊摘要吗？')) {
      try {
        await deleteSummary(id);
        await fetchSummaries();
      } catch (error) {
        console.error('删除就诊摘要失败:', error);
      }
    }
  };

  const handleOpenDialog = (summary = null) => {
    if (summary) {
      setEditingSummary(summary);
      setFormData({
        title: summary.title,
        visitDate: dayjs(summary.visitDate),
        doctor: summary.doctor,
        hospital: summary.hospital,
        department: summary.department,
        chiefComplaint: summary.chiefComplaint,
        symptoms: summary.symptoms,
        examination: summary.examination,
        diagnosis: summary.diagnosis,
        treatment: summary.treatment,
        prescription: summary.prescription,
        followUp: summary.followUp,
        notes: summary.notes,
        files: summary.files || [],
        tests: summary.tests || []
      });
    } else {
      setEditingSummary(null);
      setFormData({
        title: '',
        visitDate: dayjs(),
        doctor: '',
        hospital: '',
        department: '',
        chiefComplaint: '',
        symptoms: '',
        examination: '',
        diagnosis: '',
        treatment: '',
        prescription: '',
        followUp: '',
        notes: '',
        files: [],
        tests: []
      });
    }
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setEditingSummary(null);
  };

  const handleOpenAIDialog = () => {
    setAiFormData({
      visitDate: dayjs(),
      doctor: '',
      hospital: '',
      files: [],
      additionalInfo: ''
    });
    setOpenAIDialog(true);
  };

  const handleFileUpload = (files, isAI = false) => {
    if (isAI) {
      setAiFormData(prev => ({
        ...prev,
        files: [...prev.files, ...files]
      }));
    } else {
      setFormData(prev => ({
        ...prev,
        files: [...prev.files, ...files]
      }));
    }
  };

  const addTestRow = () => {
    setFormData(prev => ({
      ...prev,
      tests: [...(prev.tests || []), { name: '', value: '', unit: '', status: '', date: dayjs(prev.visitDate).format('YYYY-MM-DD') }]
    }));
  };

  const removeTestRow = (index) => {
    setFormData(prev => ({
      ...prev,
      tests: (prev.tests || []).filter((_, i) => i !== index)
    }));
  };

  const updateTestField = (index, field, value) => {
    setFormData(prev => ({
      ...prev,
      tests: (prev.tests || []).map((t, i) => i === index ? { ...t, [field]: value } : t)
    }));
  };

  const recentSummaries = summaries.filter(s => 
    dayjs().diff(dayjs(s.visitDate), 'days') <= 30
  );
  
  const olderSummaries = summaries.filter(s => 
    dayjs().diff(dayjs(s.visitDate), 'days') > 30
  );

  return (
    <LocalizationProvider dateAdapter={AdapterDayjs}>
      <Box sx={{ flexGrow: 1, bgcolor: '#f5f5f5', minHeight: '100vh' }}>
        <Header />
        <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
          {/* 页面标题和操作 */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h4" gutterBottom>
              就诊摘要
            </Typography>
            <Box>
              <Button
                variant="outlined"
                startIcon={<AutoAwesome />}
                onClick={handleOpenAIDialog}
                sx={{ mr: 2, borderRadius: 2 }}
              >
                AI生成摘要
              </Button>
              <Button
                variant="contained"
                startIcon={<Add />}
                onClick={() => handleOpenDialog()}
                sx={{ borderRadius: 2 }}
              >
                手动添加
              </Button>
            </Box>
          </Box>

          {/* 统计信息 */}
          <Grid container spacing={3} sx={{ mb: 3 }}>
            <Grid item xs={12} md={4}>
              <Card sx={{ bgcolor: 'primary.light' }}>
                <CardContent sx={{ textAlign: 'center' }}>
                  <Assignment sx={{ fontSize: 40, color: 'white', mb: 1 }} />
                  <Typography variant="h6" color="white">
                    总摘要数
                  </Typography>
                  <Typography variant="h4" color="white">
                    {summaries.length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card sx={{ bgcolor: 'success.light' }}>
                <CardContent sx={{ textAlign: 'center' }}>
                  <Schedule sx={{ fontSize: 40, color: 'white', mb: 1 }} />
                  <Typography variant="h6" color="white">
                    最近30天
                  </Typography>
                  <Typography variant="h4" color="white">
                    {recentSummaries.length}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} md={4}>
              <Card sx={{ bgcolor: 'info.light' }}>
                <CardContent sx={{ textAlign: 'center' }}>
                  <LocalHospital sx={{ fontSize: 40, color: 'white', mb: 1 }} />
                  <Typography variant="h6" color="white">
                    就诊医院
                  </Typography>
                  <Typography variant="h4" color="white">
                    {new Set(summaries.map(s => s.hospital)).size}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>

          {/* 标签页 */}
          <Tabs value={tabValue} onChange={(e, v) => setTabValue(v)} sx={{ mb: 2 }}>
            <Tab label={`最近摘要 (${recentSummaries.length})`} />
            <Tab label={`历史摘要 (${olderSummaries.length})`} />
            <Tab label="详细查看" />
          </Tabs>

          {/* 最近摘要 */}
          {tabValue === 0 && (
            <Grid container spacing={3}>
              {recentSummaries.length === 0 ? (
                <Grid item xs={12}>
                  <Alert severity="info">
                    暂无最近的就诊摘要
                  </Alert>
                </Grid>
              ) : (
                recentSummaries.map((summary) => (
                  <Grid item xs={12} md={6} key={summary.id}>
                    <Card sx={{ height: '100%' }}>
                      <CardContent>
                        <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                          <Avatar sx={{ bgcolor: 'primary.main', mr: 2 }}>
                            <Assignment />
                          </Avatar>
                          <Box sx={{ flexGrow: 1 }}>
                            <Typography variant="h6">
                              {summary.title}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {dayjs(summary.visitDate).format('YYYY年MM月DD日')}
                            </Typography>
                          </Box>
                        </Box>
                        
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          <strong>医生：</strong>{summary.doctor}
                        </Typography>
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          <strong>医院：</strong>{summary.hospital}
                        </Typography>
                        <Typography variant="body2" sx={{ mb: 1 }}>
                          <strong>科室：</strong>{summary.department}
                        </Typography>
                        
                        {summary.diagnosis && (
                          <Box sx={{ mt: 2 }}>
                            <Typography variant="body2" sx={{ mb: 1 }}>
                              <strong>诊断：</strong>
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                              {summary.diagnosis.length > 100 ? 
                                `${summary.diagnosis.substring(0, 100)}...` : 
                                summary.diagnosis
                              }
                            </Typography>
                          </Box>
                        )}
                        
                        {summary.files && summary.files.length > 0 && (
                          <Box sx={{ mt: 2 }}>
                            <Chip
                              icon={<Description />}
                              label={`${summary.files.length} 个附件`}
                              size="small"
                              variant="outlined"
                            />
                          </Box>
                        )}
                        {summary.tests && summary.tests.length > 0 && (
                          <Box sx={{ mt: 1 }}>
                            <Chip
                              label={`${summary.tests.length} 条检验项`}
                              size="small"
                              variant="outlined"
                            />
                          </Box>
                        )}
                      </CardContent>
                      <CardActions>
                        <IconButton size="small" onClick={() => setSelectedSummary(summary)}>
                          <Visibility />
                        </IconButton>
                        <IconButton size="small" onClick={() => handleOpenDialog(summary)}>
                          <Edit />
                        </IconButton>
                        <IconButton size="small" onClick={() => handleDelete(summary.id)}>
                          <Delete />
                        </IconButton>
                        <IconButton size="small">
                          <Download />
                        </IconButton>
                      </CardActions>
                    </Card>
                  </Grid>
                ))
              )}
            </Grid>
          )}

          {/* 历史摘要 */}
          {tabValue === 1 && (
            <List>
              {olderSummaries.length === 0 ? (
                <Alert severity="info">
                  暂无历史摘要
                </Alert>
              ) : (
                olderSummaries.map((summary) => (
                  <ListItem key={summary.id} divider>
                    <ListItemAvatar>
                      <Avatar sx={{ bgcolor: 'primary.main' }}>
                        <Assignment />
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText
                      primary={summary.title}
                      secondary={
                        <Box>
                          <Typography variant="body2">
                            {summary.doctor} • {summary.hospital} • {summary.department}
                          </Typography>
                          <Typography variant="caption">
                            {dayjs(summary.visitDate).format('YYYY年MM月DD日')}
                          </Typography>
                        </Box>
                      }
                    />
                    <ListItemSecondaryAction>
                      <IconButton onClick={() => setSelectedSummary(summary)}>
                        <Visibility />
                      </IconButton>
                      <IconButton onClick={() => handleOpenDialog(summary)}>
                        <Edit />
                      </IconButton>
                      <IconButton onClick={() => handleDelete(summary.id)}>
                        <Delete />
                      </IconButton>
                    </ListItemSecondaryAction>
                  </ListItem>
                ))
              )}
            </List>
          )}

          {/* 详细查看 */}
          {tabValue === 2 && (
            <Box>
              {selectedSummary ? (
                <Card>
                  <CardContent>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
                      <Typography variant="h5">
                        {selectedSummary.title}
                      </Typography>
                      <Box>
                        <IconButton>
                          <Print />
                        </IconButton>
                        <IconButton>
                          <Share />
                        </IconButton>
                        <IconButton>
                          <Download />
                        </IconButton>
                      </Box>
                    </Box>
                    
                    <Grid container spacing={3}>
                      <Grid item xs={12} md={6}>
                        <Typography variant="subtitle2" gutterBottom>
                          就诊信息
                        </Typography>
                        <Paper sx={{ p: 2, bgcolor: 'grey.50' }}>
                          <Typography variant="body2" sx={{ mb: 1 }}>
                            <strong>就诊日期：</strong>{dayjs(selectedSummary.visitDate).format('YYYY年MM月DD日')}
                          </Typography>
                          <Typography variant="body2" sx={{ mb: 1 }}>
                            <strong>医生：</strong>{selectedSummary.doctor}
                          </Typography>
                          <Typography variant="body2" sx={{ mb: 1 }}>
                            <strong>医院：</strong>{selectedSummary.hospital}
                          </Typography>
                          <Typography variant="body2">
                            <strong>科室：</strong>{selectedSummary.department}
                          </Typography>
                        </Paper>
                      </Grid>
                      
                      <Grid item xs={12} md={6}>
                        <Typography variant="subtitle2" gutterBottom>
                          主诉
                        </Typography>
                        <Paper sx={{ p: 2, bgcolor: 'grey.50' }}>
                          <Typography variant="body2">
                            {selectedSummary.chiefComplaint || '无'}
                          </Typography>
                        </Paper>
                      </Grid>
                      
                      <Grid item xs={12}>
                        <Accordion>
                          <AccordionSummary expandIcon={<ExpandMore />}>
                            <Typography variant="subtitle1">症状描述</Typography>
                          </AccordionSummary>
                          <AccordionDetails>
                            <Typography variant="body2">
                              {selectedSummary.symptoms || '无记录'}
                            </Typography>
                          </AccordionDetails>
                        </Accordion>
                        
                        <Accordion>
                          <AccordionSummary expandIcon={<ExpandMore />}>
                          <Typography variant="subtitle1">检查结果</Typography>
                          </AccordionSummary>
                          <AccordionDetails>
                            <Typography variant="body2">
                              {selectedSummary.examination || '无记录'}
                            </Typography>
                          </AccordionDetails>
                        </Accordion>
                        <Accordion>
                          <AccordionSummary expandIcon={<ExpandMore />}>
                            <Typography variant="subtitle1">检验单（结构化）</Typography>
                          </AccordionSummary>
                          <AccordionDetails>
                            {(selectedSummary.tests && selectedSummary.tests.length > 0) ? (
                              <List>
                                {selectedSummary.tests.map((t, idx) => (
                                  <ListItem key={idx} divider>
                                    <ListItemText
                                      primary={`${t.name || '未命名检验'}${t.value ? `：${t.value}${t.unit || ''}` : ''}`}
                                      secondary={`${t.status || ''} ${dayjs(t.date || selectedSummary.visitDate).format('YYYY年MM月DD日')}`}
                                    />
                                  </ListItem>
                                ))}
                              </List>
                            ) : (
                              <Typography variant="body2">无结构化检验记录</Typography>
                            )}
                          </AccordionDetails>
                        </Accordion>
                        
                        <Accordion>
                          <AccordionSummary expandIcon={<ExpandMore />}>
                            <Typography variant="subtitle1">诊断结果</Typography>
                          </AccordionSummary>
                          <AccordionDetails>
                            <Typography variant="body2">
                              {selectedSummary.diagnosis || '无记录'}
                            </Typography>
                          </AccordionDetails>
                        </Accordion>
                        
                        <Accordion>
                          <AccordionSummary expandIcon={<ExpandMore />}>
                            <Typography variant="subtitle1">治疗方案</Typography>
                          </AccordionSummary>
                          <AccordionDetails>
                            <Typography variant="body2">
                              {selectedSummary.treatment || '无记录'}
                            </Typography>
                          </AccordionDetails>
                        </Accordion>
                        
                        <Accordion>
                          <AccordionSummary expandIcon={<ExpandMore />}>
                            <Typography variant="subtitle1">处方药物</Typography>
                          </AccordionSummary>
                          <AccordionDetails>
                            <Typography variant="body2">
                              {selectedSummary.prescription || '无记录'}
                            </Typography>
                          </AccordionDetails>
                        </Accordion>
                        
                        <Accordion>
                          <AccordionSummary expandIcon={<ExpandMore />}>
                            <Typography variant="subtitle1">复诊安排</Typography>
                          </AccordionSummary>
                          <AccordionDetails>
                            <Typography variant="body2">
                              {selectedSummary.followUp || '无安排'}
                            </Typography>
                          </AccordionDetails>
                        </Accordion>
                        
                        {selectedSummary.notes && (
                          <Accordion>
                            <AccordionSummary expandIcon={<ExpandMore />}>
                              <Typography variant="subtitle1">备注</Typography>
                            </AccordionSummary>
                            <AccordionDetails>
                              <Typography variant="body2">
                                {selectedSummary.notes}
                              </Typography>
                            </AccordionDetails>
                          </Accordion>
                        )}
                      </Grid>
                    </Grid>
                  </CardContent>
                </Card>
              ) : (
                <Alert severity="info">
                  请从左侧列表选择一个摘要进行查看
                </Alert>
              )}
            </Box>
          )}
        </Container>

        {/* AI生成摘要对话框 */}
        <Dialog open={openAIDialog} onClose={() => setOpenAIDialog(false)} maxWidth="md" fullWidth>
          <DialogTitle>
            AI智能生成就诊摘要
          </DialogTitle>
          <DialogContent>
            <Alert severity="info" sx={{ mb: 2 }}>
              上传就诊相关文件（如病历、检查报告等），AI将自动分析并生成结构化摘要
            </Alert>
            
            <Grid container spacing={2} sx={{ mt: 1 }}>
              <Grid item xs={12} md={6}>
                <DatePicker
                  label="就诊日期"
                  value={aiFormData.visitDate}
                  onChange={(date) => setAiFormData(prev => ({ ...prev, visitDate: date }))}
                  renderInput={(params) => <TextField {...params} fullWidth />}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="医生姓名"
                  value={aiFormData.doctor}
                  onChange={(e) => setAiFormData(prev => ({ ...prev, doctor: e.target.value }))}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="医院名称"
                  value={aiFormData.hospital}
                  onChange={(e) => setAiFormData(prev => ({ ...prev, hospital: e.target.value }))}
                />
              </Grid>
              <Grid item xs={12}>
                <FileUpload
                  onUploadComplete={(files) => handleFileUpload(files, true)}
                  accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                  multiple
                  title="上传就诊文件"
                  description="支持病历、检查报告、处方等文件格式"
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label="补充信息（可选）"
                  value={aiFormData.additionalInfo}
                  onChange={(e) => setAiFormData(prev => ({ ...prev, additionalInfo: e.target.value }))}
                  placeholder="如有其他需要AI分析的信息，请在此输入..."
                />
              </Grid>
            </Grid>
            
            {generating && (
              <Box sx={{ mt: 2 }}>
                <Typography variant="body2" gutterBottom>
                  AI正在分析文件并生成摘要...
                </Typography>
                <LinearProgress />
              </Box>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setOpenAIDialog(false)}>取消</Button>
            <Button
              onClick={handleGenerateAISummary}
              variant="contained"
              disabled={generating || aiFormData.files.length === 0}
              startIcon={<AutoAwesome />}
            >
              {generating ? '生成中...' : '生成摘要'}
            </Button>
          </DialogActions>
        </Dialog>

        {/* 添加/编辑摘要对话框 */}
        <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="lg" fullWidth>
          <DialogTitle>
            {editingSummary ? '编辑就诊摘要' : '添加就诊摘要'}
          </DialogTitle>
          <DialogContent>
            <Grid container spacing={2} sx={{ mt: 1 }}>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="摘要标题"
                  value={formData.title}
                  onChange={(e) => setFormData(prev => ({ ...prev, title: e.target.value }))}
                />
              </Grid>
              
              <Grid item xs={12} md={4}>
                <DatePicker
                  label="就诊日期"
                  value={formData.visitDate}
                  onChange={(date) => setFormData(prev => ({ ...prev, visitDate: date }))}
                  renderInput={(params) => <TextField {...params} fullWidth />}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  label="医生姓名"
                  value={formData.doctor}
                  onChange={(e) => setFormData(prev => ({ ...prev, doctor: e.target.value }))}
                />
              </Grid>
              <Grid item xs={12} md={4}>
                <TextField
                  fullWidth
                  label="医院名称"
                  value={formData.hospital}
                  onChange={(e) => setFormData(prev => ({ ...prev, hospital: e.target.value }))}
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <FormControl fullWidth>
                  <InputLabel>科室</InputLabel>
                  <Select
                    value={formData.department}
                    label="科室"
                    onChange={(e) => setFormData(prev => ({ ...prev, department: e.target.value }))}
                  >
                    {departments.map(dept => (
                      <MenuItem key={dept} value={dept}>
                        {dept}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="主诉"
                  value={formData.chiefComplaint}
                  onChange={(e) => setFormData(prev => ({ ...prev, chiefComplaint: e.target.value }))}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label="症状描述"
                  value={formData.symptoms}
                  onChange={(e) => setFormData(prev => ({ ...prev, symptoms: e.target.value }))}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label="检查结果"
                  value={formData.examination}
                  onChange={(e) => setFormData(prev => ({ ...prev, examination: e.target.value }))}
                />
              </Grid>
              <Grid item xs={12}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                  <Typography variant="subtitle2">检验单（结构化）</Typography>
                  <Button size="small" variant="outlined" onClick={addTestRow}>添加检验项</Button>
                </Box>
                <List>
                  {(formData.tests || []).map((t, idx) => (
                    <ListItem key={idx} sx={{ py: 0 }}>
                      <Grid container spacing={1} alignItems="center">
                        <Grid item xs={12} md={3}>
                          <TextField size="small" label="项目" fullWidth value={t.name || ''} onChange={(e) => updateTestField(idx, 'name', e.target.value)} />
                        </Grid>
                        <Grid item xs={12} md={3}>
                          <TextField size="small" label="数值" fullWidth value={t.value || ''} onChange={(e) => updateTestField(idx, 'value', e.target.value)} />
                        </Grid>
                        <Grid item xs={12} md={2}>
                          <TextField size="small" label="单位" fullWidth value={t.unit || ''} onChange={(e) => updateTestField(idx, 'unit', e.target.value)} />
                        </Grid>
                        <Grid item xs={12} md={2}>
                          <TextField size="small" label="状态" fullWidth value={t.status || ''} onChange={(e) => updateTestField(idx, 'status', e.target.value)} />
                        </Grid>
                        <Grid item xs={12} md={2}>
                          <TextField size="small" label="日期" fullWidth value={t.date || dayjs(formData.visitDate).format('YYYY-MM-DD')} onChange={(e) => updateTestField(idx, 'date', e.target.value)} />
                        </Grid>
                      </Grid>
                      <ListItemSecondaryAction>
                        <IconButton edge="end" onClick={() => removeTestRow(idx)}>
                          <Delete />
                        </IconButton>
                      </ListItemSecondaryAction>
                    </ListItem>
                  ))}
                </List>
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label="诊断结果"
                  value={formData.diagnosis}
                  onChange={(e) => setFormData(prev => ({ ...prev, diagnosis: e.target.value }))}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label="治疗方案"
                  value={formData.treatment}
                  onChange={(e) => setFormData(prev => ({ ...prev, treatment: e.target.value }))}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label="处方药物"
                  value={formData.prescription}
                  onChange={(e) => setFormData(prev => ({ ...prev, prescription: e.target.value }))}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="复诊安排"
                  value={formData.followUp}
                  onChange={(e) => setFormData(prev => ({ ...prev, followUp: e.target.value }))}
                />
              </Grid>
              
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={2}
                  label="备注"
                  value={formData.notes}
                  onChange={(e) => setFormData(prev => ({ ...prev, notes: e.target.value }))}
                />
              </Grid>
              
              <Grid item xs={12}>
                <FileUpload
                  onUploadComplete={handleFileUpload}
                  accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                  multiple
                  title="上传相关文件"
                  description="支持病历、检查报告、处方等文件"
                />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={handleCloseDialog}>取消</Button>
            <Button onClick={(e) => { e.stopPropagation(); handleSubmit(); }} variant="contained">
              {editingSummary ? '更新' : '添加'}
            </Button>
          </DialogActions>
        </Dialog>
        
        {/* 智能助手 */}
        <AgentAssistant 
          agentType="summary"
          contextPrompt="当前用户正在使用就诊摘要页面，可能需要关于医疗文档解析、摘要生成、报告整理等方面的帮助。"
          position="bottom-right"
          size="medium"
        />
      </Box>
    </LocalizationProvider>
  );
};

export default Summary;