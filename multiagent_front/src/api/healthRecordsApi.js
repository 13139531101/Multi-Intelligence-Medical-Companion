import axios from 'axios';

// 创建axios实例
const api = axios.create({
  baseURL: import.meta.env.VITE_HOSTAGENT_API || 'http://127.0.0.1:13002',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    // 可以在这里添加认证token等
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // 统一错误处理
    if (error.response) {
      // 服务器返回错误状态码
      const { status, data } = error.response;
      switch (status) {
        case 401:
          // 未授权，可以跳转到登录页
          break;
        case 403:
          // 禁止访问
          break;
        case 404:
          // 资源不存在
          break;
        case 500:
          // 服务器内部错误
          break;
        default:
          break;
      }
      throw new Error(data.message || `请求失败: ${status}`);
    } else if (error.request) {
      // 网络错误
      throw new Error('网络连接失败，请检查网络设置');
    } else {
      // 其他错误
      throw new Error(error.message || '请求失败');
    }
  }
);

export const healthRecordsApi = {
  // 获取健康档案列表
  getHealthRecords: (params = {}) => {
    return api.get('/health-records', { params });
  },

  // 获取单个健康档案详情
  getHealthRecord: (id) => {
    return api.get(`/health-records/${id}`);
  },

  // 创建健康档案
  createHealthRecord: (data) => {
    return api.post('/health-records', data);
  },

  // 更新健康档案
  updateHealthRecord: (id, data) => {
    return api.put(`/health-records/${id}`, data);
  },

  // 删除健康档案
  deleteHealthRecord: (id) => {
    return api.delete(`/health-records/${id}`);
  },

  // 批量删除健康档案
  batchDeleteHealthRecords: (ids) => {
    return api.post('/health-records/batch-delete', { ids });
  },

  // 上传文件（单个） -> 映射到 HostAgentAPI /upload
  uploadFile: (file, onProgress) => {
    const formData = new FormData();
    formData.append('file', file);
    
    return api.post('/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          const percentCompleted = Math.round((e.loaded * 100) / e.total);
          onProgress(percentCompleted);
        }
      },
    });
  },

  // 批量上传文件 -> 映射到 HostAgentAPI /upload/multiple（字段名为 files）
  batchUploadFiles: (files, onProgress) => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });
    
    return api.post('/upload/multiple', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          const percentCompleted = Math.round((e.loaded * 100) / e.total);
          onProgress(percentCompleted);
        }
      },
    });
  },

  // 适配 HealthRecordsUpload.jsx 调用的 uploadRecords(formData, config)
  uploadRecords: (formData, config = {}) => {
    return api.post('/upload/multiple', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      ...config,
    });
  },

  // 列出已上传文件
  listUploadedFiles: () => api.get('/files'),

  // 获取文件内容（二进制）
  getUploadedFile: (fileId) => api.get(`/files/${fileId}`, { responseType: 'blob' }),

  // 删除文件
  deleteUploadedFile: (fileId) => api.delete(`/files/${fileId}`),

  // OCR识别
  performOCR: (fileId) => {
    return api.post(`/health-records/ocr/${fileId}`);
  },

  // 获取健康数据统计
  getHealthStatistics: (params = {}) => {
    return api.get('/health-records/statistics', { params });
  },

  // 获取健康趋势数据
  getHealthTrends: (params = {}) => {
    return api.get('/health-records/trends', { params });
  },

  // 获取健康洞察
  getHealthInsights: (params = {}) => {
    return api.get('/health-records/insights', { params });
  },

  // 搜索健康档案
  searchHealthRecords: (query, params = {}) => {
    return api.get('/health-records/search', {
      params: { q: query, ...params }
    });
  },

  // 获取记录类型列表
  getRecordTypes: () => {
    return api.get('/health-records/types');
  },

  // 获取标签列表
  getTags: () => {
    return api.get('/health-records/tags');
  },

  // 导出健康档案
  exportHealthRecords: (params = {}) => {
    return api.get('/health-records/export', {
      params,
      responseType: 'blob'
    });
  },

  // 导入健康档案
  importHealthRecords: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    
    return api.post('/health-records/import', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },

  // 获取健康档案附件
  getAttachment: (recordId, attachmentId) => {
    return api.get(`/health-records/${recordId}/attachments/${attachmentId}`, {
      responseType: 'blob'
    });
  },

  // 删除健康档案附件
  deleteAttachment: (recordId, attachmentId) => {
    return api.delete(`/health-records/${recordId}/attachments/${attachmentId}`);
  },

  // 获取健康评分
  getHealthScore: (params = {}) => {
    return api.get('/health-records/health-score', { params });
  },

  // 获取健康建议
  getHealthRecommendations: (params = {}) => {
    return api.get('/health-records/recommendations', { params });
  },

  // 标记记录为重要
  markAsImportant: (id) => {
    return api.post(`/health-records/${id}/mark-important`);
  },

  // 取消重要标记
  unmarkAsImportant: (id) => {
    return api.post(`/health-records/${id}/unmark-important`);
  },

  // 添加记录标签
  addTag: (id, tag) => {
    return api.post(`/health-records/${id}/tags`, { tag });
  },

  // 移除记录标签
  removeTag: (id, tag) => {
    return api.delete(`/health-records/${id}/tags/${tag}`);
  },

  // 获取相关记录
  getRelatedRecords: (id, params = {}) => {
    return api.get(`/health-records/${id}/related`, { params });
  },

  // 检查API状态
  checkApiStatus: () => {
    return api.get('/health-records/status');
  },

  // 获取用户偏好设置
  getUserPreferences: () => {
    return api.get('/health-records/preferences');
  },

  // 更新用户偏好设置
  updateUserPreferences: (preferences) => {
    return api.put('/health-records/preferences', preferences);
  }
};

export default healthRecordsApi;