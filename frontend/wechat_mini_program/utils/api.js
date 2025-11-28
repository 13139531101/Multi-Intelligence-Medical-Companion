const SERVER_URL = "http://127.0.0.1:13000"; // The default address of hostAgentAPI is http://127.0.0.1:13001

// A generic request function
const request = (endpoint, options = {}) => {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${SERVER_URL}${endpoint}`,
      method: options.method || "GET",
      data: options.data || {},
      header: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          // The backend may wrap the data in a 'result' field
          resolve(res.data.result !== undefined ? res.data.result : res.data);
        } else {
          reject(res);
        }
      },
      fail: (err) => {
        reject(err);
      },
    });
  });
};

// Check if the API is alive
export const checkApiStatus = () => {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${SERVER_URL}/ping`,
      method: "GET",
      success: (res) => {
        if (res.statusCode === 200 && res.data === "Pong") {
          resolve(true);
        } else {
          resolve(false);
        }
      },
      fail: (err) => {
        console.error("Ping API request failed:", err);
        resolve(false);
      },
    });
  });
};

// List remote agents
export const listRemoteAgents = () => {
  return request("/agent/list", { method: "POST", data: {} });
};

// Send a message
export const sendMessage = (message) => {
  return request("/message/send", {
    method: "POST",
    data: {
      params: {
        role: message.role,
        parts: [{ type: "text", text: message.message }],
        metadata: {
          conversation_id: message.conversation_id,
          message_id: `msg_${Date.now()}_${Math.random()
            .toString(36)
            .substr(2, 9)}`,
        },
      },
    },
  });
};

// Create a new conversation
export const createConversation = () => {
  return request("/conversation/create", { method: "POST", data: {} });
};

// List messages in a conversation
export const listMessages = (conversationId) => {
  return request("/message/list", {
    method: "POST",
    data: { params: { conversation_id: conversationId } },
  });
};

// The image upload function will be implemented here later
export const uploadFile = (filePath) => {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: `${SERVER_URL}/api/health-records/upload`, // The backend upload address needs to be implemented
      filePath: filePath,
      name: "file",
      success: (res) => {
        resolve(res.data);
      },
      fail: (err) => {
        reject(err);
      },
    });
  });
};

// 用户登录
export const login = (username, password) => {
  return request("/auth/login", {
    method: "POST",
    data: { username, password },
  });
};

// 用户注册
export const register = (username, password, email, phone) => {
  return request("/auth/register", {
    method: "POST",
    data: { username, password, email, phone },
  });
};

// 获取用户信息
export const getUserInfo = (token) => {
  return request("/auth/user", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
};

// 获取正在处理的消息
export const getProcessingMessages = () => {
  return request("/message/pending", { method: "POST", data: {} });
};

// 根据对话id获取它的事件
export const queryEvents = (conversationId) => {
  return request("/events/query", {
    method: "POST",
    data: { params: { conversation_id: conversationId } },
  });
};

// 获取就诊摘要历史
export const getVisitSummaries = (skip = 0, limit = 20, user_id = null) => {
  const params = { skip, limit };
  if (user_id) params.user_id = user_id;
  return request("/api/visit-summaries/history", {
    method: "GET",
    data: params,
  });
};

// 获取健康咨询历史
export const getConsultationHistory = (
  skip = 0,
  limit = 20,
  user_id = null
) => {
  const params = { skip, limit };
  if (user_id) params.user_id = user_id;
  return request("/api/consultations/history", {
    method: "GET",
    data: params,
  });
};

// 创建就诊摘要
export const createVisitSummary = (summaryData, user_id = null) => {
  let url = "/api/visit-summaries/create";
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "POST",
    data: summaryData,
    headers: {
      "Content-Type": "application/json",
    },
  });
};

// 获取所有用药记录
export const getMedications = (user_id = null) => {
  let url = "/api/medications";
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "GET",
  });
};

// 创建用药记录
export const createMedication = (medicationData, user_id = null) => {
  let url = "/api/medications";
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "POST",
    data: medicationData,
    headers: {
      "Content-Type": "application/json",
    },
  });
};

// 获取用药提醒（特定日期状态）
export const getMedicationReminders = (date = "", user_id = null) => {
  let url = "/api/medication-reminders";
  const params = [];
  if (date) params.push(`date=${date}`);
  if (user_id) params.push(`user_id=${user_id}`);
  if (params.length > 0) url += `?${params.join("&")}`;

  return request(url, {
    method: "GET",
  });
};

// 标记用药已服用
export const markMedicationTaken = (reminderId, user_id = null) => {
  let url = `/api/medication-reminders/${reminderId}/taken`;
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "POST",
    data: {},
  });
};

// 创建用药提醒（单独设置）
export const createMedicationReminder = (reminderData, user_id = null) => {
  let url = "/api/medication-reminders";
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "POST",
    data: reminderData,
    headers: {
      "Content-Type": "application/json",
    },
  });
};

// 上传药物图片进行OCR
export const uploadMedicationImage = (filePath, user_id = null) => {
  return new Promise((resolve, reject) => {
    let url = `${SERVER_URL}/api/medications/ocr`;
    if (user_id) {
      url += `?user_id=${user_id}`;
    }
    wx.uploadFile({
      url: url,
      filePath: filePath,
      name: "file",
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try {
            const data = JSON.parse(res.data);
            resolve(data);
          } catch (e) {
            resolve(res.data);
          }
        } else {
          reject(res);
        }
      },
      fail: (err) => {
        reject(err);
      },
    });
  });
};

// 获取智能体卡片信息
export const getAgentCard = (agentUrl) => {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${agentUrl}/info`,
      method: "GET",
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(res);
        }
      },
      fail: (err) => {
        reject(err);
      },
    });
  });
};

// 发送任务（流式）- 直接连接智能体
export const sendTaskStreaming = (
  agentUrl,
  payload,
  onMessage,
  onError,
  onComplete
) => {
  const requestTask = wx.request({
    url: `${agentUrl}/tasks`,
    method: "POST",
    data: payload,
    enableChunked: true, // 开启流式传输
    header: {
      "Content-Type": "application/json",
    },
    success: (res) => {
      if (res.statusCode >= 200 && res.statusCode < 300) {
        // 请求成功完成
        if (onComplete) onComplete();
      } else {
        if (onError) onError(res);
      }
    },
    fail: (err) => {
      if (onError) onError(err);
    },
  });

  // 监听分块接收数据
  requestTask.onChunkReceived((response) => {
    // response.data 是 ArrayBuffer
    const arrayBuffer = response.data;
    const uint8Array = new Uint8Array(arrayBuffer);
    // 微信小程序中 TextDecoder 可能不可用，使用简单转换（假设是 UTF-8）
    // 或者使用第三方库。这里尝试简单转换。
    let text = "";
    for (let i = 0; i < uint8Array.length; i++) {
      text += String.fromCharCode(uint8Array[i]);
    }

    // 由于中文等多字节字符可能被截断，这里只是简单处理。
    // 在生产环境建议使用兼容小程序的 TextDecoder 库。
    // 这里为了演示，假设数据块是完整的 SSE 消息。

    // 解析 SSE 格式: data: {...}
    const lines = text.split("\n");
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const jsonStr = line.substring(6);
          if (jsonStr.trim() === "[DONE]") {
            if (onComplete) onComplete();
            continue;
          }
          const data = JSON.parse(jsonStr);
          if (onMessage) onMessage(data);
        } catch (e) {
          console.error("Failed to parse chunk:", e);
        }
      }
    }
  });

  return requestTask;
};
