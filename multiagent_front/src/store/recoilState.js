import { atom, selector } from 'recoil';
import * as api from '../api/api'; // 引入 API 服务

// --- 原子状态定义 (Atoms) ---
// 对应 AppState 中的各个字段

export const sidenavOpenState = atom({
  key: 'sidenavOpenState', // 唯一 Key
  default: false, // 默认值
});

export const themeModeState = atom({
  key: 'themeModeState',
  default: 'system', // 'system', 'light', 'dark'
});

export const currentConversationIdState = atom({
  key: 'currentConversationIdState',
  default: '', // 当前对话 ID
});

export const conversationsState = atom({
  key: 'conversationsState',
  default: [], // 对话列表 StateConversation[]
});

export const messagesState = atom({
  key: 'messagesState',
  default: [], // 消息列表 StateMessage[]
});

export const taskListState = atom({
  key: 'taskListState',
  default: [], // 任务列表 SessionTask[]
});

export const backgroundTasksState = atom({
  key: 'backgroundTasksState',
  default: {}, // 后台任务状态 { [taskId]: statusText }
});

export const messageAliasesState = atom({
  key: 'messageAliasesState',
  default: {}, // 消息别名 { [aliasId]: messageId }
});

export const completedFormsState = atom({
  key: 'completedFormsState',
  default: {}, // 已完成表单数据 { [formMessageId]: formData | null }
});

export const formResponsesState = atom({
  key: 'formResponsesState',
  default: {}, // 表单响应映射 { [responseMessageId]: originalFormMessageId }
});

export const pollingIntervalState = atom({
  key: 'pollingIntervalState',
  default: 1, // 轮询间隔（秒）
});

export const apiKeyState = atom({
  key: 'apiKeyState',
  default: '',
});

export const usesVertexAiState = atom({
  key: 'usesVertexAiState',
  default: false,
});

export const apiKeyDialogOpenState = atom({
  key: 'apiKeyDialogOpenState',
  default: false,
});

// State for the agent list fetched from the backend
export const remoteAgentsListState = atom({
  key: 'remoteAgentsListState', // unique ID (with respect to other atoms/selectors)
  default: [], // default value (an empty array)
});

// State specifically for the "Add Agent" dialog logic
export const agentDialogState = atom({
    key: 'agentDialogState',
    default: {
    isOpen: false, // Corresponds to agent_dialog_open
    agentAddress: '', // Corresponds to agent_address
    agentName: '', // Corresponds to agent_name
    agentDescription: '', // Corresponds to agent_description
    inputModes: [], // Corresponds to input_modes
    outputModes: [], // Corresponds to output_modes
    streamSupported: false, // Corresponds to stream_supported
    pushNotificationsSupported: false, // Corresponds to push_notifications_supported
    error: '', // Corresponds to error
    agentFrameworkType: '', // Corresponds to agent_framework_type
    isLoadingInfo: false, // To show loading state when fetching agent info
    isSaving: false, // To show loading state when saving
    },
});