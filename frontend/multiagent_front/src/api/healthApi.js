import axios from "axios";

// 创建axios实例
// 重要说明：不要为该实例设置默认的 'Content-Type'
// 让 axios 根据请求体自动选择（JSON 或 multipart/form-data）。
const healthApi = axios.create({
  baseURL: import.meta.env.VITE_HOSTAGENT_API || "http://127.0.0.1:13002",
  timeout: 10000,
});

// 智能路由API实例
const smartChatApi = axios.create({
  baseURL:
    import.meta.env.VITE_SMART_CHAT_API ||
    import.meta.env.VITE_HOSTAGENT_API ||
    "http://127.0.0.1:13002",
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
  },
});

// 认证API实例 - 使用hostAgentAPI的认证服务
const authApi = axios.create({
  baseURL: import.meta.env.VITE_HOSTAGENT_API || "http://127.0.0.1:13002",
  timeout: 10000,
  headers: {
    "Content-Type": "application/json",
  },
});

// 为authApi添加请求拦截器
authApi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

// 为authApi添加响应拦截器
authApi.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      // Token过期或无效，清除本地存储并跳转到登录页
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

// 请求拦截器 - 添加认证token
healthApi.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  },
);

// 响应拦截器 - 处理错误
healthApi.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    if (error.response?.status === 401) {
      // Token过期或无效，清除本地存储并跳转到登录页
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  },
);

// === 认证相关API ===

// 用户登录
// 用户登录 - 使用hostAgentAPI的认证服务
export const login = async (credentials) => {
  try {
    const response = await authApi.post("/auth/login", credentials);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "登录失败" };
  }
};

// 用户注册 - 使用hostAgentAPI的认证服务
export const register = async (userData) => {
  try {
    const response = await authApi.post("/auth/register", userData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "注册失败" };
  }
};

// 退出登录 - 使用hostAgentAPI的认证服务
export const logout = async () => {
  try {
    const response = await authApi.post("/auth/logout");
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "退出失败" };
  }
};

// 获取用户信息 - 使用hostAgentAPI的认证服务
export const getUserInfo = async () => {
  try {
    const response = await authApi.get("/auth/user");
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "获取用户信息失败" };
  }
};

// 验证Token - 使用hostAgentAPI的认证服务
export const verifyToken = async () => {
  try {
    const response = await authApi.get("/auth/verify");
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "Token验证失败" };
  }
};

// === 健康档案API ===

// 获取健康档案列表
export const getHealthRecords = async (params = {}) => {
  try {
    const response = await healthApi.get("/api/health-records", { params });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "获取健康档案失败" };
  }
};

// 创建健康档案
export const createHealthRecord = async (recordData) => {
  try {
    const response = await healthApi.post("/api/health-records", recordData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "创建健康档案失败" };
  }
};

// 更新健康档案
export const updateHealthRecord = async (id, recordData) => {
  try {
    const response = await healthApi.put(
      `/api/health-records/${id}`,
      recordData,
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "更新健康档案失败" };
  }
};

