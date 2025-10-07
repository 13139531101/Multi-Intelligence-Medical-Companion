import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import {
  Box,
  Typography,
  Button,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  ListItemSecondaryAction,
  IconButton,
  Chip,
  Paper,
  Alert
} from '@mui/material';
import {
  CloudUpload,
  InsertDriveFile,
  Image,
  PictureAsPdf,
  Description,
  Delete,
  CheckCircle,
  Error
} from '@mui/icons-material';
import { useRecoilState, useSetRecoilState } from 'recoil';
import { fileUploadState, notificationState } from '../store/recoilState';
import { uploadFile, uploadMultipleFiles } from '../api/healthApi';

const FileUpload = ({ 
  onUploadComplete, 
  maxFiles = 5, 
  maxSize = 10 * 1024 * 1024, // 10MB
  acceptedTypes = {
    'image/*': ['.jpeg', '.jpg', '.png', '.gif', '.bmp', '.webp'],
    'application/pdf': ['.pdf'],
    'application/msword': ['.doc'],
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    'text/plain': ['.txt']
  },
  multiple = true,
  showPreview = true
}) => {
  const [uploadState, setUploadState] = useRecoilState(fileUploadState);
  const setNotification = useSetRecoilState(notificationState);
  const [uploadedFiles, setUploadedFiles] = useState([]);

  const onDrop = useCallback(async (acceptedFiles, rejectedFiles) => {
    // 处理被拒绝的文件
    if (rejectedFiles.length > 0) {
      const errors = rejectedFiles.map(file => {
        const error = file.errors[0];
        return `${file.file.name}: ${error.message}`;
      });
      setNotification({
        open: true,
        message: `文件上传失败:\n${errors.join('\n')}`,
        severity: 'error'
      });
    }

    if (acceptedFiles.length === 0) return;

    // 检查文件数量限制
    if (uploadedFiles.length + acceptedFiles.length > maxFiles) {
      setNotification({
        open: true,
        message: `最多只能上传 ${maxFiles} 个文件`,
        severity: 'warning'
      });
      return;
    }

    setUploadState(prev => ({ ...prev, uploading: true, progress: 0 }));

    try {
      const uploadPromises = acceptedFiles.map(async (file, index) => {
        const result = await uploadFile(file, (progress) => {
          setUploadState(prev => ({
            ...prev,
            progress: Math.round(((index + progress / 100) / acceptedFiles.length) * 100)
          }));
        });
        
        return {
          id: result.file_id || result.filename || Date.now() + index,
          file_id: result.file_id,
          record_id: result.record_id,
          filename: result.filename,
          original_filename: result.original_filename || file.name,
          name: result.filename || file.name,
          size: file.size,
          type: file.type,
          mime_type: result.mime_type || file.type,
          url: result.url || null,
          status: 'success',
          uploadedAt: new Date().toISOString()
        };
      });

      const results = await Promise.all(uploadPromises);
      
      setUploadedFiles(prev => [...prev, ...results]);
      setUploadState(prev => ({ ...prev, uploading: false, progress: 100 }));
      
      setNotification({
        open: true,
        message: `成功上传 ${results.length} 个文件`,
        severity: 'success'
      });

      if (onUploadComplete) {
        onUploadComplete(results);
      }

    } catch (error) {
      console.error('文件上传失败:', error);
      setUploadState(prev => ({ ...prev, uploading: false, progress: 0 }));
      // 优化错误信息展示：优先后端返回的 detail，其次 message/错误数组
      const detail =
        (typeof error === 'string' ? error :
          error?.detail ||
          error?.message ||
          error?.error ||
          (Array.isArray(error?.errors) ? error.errors[0]?.message : null) ||
          '文件上传失败');
      setNotification({
        open: true,
        message: detail,
        severity: 'error'
      });
    }
  }, [uploadedFiles, maxFiles, onUploadComplete, setUploadState, setNotification]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: acceptedTypes,
    maxSize,
    multiple,
    disabled: uploadState.uploading
  });

  const removeFile = (fileId) => {
    setUploadedFiles(prev => prev.filter(file => file.id !== fileId));
  };

  const getFileIcon = (fileType) => {
    if (fileType.startsWith('image/')) {
      return <Image color="primary" />;
    } else if (fileType === 'application/pdf') {
      return <PictureAsPdf color="error" />;
    } else if (fileType.includes('word') || fileType.includes('document')) {
      return <Description color="info" />;
    }
    return <InsertDriveFile color="action" />;
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <Box sx={{ width: '100%' }}>
      {/* 上传区域 */}
      <Paper
        {...getRootProps()}
        sx={{
          border: '2px dashed',
          borderColor: isDragActive ? 'primary.main' : 'grey.300',
          borderRadius: 2,
          p: 4,
          textAlign: 'center',
          cursor: uploadState.uploading ? 'not-allowed' : 'pointer',
          bgcolor: isDragActive ? 'action.hover' : 'background.paper',
          transition: 'all 0.2s ease-in-out',
          '&:hover': {
            borderColor: 'primary.main',
            bgcolor: 'action.hover'
          }
        }}
      >
        <input {...getInputProps()} />
        <CloudUpload 
          sx={{ 
            fontSize: 48, 
            color: isDragActive ? 'primary.main' : 'grey.400',
            mb: 2 
          }} 
        />
        <Typography variant="h6" gutterBottom>
          {isDragActive ? '释放文件以上传' : '拖拽文件到此处或点击选择'}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          支持的文件类型: 图片、PDF、Word文档、文本文件
        </Typography>
        <Typography variant="caption" color="text.secondary">
          最大文件大小: {formatFileSize(maxSize)} | 最多 {maxFiles} 个文件
        </Typography>
        
        {!isDragActive && (
          <Box sx={{ mt: 2 }}>
            <Button 
              variant="contained" 
              disabled={uploadState.uploading}
              startIcon={<CloudUpload />}
            >
              选择文件
            </Button>
          </Box>
        )}
      </Paper>

      {/* 上传进度 */}
      {uploadState.uploading && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            上传进度: {uploadState.progress}%
          </Typography>
          <LinearProgress 
            variant="determinate" 
            value={uploadState.progress} 
            sx={{ height: 8, borderRadius: 4 }}
          />
        </Box>
      )}

      {/* 已上传文件列表 */}
      {uploadedFiles.length > 0 && showPreview && (
        <Box sx={{ mt: 3 }}>
          <Typography variant="h6" gutterBottom>
            已上传文件 ({uploadedFiles.length})
          </Typography>
          <List>
            {uploadedFiles.map((file) => (
              <ListItem
                key={file.id}
                sx={{
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                  mb: 1,
                  bgcolor: 'background.paper'
                }}
              >
                <ListItemIcon>
                  {getFileIcon(file.type)}
                </ListItemIcon>
                <ListItemText
                  disableTypography
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography variant="body2" noWrap>
                        {file.name}
                      </Typography>
                      <Chip
                        icon={<CheckCircle />}
                        label="已上传"
                        size="small"
                        color="success"
                        variant="outlined"
                      />
                    </Box>
                  }
                  secondary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mt: 0.5 }}>
                      <Typography variant="caption" color="text.secondary">
                        {formatFileSize(file.size)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(file.uploadedAt).toLocaleString()}
                      </Typography>
                    </Box>
                  }
                />
                <ListItemSecondaryAction>
                  <IconButton
                    edge="end"
                    aria-label="delete"
                    onClick={() => removeFile(file.id)}
                    size="small"
                  >
                    <Delete />
                  </IconButton>
                </ListItemSecondaryAction>
              </ListItem>
            ))}
          </List>
        </Box>
      )}

      {/* 使用提示 */}
      {uploadedFiles.length === 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>
          <Typography variant="body2">
            <strong>上传提示:</strong>
          </Typography>
          <Typography variant="body2" component="ul" sx={{ mt: 1, pl: 2 }}>
            <li>支持拖拽上传，也可以点击选择文件</li>
            <li>支持批量上传多个文件</li>
            <li>上传的文件会自动保存到您的健康档案中</li>
            <li>建议上传清晰的医疗报告、检查结果等</li>
          </Typography>
        </Alert>
      )}
    </Box>
  );
};

export default FileUpload;