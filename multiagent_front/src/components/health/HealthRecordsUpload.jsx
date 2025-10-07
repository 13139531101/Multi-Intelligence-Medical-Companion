import React, { useState, useCallback } from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Chip,
  Grid,
  Card,
  CardContent,
  LinearProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  IconButton,
  Divider
} from '@mui/material';
import {
  CloudUpload as CloudUploadIcon,
  Description as DescriptionIcon,
  Image as ImageIcon,
  PictureAsPdf as PdfIcon,
  Delete as DeleteIcon,
  Visibility as VisibilityIcon,
  Add as AddIcon
} from '@mui/icons-material';
import { healthRecordsApi } from '../../api/healthRecordsApi';

const HealthRecordsUpload = ({ apiAlive }) => {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [ocrResults, setOcrResults] = useState([]);
  const [showOcrDialog, setShowOcrDialog] = useState(false);
  const [selectedOcrResult, setSelectedOcrResult] = useState(null);
  
  // 表单数据
  const [formData, setFormData] = useState({
    recordType: '',
    title: '',
    summary: '',
    importance: 'medium',
    tags: [],
    urgent: false
  });
  const [newTag, setNewTag] = useState('');

  // 记录类型选项
  const recordTypes = [
    { value: 'medical_report', label: '体检报告' },
    { value: 'prescription', label: '处方单' },
    { value: 'lab_result', label: '化验结果' },
    { value: 'imaging', label: '影像检查' },
    { value: 'diagnosis', label: '诊断记录' },
    { value: 'surgery', label: '手术记录' },
    { value: 'vaccination', label: '疫苗接种' },
    { value: 'allergy', label: '过敏记录' },
    { value: 'medication', label: '用药记录' },
    { value: 'vital_signs', label: '生命体征' },
    { value: 'other', label: '其他' }
  ];

  // 重要性选项
  const importanceOptions = [
    { value: 'low', label: '低' },
    { value: 'medium', label: '中' },
    { value: 'high', label: '高' },
    { value: 'critical', label: '紧急' }
  ];

  const handleFileSelect = useCallback((event) => {
    const selectedFiles = Array.from(event.target.files);
    const validFiles = selectedFiles.filter(file => {
      const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'application/pdf', 'text/plain'];
      const maxSize = 10 * 1024 * 1024; // 10MB
      
      if (!validTypes.includes(file.type)) {
        setError(`文件 ${file.name} 格式不支持`);
        return false;
      }
      
      if (file.size > maxSize) {
        setError(`文件 ${file.name} 大小超过10MB限制`);
        return false;
      }
      
      return true;
    });
    
    setFiles(prev => [...prev, ...validFiles]);
    setError(null);
  }, []);

  const handleDrop = useCallback((event) => {
    event.preventDefault();
    const droppedFiles = Array.from(event.dataTransfer.files);
    handleFileSelect({ target: { files: droppedFiles } });
  }, [handleFileSelect]);

  const handleDragOver = useCallback((event) => {
    event.preventDefault();
  }, []);

  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const getFileIcon = (file) => {
    if (file.type.startsWith('image/')) {
      return <ImageIcon />;
    } else if (file.type === 'application/pdf') {
      return <PdfIcon />;
    } else {
      return <DescriptionIcon />;
    }
  };

  const handleFormChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const addTag = () => {
    if (newTag.trim() && !formData.tags.includes(newTag.trim())) {
      setFormData(prev => ({
        ...prev,
        tags: [...prev.tags, newTag.trim()]
      }));
      setNewTag('');
    }
  };

  const removeTag = (tagToRemove) => {
    setFormData(prev => ({
      ...prev,
      tags: prev.tags.filter(tag => tag !== tagToRemove)
    }));
  };

  const handleUpload = async () => {
    if (!apiAlive) {
      setError('健康档案管理服务未连接');
      return;
    }

    if (files.length === 0 && !formData.title) {
      setError('请选择文件或填写标题');
      return;
    }

    if (!formData.recordType) {
      setError('请选择记录类型');
      return;
    }

    try {
      setUploading(true);
      setError(null);
      setSuccess(null);
      setUploadProgress(0);

      const uploadData = new FormData();
      
      // 添加文件
      files.forEach(file => {
        uploadData.append('files', file);
      });
      
      // 添加表单数据
      uploadData.append('recordType', formData.recordType);
      uploadData.append('title', formData.title);
      uploadData.append('summary', formData.summary);
      uploadData.append('importance', formData.importance);
      uploadData.append('tags', JSON.stringify(formData.tags));
      uploadData.append('urgent', formData.urgent);

      const response = await healthRecordsApi.uploadRecords(uploadData, {
        onUploadProgress: (progressEvent) => {
          const progress = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          );
          setUploadProgress(progress);
        }
      });

      setSuccess('健康档案上传成功！');
      
      // 如果有OCR结果，显示结果对话框
      if (response.data.ocrResults && response.data.ocrResults.length > 0) {
        setOcrResults(response.data.ocrResults);
        setShowOcrDialog(true);
      }
      
      // 重置表单
      setFiles([]);
      setFormData({
        recordType: '',
        title: '',
        summary: '',
        importance: 'medium',
        tags: [],
        urgent: false
      });
      setUploadProgress(0);
      
    } catch (err) {
      setError('上传失败: ' + (err.message || '未知错误'));
    } finally {
      setUploading(false);
    }
  };

  const viewOcrResult = (result) => {
    setSelectedOcrResult(result);
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
      <Grid container spacing={3}>
        {/* 文件上传区域 */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                文件上传
              </Typography>
              
              <Paper
                sx={{
                  p: 3,
                  border: '2px dashed',
                  borderColor: 'grey.300',
                  textAlign: 'center',
                  cursor: 'pointer',
                  '&:hover': {
                    borderColor: 'primary.main',
                    bgcolor: 'action.hover'
                  }
                }}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onClick={() => document.getElementById('file-input').click()}
              >
                <CloudUploadIcon sx={{ fontSize: 48, color: 'grey.400', mb: 2 }} />
                <Typography variant="h6" gutterBottom>
                  拖拽文件到此处或点击选择
                </Typography>
                <Typography variant="body2" color="textSecondary">
                  支持 JPG、PNG、PDF、TXT 格式，最大 10MB
                </Typography>
                <input
                  id="file-input"
                  type="file"
                  multiple
                  accept="image/*,.pdf,.txt"
                  style={{ display: 'none' }}
                  onChange={handleFileSelect}
                />
              </Paper>

              {/* 已选择的文件列表 */}
              {files.length > 0 && (
                <Box sx={{ mt: 2 }}>
                  <Typography variant="subtitle2" gutterBottom>
                    已选择的文件 ({files.length})
                  </Typography>
                  <List dense>
                    {files.map((file, index) => (
                      <ListItem key={index}>
                        <ListItemIcon>
                          {getFileIcon(file)}
                        </ListItemIcon>
                        <ListItemText
                          primary={file.name}
                          secondary={`${(file.size / 1024 / 1024).toFixed(2)} MB`}
                        />
                        <IconButton
                          edge="end"
                          onClick={() => removeFile(index)}
                          size="small"
                        >
                          <DeleteIcon />
                        </IconButton>
                      </ListItem>
                    ))}
                  </List>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* 档案信息表单 */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                档案信息
              </Typography>
              
              <Grid container spacing={2}>
                <Grid item xs={12}>
                  <FormControl fullWidth required>
                    <InputLabel>记录类型</InputLabel>
                    <Select
                      value={formData.recordType}
                      label="记录类型"
                      onChange={(e) => handleFormChange('recordType', e.target.value)}
                    >
                      {recordTypes.map(type => (
                        <MenuItem key={type.value} value={type.value}>
                          {type.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    label="标题"
                    value={formData.title}
                    onChange={(e) => handleFormChange('title', e.target.value)}
                    placeholder="请输入档案标题"
                  />
                </Grid>
                
                <Grid item xs={12}>
                  <TextField
                    fullWidth
                    multiline
                    rows={3}
                    label="摘要"
                    value={formData.summary}
                    onChange={(e) => handleFormChange('summary', e.target.value)}
                    placeholder="请输入档案摘要或描述"
                  />
                </Grid>
                
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>重要性</InputLabel>
                    <Select
                      value={formData.importance}
                      label="重要性"
                      onChange={(e) => handleFormChange('importance', e.target.value)}
                    >
                      {importanceOptions.map(option => (
                        <MenuItem key={option.value} value={option.value}>
                          {option.label}
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                </Grid>
                
                <Grid item xs={12}>
                  <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
                    <TextField
                      label="添加标签"
                      value={newTag}
                      onChange={(e) => setNewTag(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && addTag()}
                      size="small"
                      sx={{ flexGrow: 1 }}
                    />
                    <Button
                      variant="outlined"
                      onClick={addTag}
                      startIcon={<AddIcon />}
                      size="small"
                    >
                      添加
                    </Button>
                  </Box>
                  
                  {formData.tags.length > 0 && (
                    <Box sx={{ mt: 1, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                      {formData.tags.map((tag, index) => (
                        <Chip
                          key={index}
                          label={tag}
                          onDelete={() => removeTag(tag)}
                          size="small"
                        />
                      ))}
                    </Box>
                  )}
                </Grid>
              </Grid>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* 上传进度 */}
      {uploading && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="body2" gutterBottom>
            上传进度: {uploadProgress}%
          </Typography>
          <LinearProgress variant="determinate" value={uploadProgress} />
        </Box>
      )}

      {/* 错误和成功消息 */}
      {error && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      )}
      
      {success && (
        <Alert severity="success" sx={{ mt: 2 }}>
          {success}
        </Alert>
      )}

      {/* 上传按钮 */}
      <Box sx={{ mt: 3, textAlign: 'center' }}>
        <Button
          variant="contained"
          size="large"
          onClick={handleUpload}
          disabled={uploading || (!files.length && !formData.title)}
          startIcon={<CloudUploadIcon />}
        >
          {uploading ? '上传中...' : '上传档案'}
        </Button>
      </Box>

      {/* OCR结果对话框 */}
      <Dialog
        open={showOcrDialog}
        onClose={() => setShowOcrDialog(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>OCR识别结果</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="textSecondary" gutterBottom>
            以下是从上传文件中识别出的文字内容：
          </Typography>
          
          <List>
            {ocrResults.map((result, index) => (
              <React.Fragment key={index}>
                <ListItem>
                  <ListItemText
                    primary={result.fileName}
                    secondary={`置信度: ${(result.confidence * 100).toFixed(1)}%`}
                  />
                  <IconButton onClick={() => viewOcrResult(result)}>
                    <VisibilityIcon />
                  </IconButton>
                </ListItem>
                {index < ocrResults.length - 1 && <Divider />}
              </React.Fragment>
            ))}
          </List>
          
          {selectedOcrResult && (
            <Paper sx={{ p: 2, mt: 2, bgcolor: 'grey.50' }}>
              <Typography variant="subtitle2" gutterBottom>
                {selectedOcrResult.fileName} - 识别内容：
              </Typography>
              <Typography variant="body2" style={{ whiteSpace: 'pre-wrap' }}>
                {selectedOcrResult.text}
              </Typography>
            </Paper>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowOcrDialog(false)}>关闭</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default HealthRecordsUpload;
