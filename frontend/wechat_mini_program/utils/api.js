// 阶段35: 默认连本地 docker (hostapi stage35fix1 容器，端口 13002)
// 微信开发者工具调试时需要：详情 → 本地设置 → 勾选"不校验合法域名"
// 也可以在 wx.setStorageSync("SERVER_URL", "http://你的IP:13002") 运行时切换
const DEFAULT_SERVER_URL = "http://127.0.0.1:13002";
// const DEFAULT_SERVER_URL = "http://8.155.166.136:13002";   // 公网（已废弃）
// const DEFAULT_SERVER_URL = "http://www.duozhiyiban.icu";     // 域名（旧）

const normalizeBaseUrl = (raw) => {
  let s = String(raw || "")
    .replace(/[\u200B-\u200D\u2060\uFEFF]/g, "")
    .trim();
  if (!s) return "";
  const pairs = [
    ['"', '"'],
    ["'", "'"],
    ["`", "`"],
    ["“", "”"],
    ["‘", "’"],
  ];
  let changed = true;
  while (changed && s.length >= 2) {
    changed = false;
    for (let i = 0; i < pairs.length; i += 1) {
      const left = pairs[i][0];
      const right = pairs[i][1];
      if (s.startsWith(left) && s.endsWith(right)) {
        s = s.slice(1, -1).trim();
        changed = true;
        break;
      }
    }
  }
  if (!/^https?:\/\//i.test(s)) return "";
  try {
    const u = new URL(s);
    if (u.hostname === "0.0.0.0") {
      u.hostname = "127.0.0.1";
    }
    return u.toString().replace(/\/+$/, "");
  } catch (e) {
    return s.replace(/\/+$/, "");
  }
};

const getServerUrlFromRuntime = () => {
  try {
    const stored =
      wx.getStorageSync("SERVER_URL") ||
      wx.getStorageSync("serverUrl") ||
      wx.getStorageSync("server_url") ||
      "";
    if (stored) {
      const normalizedStored = normalizeBaseUrl(stored);
      if (normalizedStored) return normalizedStored;
    }

    const ext = wx.getExtConfigSync ? wx.getExtConfigSync() : null;
    const extUrl = ext && (ext.SERVER_URL || ext.serverUrl || ext.server_url);
    if (extUrl) {
      const normalizedExtUrl = normalizeBaseUrl(extUrl);
      if (normalizedExtUrl) return normalizedExtUrl;
    }
  } catch (e) {}

  return normalizeBaseUrl(DEFAULT_SERVER_URL) || "http://127.0.0.1:13003";
};

const SERVER_URL = getServerUrlFromRuntime();

// 阶段35: 调试日志（启动时打印当前 SERVER_URL 来源）
try {
  const stored =
    wx.getStorageSync("SERVER_URL") ||
    wx.getStorageSync("serverUrl") ||
    wx.getStorageSync("server_url") ||
    "";
  let source = "DEFAULT";
  if (stored && normalizeBaseUrl(stored)) {
    source = "storage";
  } else {
    const ext = wx.getExtConfigSync ? wx.getExtConfigSync() : null;
    const extUrl = ext && (ext.SERVER_URL || ext.serverUrl || ext.server_url);
    if (extUrl && normalizeBaseUrl(extUrl)) source = "ext";
  }
  console.log("[PHA] SERVER_URL =", SERVER_URL, "(来源:", source + ")");
  if (source === "storage" && SERVER_URL !== "http://127.0.0.1:13002") {
    console.warn(
      "[PHA] ⚠️  Storage 里的 SERVER_URL 覆盖了默认值！\n" +
        "        当前连: " +
        SERVER_URL +
        "\n" +
        "        如需切换到本地 docker，请执行：\n" +
        "        wx.setStorageSync('SERVER_URL', 'http://127.0.0.1:13002')\n" +
        "        然后清除缓存或重新编译。",
    );
  }
} catch (e) {}

const ensureHttpsUrl = (url) => {
  const s = String(url || "").trim();
  if (!s) return "";
  if (s.startsWith("https://")) return s;
  if (s.startsWith("http://")) return `https://${s.slice("http://".length)}`;
  return s;
};

const isReleaseLike = () => {
  try {
    const v = wx.getAccountInfoSync
      ? wx.getAccountInfoSync().miniProgram.envVersion
      : "";
    return v === "release" || v === "trial";
  } catch (e) {
    return false;
  }
};

const resolveFileUrl = (fileIdOrUrl) => {
  if (!fileIdOrUrl) return "";
  let raw = fileIdOrUrl;
  if (typeof raw === "object") {
    raw =
      raw.url ||
      raw.file_url ||
      raw.fileId ||
      raw.file_id ||
      raw.id ||
      raw.path ||
      "";
  }
  const s = String(raw || "").trim();
  if (!s) return "";
  const url =
    s.startsWith("http://") || s.startsWith("https://")
      ? s
      : `${SERVER_URL}/api/health-records/files/${encodeURIComponent(s)}`;
  return isReleaseLike() ? ensureHttpsUrl(url) : url;
};

// A generic request function
const request = (endpoint, options = {}) => {
  return new Promise((resolve, reject) => {
    const userInfo = wx.getStorageSync("userInfo");
    const token = userInfo ? userInfo.token : "";
    const header = Object.assign(
      {
        "Content-Type": "application/json",
      },
      options.headers || {},
    );
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

const rightRotate = (value, amount) =>
  (value >>> amount) | (value << (32 - amount));

const sha256 = (ascii) => {
  const maxWord = Math.pow(2, 32);
  const lengthProperty = "length";
  let i;
  let j;
  let result = "";
  const words = [];
  const asciiBitLength = ascii[lengthProperty] * 8;
  const hash = [];
  const k = [];
  let primeCounter = k[lengthProperty];
  const isComposite = {};
  for (let candidate = 2; primeCounter < 64; candidate += 1) {
    if (!isComposite[candidate]) {
      for (i = 0; i < 313; i += candidate) {
        isComposite[i] = candidate;
      }
      hash[primeCounter] = (Math.pow(candidate, 0.5) * maxWord) | 0;
      k[primeCounter] = (Math.pow(candidate, 1 / 3) * maxWord) | 0;
      primeCounter += 1;
    }
  }
  ascii += "\x80";
  while ((ascii[lengthProperty] % 64) - 56) ascii += "\x00";
  for (i = 0; i < ascii[lengthProperty]; i += 1) {
    j = ascii.charCodeAt(i);
    if (j >> 8) return "";
    words[i >> 2] |= j << (((3 - i) % 4) * 8);
  }
  words[words[lengthProperty]] = (asciiBitLength / maxWord) | 0;
  words[words[lengthProperty]] = asciiBitLength;
  for (j = 0; j < words[lengthProperty]; ) {
    const w = words.slice(j, (j += 16));
    const oldHash = hash.slice(0);
    for (i = 0; i < 64; i += 1) {
      const w15 = w[i - 15];
      const w2 = w[i - 2];
      const a = hash[0];
      const e = hash[4];
      const temp1 =
        hash[7] +
        (rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25)) +
        ((e & hash[5]) ^ (~e & hash[6])) +
        k[i] +
        (w[i] =
          i < 16
            ? w[i]
            : (w[i - 16] +
                (rightRotate(w15, 7) ^ rightRotate(w15, 18) ^ (w15 >>> 3)) +
                w[i - 7] +
                (rightRotate(w2, 17) ^ rightRotate(w2, 19) ^ (w2 >>> 10))) |
              0);
      const temp2 =
        (rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22)) +
        ((a & hash[1]) ^ (a & hash[2]) ^ (hash[1] & hash[2]));
      hash.unshift((temp1 + temp2) | 0);
      hash[4] = (hash[4] + temp1) | 0;
      hash.pop();
    }
    for (i = 0; i < 8; i += 1) {
      hash[i] = (hash[i] + oldHash[i]) | 0;
    }
  }
  for (i = 0; i < 8; i += 1) {
    for (j = 3; j + 1; j -= 1) {
      const b = (hash[i] >> (j * 8)) & 255;
      result += (b < 16 ? 0 : "") + b.toString(16);
    }
  }
  return result;
};

const toSha256Payload = (password) => {
  const raw = String(password || "");
  const digest = sha256(raw);
  return digest ? `sha256:${digest}` : raw;
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
        metadata: Object.assign(
          {
            conversation_id: message.conversation_id,
            message_id: `msg_${Date.now()}_${Math.random()
              .toString(36)
              .substr(2, 9)}`,
          },
          message.metadata || {},
        ),
      },
    },
    headers: {},
    timeout: 120000,
  };

  // Extract selected_agent from metadata and add to headers
  if (message.metadata && message.metadata.selected_agent) {
    options.headers["X-Target-Agent"] = encodeURIComponent(
      message.metadata.selected_agent,
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
  formData = {},
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

const transcribeAudioFile = (filePath) => {
  return new Promise((resolve, reject) => {
    const userInfo = wx.getStorageSync("userInfo");
    const token = userInfo ? userInfo.token : "";
    const header = {};
    if (token) {
      header["Authorization"] = `Bearer ${token}`;
    }
    wx.uploadFile({
      url: `${SERVER_URL}/api/audio/transcribe`,
      filePath,
      name: "file",
      header,
      success: (res) => {
        let data = res.data;
        try {
          data = JSON.parse(data);
        } catch (e) {}
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data);
          return;
        }
        reject(data || res);
      },
      fail: (err) => reject(err),
    });
  });
};

