import { v4 as uuidv4 } from 'uuid'
import { fetchEventSource } from '@microsoft/fetch-event-source'

const SERVER_URL = import.meta.env.VITE_HOSTAGENT_API || 'http://127.0.0.1:13002';
const SMART_CHAT_URL = import.meta.env.VITE_SMART_CHAT_API || SERVER_URL;
const AGENT_CARD_PATH = '/.well-known/agent.json';


//检测 API 是否存活
export const checkApiStatus = async () => {
  try {
    console.log("Checking API status..., SERVER_URL:", SERVER_URL);
    const response = await fetch(`${SERVER_URL}/ping`);
    if (!response.ok) {
      return false; // API 返回非 2xx 状态码，认为未存活
    }
    const data = await response.json();
    return data === "Pong"; // 检查返回内容是否为 "Pong"
  } catch (error) {
    console.error("Ping API 请求失败:", error);
    return false; // 请求失败认为未存活
  }
};

/**
 * Fetches the list of remote agents from the backend.
 * Mimics ListRemoteAgents()
 * @returns {Promise<AgentCard[]>}
 */
export const listRemoteAgents = async () => {
  try {
    const response = await fetch(`${SERVER_URL}/agent/list`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({}), // 如果需要传内容就填，不需要就传空对象
      });
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();
    // Assuming the API returns { result: [...] } structure like the Python client expects
    return data.result || [];
  } catch (error) {
    console.error("Failed to list remote agents:", error);
    // Return empty array or throw error for component to handle
    return [];
    // Or: throw error;
  }
};

/**
 * Registers a new remote agent via the backend.
 * Mimics AddRemoteAgent()
 * @param {string} agentAddress - The address (e.g., "localhost:10000")
 * @returns {Promise<boolean>} - True on success, false on failure
 */
export const addRemoteAgent = async (agentAddress) => {
  try {
    // Assuming backend endpoint like '/register_agent' expecting POST with address
    const response = await fetch(`${SERVER_URL}/agent/register`, { // Adjust endpoint as needed
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      // The Python code sends RegisterAgentRequest(params=path)
      // Adapt the body structure based on your actual backend API requirement
      body: JSON.stringify({ params: agentAddress }),
      // Or maybe just: body: JSON.stringify(agentAddress),
      // Or maybe: body: JSON.stringify({ url: agentAddress }),
    });

    if (!response.ok) {
        const errorBody = await response.text();
        console.error("Failed to register agent:", response.status, errorBody);
        throw new Error(`Failed to register agent. Status: ${response.status}. ${errorBody}`);
    }
     // The Python code doesn't seem to expect a specific return value on success
    return true;
  } catch (error) {
    console.error("Failed to add remote agent:", error);
     throw error; // Re-throw for the component to handle and show message
  }
};

/**
 * Fetches the agent card details from the agent itself.
 * 兼容传入不带协议的 address（如 "localhost:10011"），自动补全为 http://
 * 返回结构在原有基础上补充 agentBaseUrl 与 agentEndpointUrl（JSON-RPC 入口）。
 * @param {string} agentAddress - 基础地址（例如 "localhost:10011" 或 "http://localhost:10011"）
 * @returns {Promise<AgentCard | null>}
 */
export const getAgentCard = async (agentAddress) => {
  const baseUrl = /^(http|https):\/\//i.test(agentAddress) ? agentAddress : `http://${agentAddress}`;
  const url = `${baseUrl.replace(/\/$/, '')}${AGENT_CARD_PATH}`;
  console.log(`Fetching agent card from: ${url}`);

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const agentCardData = await response.json();

    // 合并返回，保留旧字段，新增 agentBaseUrl 与 agentEndpointUrl（cardData.url）
    return {
      url: agentAddress,
      name: agentCardData.name || 'N/A',
      description: agentCardData.description || '',
      provider: agentCardData.provider || null,
      defaultInputModes: agentCardData.defaultInputModes || [],
      defaultOutputModes: agentCardData.defaultOutputModes || [],
      capabilities: agentCardData.capabilities || { streaming: false, pushNotifications: false },
      // 新增字段，便于直接调用 JSON-RPC
      agentBaseUrl: baseUrl,
      agentEndpointUrl: agentCardData.url,
    };
  } catch (error) {
    console.error(`Cannot connect to agent at ${agentAddress}:`, error);
    throw new Error(`Cannot connect to agent at ${agentAddress}`);
  }
};

