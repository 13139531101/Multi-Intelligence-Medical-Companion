import axios from 'axios';

// 创建axios实例
// 重要说明：不要为该实例设置默认的 'Content-Type'
// 让 axios 根据请求体自动选择（JSON 或 multipart/form-data）。
const healthApi = axios.create({
  baseURL: import.meta.env.VITE_HOSTAGENT_API || 'http://127.0.0.1:13002',
  timeout: 10000,
});

// 智能路由API实例
const smartChatApi = axios.create({
  baseURL: import.meta.env.VITE_HOSTAGENT_API || 'http://127.0.0.1:13002',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 认证API实例 - 使用hostAgentAPI的认证服务
const authApi = axios.create({
  baseURL: import.meta.env.VITE_HOSTAGENT_API || 'http://127.0.0.1:13002',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 为authApi添加请求拦截器
authApi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 为authApi添加响应拦截器
authApi.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      // Token过期或无效，清除本地存储并跳转到登录页
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// 请求拦截器 - 添加认证token
healthApi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器 - 处理错误
healthApi.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      // Token过期或无效，清除本地存储并跳转到登录页
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// === 认证相关API ===

// 用户登录
// 用户登录 - 使用hostAgentAPI的认证服务
export const login = async (credentials) => {
  try {
    const response = await authApi.post('/auth/login', credentials);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '登录失败' };
  }
};

// 用户注册 - 使用hostAgentAPI的认证服务
export const register = async (userData) => {
  try {
    const response = await authApi.post('/auth/register', userData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '注册失败' };
  }
};

// 退出登录 - 使用hostAgentAPI的认证服务
export const logout = async () => {
  try {
    const response = await authApi.post('/auth/logout');
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '退出失败' };
  }
};

// 获取用户信息 - 使用hostAgentAPI的认证服务
export const getUserInfo = async () => {
  try {
    const response = await authApi.get('/auth/user');
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '获取用户信息失败' };
  }
};

// 验证Token - 使用hostAgentAPI的认证服务
export const verifyToken = async () => {
  try {
    const response = await authApi.get('/auth/verify');
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: 'Token验证失败' };
  }
};

// === 健康档案API ===

// 获取健康档案列表
export const getHealthRecords = async (params = {}) => {
  try {
    const response = await healthApi.get('/api/health-records', { params });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '获取健康档案失败' };
  }
};

// 创建健康档案
export const createHealthRecord = async (recordData) => {
  try {
    const response = await healthApi.post('/api/health-records', recordData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '创建健康档案失败' };
  }
};

// 更新健康档案
export const updateHealthRecord = async (id, recordData) => {
  try {
    const response = await healthApi.put(`/api/health-records/${id}`, recordData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '更新健康档案失败' };
  }
};

// 删除健康档案
export const deleteHealthRecord = async (id) => {
  try {
    const response = await healthApi.delete(`/api/health-records/${id}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '删除健康档案失败' };
  }
};

// === 健康咨询API ===

// 获取咨询历史
export const getConsultationHistory = async (params = {}) => {
  try {
    const response = await healthApi.get('/consultations', { params });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '获取咨询历史失败' };
  }
};

// 创建新咨询
export const createConsultation = async (consultationData) => {
  try {
    const response = await healthApi.post('/consultations', consultationData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '创建咨询失败' };
  }
};

// 发送消息
export const sendMessage = async (consultationId, messageData) => {
  try {
    const response = await healthApi.post(`/consultations/${consultationId}/messages`, messageData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '发送消息失败' };
  }
};

// 获取咨询消息
export const getConsultationMessages = async (consultationId, params = {}) => {
  try {
    const response = await healthApi.get(`/consultations/${consultationId}/messages`, { params });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '获取消息失败' };
  }
};

// === 用药管理API ===

// 获取药物列表
export const getMedications = async (params = {}) => {
  try {
    const response = await healthApi.get('/medications', { params });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '获取药物列表失败' };
  }
};

// 添加药物
export const addMedication = async (medicationData) => {
  try {
    const response = await healthApi.post('/medications', medicationData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '添加药物失败' };
  }
};

// 更新药物
export const updateMedication = async (id, medicationData) => {
  try {
    const response = await healthApi.put(`/medications/${id}`, medicationData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '更新药物失败' };
  }
};

// 删除药物
export const deleteMedication = async (id) => {
  try {
    const response = await healthApi.delete(`/medications/${id}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '删除药物失败' };
  }
};

