const SERVER_URL = "http://127.0.0.1:13002"; // The default address of hostAgentAPI is http://127.0.0.1:13002

// A generic request function
const request = (endpoint, options = {}) => {
  return new Promise((resolve, reject) => {
    const userInfo = wx.getStorageSync("userInfo");
    const token = userInfo ? userInfo.token : "";
    const header = {
      "Content-Type": "application/json",
      ...options.headers,
    };
    if (token) {
      header["Authorization"] = `Bearer ${token}`;
    }

    wx.request({
      url: `${SERVER_URL}${endpoint}`,
      method: options.method || "GET",
      data: options.data || {},
      header: header,
      timeout: options.timeout || 60000, // Increase timeout to 60 seconds
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          // The backend may wrap the data in a 'result' field
          resolve(res.data.result !== undefined ? res.data.result : res.data);
        } else if (res.statusCode === 401 || res.statusCode === 403) {
          // Token expired or invalid
          wx.removeStorageSync("userInfo");
          wx.showToast({
            title: "登录已过期，请重新登录",
            icon: "none",
            duration: 2000,
          });
          setTimeout(() => {
            wx.reLaunch({
              url: "/pages/login/login",
            });
          }, 1000);
          reject(res);
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
const checkApiStatus = () => {
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
const listRemoteAgents = () => {
  return request("/agent/list", { method: "POST", data: {} });
};

// Send a message
const sendMessage = (message) => {
  const options = {
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
          ...(message.metadata || {}),
        },
      },
    },
    headers: {},
    timeout: 120000,
  };

  // Extract selected_agent from metadata and add to headers
  if (message.metadata && message.metadata.selected_agent) {
    options.headers["X-Target-Agent"] = encodeURIComponent(
      message.metadata.selected_agent
    );
  }

  return request("/message/send", options);
};

// Create a new conversation
const createConversation = () => {
  return request("/conversation/create", { method: "POST", data: {} });
};

// List messages in a conversation
const listMessages = (conversationId) => {
  return request("/message/list", {
    method: "POST",
    data: { params: { conversation_id: conversationId } },
  });
};

// The image upload function
const uploadFile = (
  filePath,
  endpoint = "/api/health-records/upload",
  formData = {}
) => {
  return new Promise((resolve, reject) => {
    const userInfo = wx.getStorageSync("userInfo");
    const token = userInfo ? userInfo.token : "";
    const header = {};
    if (token) {
      header["Authorization"] = `Bearer ${token}`;
    }

    wx.uploadFile({
      url: `${SERVER_URL}${endpoint}`,
      filePath: filePath,
      name: "file",
      formData: formData,
      header: header,
      success: (res) => {
        let data = res.data;
        try {
          // wx.uploadFile returns string response
          data = JSON.parse(data);
        } catch (e) {}

        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data);
        } else if (res.statusCode === 401 || res.statusCode === 403) {
          wx.removeStorageSync("userInfo");
          wx.showToast({
            title: "登录已过期",
            icon: "none",
          });
          setTimeout(() => {
            wx.reLaunch({ url: "/pages/login/login" });
          }, 1000);
          reject(res);
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

// 用户登录
const login = (username, password) => {
  return request("/auth/login", {
    method: "POST",
    data: { username, password },
  });
};

// 用户注册
const register = (username, password, email, phone) => {
  return request("/auth/register", {
    method: "POST",
    data: { username, password, email, phone },
  });
};

// 获取用户信息
const getUserInfo = (token) => {
  return request("/auth/user", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
};

// 获取正在处理的消息
const getProcessingMessages = () => {
  return request("/message/pending", { method: "POST", data: {} });
};

// 根据对话id获取它的事件
const queryEvents = (conversationId) => {
  return request("/events/query", {
    method: "POST",
    data: { params: { conversation_id: conversationId } },
  });
};

// 获取就诊摘要历史
const getVisitSummaries = (skip = 0, limit = 20, user_id = null) => {
  const params = { skip, limit };
  if (user_id) params.user_id = user_id;
  return request("/api/visit-summaries/history", {
    method: "GET",
    data: params,
  });
};

// 获取健康咨询历史
const getConsultationHistory = (skip = 0, limit = 20, user_id = null) => {
  const params = { skip, limit };
  if (user_id) params.user_id = user_id;
  return request("/api/consultations/history", {
    method: "GET",
    data: params,
  });
};

// 创建咨询记录
const createConsultation = (consultationData, user_id = null) => {
  let url = "/api/consultations/create";
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "POST",
    data: consultationData,
    headers: {
      "Content-Type": "application/json",
    },
  });
};

// 创建就诊摘要
const createVisitSummary = (summaryData, user_id = null) => {
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
const getMedications = (user_id = null) => {
  let url = "/api/medications";
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "GET",
  });
};

// 创建用药记录
const createMedication = (medicationData, user_id = null) => {
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
const getMedicationReminders = (date = "", user_id = null) => {
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
const markMedicationTaken = (reminderId, user_id = null) => {
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
const createMedicationReminder = (reminderData, user_id = null) => {
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

// 解析智能体 URL (将 Docker 内部域名转换为 localhost/IP)
const resolveAgentUrl = (url) => {
  if (!url) return url;

  // 1. 处理 0.0.0.0 和 localhost 替换为 127.0.0.1 (Windows 兼容性)
  let resolvedUrl = url
    .replace("0.0.0.0", "127.0.0.1")
    .replace("localhost", "127.0.0.1");

  // 服务映射表 (Docker Service Name -> Port)
  const svcMap = {
    health_records: "10010",
    health_advisor: "10011",
    medication_reminder: "10012",
    visit_summary: "10013",
  };

  // 2. 根据服务名匹配
  for (const [name, port] of Object.entries(svcMap)) {
    // 匹配 http://health_advisor:10011 或 health_advisor
    if (resolvedUrl.includes(`://${name}`) || resolvedUrl.includes(name)) {
      return `http://127.0.0.1:${port}`;
    }
    // 3. 根据端口匹配 (如果 URL 中没有服务名，但端口匹配)
    if (resolvedUrl.includes(`:${port}`)) {
      return `http://127.0.0.1:${port}`;
    }
  }

  return resolvedUrl;
};

// 上传药物图片进行OCR
const uploadMedicationImage = (filePath, user_id = null) => {
  let endpoint = "/api/medications/ocr";
  if (user_id) {
    endpoint += `?user_id=${user_id}`;
  }
  return uploadFile(filePath, endpoint);
};

// 获取智能体卡片信息
const getAgentCard = (agentUrl) => {
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
const sendTaskStreaming = (
  agentUrl,
  payload,
  onMessage,
  onError,
  onComplete
) => {
  // 确保 agentUrl 没有末尾斜杠
  const cleanAgentUrl = agentUrl.endsWith("/")
    ? agentUrl.slice(0, -1)
    : agentUrl;

  // 构造 JSON-RPC 请求体
  const requestBody = {
    jsonrpc: "2.0",
    method: "tasks/sendSubscribe",
    params: payload,
    id: `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
  };

  const userInfo = wx.getStorageSync("userInfo");
  const token = userInfo ? userInfo.token : "";

  // 微信小程序流式请求
  const requestTask = wx.request({
    url: cleanAgentUrl, // A2A Server 直接监听根路径
    method: "POST",
    data: requestBody,
    enableChunked: true,
    timeout: 300000,
    header: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    success: (res) => {
      if (res.statusCode >= 200 && res.statusCode < 300) {
        // 请求成功
      } else {
        if (onError) onError(res);
      }
    },
    fail: (err) => {
      if (onError) onError(err);
    },
    complete: () => {
      // onComplete is handled by [DONE] message or manual check
    },
  });

  requestTask.onChunkReceived((response) => {
    const arrayBuffer = response.data;
    let uint8Array = new Uint8Array(arrayBuffer);

    // 累积缓冲区处理多字节字符截断问题
    if (requestTask._pendingBuffer) {
      const newBuffer = new Uint8Array(
        requestTask._pendingBuffer.length + uint8Array.length
      );
      newBuffer.set(requestTask._pendingBuffer, 0);
      newBuffer.set(uint8Array, requestTask._pendingBuffer.length);
      uint8Array = newBuffer;
      requestTask._pendingBuffer = null;
    }

    let safeEnd = uint8Array.length;
    // 检查末尾是否是不完整的 UTF-8 序列
    // 向回查找最多3个字节
    for (let k = 1; k <= 3 && safeEnd - k >= 0; k++) {
      const b = uint8Array[safeEnd - k];
      if ((b & 0xc0) === 0x80) {
        // 是后续字节 (10xxxxxx)，继续向前
        continue;
      }
      // 找到了开始字节
      let seqLen = 0;
      if ((b & 0xe0) === 0xc0) seqLen = 2;
      else if ((b & 0xf0) === 0xe0) seqLen = 3;
      else if ((b & 0xf8) === 0xf0) seqLen = 4;

      if (seqLen > 0) {
        // 如果剩余长度不足完整序列，则截断
        if (k < seqLen) {
          safeEnd = safeEnd - k;
          requestTask._pendingBuffer = uint8Array.slice(safeEnd);
        }
      }
      break; // 找到开始字节后停止
    }

    const validData = uint8Array.slice(0, safeEnd);
    let text = "";

    // 优先使用 TextDecoder
    if (typeof TextDecoder !== "undefined") {
      try {
        text = new TextDecoder("utf-8").decode(validData);
      } catch (e) {
        console.error("TextDecoder failed:", e);
        // Fallback manual decode
        text = utf8ArrayToString(validData);
      }
    } else {
      text = utf8ArrayToString(validData);
    }

    console.log("[Stream] Chunk received:", text);

    // 处理 SSE 格式
    // 需要处理跨 chunk 的行分割
    const fullText = (requestTask._pendingText || "") + text;
    const lines = fullText.split("\n");

    // 如果最后一行不是空字符串，说明最后一行可能不完整，保留到下一次
    // SSE 消息通常以 \n\n 结束，所以最后一行如果是空的，说明上一条消息完整
    if (fullText.length > 0 && !fullText.endsWith("\n") && lines.length > 0) {
      requestTask._pendingText = lines.pop();
    } else {
      requestTask._pendingText = "";
    }

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const jsonStr = line.substring(6).trim();
        if (jsonStr === "[DONE]") {
          console.log("[Stream] DONE signal received");
          if (onComplete) onComplete();
          return;
        }
        try {
          const data = JSON.parse(jsonStr);
          if (onMessage) onMessage(data);
        } catch (e) {
          console.error("Parse error:", e, "JSON:", jsonStr);
        }
      }
    }
  });

  return requestTask;
};

// Helper function for manual UTF-8 decoding
function utf8ArrayToString(array) {
  let out = "";
  let i = 0;
  let len = array.length;
  let c;
  let char2, char3;

  while (i < len) {
    c = array[i++];
    switch (c >> 4) {
      case 0:
      case 1:
      case 2:
      case 3:
      case 4:
      case 5:
      case 6:
      case 7:
        // 0xxxxxxx
        out += String.fromCharCode(c);
        break;
      case 12:
      case 13:
        // 110x xxxx   10xx xxxx
        char2 = array[i++];
        out += String.fromCharCode(((c & 0x1f) << 6) | (char2 & 0x3f));
        break;
      case 14:
        // 1110 xxxx  10xx xxxx  10xx xxxx
        char2 = array[i++];
        char3 = array[i++];
        out += String.fromCharCode(
          ((c & 0x0f) << 12) | ((char2 & 0x3f) << 6) | (char3 & 0x3f)
        );
        break;
    }
  }
  return out;
}

// 保存咨询消息
const saveConsultationMessage = (data) => {
  return request("/api/consultations/message", {
    method: "POST",
    data: data,
  });
};

// 获取咨询消息历史 (从数据库)
const getConsultationMessages = (consultationId) => {
  return request(`/api/consultations/${consultationId}/messages`, {
    method: "GET",
  });
};

const deleteConsultation = (consultationId, user_id = null) => {
  let url = `/api/consultations/${consultationId}`;
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "DELETE",
  });
};

module.exports = {
  request,
  checkApiStatus,
  listRemoteAgents,
  sendMessage,
  createConversation,
  listMessages,
  uploadFile,
  login,
  register,
  getUserInfo,
  getProcessingMessages,
  queryEvents,
  getVisitSummaries,
  createVisitSummary,
  getConsultationHistory,
  createConsultation,
  saveConsultationMessage,
  getConsultationMessages,
  deleteConsultation,
  getMedications,
  createMedication,
  getMedicationReminders,
  markMedicationTaken,
  createMedicationReminder,
  uploadMedicationImage,
  getAgentCard,
  sendTaskStreaming,
  resolveAgentUrl,
  SERVER_URL,
};