// 用户登录
const login = (username, password) => {
  const encryptedPayload = {
    username,
    password: toSha256Payload(password),
  };
  return request("/auth/login", {
    method: "POST",
    data: encryptedPayload,
  }).catch((error) => {
    if (error && (error.statusCode === 401 || error.statusCode === 400)) {
      return request("/auth/login", {
        method: "POST",
        data: { username, password },
      });
    }
    throw error;
  });
};

// 用户注册
const register = (username, password, email, phone) => {
  return request("/auth/register", {
    method: "POST",
    data: { username, password: toSha256Payload(password), email, phone },
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

const getWeChatTemplateIds = () => {
  return request("/api/wechat/template-ids", { method: "GET" });
};

const bindWeChatOpenid = (code) => {
  return request("/api/wechat/bind-openid", {
    method: "POST",
    data: { code },
    headers: {
      "Content-Type": "application/json",
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

// 删除用药记录（软删除）
const deleteMedication = (medicationId, user_id = null) => {
  let url = `/api/medications/${medicationId}`;
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "DELETE",
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
const markMedicationTaken = (reminderId, scheduledTime, user_id = null) => {
  let url = `/api/medication-reminders/${reminderId}/taken`;
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "POST",
    data: { scheduledTime: scheduledTime || "" },
    headers: {
      "Content-Type": "application/json",
    },
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

// 获取提醒计划列表（用于“用药提醒”卡片展示）
const getMedicationReminderPlans = (active_only = true, user_id = null) => {
  let url = "/api/medication-reminder-plans";
  const params = [];
  if (active_only !== null && active_only !== undefined) {
    params.push(`active_only=${active_only ? "true" : "false"}`);
  }
  if (user_id) params.push(`user_id=${user_id}`);
  if (params.length > 0) url += `?${params.join("&")}`;
  return request(url, {
    method: "GET",
  });
};

// 启用/停用单条提醒
const setMedicationReminderActive = (reminderId, enabled, user_id = null) => {
  let url = `/api/medication-reminders/${reminderId}/active`;
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "PUT",
    data: { enabled: !!enabled },
    headers: {
      "Content-Type": "application/json",
    },
  });
};

// 标记“跳过/漏服”（写日志）
const markMedicationSkipped = (reminderId, scheduledTime, user_id = null) => {
  let url = `/api/medication-reminders/${reminderId}/skipped`;
  if (user_id) {
    url += `?user_id=${user_id}`;
  }
  return request(url, {
    method: "POST",
    data: { scheduledTime: scheduledTime || "" },
    headers: {
      "Content-Type": "application/json",
    },
  });
};

// 给已有用药新增提醒时间（不重复创建用药）
const addMedicationRemindersToMedication = (
  medicationId,
  reminderData,
  user_id = null,
) => {
  let url = `/api/medications/${medicationId}/reminders`;
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

// 获取用药统计
const getMedicationStats = (days = 7, date = "", user_id = null) => {
  let url = "/api/medication-stats";
  const params = [];
  if (days) params.push(`days=${days}`);
  if (date) params.push(`date=${date}`);
  if (user_id) params.push(`user_id=${user_id}`);
  if (params.length > 0) url += `?${params.join("&")}`;

  return request(url, {
    method: "GET",
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
  onComplete,
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
    header: token
      ? {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        }
      : {
          "Content-Type": "application/json",
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
        requestTask._pendingBuffer.length + uint8Array.length,
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

// 阶段37: v2 SSE 流式端点
const sendMessageV2Stream = (message, onEvent, onError, onComplete) => {
  const requestBody = {
    message: message.message || message.text,
    conversation_id: message.conversation_id,
    role: message.role,
    mode: message.mode || "single",
    metadata: message.metadata || {},
  };
  if (message.metadata && message.metadata.selected_agent) {
    requestBody.metadata.selected_agent = message.metadata.selected_agent;
    requestBody.selected_agent = message.metadata.selected_agent;
  }
  const userInfo = wx.getStorageSync("userInfo");
  const token = userInfo ? userInfo.token : "";
  const requestTask = wx.request({
    url: `${SERVER_URL}/v2/chat/stream`,
    method: "POST",
    data: requestBody,
    enableChunked: true,
    timeout: 300000,
    header: token
      ? { "Content-Type": "application/json", Authorization: `Bearer ${token}` }
      : { "Content-Type": "application/json" },
    fail: (err) => {
      if (onError) onError(err);
    },
  });

  let pendingText = "";
  requestTask.onChunkReceived((response) => {
    const arrayBuffer = response.data;
    let uint8Array = new Uint8Array(arrayBuffer);
    if (requestTask._pendingBuffer) {
      const nb = new Uint8Array(
        requestTask._pendingBuffer.length + uint8Array.length,
      );
      nb.set(requestTask._pendingBuffer, 0);
      nb.set(uint8Array, requestTask._pendingBuffer.length);
      uint8Array = nb;
      requestTask._pendingBuffer = null;
    }
    // UTF-8 safe trim
    let safeEnd = uint8Array.length;
    for (let k = 1; k <= 3 && safeEnd - k >= 0; k--) {
      const b = uint8Array[safeEnd - k];
      if ((b & 0xc0) === 0x80) continue;
      let seqLen = 0;
      if ((b & 0xe0) === 0xc0) seqLen = 2;
      else if ((b & 0xf0) === 0xe0) seqLen = 3;
      else if ((b & 0xf8) === 0xf0) seqLen = 4;
      if (seqLen > 0 && k < seqLen) {
        safeEnd -= k;
        requestTask._pendingBuffer = uint8Array.slice(safeEnd);
      }
      break;
    }
    const valid = uint8Array.slice(0, safeEnd);
    let text = "";
    try {
      text = new TextDecoder("utf-8").decode(valid);
    } catch (e) {
      text = String.fromCharCode.apply(null, valid);
    }
    const fullText = (requestTask._pendingText || "") + text;
    const lines = fullText.split("\n");
    if (fullText.length > 0 && !fullText.endsWith("\n") && lines.length > 0) {
      requestTask._pendingText = lines.pop();
    } else {
      requestTask._pendingText = "";
    }
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        pendingText = line.substring(7).trim();
      } else if (line.startsWith("data: ")) {
        const jsonStr = line.substring(6).trim();
        try {
          const data = JSON.parse(jsonStr);
          if (onEvent) onEvent({ event: pendingText || "message", data });
        } catch (e) {
          // ignore
        }
        pendingText = "";
      } else if (line === "") {
        pendingText = "";
      }
    }
  });
  return requestTask;
};

// 发送任务（流式）- 统一走 HostAPI，由 HostAPI 转发到目标智能体
const sendTaskStreamingViaHost = (
  targetAgentName,
  payload,
  onMessage,
  onError,
  onComplete,
) => {
  const requestBody = {
    jsonrpc: "2.0",
    method: "tasks/sendSubscribe",
    params: payload,
    id: `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
  };

  const userInfo = wx.getStorageSync("userInfo");
  const token = userInfo ? userInfo.token : "";

  const requestTask = wx.request({
    url: `${SERVER_URL}/a2a`,
    method: "POST",
    data: requestBody,
    enableChunked: true,
    timeout: 300000,
    header: token
      ? {
          "Content-Type": "application/json",
          "X-Target-Agent": encodeURIComponent(targetAgentName || ""),
          Authorization: `Bearer ${token}`,
        }
      : {
          "Content-Type": "application/json",
          "X-Target-Agent": encodeURIComponent(targetAgentName || ""),
        },
    success: (res) => {
      if (res.statusCode >= 200 && res.statusCode < 300) {
      } else {
        if (onError) onError(res);
      }
    },
    fail: (err) => {
      if (onError) onError(err);
    },
    complete: () => {},
  });

  requestTask.onChunkReceived((response) => {
    const arrayBuffer = response.data;
    let uint8Array = new Uint8Array(arrayBuffer);

    if (requestTask._pendingBuffer) {
      const newBuffer = new Uint8Array(
        requestTask._pendingBuffer.length + uint8Array.length,
      );
      newBuffer.set(requestTask._pendingBuffer, 0);
      newBuffer.set(uint8Array, requestTask._pendingBuffer.length);
      uint8Array = newBuffer;
      requestTask._pendingBuffer = null;
    }

    let safeEnd = uint8Array.length;
    for (let k = 1; k <= 3 && safeEnd - k >= 0; k++) {
      const b = uint8Array[safeEnd - k];
      if ((b & 0xc0) === 0x80) {
        continue;
      }
      let seqLen = 0;
      if ((b & 0xe0) === 0xc0) seqLen = 2;
      else if ((b & 0xf0) === 0xe0) seqLen = 3;
      else if ((b & 0xf8) === 0xf0) seqLen = 4;

      if (seqLen > 0) {
        if (k < seqLen) {
          safeEnd = safeEnd - k;
          requestTask._pendingBuffer = uint8Array.slice(safeEnd);
        }
      }
      break;
    }

    const validData = uint8Array.slice(0, safeEnd);
    let text = "";

    if (typeof TextDecoder !== "undefined") {
      try {
        text = new TextDecoder("utf-8").decode(validData);
      } catch (e) {
        console.error("TextDecoder failed:", e);
        text = utf8ArrayToString(validData);
      }
    } else {
      text = utf8ArrayToString(validData);
    }

    const fullText = (requestTask._pendingText || "") + text;
    const lines = fullText.split("\n");

    if (fullText.length > 0 && !fullText.endsWith("\n") && lines.length > 0) {
      requestTask._pendingText = lines.pop();
    } else {
      requestTask._pendingText = "";
    }

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const jsonStr = line.substring(6).trim();
        if (jsonStr === "[DONE]") {
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
          ((c & 0x0f) << 12) | ((char2 & 0x3f) << 6) | (char3 & 0x3f),
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

// === 阶段35: v2 LangGraph 入口 + ANP 协议 实现 ===

// v2 smart_chat（默认 single 模式）
// 实际端点：POST /smart_chat（顶层，无 /api/v2 前缀）
const sendMessageV2 = (message) => {
  const options = {
    method: "POST",
    data: {
      message: message.message,
      conversation_id: message.conversation_id,
      role: message.role,
      mode: "single",
      metadata: {
        ...(message.metadata || {}),
        selected_agent:
          message.metadata && message.metadata.selected_agent
            ? message.metadata.selected_agent
            : undefined,
      },
    },
    headers: {},
    timeout: 120000,
  };
  if (message.metadata && message.metadata.selected_agent) {
    options.headers["X-Target-Agent"] = encodeURIComponent(
      message.metadata.selected_agent,
    );
  }
  return request("/smart_chat", options);
};

// v2 multi 模式（4 agent 并行）
const sendMessageV2Multi = (message) => {
  const options = {
    method: "POST",
    data: {
      message: message.message,
      conversation_id: message.conversation_id,
      role: message.role,
      mode: "multi",
      metadata: message.metadata || {},
    },
    headers: {},
    timeout: 180000,
  };
  return request("/smart_chat", options);
};

// 列出所有 sub-agent 状态
const getV2AgentsStatus = () => {
  return request("/v2/agents/status", { method: "GET" });
};

// 单 agent 详情
const getV2AgentStatus = (agentName) => {
  return request(`/v2/agents/${encodeURIComponent(agentName)}/status`, {
    method: "GET",
  });
};

// 多模型列表
const getV2Models = () => {
  return request("/v2/models", { method: "GET" });
};

// 4 个 LLM provider
const getV2ModelProviders = () => {
  return request("/v2/models/providers", { method: "GET" });
};

// === ANP 协议接口 ===

// ANP 健康检查
const getAnpHealth = () => {
  return request("/anp/health", { method: "GET" });
};

// ANP Agent Description（hostapi 自己的）
const getAnpAgentDescription = () => {
  return request("/anp/agent/ad.json", { method: "GET" });
};

// ANP OpenRPC
const getAnpAgentInterface = () => {
  return request("/anp/agent/interface.json", { method: "GET" });
};

// 列出所有 PHA agent (带 DID:WBA)
const getAnpAgents = () => {
  return request("/anp/agents", { method: "GET" });
};

// ANP crawler 主动发现
const discoverAnpAgents = (params = {}) => {
  return request("/anp/agents/discover", {
    method: "POST",
    data: params,
    headers: {
      "Content-Type": "application/json",
    },
  });
};

// 阶段38-1: ANP 递归爬虫（增强版：BFS + DID 去重 + 缓存）
const crawlAnpAgents = (params = {}) => {
  return request("/anp/agents/crawl", {
    method: "GET",
    data: params, // max_depth, max_nodes, force_refresh
  });
};

// 阶段38-2: 多模型 SSE 流式（task_type + prefer_provider + fallback）
const sendMessageV2ModelsStream = (params, onEvent, onError) => {
  const requestBody = {
    messages: params.messages || [
      { role: "user", content: params.message || "" },
    ],
    task_type: params.task_type || "chat",
    prefer_provider: params.prefer_provider || "",
    max_tokens: params.max_tokens || 2048,
    temperature: params.temperature || 0.7,
  };
  const userInfo = wx.getStorageSync("userInfo");
  const token = userInfo ? userInfo.token : "";
  const requestTask = wx.request({
    url: `${SERVER_URL}/v2/models/stream`,
    method: "POST",
    data: requestBody,
    enableChunked: true,
    timeout: 300000,
    header: token
      ? { "Content-Type": "application/json", Authorization: `Bearer ${token}` }
      : { "Content-Type": "application/json" },
    fail: (err) => {
      if (onError) onError(err);
    },
  });
  let pendingText = "";
  requestTask.onChunkReceived((response) => {
    const arrayBuffer = response.data;
    let uint8Array = new Uint8Array(arrayBuffer);
    if (requestTask._pendingBuffer) {
      const nb = new Uint8Array(
        requestTask._pendingBuffer.length + uint8Array.length,
      );
      nb.set(requestTask._pendingBuffer, 0);
      nb.set(uint8Array, requestTask._pendingBuffer.length);
      uint8Array = nb;
      requestTask._pendingBuffer = null;
    }
    let safeEnd = uint8Array.length;
    for (let k = 1; k <= 3 && safeEnd - k >= 0; k--) {
      const b = uint8Array[safeEnd - k];
      if ((b & 0xc0) === 0x80) continue;
      let seqLen = 0;
      if ((b & 0xe0) === 0xc0) seqLen = 2;
      else if ((b & 0xf0) === 0xe0) seqLen = 3;
      else if ((b & 0xf8) === 0xf0) seqLen = 4;
      if (seqLen > 0 && k < seqLen) {
        safeEnd -= k;
        requestTask._pendingBuffer = uint8Array.slice(safeEnd);
      }
      break;
    }
    const valid = uint8Array.slice(0, safeEnd);
    let text = "";
    try {
      text = new TextDecoder("utf-8").decode(valid);
    } catch (e) {
      text = String.fromCharCode.apply(null, valid);
    }
    const fullText = (requestTask._pendingText || "") + text;
    const lines = fullText.split("\n");
    if (fullText.length > 0 && !fullText.endsWith("\n") && lines.length > 0) {
      requestTask._pendingText = lines.pop();
    } else {
      requestTask._pendingText = "";
    }
    for (const line of lines) {
      if (line.startsWith("event: ")) pendingText = line.substring(7).trim();
      else if (line.startsWith("data: ")) {
        const jsonStr = line.substring(6).trim();
        try {
          const data = JSON.parse(jsonStr);
          if (onEvent) onEvent({ event: pendingText || "message", data });
        } catch (e) {}
        pendingText = "";
      } else if (line === "") pendingText = "";
    }
  });
  return requestTask;
};

// 阶段38-1: ANP crawler 缓存状态
const getAnpCrawlerCache = () => {
  return request("/anp/agents/crawl/cache", { method: "GET" });
};

// 阶段38-1: 清 ANP crawler 缓存
const clearAnpCrawlerCache = () => {
  return request("/anp/agents/crawl/clear", { method: "GET" });
};

// 阶段38-1: DID 解析（DID:WBA → URL）
const didResolve = (did) => {
  return request(`/anp/did/resolve/${encodeURIComponent(did)}`, {
    method: "GET",
  });
};

// ANP JSON-RPC 2.0 调用（hostapi 的 /anp/agent/rpc）
const callAnpRpc = (method, params = {}, id = null) => {
  const requestBody = {
    jsonrpc: "2.0",
    method: method,
    params: params,
    id: id || `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
  };
  return request(`/anp/agent/rpc`, {
    method: "POST",
    data: requestBody,
    headers: {
      "Content-Type": "application/json",
    },
  });
};

// 自动探测后端是 v1 还是 v2（用 /health 探测 + /v2/agents/status 看 404/200）
const detectBackendVersion = () => {
  return new Promise((resolve) => {
    // 先 GET /health
    wx.request({
      url: `${SERVER_URL}/health`,
      method: "GET",
      success: (res) => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          // v1 和 v2 都有 /health，再探测 /v2/agents/status
          wx.request({
            url: `${SERVER_URL}/v2/agents/status`,
            method: "GET",
            success: (res2) => {
              const isV2 = res2.statusCode === 200;
              resolve({
                ok: true,
                version: isV2 ? "v2" : "v1",
                v2_available: isV2,
                health: res.data,
                v2_agents: isV2 ? res2.data : null,
              });
            },
            fail: () => {
              resolve({
                ok: true,
                version: "v1",
                v2_available: false,
                health: res.data,
              });
            },
          });
        } else {
          resolve({ ok: false, version: "unknown" });
        }
      },
      fail: (err) => {
        resolve({ ok: false, version: "unknown", error: err });
      },
    });
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
  transcribeAudioFile,
  login,
  register,
  getUserInfo,
  getWeChatTemplateIds,
  bindWeChatOpenid,
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
  deleteMedication,
  getMedicationReminders,
  markMedicationTaken,
  createMedicationReminder,
  getMedicationReminderPlans,
  setMedicationReminderActive,
  markMedicationSkipped,
  addMedicationRemindersToMedication,
  getMedicationStats,
  uploadMedicationImage,
  getAgentCard,
  sendTaskStreaming,
  sendTaskStreamingViaHost,
  resolveAgentUrl,
  resolveFileUrl,
  SERVER_URL,
  // === 阶段35: v2 LangGraph 入口 + ANP 协议 ===
  // 阶段35新增的 v2 接口
  sendMessageV2, // v2 smart_chat（默认 single 模式）
  sendMessageV2Multi, // v2 multi 模式（4 agent 并行）
  sendMessageV2Stream, // 阶段37: v2 SSE 流式（真流式输出 LLM 答案）
  getV2AgentsStatus, // 列出所有 sub-agent 状态
  getV2AgentStatus, // 单 agent 详情
  getV2Models, // 多模型列表
  getV2ModelProviders, // 4 个 LLM provider
  // 阶段35新增的 ANP 接口
  getAnpHealth,
  getAnpAgentDescription, // ANP Agent Description
  getAnpAgentInterface, // ANP OpenRPC
  getAnpAgents, // 列出所有 PHA agent (带 DID:WBA)
  discoverAnpAgents, // ANP crawler 主动发现
  // 阶段38-1: ANP 递归爬虫（增强版）
  crawlAnpAgents, // GET /anp/agents/crawl
  getAnpCrawlerCache, // 缓存状态
  clearAnpCrawlerCache, // 清缓存
  didResolve, // DID:WBA → URL
  // 阶段38-2: 多 LLM provider SSE 流式
  sendMessageV2ModelsStream,
  callAnpRpc, // ANP JSON-RPC 2.0 调用
  // 阶段35新增：版本探测
  detectBackendVersion, // 自动探测后端是 v1 还是 v2
};