// 获取用药提醒
export const getMedicationReminders = async (params = {}) => {
  try {
    const response = await healthApi.get('/medication-reminders', { params });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '获取用药提醒失败' };
  }
};

// 设置用药提醒
export const setMedicationReminder = async (reminderData) => {
  try {
    const response = await healthApi.post('/medication-reminders', reminderData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '设置用药提醒失败' };
  }
};

// 标记提醒为已服用
export const markReminderTaken = async (reminderId, takenTime = '') => {
  try {
    const response = await healthApi.post(`/medication-reminders/${reminderId}/taken`, null, {
      params: { taken_time: takenTime }
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '标记服药失败' };
  }
};

// === 就诊摘要API ===

// 获取就诊摘要
export const getSummaries = async (params = {}) => {
  try {
    const response = await healthApi.get('/summaries', { params });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '获取就诊摘要失败' };
  }
};

// 创建就诊摘要
export const createSummary = async (summaryData) => {
  try {
    const response = await healthApi.post('/summaries', summaryData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '创建就诊摘要失败' };
  }
};

// 更新就诊摘要
export const updateSummary = async (id, summaryData) => {
  try {
    const response = await healthApi.put(`/summaries/${id}`, summaryData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '更新就诊摘要失败' };
  }
};

// 删除就诊摘要
export const deleteSummary = async (id) => {
  try {
    const response = await healthApi.delete(`/summaries/${id}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '删除就诊摘要失败' };
  }
};

// AI生成摘要
export const generateAISummary = async (summaryData) => {
  try {
    const response = await healthApi.post('/summaries/generate', summaryData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: 'AI生成摘要失败' };
  }
};

// === 文件上传API ===

// 上传文件
export const uploadFile = async (file, onProgress = null) => {
  try {
    const formData = new FormData();
    formData.append('file', file);
    const response = await healthApi.post('/api/health-records/upload', formData, {
      // 不要手动设置 Content-Type，浏览器会自动添加 boundary
      ...(onProgress
        ? {
            onUploadProgress: (progressEvent) => {
              const percentCompleted = Math.round(
                (progressEvent.loaded * 100) / progressEvent.total
              );
              onProgress(percentCompleted);
            },
          }
        : {}),
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '文件上传失败' };
  }
};

// 新增：根据 fileId 生成可直接访问的附件直链（HostAgentAPI网关会代理到后端）
export const getAttachmentUrl = (fileId) => {
  if (!fileId) return '';
  // healthApi.defaults.baseURL 例如 http://localhost:13002
  const base = healthApi.defaults.baseURL?.replace(/\/$/, '') || '';
  return `${base}/api/health-records/files/${encodeURIComponent(fileId)}`;
};

// 新增：获取指定记录的结构化与OCR信息
export const getExtractedRecordInfo = async (recordId) => {
  try {
    const response = await healthApi.get(`/api/health-records/${recordId}/extracted`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '获取结构化信息失败' };
  }
};

// 批量上传文件
export const uploadMultipleFiles = async (files, onProgress = null) => {
  try {
    const formData = new FormData();
    files.forEach((file, index) => {
      formData.append(`files`, file);
    });
    // 对齐后端健康档案批量上传端点
    const response = await healthApi.post('/api/health-records/upload/multiple', formData, {
      // 不要手动设置 Content-Type，浏览器会自动添加 boundary
      ...(onProgress
        ? {
            onUploadProgress: (progressEvent) => {
              const percentCompleted = Math.round(
                (progressEvent.loaded * 100) / progressEvent.total
              );
              onProgress(percentCompleted);
            },
          }
        : {}),
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '批量上传失败' };
  }
};

// 删除文件
export const deleteFile = async (fileId) => {
  try {
    const response = await healthApi.delete(`/files/${fileId}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '删除文件失败' };
  }
};