// A2A 非流式任务发送（JSON-RPC: tasks/send）
export const sendTaskNonStreaming = async (agentEndpointUrl, payload) => {
  const requestBody = {
    jsonrpc: '2.0',
    method: 'tasks/send',
    params: payload,
    id: uuidv4(),
  };

  const response = await fetch(agentEndpointUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(requestBody),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`HTTP error ${response.status}: ${errorText}`);
  }
  return response.json();
};

// A2A 流式任务发送（JSON-RPC: tasks/sendSubscribe via SSE）
export const sendTaskStreaming = (agentEndpointUrl, payload, onMessage, onError, onClose) => {
  const requestBody = {
    jsonrpc: '2.0',
    method: 'tasks/sendSubscribe',
    params: payload,
    id: uuidv4(),
  };

  const ctrl = new AbortController();

  fetchEventSource(agentEndpointUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(requestBody),
    signal: ctrl.signal,
    openWhenHidden: true,
    async onopen(response) {
      if (response.ok && response.headers.get('content-type')?.includes('text/event-stream')) {
        console.log('SSE Connection opened');
      } else {
        const errorText = await response.text();
        const err = new Error(`Failed to connect to SSE: ${response.status} ${errorText}`);
        console.error(err);
        onError?.(err);
        ctrl.abort();
      }
    },
    onmessage(event) {
      if (!event.data?.trim()) return; // 忽略心跳
      try {
        const parsed = JSON.parse(event.data);
        onMessage?.(parsed);
      } catch (e) {
        console.error('Failed to parse SSE message:', e, 'raw:', event.data);
        onError?.(e);
      }
    },
    onclose() {
      console.log('SSE Connection closed');
      onClose?.();
    },
    onerror(err) {
      console.error('SSE Error:', err);
      onError?.(err);
      throw err; // 终止重试
    },
  });

  return () => ctrl.abort();
};


// 请求辅助函数
async function request(endpoint, options = {}) {
    const url = `${SERVER_URL}${endpoint}`;
    const config = {
        method: options.method || 'GET',
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    };
    if (options.body) {
        config.body = JSON.stringify(options.body);
    }

    try {
        const response = await fetch(url, config);
        if (!response.ok) {
            const errorData = await response.text(); // 或者 response.json() 如果错误详情是 JSON
            throw new Error(`HTTP 错误! 状态: ${response.status}, 消息: ${errorData}`);
        }
        // 处理可能没有响应体的响应 (例如 204 No Content)
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
            const data = await response.json();
             // 假设后端像 python 客户端一样将数据包装在 { result: ... } 中
            return data.result !== undefined ? data.result : data;
        } else {
            // 按需处理非 JSON 响应，或返回 null/undefined
            return null; // 或者 await response.text();
        }
    } catch (error) {
        console.error(`API 请求失败 ${endpoint}:`, error);
        throw error; // 重新抛出错误，让调用代码处理
    }
}

// 获取对话列表
export const listConversations = async () => {
    // 假设基于 Python 代码是 POST 请求且请求体为空
    return request('/conversation/list', { method: 'POST', body: {} });
};

// 发送消息
export const sendMessage = async (message) => {
    // message 参数应符合 SendMessageRequest (common.types.Message) 的结构
    return request('/message/send', { method: 'POST', body: { params: message } });
};

// 创建新对话
export const createConversation = async () => {
    return request('/conversation/create', { method: 'POST', body: {} });
};

// 获取指定对话的消息列表
export const listMessages = async (conversationId) => {
    return request('/message/list', { method: 'POST', body: { params: conversationId } });
};

// 获取任务列表
export const getTasks = async () => {
    return request('/task/list', { method: 'POST', body: {} });
};

// 获取正在处理的消息
export const getProcessingMessages = async () => {
    return request('/message/pending', { method: 'POST', body: {} });
};

// 更新 API Key
export const updateApiKey = async (apiKey) => {
    try {
        await request('/api_key/update', { method: 'POST', body: { api_key: apiKey } });
        return true;
    } catch (error) {
        console.error("API 调用更新 API key 失败:", error);
        return false;
    }
};

export const getEvents = async () => {
    return request('/events/get', { method: 'POST', body: {} });
};

//根据对话id获取它的事件
export const queryEvents = async (conversationId) => {
  return request('/events/query', { method: 'POST', body: {params: { conversation_id: conversationId }} });
};

// 智能路由相关 API
export const smartChat = async (message) => {
  try {
    const response = await fetch(`${SMART_CHAT_URL}/smart_chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ message })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    return await response.json();
  } catch (error) {
    console.error('智能路由 API 调用失败:', error);
    throw error;
  }
};

// 导出智能路由 URL 供其他组件使用
export { SMART_CHAT_URL };