// 删除健康档案
export const deleteHealthRecord = async (id) => {
  try {
    const response = await healthApi.delete(`/api/health-records/${id}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "删除健康档案失败" };
  }
};

// === 健康咨询API ===

// 获取咨询历史 - 阶段48-9 支持按 agent_id 过滤
export const getConsultationHistory = async (params = {}) => {
  try {
    const response = await healthApi.get("/api/consultations/history", {
      params,
    });
    // 后端直接返回数组，非 { history: [] }
    return Array.isArray(response.data) ? response.data : [];
  } catch (error) {
    throw error.response?.data || { message: "获取咨询历史失败" };
  }
};

// 简化接口 — 直接通过 /api/consultations?agent_id=xxx 取
export const listConsultations = async (agentId = null) => {
  try {
    const params = agentId ? { agent_id: agentId } : {};
    const response = await healthApi.get("/api/consultations", { params });
    return Array.isArray(response.data) ? response.data : [];
  } catch (error) {
    throw error.response?.data || { message: "获取咨询列表失败" };
  }
};

// 创建新咨询
export const createConsultation = async (consultationData) => {
  try {
    const response = await healthApi.post(
      "/api/consultations/create",
      consultationData,
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "创建咨询失败" };
  }
};

// 发送消息
export const sendMessage = async (consultationId, messageData) => {
  try {
    const response = await healthApi.post("/api/consultations/message", {
      consultation_id: consultationId,
      ...messageData,
    });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "发送消息失败" };
  }
};

// 获取咨询消息
export const getConsultationMessages = async (consultationId) => {
  try {
    const response = await healthApi.get(
      `/api/consultations/${consultationId}/messages`,
    );
    return response.data.messages || [];
  } catch (error) {
    throw error.response?.data || { message: "获取消息失败" };
  }
};

// 删除咨询
export const deleteConsultation = async (consultationId) => {
  try {
    const response = await healthApi.delete(
      `/api/consultations/${consultationId}`,
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "删除咨询失败" };
  }
};

// === 用药管理API ===

// 获取药物列表
export const getMedications = async (params = {}) => {
  try {
    const response = await healthApi.get("/medications", { params });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "获取药物列表失败" };
  }
};

// 添加药物
export const addMedication = async (medicationData) => {
  try {
    const response = await healthApi.post("/medications", medicationData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "添加药物失败" };
  }
};

// 更新药物
export const updateMedication = async (id, medicationData) => {
  try {
    const response = await healthApi.put(`/medications/${id}`, medicationData);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "更新药物失败" };
  }
};

// 删除药物
export const deleteMedication = async (id) => {
  try {
    const response = await healthApi.delete(`/medications/${id}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "删除药物失败" };
  }
};

// 获取用药提醒
export const getMedicationReminders = async (params = {}) => {
  try {
    const response = await healthApi.get("/medication-reminders", { params });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "获取用药提醒失败" };
  }
};

// 设置用药提醒
export const setMedicationReminder = async (reminderData) => {
  try {
    const response = await healthApi.post(
      "/medication-reminders",
      reminderData,
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "设置用药提醒失败" };
  }
};

// 标记提醒为已服用
export const markReminderTaken = async (reminderId, takenTime = "") => {
  try {
    const response = await healthApi.post(
      `/medication-reminders/${reminderId}/taken`,
      null,
      {
        params: { taken_time: takenTime },
      },
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "标记服药失败" };
  }
};

// === 就诊摘要API ===

const normalizeVisitSummaryPayload = (data) => {
  const toDateString = (v) => {
    if (!v) return undefined;
    if (typeof v === "string") return v;
    if (v instanceof Date) return v.toISOString().slice(0, 10);
    if (typeof v === "object" && typeof v.format === "function") {
      return v.format("YYYY-MM-DD");
    }
    if (typeof v === "object" && typeof v.toDate === "function") {
      return v.toDate().toISOString().slice(0, 10);
    }
    return undefined;
  };

  const rawFiles = Array.isArray(data?.files) ? data.files : [];
  const files = rawFiles
    .map((f) => {
      if (typeof f === "string") return f;
      return f?.file_id || f?.id || f?.filename;
    })
    .filter(Boolean);

  const rawTests = Array.isArray(data?.tests) ? data.tests : [];
  const tests = rawTests.map((t) => {
    if (!t || typeof t !== "object") return t;
    const d = toDateString(t.date);
    return d ? { ...t, date: d } : t;
  });

  return {
    summary_id: data?.summary_id || data?.summaryId,
    title: data?.title,
    visit_date: toDateString(data?.visit_date || data?.visitDate),
    doctor: data?.doctor,
    hospital: data?.hospital,
    department: data?.department,
    chief_complaint: data?.chief_complaint || data?.chiefComplaint,
    symptoms: data?.symptoms,
    examination: data?.examination,
    diagnosis: data?.diagnosis,
    treatment: data?.treatment,
    prescription: data?.prescription,
    follow_up: data?.follow_up || data?.followUp,
    notes: data?.notes,
    files,
    tests,
    summary_content: data?.summary_content || data?.summaryContent,
  };
};

// 获取就诊摘要
export const getSummaries = async (params = {}) => {
  try {
    const response = await healthApi.get("/api/visit-summaries/history", {
      params,
    });
    // 后端直接返回数组
    return Array.isArray(response.data) ? response.data : [];
  } catch (error) {
    throw error.response?.data || { message: "获取就诊摘要失败" };
  }
};

// 创建就诊摘要
export const createSummary = async (summaryData) => {
  try {
    const payload = normalizeVisitSummaryPayload(summaryData);
    const response = await healthApi.post(
      "/api/visit-summaries/create",
      payload,
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "创建就诊摘要失败" };
  }
};