// === 健康数据API ===

// 获取健康数据 - 真实聚合自各模块接口
export const getHealthData = async (params = {}) => {
  try {
    const [recordsRes, consultationsRes, medicationsRes, remindersRes, summariesRes] = await Promise.all([
      healthApi.get('/api/health-records', { params: { limit: 100, ...(params || {}) } }).catch(() => ({ data: [] })),
      healthApi.get('/consultations').catch(() => ({ data: [] })),
      healthApi.get('/medications', { params: { is_active: true } }).catch(() => ({ data: [] })),
      healthApi.get('/api/medication-reminders', { params: { active_only: true } }).catch(() => ({ data: [] })),
      healthApi.get('/summaries').catch(() => ({ data: [] })),
    ]);
    const records = Array.isArray(recordsRes.data) ? recordsRes.data : [];
    const consultations = Array.isArray(consultationsRes.data) ? consultationsRes.data : [];
    const medications = Array.isArray(medicationsRes.data) ? medicationsRes.data : [];
    const reminders = Array.isArray(remindersRes.data) ? remindersRes.data : [];
    const summaries = Array.isArray(summariesRes.data) ? summariesRes.data : [];

    const remindersCount = reminders.filter((r) => !r.taken).length;

    return {
      recordsCount: records.length,
      consultationsCount: consultations.length,
      medicationsCount: medications.length,
      summariesCount: summaries.length,
      hasReminders: remindersCount > 0,
      remindersCount,
    };
  } catch (error) {
    // 返回安全的默认值，避免仪表盘白屏
    return {
      recordsCount: 0,
      consultationsCount: 0,
      medicationsCount: 0,
      summariesCount: 0,
      hasReminders: false,
      remindersCount: 0,
    };
  }
};

// 更新健康数据 - 模拟实现
export const updateHealthData = async (healthData) => {
  try {
    return { success: true };
  } catch (error) {
    throw error.response?.data || { message: '更新健康数据失败' };
  }
};

// 获取健康趋势 - 模拟数据
export const getHealthTrends = async (params = {}) => {
  try {
    // 返回模拟的健康趋势数据
    return [
      { date: '2024-09-01', value: 75 },
      { date: '2024-09-02', value: 78 },
      { date: '2024-09-03', value: 80 },
      { date: '2024-09-04', value: 79 },
      { date: '2024-09-05', value: 82 },
      { date: '2024-09-06', value: 81 },
      { date: '2024-09-07', value: 83 },
    ];
  } catch (error) {
    throw error.response?.data || { message: '获取健康趋势失败' };
  }
};

// === 智能路由 ===
export const smartChat = async (message) => {
  try {
    const response = await smartChatApi.post('/smart_chat', { message });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: '智能路由失败' };
  }
};

// 轮询获取智能体回复
const pollForAgentResponse = async (conversationId, maxAttempts = 30, interval = 1000) => {
  const { listMessages, getPendingMessages } = await import('../api/api');

  let attempts = 0;
  while (attempts < maxAttempts) {
    attempts++;

    // 检查是否还有消息在处理中
    const pending = await getPendingMessages();
    const hasPendingForConversation = pending.some((msg) =>
      msg.metadata?.conversation_id === conversationId
    );
    if (!hasPendingForConversation) {
      // 获取消息列表
      const messages = await listMessages(conversationId);
      return messages;
    }

    // 等待一段时间后继续轮询
    await new Promise((resolve) => setTimeout(resolve, interval));
  }

  return [];
};

// 获取智能体回复（供外部调用）
export const getAgentResponse = async (conversationId) => {
  return await pollForAgentResponse(conversationId);
};

export default healthApi;