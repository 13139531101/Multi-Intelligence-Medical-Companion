import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  IconButton,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  MenuItem,
  FormControl,
  InputLabel,
  Select,
  Grid,
  Card,
  CardContent,
  CardActions,
  Pagination,
  Alert,
  Skeleton
} from '@mui/material';
import {
  Visibility as VisibilityIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  Search as SearchIcon,
  Add as AddIcon,
  FileDownload as FileDownloadIcon
} from '@mui/icons-material';
import { healthRecordsApi } from '../../api/healthRecordsApi';

const HealthRecordsList = ({ apiAlive }) => {
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [detailDialogOpen, setDetailDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [recordsPerPage] = useState(10);

  // 记录类型映射
  const recordTypeMap = {
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

  // 重要性等级映射
  const importanceMap = {
    'low': { label: '低', color: 'default' },
    'medium': { label: '中', color: 'primary' },
    'high': { label: '高', color: 'warning' },
    'critical': { label: '紧急', color: 'error' }
  };

  useEffect(() => {
    if (apiAlive) {
      fetchRecords();
    } else {
      setLoading(false);
    }
  }, [apiAlive, page, searchTerm, filterType]);

  const fetchRecords = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const params = {
        page,
        limit: recordsPerPage,
        search: searchTerm,
        type: filterType !== 'all' ? filterType : undefined
      };
      
      const response = await healthRecordsApi.getRecords(params);
      setRecords(response.data.records || []);
      setTotalPages(Math.ceil((response.data.total || 0) / recordsPerPage));
    } catch (err) {
      setError('获取健康档案失败: ' + (err.message || '未知错误'));
      setRecords([]);
    } finally {
      setLoading(false);
    }
  };

  const handleViewRecord = (record) => {
    setSelectedRecord(record);
    setDetailDialogOpen(true);
  };

  const handleEditRecord = (record) => {
    setSelectedRecord(record);
    setEditDialogOpen(true);
  };

  const handleDeleteRecord = (record) => {
    setSelectedRecord(record);
    setDeleteDialogOpen(true);
  };

  const confirmDelete = async () => {
    try {
      await healthRecordsApi.deleteRecord(selectedRecord.id);
      setDeleteDialogOpen(false);
      setSelectedRecord(null);
      fetchRecords(); // 刷新列表
    } catch (err) {
      setError('删除记录失败: ' + (err.message || '未知错误'));
    }
  };

  const handleSearch = () => {
    setPage(1);
    fetchRecords();
  };

  const handlePageChange = (event, newPage) => {
    setPage(newPage);
  };

  const formatDate = (dateString) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleDateString('zh-CN');
  };

  const getImportanceChip = (importance) => {
    const config = importanceMap[importance] || importanceMap.medium;
    return (
      <Chip 
        label={config.label} 
        color={config.color} 
        size="small" 
      />
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
      {/* 搜索和筛选区域 */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} md={4}>
          <TextField
            fullWidth
            label="搜索档案"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            InputProps={{
              endAdornment: (
                <IconButton onClick={handleSearch}>
                  <SearchIcon />
                </IconButton>
              )
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
              {Object.entries(recordTypeMap).map(([key, label]) => (
                <MenuItem key={key} value={key}>{label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} md={5}>
          <Box sx={{ display: 'flex', gap: 1, height: '100%', alignItems: 'center' }}>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setEditDialogOpen(true)}
            >
              新增档案
            </Button>
            <Button
              variant="outlined"
              startIcon={<FileDownloadIcon />}
              onClick={() => {/* TODO: 导出功能 */}}
            >
              导出
            </Button>
          </Box>
        </Grid>
      </Grid>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* 档案列表 */}
      {loading ? (
        <Box>
          {[...Array(5)].map((_, index) => (
            <Card key={index} sx={{ mb: 2 }}>
              <CardContent>
                <Skeleton variant="text" width="60%" height={32} />
                <Skeleton variant="text" width="40%" height={24} />
                <Skeleton variant="text" width="80%" height={20} />
              </CardContent>
            </Card>
          ))}
        </Box>
      ) : records.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h6" color="textSecondary">
            暂无健康档案记录
          </Typography>
          <Typography variant="body2" color="textSecondary" sx={{ mt: 1 }}>
            点击"新增档案"开始创建您的第一条健康记录
          </Typography>
        </Paper>
      ) : (
        <>
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>记录类型</TableCell>
                  <TableCell>标题</TableCell>
                  <TableCell>创建日期</TableCell>
                  <TableCell>重要性</TableCell>
                  <TableCell>标签</TableCell>
                  <TableCell align="center">操作</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {records.map((record) => (
                  <TableRow key={record.id} hover>
                    <TableCell>
                      <Chip 
                        label={recordTypeMap[record.record_type] || record.record_type}
                        variant="outlined"
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" fontWeight="medium">
                        {record.title || record.summary || '无标题'}
                      </Typography>
                    </TableCell>
                    <TableCell>{formatDate(record.created_at)}</TableCell>
                    <TableCell>{getImportanceChip(record.importance)}</TableCell>
                    <TableCell>
                      <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                        {(record.tags || []).slice(0, 2).map((tag, index) => (
                          <Chip key={index} label={tag} size="small" variant="outlined" />
                        ))}
                        {(record.tags || []).length > 2 && (
                          <Chip label={`+${record.tags.length - 2}`} size="small" variant="outlined" />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell align="center">
                      <IconButton 
                        size="small" 
                        onClick={() => handleViewRecord(record)}
                        title="查看详情"
                      >
                        <VisibilityIcon />
                      </IconButton>
                      <IconButton 
                        size="small" 
                        onClick={() => handleEditRecord(record)}
                        title="编辑"
                      >
                        <EditIcon />
                      </IconButton>
                      <IconButton 
                        size="small" 
                        onClick={() => handleDeleteRecord(record)}
                        title="删除"
                        color="error"
                      >
                        <DeleteIcon />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>

          {/* 分页 */}
          {totalPages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
              <Pagination
                count={totalPages}
                page={page}
                onChange={handlePageChange}
                color="primary"
              />
            </Box>
          )}
        </>
      )}

      {/* 详情对话框 */}
      <Dialog 
        open={detailDialogOpen} 
        onClose={() => setDetailDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>健康档案详情</DialogTitle>
        <DialogContent>
          {selectedRecord && (
            <Box sx={{ mt: 1 }}>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle2" color="textSecondary">记录类型</Typography>
                  <Typography variant="body1" sx={{ mb: 2 }}>
                    {recordTypeMap[selectedRecord.record_type] || selectedRecord.record_type}
                  </Typography>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle2" color="textSecondary">重要性</Typography>
                  <Box sx={{ mb: 2 }}>
                    {getImportanceChip(selectedRecord.importance)}
                  </Box>
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="subtitle2" color="textSecondary">摘要</Typography>
                  <Typography variant="body1" sx={{ mb: 2 }}>
                    {selectedRecord.summary || '无摘要'}
                  </Typography>
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="subtitle2" color="textSecondary">详细内容</Typography>
                  <Paper sx={{ p: 2, bgcolor: 'grey.50', mt: 1 }}>
                    <Typography variant="body2" style={{ whiteSpace: 'pre-wrap' }}>
                      {JSON.stringify(selectedRecord.record_data, null, 2)}
                    </Typography>
                  </Paper>
                </Grid>
                {selectedRecord.tags && selectedRecord.tags.length > 0 && (
                  <Grid item xs={12}>
                    <Typography variant="subtitle2" color="textSecondary">标签</Typography>
                    <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mt: 1 }}>
                      {selectedRecord.tags.map((tag, index) => (
                        <Chip key={index} label={tag} size="small" />
                      ))}
                    </Box>
                  </Grid>
                )}
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle2" color="textSecondary">创建时间</Typography>
                  <Typography variant="body2">
                    {formatDate(selectedRecord.created_at)}
                  </Typography>
                </Grid>
                <Grid item xs={12} md={6}>
                  <Typography variant="subtitle2" color="textSecondary">更新时间</Typography>
                  <Typography variant="body2">
                    {formatDate(selectedRecord.updated_at)}
                  </Typography>
                </Grid>
              </Grid>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDetailDialogOpen(false)}>关闭</Button>
          <Button 
            variant="contained" 
            onClick={() => {
              setDetailDialogOpen(false);
              handleEditRecord(selectedRecord);
            }}
          >
            编辑
          </Button>
        </DialogActions>
      </Dialog>

      {/* 删除确认对话框 */}
      <Dialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
      >
        <DialogTitle>确认删除</DialogTitle>
        <DialogContent>
          <Typography>
            确定要删除这条健康档案记录吗？此操作不可撤销。
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>取消</Button>
          <Button onClick={confirmDelete} color="error" variant="contained">
            删除
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default HealthRecordsList;
