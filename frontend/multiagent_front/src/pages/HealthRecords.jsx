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
  Fab,
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
  Collapse
} from '@mui/material';
import {
  Add,
  CloudUpload,
  Description,
  LocalHospital,
  Medication,
  Biotech,
  Visibility,
  VisibilityOff,
  Edit,
  Delete,
  Download,
  Search
} from '@mui/icons-material';
import { DatePicker } from '@mui/x-date-pickers/DatePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import dayjs from 'dayjs';
import Header from '../components/HealthHeader';
import FileUpload from '../components/FileUpload';
import AgentAssistant from '../components/AgentAssistant';
import { getHealthRecords, createHealthRecord, updateHealthRecord, deleteHealthRecord, getAttachmentUrl } from '../api/healthApi';

const HealthRecords = () => {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [openDialog, setOpenDialog] = useState(false);
  const [editingRecord, setEditingRecord] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [expanded, setExpanded] = useState({});

  const [formData, setFormData] = useState({
    title: '',
    type: 'examination',
    date: dayjs(),
    description: '',
    doctor: '',
    hospital: '',
    files: []
  });

  const recordTypes = [
    { value: 'examination', label: '检查报告', icon: <Biotech />, color: '#2196F3' },
    { value: 'diagnosis', label: '诊断记录', icon: <LocalHospital />, color: '#4CAF50' },
    { value: 'prescription', label: '处方记录', icon: <Medication />, color: '#FF9800' },
    { value: 'surgery', label: '手术记录', icon: <Description />, color: '#F44336' },
    { value: 'other', label: '其他', icon: <Description />, color: '#9C27B0' }
  ];

  // 映射：UI 类型 <-> 后端类型
  const uiToApiRecordType = {
    examination: 'lab_result',
    diagnosis: 'medical_report',
    prescription: 'prescription',
    surgery: 'surgery',
    other: 'other',
  };
  const apiToUiRecordType = {
    medical_report: 'diagnosis',
    lab_result: 'examination',
    prescription: 'prescription',
    surgery: 'surgery',
    vaccination: 'other',
    allergy: 'other',
    symptom: 'other',
    vital_signs: 'other',
    other: 'other',
  };

  const toUiRecord = (r) => ({
    id: r.id,
    title: r.title,
    type: r.type || apiToUiRecordType[r.record_type] || 'other',
    date: r.date || r.record_date,
    description: r.description || r.summary || r.content || '',
    doctor: r.doctor || r.metadata?.doctor || '',
    hospital: r.hospital || r.metadata?.hospital || '',
    files: r.files || r.file_attachments || r.metadata?.files || [],
  });

  const toApiPayload = (form) => {
    const fileIds = (form.files || [])
      .map((m) => (typeof m === 'string' ? m : (m.file_id || m.id || m.name || m.filename)))
      .filter(Boolean);
    return {
      title: form.title,
      record_type: uiToApiRecordType[form.type] || 'other',
      summary: form.description || '',
      content: form.description || '',
      // importance 留空使用后端默认 medium
      tags: [],
      metadata: {
        ...(form.metadata || {}),
        doctor: form.doctor || null,
        hospital: form.hospital || null,
        // 将上传的文件ID保存到 metadata.files，便于后端持久化
        files: fileIds,
      },
      record_date: form.date ? dayjs(form.date).format('YYYY-MM-DD') : null,
      // 新增：顶层 files 供网关转换为 metadata.uploaded_files
      files: fileIds,
    };
  };

  useEffect(() => {
    fetchRecords();
  }, []);

  const fetchRecords = async () => {
    try {
      const data = await getHealthRecords();
      const adapted = Array.isArray(data) ? data.map(toUiRecord) : [];
      setRecords(adapted);
    } catch (error) {
      console.error('获取健康档案失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    try {
      const payload = toApiPayload(formData);
      // 如果是新建且已通过上传创建了OCR记录，则改为更新这些记录，避免重复创建与覆盖OCR内容
      const uploadedRecordIds = (formData.files || [])
        .map((f) => (typeof f === 'object' ? f.record_id : null))
        .filter(Boolean);

      if (editingRecord) {
        await updateHealthRecord(editingRecord.id, payload);
      } else if (uploadedRecordIds.length > 0) {
        // 不覆盖OCR content，仅更新其他字段
        const updatePayload = { ...payload };
        delete updatePayload.content;
        for (const rid of uploadedRecordIds) {
          await updateHealthRecord(rid, updatePayload);
        }
      } else {
        await createHealthRecord(payload);
      }
      await fetchRecords();
      handleCloseDialog();
    } catch (error) {
      console.error('保存健康档案失败:', error);
    }
  };

  const handleOpenDialog = (record = null) => {
    if (record) {
      setEditingRecord(record);
      setFormData({
        title: record.title,
        type: record.type,
        date: record.date ? dayjs(record.date) : dayjs(),
        description: record.description,
        doctor: record.doctor,
        hospital: record.hospital,
        files: record.files || []
      });
    } else {
      setEditingRecord(null);
      setFormData({
        title: '',
        type: 'examination',
        date: dayjs(),
        description: '',
        doctor: '',
        hospital: '',
        files: []
      });
    }
    setOpenDialog(true);
  };

  const handleFileUpload = (uploadedFiles) => {
    // 统一提取 file_id，回退到 id，再回退到 name/filename
    const mapped = (uploadedFiles || []).map((f) => {
      const fileId = f.file_id || f.id || f.fileId;
      const displayName = f.original_filename || f.filename || f.name || `文件-${fileId || ''}`;
      return {
        file_id: fileId,
        record_id: f.record_id,
        name: displayName,
        url: fileId ? getAttachmentUrl(fileId) : undefined,
      };
    });
    setFormData((prev) => ({
      ...prev,
      // 与后端网关 transform_record_payload 对齐：前端提交时写入 metadata.files（字符串数组为文件名回退），但优先包含 file_id 以便直链
      files: mapped,
      metadata: {
        ...(prev.metadata || {}),
        files: mapped.map((m) => m.file_id || m.name),
      },
    }));
  };

  const handleDelete = async (id) => {
    if (window.confirm('确定要删除这条记录吗？')) {
      try {
        await deleteHealthRecord(id);
        await fetchRecords();
      } catch (error) {
        console.error('删除健康档案失败:', error);
      }
    }
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
    setEditingRecord(null);
  };

  const toggleExpand = (id) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  // 新增：渲染附件缩略图/查看按钮
  const renderAttachments = (record) => {
    const files = record.files || [];
    if (!files.length) return null;
    return (
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
        {files.map((f, idx) => {
          const fileId = typeof f === 'string' ? f : (f.file_id || f.id);
          const displayName = typeof f === 'string' ? f : (f.name || f.filename || '文件');
          const url = (typeof f === 'object' && f.url) ? f.url : (fileId ? getAttachmentUrl(fileId) : undefined);
          const isImage = (typeof f === 'object' && (f.mime_type || '').startsWith('image')) || (url && /(\.(png|jpe?g|gif|bmp|webp|svg|heic|heif|tiff?))$/i.test(url));
          return (
            <div key={idx} style={{ width: 96, textAlign: 'center' }}>
              {url ? (
                <a href={url} target="_blank" rel="noreferrer" title={displayName}>
                  {isImage ? (
                    <img src={url} alt={displayName} style={{ width: 96, height: 72, objectFit: 'cover', borderRadius: 6, border: '1px solid #e0e0e0' }} />
                  ) : (
                    <div style={{ width: 96, height: 72, border: '1px solid #e0e0e0', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fafafa' }}>
                      <span style={{ fontSize: 12 }}>预览</span>
                    </div>
                  )}
                </a>
              ) : (
                <div style={{ width: 96, height: 72, border: '1px solid #e0e0e0', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fafafa' }}>
                  <span style={{ fontSize: 12 }}>无链接</span>
                </div>
              )}
              <div style={{ fontSize: 12, marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {displayName}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const getTypeInfo = (type) => {
    return recordTypes.find(t => t.value === type) || recordTypes[0];
  };

  const filteredRecords = records.filter(record => {
    const matchesSearch = record.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         record.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesType = filterType === 'all' || record.type === filterType;
    return matchesSearch && matchesType;
  });

  const groupedRecords = {
    recent: filteredRecords.filter(r => dayjs().diff(dayjs(r.date), 'days') <= 30),
    older: filteredRecords.filter(r => dayjs().diff(dayjs(r.date), 'days') > 30)
  };

  return (
    <LocalizationProvider dateAdapter={AdapterDayjs}>
      <Box sx={{ flexGrow: 1, bgcolor: '#f5f5f5', minHeight: '100vh' }}>
        <Header />
        <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
          {/* 页面标题和操作 */}
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h4" gutterBottom>
              健康档案
            </Typography>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => handleOpenDialog()}
              sx={{ borderRadius: 2 }}
            >
              添加记录
            </Button>
          </Box>

          {/* 搜索和筛选 */}
          <Card sx={{ mb: 3 }}>
            <CardContent>
              <Grid container spacing={2} alignItems="center">
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    placeholder="搜索健康记录..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    InputProps={{
                      startAdornment: <Search sx={{ mr: 1, color: 'text.secondary' }} />
                    }}
                  />
                </Grid>
                <Grid item xs={12} md={3}>
                  <FormControl fullWidth>
                    <InputLabel>记录类型</InputLabel>
                    <Select
                      value={filterType}
                      label="记录类型"
                      onChange={(e) => setFilterType(e.target.value)}
                    >
                      <MenuItem value="all">全部类型</MenuItem>
                      {recordTypes.map(type => (
                        <MenuItem key={type.value} value={type.value}>
                          {type.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} md={3}>
                  <Typography variant="body2" color="text.secondary">
                    共 {filteredRecords.length} 条记录
                  </Typography>
                </Grid>
              </Grid>
            </CardContent>
          </Card>

          {/* 记录列表 */}
          <Tabs value={tabValue} onChange={(e, v) => setTabValue(v)} sx={{ mb: 2 }}>
            <Tab label={`最近记录 (${groupedRecords.recent.length})`} />
            <Tab label={`历史记录 (${groupedRecords.older.length})`} />
          </Tabs>

          {tabValue === 0 && (
            <Grid container spacing={3}>
              {groupedRecords.recent.length === 0 ? (
                <Grid item xs={12}>
                  <Alert severity="info">
                    暂无最近的健康记录
                  </Alert>
                </Grid>
              ) : (
                groupedRecords.recent.map((record) => {
                  const typeInfo = getTypeInfo(record.type);
                  return (
                    <Grid item xs={12} md={6} key={record.id}>
                      <Card sx={{ height: '100%' }}>
                        <CardContent>
                          <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                            <Avatar sx={{ bgcolor: typeInfo.color, mr: 2 }}>
                              {typeInfo.icon}
                            </Avatar>
                            <Box sx={{ flexGrow: 1 }}>
                              <Typography variant="h6">
                                {record.title}
                              </Typography>
                              <Typography variant="body2" color="text.secondary">
                                {dayjs(record.date).format('YYYY年MM月DD日')}
                              </Typography>
                            </Box>
                            <Chip
                              label={typeInfo.label}
                              size="small"
                              sx={{ bgcolor: typeInfo.color, color: 'white' }}
                            />
                          </Box>
                          <Collapse in={!!expanded[record.id]} timeout="auto" unmountOnExit>
                            {record.description && (
                              <Typography variant="body2" sx={{ mb: 1 }}>
                                {record.description}
                              </Typography>
                            )}
                            {record.doctor && (
                              <Typography variant="caption" display="block">
                                医生：{record.doctor}
                              </Typography>
                            )}
                            {record.hospital && (
                              <Typography variant="caption" display="block">
                                医院：{record.hospital}
                              </Typography>
                            )}
                            {renderAttachments(record)}
                            <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                              记录ID：{record.id}
                            </Typography>
                          </Collapse>
                        </CardContent>
                        <CardActions>
                          <IconButton size="small" onClick={() => handleOpenDialog(record)}>
                            <Edit />
                          </IconButton>
                          <IconButton size="small" onClick={() => handleDelete(record.id)}>
                            <Delete />
                          </IconButton>
                          <IconButton
                            size="small"
                            onClick={() => toggleExpand(record.id)}
                            aria-label={expanded[record.id] ? '收起详情' : '展开详情'}
                          >
                            {expanded[record.id] ? <VisibilityOff /> : <Visibility />}
                          </IconButton>
                        </CardActions>
                      </Card>
                    </Grid>
                  );
                })
              )}
            </Grid>
          )}

          {tabValue === 1 && (
            <List>
              {groupedRecords.older.length === 0 ? (
                <Alert severity="info">
                  暂无历史记录
                </Alert>
              ) : (
                groupedRecords.older.map((record) => {
                  const typeInfo = getTypeInfo(record.type);
                  return (
                    <ListItem key={record.id} divider>
                      <ListItemAvatar>
                        <Avatar sx={{ bgcolor: typeInfo.color }}>
                          {typeInfo.icon}
                        </Avatar>
                      </ListItemAvatar>
                      <ListItemText
                        primary={record.title}
                        secondary={
                          <Box>
                            <Typography variant="body2">
                              {record.description}
                            </Typography>
                            <Typography variant="caption">
                              {dayjs(record.date).format('YYYY年MM月DD日')} • {typeInfo.label}
                            </Typography>
                          </Box>
                        }
                      />
                      <ListItemSecondaryAction>
                        <IconButton onClick={() => handleOpenDialog(record)}>
                          <Edit />
                        </IconButton>
                        <IconButton onClick={() => handleDelete(record.id)}>
                          <Delete />
                        </IconButton>
                      </ListItemSecondaryAction>
                    </ListItem>
                  );
                })
              )}
            </List>
          )}
        </Container>

        {/* 添加/编辑对话框 */}
        <Dialog open={openDialog} onClose={handleCloseDialog} maxWidth="md" fullWidth>
          <DialogTitle>
            {editingRecord ? '编辑健康记录' : '添加健康记录'}
          </DialogTitle>
          <DialogContent>
            <Grid container spacing={2} sx={{ mt: 1 }}>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label="记录标题"
                  value={formData.title}
                  onChange={(e) => setFormData(prev => ({ ...prev, title: e.target.value }))}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <FormControl fullWidth>
                  <InputLabel>记录类型</InputLabel>
                  <Select
                    value={formData.type}
                    label="记录类型"
                    onChange={(e) => setFormData(prev => ({ ...prev, type: e.target.value }))}
                  >
                    {recordTypes.map(type => (
                      <MenuItem key={type.value} value={type.value}>
                        {type.label}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
              </Grid>
              <Grid item xs={12} md={6}>
                <DatePicker
                  label="记录日期"
                  value={formData.date}
                  onChange={(date) => setFormData(prev => ({ ...prev, date }))}
                  renderInput={(params) => <TextField {...params} fullWidth />}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="医生姓名"
                  value={formData.doctor}
                  onChange={(e) => setFormData(prev => ({ ...prev, doctor: e.target.value }))}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label="医院名称"
                  value={formData.hospital}
                  onChange={(e) => setFormData(prev => ({ ...prev, hospital: e.target.value }))}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={4}
                  label="详细描述"
                  value={formData.description}
                  onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                />
              </Grid>
              <Grid item xs={12}>
                <FileUpload
                  onUploadComplete={handleFileUpload}
                  multiple
                />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={handleCloseDialog}>取消</Button>
            <Button onClick={handleSubmit} variant="contained">
              {editingRecord ? '更新' : '添加'}
            </Button>
          </DialogActions>
        </Dialog>
        
        {/* 智能助手 */}
        <AgentAssistant 
          agentType="health_records"
          contextPrompt="当前用户正在查看健康档案页面，可能需要关于健康记录管理、数据录入、档案查询等方面的帮助。"
          position="bottom-right"
          size="medium"
        />
      </Box>
    </LocalizationProvider>
  );
};

export default HealthRecords;