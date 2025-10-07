import React, { useEffect, useState } from 'react';
import Header from './Header';
import { Box, Container, Typography, Grid, Card, CardActionArea, CardMedia, CardContent, IconButton, Tooltip, CircularProgress } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import { healthRecordsApi } from '../api/healthRecordsApi';

const PhotosPage = () => {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const res = await healthRecordsApi.listUploadedFiles();
      setFiles(res.data || res || []);
    } catch (e) {
      console.error('获取文件列表失败', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  const onFileChange = async (e) => {
    const fileList = Array.from(e.target.files || []);
    if (fileList.length === 0) return;
    setUploading(true);
    try {
      if (fileList.length === 1) {
        await healthRecordsApi.uploadFile(fileList[0]);
      } else {
        await healthRecordsApi.batchUploadFiles(fileList);
      }
      await fetchFiles();
    } catch (err) {
      console.error('上传失败', err);
      alert('上传失败: ' + (err.message || '未知错误'));
    } finally {
      setUploading(false);
      e.target.value = '';
    }
  };

  const onDelete = async (fileId) => {
    if (!window.confirm('确定删除这张照片/文件吗？')) return;
    try {
      await healthRecordsApi.deleteUploadedFile(fileId);
      await fetchFiles();
    } catch (e) {
      console.error('删除失败', e);
      alert('删除失败: ' + (e.message || '未知错误'));
    }
  };

  const isImage = (mime) => mime && mime.startsWith('image/');

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      <Header />
      <Container maxWidth="lg" sx={{ mt: 4, mb: 4, flexGrow: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 'bold', color: 'primary.main' }}>
            照片库
          </Typography>
          <label htmlFor="photo-upload-input">
            <input id="photo-upload-input" type="file" accept="image/*,application/pdf,text/plain" multiple hidden onChange={onFileChange} />
            <Tooltip title="上传照片/文件">
              <IconButton color="primary" component="span" disabled={uploading}>
                <CloudUploadIcon />
              </IconButton>
            </Tooltip>
          </label>
        </Box>

        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
            <CircularProgress />
          </Box>
        ) : (
          <Grid container spacing={2}>
            {files.length === 0 && (
              <Box sx={{ width: '100%', textAlign: 'center', color: 'text.secondary', py: 8 }}>
                暂无文件，点击右上角上传按钮添加。
              </Box>
            )}
            {files.map((f) => (
              <Grid key={f.fileId || f.filename} item xs={12} sm={6} md={4} lg={3}>
                <Card>
                  <CardActionArea href={(f.url?.startsWith('http') ? f.url : (import.meta.env.VITE_HOSTAGENT_API || 'http://127.0.0.1:13002') + (f.url || ''))} target="_blank">
                    {isImage(f.mimeType) ? (
                      <CardMedia component="img" height="180" image={(f.url?.startsWith('http') ? f.url : (import.meta.env.VITE_HOSTAGENT_API || 'http://127.0.0.1:13002') + (f.url || ''))} alt={f.filename} />
                    ) : (
                      <Box sx={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center', bgcolor: 'grey.100' }}>
                        <Typography variant="body2" color="text.secondary">{f.filename}</Typography>
                      </Box>
                    )}
                    <CardContent sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <Typography variant="body2" noWrap title={f.filename}>{f.filename}</Typography>
                      <Tooltip title="删除">
                        <IconButton size="small" onClick={(e) => { e.preventDefault(); onDelete(f.fileId); }}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Container>
    </div>
  );
};

export default PhotosPage;
