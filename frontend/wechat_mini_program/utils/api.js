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
      url: `${SERVER_URL}/upload`, // The backend upload address needs to be implemented
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