// 更新就诊摘要
export const updateSummary = async (id, summaryData) => {
  try {
    const payload = normalizeVisitSummaryPayload(summaryData);
    const response = await healthApi.put(
      `/api/visit-summaries/update/${id}`,
      payload,
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "更新就诊摘要失败" };
  }
};

// 删除就诊摘要
export const deleteSummary = async (id) => {
  try {
    const response = await healthApi.delete(
      `/api/visit-summaries/delete/${id}`,
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "删除就诊摘要失败" };
  }
};

// AI生成摘要 - 使用智能体流式接口，此处仅保留接口定义
export const generateAISummary = async (summaryData) => {
  // 注意：前端建议直接使用 sendTaskStreaming 调用智能体
  try {
    const response = await healthApi.post(
      "/api/visit-summaries/generate",
      summaryData,
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "AI生成摘要失败" };
  }
};

// === 文件上传API ===

// 上传文件
export const uploadFile = async (file, onProgress = null) => {
  try {
    const formData = new FormData();
    formData.append("file", file);
    const response = await healthApi.post(
      "/api/health-records/upload",
      formData,
      {
        timeout: 120000,
        // 不要手动设置 Content-Type，浏览器会自动添加 boundary
        ...(onProgress
          ? {
              onUploadProgress: (progressEvent) => {
                const percentCompleted = Math.round(
                  (progressEvent.loaded * 100) / progressEvent.total,
                );
                onProgress(percentCompleted);
              },
            }
          : {}),
      },
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "文件上传失败" };
  }
};

// 新增：根据 fileId 生成可直接访问的附件直链（HostAgentAPI网关会代理到后端）
export const getAttachmentUrl = (fileId) => {
  if (!fileId) return "";
  // healthApi.defaults.baseURL 例如 http://localhost:13002
  // 注意: 阶段48-22 v6 修复 — 之前 /api/health-records/files/<id> 是错的
  //   正确路由是 /v2/files/<id> (upload_pipeline.py serve_file)
  const base = healthApi.defaults.baseURL?.replace(/\/$/, "") || "";
  return `${base}/v2/files/${encodeURIComponent(fileId)}`;
};

// 新增：手动重跑 OCR. 阶段48-22 v6 替换老 /api/health-records/{id}/extracted (404).
export const reextractFile = async (fileId, userId, opts = {}) => {
  try {
    const response = await healthApi.post(
      `/v2/upload/files/${encodeURIComponent(fileId)}/reextract`,
      { user_id: userId, force: !!opts.force },
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: `OCR 重跑失败 (${fileId})`, ocr_error: String(error) };
  }
};

// 兼容旧名字 (避免改业务页面 import)
export const getExtractedRecordInfo = async (recordId) => {
  try {
    // 阶段48-22 v6: 老接口已 404, 改走 /api/health-records/{id} 拿最新数据
    //   (OCR 文本已经在 file_attachments/uploaded_files 里, 后端 merge 进 metadata._attached_files_meta)
    const response = await healthApi.get(`/api/health-records/${recordId}`);
    const files = response.data?.metadata?._attached_files_meta || [];
    // 把 list 形式转成老 extracted API 的 shape (OCR key=full_join)
    const merged = {
      ok: true,
      source: "reextract-stub",
      record_id: recordId,
      ocr_text: files.map((f) => f.file_name ? `[${f.file_name}] ${f.ocr_status}` : f.ocr_status).join("\n"),
      files,
    };
    return merged;
  } catch (error) {
    throw error.response?.data || { message: "获取结构化信息失败" };
  }
};

// 新增: 对一条 record 上所有附件 OCR 重跑
export const extractHealthRecord = async (recordId) => {
  // 先拉 record, 拿到 files list + user_id
  const r = await healthApi.get(`/api/health-records/${recordId}`);
  const data = r.data || {};
  const meta = data.metadata || {};
  const files = meta._attached_files_meta || [];
  const uid = data.user_id;
  if (!uid) throw { message: "无 user_id" };
  if (!files.length) {
    return { ok: false, message: "本档案没有附件可 OCR", files_ocr: [] };
  }
  const results = [];
  for (const f of files) {
    try {
      const r2 = await reextractFile(f.file_id, uid, { force: false });
      results.push({ ...f, reextract: r2 });
    } catch (e) {
      results.push({ ...f, reextract: { ok: false, ocr_error: e?.message || "fail" } });
    }
  }
  // 用全部 OCR 文本拼成完整正文 (写回 record.content)
  const fullText = results
    .filter((r) => r.reextract?.ocr_text)
    .map((r) => `\n## ${r.file_name || r.file_id}\n\n${r.reextract.ocr_text}`)
    .join("\n");
  if (fullText && !data.content) {
    try {
      await healthApi.put(`/api/health-records/${recordId}`, {
        content: fullText,
      });
    } catch (e) {
      // 不强制, 写回失败也没事 (前端缓存即可)
    }
  }
  return { ok: true, full_text: fullText, files_ocr: results };
};

// 批量上传文件
export const uploadMultipleFiles = async (files, onProgress = null) => {
  try {
    const formData = new FormData();
    files.forEach((file, index) => {
      formData.append(`files`, file);
    });
    // 对齐后端健康档案批量上传端点
    const response = await healthApi.post(
      "/api/health-records/upload/multiple",
      formData,
      {
        timeout: 120000,
        // 不要手动设置 Content-Type，浏览器会自动添加 boundary
        ...(onProgress
          ? {
              onUploadProgress: (progressEvent) => {
                const percentCompleted = Math.round(
                  (progressEvent.loaded * 100) / progressEvent.total,
                );
                onProgress(percentCompleted);
              },
            }
          : {}),
      },
    );
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "批量上传失败" };
  }
};

// 删除文件
export const deleteFile = async (fileId) => {
  try {
    const response = await healthApi.delete(`/files/${fileId}`);
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "删除文件失败" };
  }
};

// === 健康数据API ===

// 获取健康数据 - 真实聚合自各模块接口
export const getHealthData = async (params = {}) => {
  try {
    const [
      recordsRes,
      consultationsRes,
      medicationsRes,
      remindersRes,
      summariesRes,
    ] = await Promise.all([
      healthApi
        .get("/api/health-records", {
          params: { limit: 100, ...(params || {}) },
        })
        .catch(() => ({ data: [] })),
      healthApi.get("/consultations").catch(() => ({ data: [] })),
      healthApi
        .get("/medications", { params: { is_active: true } })
        .catch(() => ({ data: [] })),
      healthApi
        .get("/api/medication-reminders", { params: { active_only: true } })
        .catch(() => ({ data: [] })),
      healthApi.get("/summaries").catch(() => ({ data: [] })),
    ]);
    const records = Array.isArray(recordsRes.data) ? recordsRes.data : [];
    const consultations = Array.isArray(consultationsRes.data)
      ? consultationsRes.data
      : [];
    const medications = Array.isArray(medicationsRes.data)
      ? medicationsRes.data
      : [];
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
    throw error.response?.data || { message: "更新健康数据失败" };
  }
};

// 获取健康趋势 - 阶段48-8: 实际计算交给 utils/healthMetrics.js
// API 返回 null, 让前端用真实算法计算 (recList/medList/convs)
export const getHealthTrends = async (params = {}) => {
  return null; // no-op, 前端用 utils
};

// 获取服药历史 (未实现 - 给个兜底)
export const getMedicationsHistory = async (params = {}) => {
  return [
    { day: "周一", value: 85 },
    { day: "周二", value: 92 },
    { day: "周三", value: 78 },
    { day: "周四", value: 88 },
    { day: "周五", value: 95 },
    { day: "周六", value: 100 },
    { day: "今日", value: 60 },
  ];
};

// === 智能路由 ===
export const smartChat = async (message) => {
  try {
    const response = await smartChatApi.post("/smart_chat", { message });
    return response.data;
  } catch (error) {
    throw error.response?.data || { message: "智能路由失败" };
  }
};

// 轮询获取智能体回复
const pollForAgentResponse = async (
  conversationId,
  maxAttempts = 30,
  interval = 1000,
) => {
  const { listMessages, getPendingMessages } = await import("../api/api");

  let attempts = 0;
  while (attempts < maxAttempts) {
    attempts++;

    // 检查是否还有消息在处理中
    const pending = await getPendingMessages();
    const hasPendingForConversation = pending.some(
      (msg) => msg.metadata?.conversation_id === conversationId,
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
