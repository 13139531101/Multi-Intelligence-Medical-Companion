// pages/agent_chat/agent_chat.js
const {
  sendMessage,
  sendMessageV2, // 阶段35: v2 smart_chat
  sendMessageV2Multi, // 阶段35: v2 multi
  sendMessageV2Stream, // 阶段37: v2 SSE 流式
  getV2AgentsStatus, // 阶段35: sub-agent 状态
  getV2AgentStatus,
  getAnpAgents, // 阶段35: ANP 列出
  getAnpHealth,
  detectBackendVersion, // 阶段35: 版本探测
  uploadFile,
  createConversation,
  listMessages,
  getProcessingMessages,
  queryEvents,
  sendTaskStreaming,
  sendTaskStreamingViaHost,
  listRemoteAgents,
  getAgentCard,
  createConsultation,
  saveConsultationMessage,
  getConsultationMessages,
  getConsultationHistory,
  getWeChatTemplateIds,
  transcribeAudioFile,
  resolveAgentUrl,
  SERVER_URL,
} = require("../../utils/api");

Page({
  /**
   * Page initial data
   */
  data: {
    messages: [],
    inputText: "",
    conversationId: null,
    isPolling: false,
    scrollIntoView: "",
    shouldAutoScroll: true,
    showJumpToBottom: false,
    unreadCount: 0,
    scrollViewHeight: 0,
    isSending: false,
    mode: "default", // default, summary, consultation, medication, health_records
    agentType: "default",
    agentUrl: "",
    selectedAgentName: "",
    sessionId: "",
    suggestions: [],
    isHistorySynced: false,
    hasRequestedSubscribe: false,
    pendingAttachments: [],
    isRecording: false,
    // === 阶段35: v2 LangGraph 选项 ===
    useV2: true, // 默认开 v2（PHA_USE_V2=true 是 backend 默认）
    v2ExecMode: "single", // "single" | "multi"
    showV2Bar: true, // 显示 v2 模式切换栏
    v2ModeInfo: "", // 副信息（如后端版本 / agent 路由）
    v2Agents: [], // 缓存的 4 个 sub-agent 状态
    selectedAgent: null, // 当前选中的 agent（路由结果）
    agentRouting: null, // 路由详情 {layer, target}
    anpAgents: [], // 缓存 ANP agents（带 DID）
  },

  // 阶段35: 切换 v1/v2
  setV2Mode(e) {
    const mode = (e.currentTarget.dataset.mode || "").toLowerCase();
    const useV2 = mode === "v2";
    this.setData({ useV2 });
    this._updateV2ModeInfo();
    wx.showToast({ title: useV2 ? "v2 LangGraph" : "v1 A2A", icon: "none" });
  },

  // 阶段35: 切换 single/multi
  setV2ExecMode(e) {
    const mode = (e.currentTarget.dataset.mode || "single").toLowerCase();
    this.setData({ v2ExecMode: mode });
    this._updateV2ModeInfo();
    wx.showToast({
      title: mode === "multi" ? "4 agent 并行" : "单 agent",
      icon: "none",
    });
  },

  // 阶段35: 刷新副信息
  async _updateV2ModeInfo() {
    const { useV2, v2ExecMode } = this.data;
    let info = "";
    if (useV2) {
      info = v2ExecMode === "multi" ? "v2 · 4 agent 并行" : "v2 · 单 agent";
    } else {
      info = "v1 · A2A 私有";
    }
    this.setData({ v2ModeInfo: info });
  },

  // 阶段35: 启动时探测后端 + 拉 agent 列表
  async onLoadStage35Init() {
    try {
      // 1) 探测后端
      const probe = await detectBackendVersion();
      if (probe.ok) {
        if (!probe.v2_available) {
          console.warn("[v2] 探测显示后端是 v1（无 /v2/agents/status）");
          // 阶段36: 不要自动切回 v1！保留 v2 路径（_sendWithV2 自己 fallback）
          // 因为探测可能在某些情况下失败但实际可用
        } else {
          console.log("[v2] 探测显示后端是 v2，可用");
        }
      } else {
        console.warn("[v2] 探测失败（可能后端未启动）", probe);
      }
      this._updateV2ModeInfo();

      // 2) 拉 v2 agents 状态（不依赖 useV2，因为可能探测假阴性）
      try {
        const status = await getV2AgentsStatus();
        const registry = (status && status.registry) || [];
        this.setData({ v2Agents: registry });
      } catch (e) {
        console.warn("[v2] getV2AgentsStatus failed", e);
      }
      // 3) 拉 ANP agents
      try {
        const anp = await getAnpAgents();
        this.setData({ anpAgents: (anp && anp.agents) || [] });
      } catch (e) {
        console.warn("[v2] getAnpAgents failed", e);
      }
    } catch (e) {
      console.error("[v2] init failed", e);
    }
  },

  // 在页面实例上维护已处理的事件ID集合
  processedEventIds: null,
  dbSavedMessageIds: null,
  // 维护流式请求任务
  requestTask: null,
  // 流式回复内容缓存
  streamingContent: "",
  streamingThinkingRaw: "",
  currentStreamingId: null,
  currentPendingAssistantId: null,
  scrollTimer: null,
  lastScrollDetail: null,
  streamingUpdateTimer: null,
  userScrollLockUntil: 0,
  debugLoggedKeys: null,
  recorderManager: null,
  recorderStopPromiseResolve: null,

  /**
   * Lifecycle function--Called when page load
   */
  async onLoad(options) {
    this.processedEventIds = new Set();
    this.debugLoggedKeys = new Set();
    this.dbSavedMessageIds = new Set();
    const hasQuery =
      options.query !== undefined &&
      options.query !== null &&
      String(options.query).trim();
    const hasExplicitAgentType = !!(options.agentType || options.mode);
    let agentType = options.agentType || options.mode || "default";
    let conversationId = options.id || null;

    if (!hasExplicitAgentType && !conversationId && !hasQuery) {
      try {
        const lastContext = wx.getStorageSync("agent_chat:lastContext");
        if (
          lastContext &&
          typeof lastContext === "object" &&
          lastContext.agentType &&
          lastContext.conversationId
        ) {
          agentType = String(lastContext.agentType || agentType);
          conversationId = String(lastContext.conversationId || conversationId);
        }
      } catch (e) {
        console.warn("Read agent_chat:lastContext failed:", e);
      }
    }
    if (!conversationId && !hasQuery) {
      try {
        const cached = wx.getStorageSync(
          `agent_chat:lastConversationId:${agentType}`,
        );
        if (cached) conversationId = String(cached);
      } catch (e) {
        console.warn("Read lastConversationId cache failed:", e);
      }
    }
    const sessionId = conversationId || this.generateUUID();
    const shouldPersistType = this.shouldPersistConversationToDb(agentType);

    this.setData({
      agentType,
      sessionId,
      conversationId: conversationId,
      isHistorySynced: !!conversationId && shouldPersistType,
    });

    if (conversationId) {
      try {
        wx.setStorageSync(
          `agent_chat:lastConversationId:${agentType}`,
          conversationId,
        );
        wx.setStorageSync("agent_chat:lastContext", {
          agentType,
          conversationId,
        });
      } catch (e) {
        console.warn("Persist agent_chat last context failed:", e);
      }
    }

    await this.initializeAgent(agentType);

    if (conversationId) {
      await this.loadHistory(conversationId);
    }

    if (options.query) {
      const query = decodeURIComponent(options.query);
      this.setData({ inputText: query }, () => {
        this.sendMessage();
      });
    }
  },

  shouldPersistConversationToDb(agentType) {
    return [
      "default",
      "host",
      "consultation",
      "medication",
      "summary",
      "health_records",
    ].includes(String(agentType || ""));
  },

  getDbSaveKey(messageId, role, content) {
    const id = messageId ? String(messageId) : "";
    if (id) return id;
    return `${String(role || "")}:${this.hashText32(String(content || ""))}`;
  },

  async saveMessageToDbOnce(consultationId, role, content, messageId, files) {
    const cid = consultationId ? String(consultationId) : "";
    if (!cid) return;
    const key = this.getDbSaveKey(messageId, role, content);
    if (!this.dbSavedMessageIds) this.dbSavedMessageIds = new Set();
    if (this.dbSavedMessageIds.has(key)) return;
    this.dbSavedMessageIds.add(key);
    try {
      await saveConsultationMessage({
        consultation_id: cid,
        role: role,
        content: content,
        files: Array.isArray(files) ? files : [],
      });
    } catch (e) {
      console.warn("Save consultation message failed:", e);
    }
  },

  onReady() {
    this.refreshScrollViewHeight();
  },

  formatTextToRichHtml(text) {
    const rawInput = text === undefined || text === null ? "" : String(text);
    const raw = this.normalizeStreamingText(rawInput);
    let html = raw.replace(/\r\n/g, "\n");
    html = html
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    html = html.replace(/^#{1,6}\s*(.+)$/gm, "<b>$1</b>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    html = html.replace(
      /`([^`]+)`/g,
      '<span style="font-family: monospace;">$1</span>',
    );
    html = html.replace(/^\s*-\s+/gm, "&bull; ");
    html = html.replace(/\n/g, "<br/>");
    return `<div style="word-break: break-word;">${html}</div>`;
  },

  normalizeStreamingText(text) {
    const raw = text === undefined || text === null ? "" : String(text);
    const htmlLike = /<br\s*\/?>|<\/p>|<p(\s|>)/i.test(raw);
    const normalized = raw
      .replace(/<br\s*\/?>/gi, "\n")
      .replace(/<\/p>\s*<p(\s|>)/gi, "\n")
      .replace(/<\/?p(\s|>)[^>]*>/gi, "")
      .replace(/\r\n/g, "\n")
      .replace(/\u2028|\u2029/g, "\n");
    const nlCount = (normalized.match(/\n/g) || []).length;
    if (nlCount < 6) return normalized;
    if (normalized.length > 0 && nlCount / normalized.length < 0.03) {
      return normalized;
    }
    const density = nlCount / Math.max(normalized.length, 1);
    const compacted = normalized.replace(
      /([\u4e00-\u9fffA-Za-z0-9])\n+\s*(?=[\u4e00-\u9fffA-Za-z0-9，。！？；：、,.!?;:])/g,
      "$1",
    );
    if (nlCount >= 30 && density > 0.08) {
      return compacted
        .replace(/([^\s])\n+\s*(?=[^\s])/g, "$1")
        .replace(/\n{3,}/g, "\n\n");
    }
    if (htmlLike) {
      return compacted.replace(/\n{3,}/g, "\n\n");
    }
    return compacted;
  },

  hashText32(text) {
    const s = text === undefined || text === null ? "" : String(text);
    let hash = 2166136261;
    for (let i = 0; i < s.length; i++) {
      hash ^= s.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  },

  getTextDebugStats(text) {
    const s = text === undefined || text === null ? "" : String(text);
    const nlCount = (s.match(/\n/g) || []).length;
    const brCount = (s.match(/<br\s*\/?>/gi) || []).length;
    const pCount = (s.match(/<\/?p(\s|>)/gi) || []).length;
    const htmlLike = brCount > 0 || pCount > 0;
    const density = nlCount / Math.max(s.length, 1);
    return {
      len: s.length,
      nlCount,
      density: Number(density.toFixed(4)),
      brCount,
      pCount,
      htmlLike,
      hash32: this.hashText32(s),
    };
  },

  shouldLogVertical(stats) {
    if (!stats) return false;
    if (stats.len < 10) return false;
    if (stats.nlCount >= 10 && stats.density >= 0.08) return true;
    if (stats.brCount >= 10 && stats.brCount / Math.max(stats.len, 1) > 0.02)
      return true;
    return false;
  },

  logVerticalDebug(key, rawText, normalizedText, extra = {}) {
    if (this.data.agentType !== "consultation") return;
    if (!key) return;
    if (!this.debugLoggedKeys) this.debugLoggedKeys = new Set();
    if (this.debugLoggedKeys.has(key)) return;
    const rawStats = this.getTextDebugStats(rawText);
    const normStats = this.getTextDebugStats(normalizedText);
    if (!this.shouldLogVertical(rawStats) && !this.shouldLogVertical(normStats))
      return;
    this.debugLoggedKeys.add(key);
    const verticalPayload = Object.assign(
      {
        key,
        agentType: this.data.agentType,
        raw: rawStats,
        normalized: normStats,
      },
      extra || {},
    );
    console.warn("[vertical-text-debug]", verticalPayload);
  },

  getPartsDebugStats(parts) {
    const list = Array.isArray(parts) ? parts : [];
    let textCount = 0;
    let totalLen = 0;
    let minLen = Infinity;
    let maxLen = 0;
    list.forEach((p) => {
      if (!p || p.type !== "text") return;
      const t = p.text === undefined || p.text === null ? "" : String(p.text);
      const len = t.length;
      textCount += 1;
      totalLen += len;
      if (len < minLen) minLen = len;
      if (len > maxLen) maxLen = len;
    });
    const avgLen = textCount ? totalLen / textCount : 0;
    return {
      partCount: list.length,
      textCount,
      totalLen,
      avgLen: Number(avgLen.toFixed(2)),
      minLen: Number.isFinite(minLen) ? minLen : 0,
      maxLen,
    };
  },

  shouldLogSplitParts(stats) {
    if (!stats) return false;
    if (stats.textCount >= 40 && stats.avgLen <= 3) return true;
    if (stats.textCount >= 80) return true;
    return false;
  },

  logPartsDebug(key, stats, extra = {}) {
    if (this.data.agentType !== "consultation") return;
    if (!key) return;
    const k = `parts:${key}`;
    if (!this.debugLoggedKeys) this.debugLoggedKeys = new Set();
    if (this.debugLoggedKeys.has(k)) return;
    if (!this.shouldLogSplitParts(stats)) return;
    this.debugLoggedKeys.add(k);
    const partsPayload = Object.assign({ key, stats }, extra || {});
    console.warn("[vertical-parts-debug]", partsPayload);
  },

  mergeStreamingText(incomingText, reset = false) {
    const incoming =
      incomingText === undefined || incomingText === null
        ? ""
        : String(incomingText);
    if (!incoming) return;
    if (reset || !this.streamingContent) {
      this.streamingContent = incoming;
      return;
    }
    if (incoming.startsWith(this.streamingContent)) {
      this.streamingContent = incoming;
      return;
    }
    if (this.streamingContent.endsWith(incoming)) return;
    this.streamingContent += incoming;
  },

  scheduleStreamingContentUpdate() {
    if (!this.currentStreamingId) return;
    if (this.streamingUpdateTimer) return;
    const now = Date.now();
    let delay = this.data.shouldAutoScroll ? 50 : 200;
    if (
      !this.data.shouldAutoScroll &&
      this.userScrollLockUntil &&
      now < this.userScrollLockUntil
    ) {
      delay = Math.max(delay, 350);
    }
    this.streamingUpdateTimer = setTimeout(() => {
      this.streamingUpdateTimer = null;
      this.applyStreamingContentUpdate();
    }, delay);
  },

  applyStreamingContentUpdate() {
    if (!this.currentStreamingId) return;
    const displayText = this.normalizeStreamingText(
      this.streamingContent || "",
    );
    this.logVerticalDebug(
      `streaming:${this.currentStreamingId}`,
      this.streamingContent || "",
      displayText,
      { phase: "applyStreamingContentUpdate" },
    );
    const updatedMessages = this.data.messages.map((m) => {
      if (m.id === this.currentStreamingId) {
        const isLong = this.isLongAssistantText(displayText);
        return Object.assign({}, m, {
          contentParts: displayText
            ? [
                {
                  type: "text",
                  content: this.formatTextToRichHtml(displayText),
                },
              ]
            : m.contentParts,
          rawText: displayText,
          isLong,
          collapsed: false,
        });
      }
      return m;
    });
    this.setData({ messages: updatedMessages }, () =>
      this.scheduleScrollToBottom(false, 0),
    );
  },

  async ensureTaskSubscribeAuth() {
    const cached = wx.getStorageSync("taskSubscribeAccepted");
    if (cached) return true;

    let templateId = "";
    try {
      const ids = await getWeChatTemplateIds();
      templateId = (ids && (ids.task_complete || ids.taskComplete)) || "";
    } catch (e) {
      console.warn("Get WeChat template ids failed:", e);
      templateId = "";
    }
    if (!templateId) return false;

    return await new Promise((resolve) => {
      wx.requestSubscribeMessage({
        tmplIds: [templateId],
        success: (res) => {
          const state = res ? res[templateId] : "";
          if (state === "accept") {
            try {
              wx.setStorageSync("taskSubscribeAccepted", true);
            } catch (e) {
              console.warn("Persist taskSubscribeAccepted failed:", e);
            }
            resolve(true);
            return;
          }
          resolve(false);
        },
        fail: () => resolve(false),
      });
    });
  },

  async tryRequestTaskSubscribe() {
    if (this.data.hasRequestedSubscribe) return;
    this.setData({ hasRequestedSubscribe: true });
    try {
      await this.ensureTaskSubscribeAuth();
    } catch (e) {
      console.warn("Request task subscribe failed:", e);
    }
  },

  isAssistantRole(role) {
    if (!role) return false;
    const r = String(role).toLowerCase();
    return r === "assistant" || r === "ai" || r === "model" || r === "agent";
  },

  isLongAssistantText(text) {
    const raw = text === undefined || text === null ? "" : String(text);
    const nlCount = (raw.match(/\n/g) || []).length;
    const lineCount = nlCount + 1;
    if (raw.length >= 700) return true;
    if (lineCount >= 18) return true;
    if (nlCount >= 30 && nlCount / Math.max(raw.length, 1) > 0.12) return true;
    return false;
  },

  refreshScrollViewHeight() {
    return new Promise((resolve) => {
      wx.createSelectorQuery()
        .in(this)
        .select("#messageList")
        .boundingClientRect((rect) => {
          const height = rect && rect.height ? rect.height : 0;
          if (height && height !== this.data.scrollViewHeight) {
            this.setData({ scrollViewHeight: height });
          }
          resolve(height);
        })
        .exec();
    });
  },

  getLastMessageViewId() {
    const list = this.data.messages || [];
    if (!Array.isArray(list) || list.length === 0) return "";
    return `msg-${list[list.length - 1].id}`;
  },

  scheduleScrollToBottom(force = false, newItems = 0) {
    const viewId = this.getLastMessageViewId();
    if (!viewId) return;

    if (!force && !this.data.shouldAutoScroll) {
      const nextUnread = newItems
        ? (this.data.unreadCount || 0) + newItems
        : this.data.unreadCount || 0;
      const patch = {};
      if (!this.data.showJumpToBottom) patch.showJumpToBottom = true;
      if (newItems) patch.unreadCount = nextUnread;
      if (Object.keys(patch).length) this.setData(patch);
      return;
    }

    if (this.scrollTimer) return;
    this.scrollTimer = setTimeout(() => {
      this.scrollTimer = null;
      const latestId = this.getLastMessageViewId();
      if (!latestId) return;
      if (force || this.data.shouldAutoScroll) {
        this.setData({
          scrollIntoView: latestId,
          showJumpToBottom: false,
          unreadCount: 0,
        });
      }
    }, 80);
  },

  jumpToBottom() {
    this.setData(
      {
        shouldAutoScroll: true,
        showJumpToBottom: false,
        unreadCount: 0,
      },
      () => this.scheduleScrollToBottom(true),
    );
  },

  handleScroll(e) {
    const detail = e && e.detail ? e.detail : null;
    if (!detail) return;
    this.lastScrollDetail = detail;

    if (!this.data.scrollViewHeight) {
      this.refreshScrollViewHeight();
      return;
    }

    const scrollTop = Number(detail.scrollTop || 0);
    const scrollHeight = Number(detail.scrollHeight || 0);
    const viewHeight = Number(this.data.scrollViewHeight || 0);
    if (!scrollHeight || !viewHeight) return;

    const distanceToBottom = scrollHeight - (scrollTop + viewHeight);
    const atBottom = distanceToBottom <= 80;

    if (atBottom) {
      this.userScrollLockUntil = 0;
      if (!this.data.shouldAutoScroll || this.data.showJumpToBottom) {
        this.setData({
          shouldAutoScroll: true,
          showJumpToBottom: false,
          unreadCount: 0,
        });
      }
      return;
    }

    this.userScrollLockUntil = Date.now() + 600;
    if (this.data.shouldAutoScroll) {
      this.setData({ shouldAutoScroll: false });
    }
  },

  handleUserTouchStart() {
    this.userScrollLockUntil = Date.now() + 800;
    if (this.data.shouldAutoScroll) {
      this.setData({ shouldAutoScroll: false, showJumpToBottom: true });
      return;
    }
    if (!this.data.showJumpToBottom) {
      this.setData({ showJumpToBottom: true });
    }
  },

  handleScrollToLower() {
    if (!this.data.shouldAutoScroll || this.data.showJumpToBottom) {
      this.setData({
        shouldAutoScroll: true,
        showJumpToBottom: false,
        unreadCount: 0,
      });
    }
  },

  toggleExpand(e) {
    const index = e.currentTarget.dataset.index;
    const messages = this.data.messages;
    const msg = messages[index];
    if (msg && msg.role === "assistant" && msg.isLong && !msg.isStreaming) {
      msg.collapsed = !msg.collapsed;
      this.setData({ messages }, () => this.scheduleScrollToBottom());
    }
  },

  extractTextFromMessage(message) {
    if (!message) return "";
    if (message.content !== undefined && message.content !== null) {
      const raw = String(message.content);
      return this.isAssistantRole(message.role)
        ? this.normalizeStreamingText(raw)
        : raw;
    }
    if (Array.isArray(message.parts) && message.parts.length > 0) {
      let s = "";
      message.parts.forEach((p) => {
        if (p && p.type === "text" && p.text) s += String(p.text);
      });
      return this.isAssistantRole(message.role)
        ? this.normalizeStreamingText(s)
        : s;
    }
    return "";
  },

  // 处理消息内容，返回结构化部分
  processMessageContent(message) {
    let parts = [];
    const toRichTextNodes = (text) => {
      const raw = text === undefined || text === null ? "" : String(text);
      const display = this.isAssistantRole(message?.role)
        ? this.normalizeStreamingText(raw)
        : raw;
      this.logVerticalDebug(
        `processMessageContent:${message?.id || this.hashText32(raw)}`,
        raw,
        display,
        { phase: "processMessageContent", role: message?.role || "" },
      );
      return this.formatTextToRichHtml(display);
    };

    const parseFilesToParts = (files) => {
      if (!Array.isArray(files) || files.length === 0) return [];
      const mapped = [];
      files.forEach((f) => {
        if (!f) return;
        const mimeType = f.mimeType || f.mime_type || f.type || "";
        const name = f.name || f.file_name || f.filename || "文件";
        const rawUrl = f.url || f.uri || f.path || f.file_url;
        if (!rawUrl) return;

        const url = rawUrl.startsWith("http")
          ? rawUrl
          : `${SERVER_URL}${rawUrl}`;
        const isImage = mimeType && String(mimeType).startsWith("image/");
        mapped.push({
          type: isImage ? "image" : "file",
          url,
          name,
          mimeType,
        });
      });
      return mapped;
    };

    if (message.parts && message.parts.length > 0) {
      const stats = this.getPartsDebugStats(message.parts);
      const statsKey =
        message.id ||
        (message.metadata && message.metadata.message_id) ||
        `anon_${this.hashText32(`${stats.textCount}_${stats.totalLen}`)}`;
      this.logPartsDebug(statsKey, stats, {
        phase: "processMessageContent",
        role: message?.role || "",
      });

      let textBuffer = "";
      const flushText = () => {
        if (!textBuffer) return;
        parts.push({ type: "text", content: toRichTextNodes(textBuffer) });
        textBuffer = "";
      };

      message.parts.forEach((p) => {
        if (!p) return;
        if (p.type === "text") {
          const t =
            p.text === undefined || p.text === null ? "" : String(p.text);
          textBuffer += t;
          return;
        }

        flushText();

        if (p.type === "file" && p.file && p.file.uri) {
          const rawUri = String(p.file.uri || "");
          const fileUrl = rawUri.startsWith("http")
            ? rawUri
            : `${SERVER_URL}${rawUri}`;
          const isImage =
            p.file.mimeType && p.file.mimeType.startsWith("image/");
          parts.push({
            type: isImage ? "image" : "file",
            url: fileUrl,
            name: p.file.name || "文件",
            mimeType: p.file.mimeType,
          });
        }
      });

      flushText();
    } else if (message.content) {
      parts.push({ type: "text", content: toRichTextNodes(message.content) });
    }

    if ((!parts || parts.length === 0) && message.files) {
      parts = parseFilesToParts(message.files);
    } else if (message.files) {
      parts = (parts || []).concat(parseFilesToParts(message.files));
    }
    return parts;
  },

  parseTimestampSeconds(value) {
    if (value === undefined || value === null || value === "") {
      return Date.now() / 1000;
    }

    if (typeof value === "number") {
      if (value > 1e12) return value / 1000;
      if (value > 1e9) return value;
      return value;
    }

    const raw = String(value).trim();
    if (!raw) return Date.now() / 1000;

    if (/^\d+$/.test(raw)) {
      const num = Number(raw);
      if (num > 1e12) return num / 1000;
      if (num > 1e9) return num;
      return num;
    }

    let s = raw;
    if (s.includes(" ") && !s.includes("T")) {
      s = s.replace(" ", "T");
    }
    s = s.replace(/(\.\d{3})\d+/, "$1");
    if (/^\d{4}-\d{2}-\d{2}T/.test(s) && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(s)) {
      s = `${s}Z`;
    }

    const ms = Date.parse(s);
    if (!Number.isNaN(ms)) return ms / 1000;
    return Date.now() / 1000;
  },

  normalizeHistoryMessages(rawMessages) {
    const toRichTextNodes = (text) => this.formatTextToRichHtml(text);

    const normalizeRole = (role) => {
      if (!role) return "assistant";
      const r = String(role).toLowerCase();
      if (r === "ai" || r === "assistant" || r === "model" || r === "agent")
        return "assistant";
      if (r === "user" || r === "human") return "user";
      return role;
    };

    const result = [];
    (Array.isArray(rawMessages) ? rawMessages : []).forEach((item, index) => {
      if (!item) return;

      const createdAt = item.created_at || item.createdAt || item.timestamp;
      const baseTime = this.parseTimestampSeconds(createdAt);

      if (item.question !== undefined || item.answer !== undefined) {
        if (item.question) {
          result.push({
            id: item.id
              ? `${item.id}_q`
              : item.consultation_id
                ? `${item.consultation_id}_q_${index}`
                : `history_${index}_q`,
            role: "user",
            contentParts: [
              { type: "text", content: toRichTextNodes(item.question) },
            ],
            rawText: String(item.question || ""),
            isLong: false,
            collapsed: false,
            timestamp: baseTime,
            timeString: this.formatTime(baseTime),
          });
        }
        if (item.answer) {
          const rawAnswerText = String(item.answer || "");
          const answerText = this.normalizeStreamingText(rawAnswerText);
          this.logVerticalDebug(
            `historyAnswer:${item.id || item.consultation_id || index}`,
            rawAnswerText,
            answerText,
            { phase: "normalizeHistoryMessages", kind: "answerRecord" },
          );
          const isLong = this.isLongAssistantText(answerText);
          result.push({
            id: item.id
              ? `${item.id}_a`
              : item.consultation_id
                ? `${item.consultation_id}_a_${index}`
                : `history_${index}_a`,
            role: "assistant",
            contentParts: [
              { type: "text", content: toRichTextNodes(answerText) },
            ],
            rawText: answerText,
            thinkingRaw: "",
            thinkingHtml: "",
            showThinking: false,
            isLong,
            collapsed: isLong,
            timestamp: baseTime + 0.1,
            timeString: this.formatTime(baseTime + 0.1),
          });
        }
        return;
      }

      const msgId =
        item.id ||
        (item.metadata && item.metadata.message_id) ||
        (item.consultation_id ? `${item.consultation_id}_${index}` : null) ||
        `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

      const role = normalizeRole(item.role);
      const rawText = this.extractTextFromMessage(item);
      const isLong = role === "assistant" && this.isLongAssistantText(rawText);
      const contentParts = this.processMessageContent(item);
      if (!contentParts || contentParts.length === 0) return;

      result.push({
        id: msgId,
        role,
        contentParts,
        rawText,
        thinkingRaw: "",
        thinkingHtml: "",
        showThinking: false,
        isLong,
        collapsed: isLong,
        timestamp: baseTime,
        timeString: this.formatTime(baseTime),
      });
    });
    return result;
  },

  isThinkingLikeMessage(msg) {
    if (!msg || msg.role === "user") return false;
    const text =
      msg.rawText === undefined || msg.rawText === null
        ? ""
        : String(msg.rawText);
    if (!text) return false;
    if (text.length >= 1200) return false;
    if (/^#{2,6}\s/m.test(text)) return false;
    const nlCount = (text.match(/\n/g) || []).length;
    const density = nlCount / Math.max(text.length, 1);
    if (text.length <= 800 && nlCount >= 15 && density > 0.06) return true;
    const keywordHit =
      /(检索|搜索|查询|思考|推理|分析|整理|规划|推断|综合)/.test(text);
    if (keywordHit && text.length <= 6000) return true;
    const leadHit =
      /(我来帮您|我将|接下来我会|我可以为您|为了更|请您提供|请你提供|请提供|我先|我会先|我们先)/.test(
        text,
      );
    if (leadHit && text.length <= 3000) return true;
    return false;
  },

  mergeThinkingMessages(messages) {
    if (!Array.isArray(messages) || messages.length === 0) return messages;

    if (this.data.agentType === "consultation") {
      const result = [];
      let assistantRun = [];

      const flushAssistantRun = () => {
        if (!assistantRun.length) return;
        if (assistantRun.length === 1) {
          result.push(assistantRun[0]);
          assistantRun = [];
          return;
        }

        const scoreFinal = (m) => {
          if (!m || !m.rawText) return 0;
          const t = String(m.rawText).trim();
          if (!t) return 0;
          let score = Math.min(t.length, 2000);
          if (t.length >= 200) score += 2000;
          if (/^#{2,6}\s/m.test(t)) score += 800;
          if (/\n\s*-\s+/.test(t)) score += 400;
          if (/\n\s*\d+\.\s+/.test(t)) score += 400;
          if (/[。！？!?]$/.test(t)) score += 80;
          return score;
        };

        let bestIdx = assistantRun.length - 1;
        let bestScore = -1;
        for (let i = 0; i < assistantRun.length; i++) {
          const s = scoreFinal(assistantRun[i]);
          if (s > bestScore) {
            bestScore = s;
            bestIdx = i;
          }
        }

        const finalMsg = assistantRun[bestIdx];
        const before = assistantRun.slice(0, bestIdx);
        const after = assistantRun.slice(bestIdx + 1);

        const combinedThinking = before
          .map((m) => (m && m.rawText ? String(m.rawText) : ""))
          .filter(Boolean)
          .join("\n\n")
          .trim();

        const trailingKept = after.filter((m) => {
          if (!m || !m.rawText) return false;
          return String(m.rawText).trim().length >= 80;
        });

        assistantRun = [];

        const existing = (finalMsg.thinkingRaw || "").trim();
        const finalThinkingRaw = combinedThinking
          ? existing
            ? `${combinedThinking}\n\n${existing}`
            : combinedThinking
          : existing;

        result.push(
          Object.assign({}, finalMsg, {
            thinkingRaw: finalThinkingRaw,
            thinkingHtml: finalThinkingRaw
              ? this.formatTextToRichHtml(finalThinkingRaw)
              : "",
            showThinking: false,
          }),
        );

        trailingKept.forEach((m) => result.push(m));
      };

      for (let i = 0; i < messages.length; i++) {
        const msg = messages[i];
        if (msg && msg.role === "assistant") {
          if (msg.isStreaming) {
            flushAssistantRun();
            result.push(msg);
            continue;
          }
          assistantRun.push(msg);
          continue;
        }
        flushAssistantRun();
        result.push(msg);
      }

      flushAssistantRun();
      return result;
    }

    const result = [];
    let pending = [];

    const attachPending = (target) => {
      if (!pending.length) return target;
      const combined = pending
        .map((m) => m.rawText)
        .filter(Boolean)
        .join("\n\n");
      pending = [];
      if (!combined) return target;
      const nextRaw = (target.thinkingRaw || "").trim();
      const finalThinkingRaw = nextRaw ? `${nextRaw}\n\n${combined}` : combined;
      return Object.assign({}, target, {
        thinkingRaw: finalThinkingRaw,
        thinkingHtml: this.formatTextToRichHtml(finalThinkingRaw),
        showThinking: false,
      });
    };

    for (let i = 0; i < messages.length; i++) {
      const msg = messages[i];
      if (msg && msg.role === "assistant" && this.isThinkingLikeMessage(msg)) {
        pending.push(msg);
        continue;
      }
      if (msg && msg.role === "assistant") {
        result.push(attachPending(msg));
        continue;
      }
      if (pending.length) {
        Array.prototype.push.apply(result, pending);
        pending = [];
      }
      result.push(msg);
    }

    if (pending.length) {
      Array.prototype.push.apply(result, pending);
      pending = [];
    }

    return result;
  },

  // 预览图片
  previewImage(e) {
    const src = e.currentTarget.dataset.src;
    wx.previewImage({
      urls: [src],
      current: src,
    });
  },

  // 打开文件
  openFile(e) {
    const url = e.currentTarget.dataset.url;
    // 微信小程序需要下载后才能打开
    wx.showLoading({ title: "下载中..." });
    wx.downloadFile({
      url: url,
      success: (res) => {
        const filePath = res.tempFilePath;
        wx.openDocument({
          filePath: filePath,
          showMenu: true,
          success: function () {
            console.log("打开文档成功");
          },
          fail: function (err) {
            console.error("打开文档失败", err);
            wx.showToast({
              title: "无法打开此文件",
              icon: "none",
            });
          },
        });
      },
      fail: (err) => {
        console.error("下载失败", err);
        wx.showToast({
          title: "下载失败",
          icon: "none",
        });
      },
      complete: () => {
        wx.hideLoading();
      },
    });
  },

  async loadHistory(conversationId) {
    wx.showLoading({ title: "加载历史..." });
    console.log("Loading history for conversation:", conversationId);
    try {
      let messages = [];
      let dbHasMessages = false;
      if (
        [
          "default",
          "consultation",
          "medication",
          "summary",
          "health_records",
        ].includes(this.data.agentType)
      ) {
        try {
          console.log("Fetching messages from DB...");
          const dbResponse = await getConsultationMessages(conversationId);
          console.log("DB history response:", dbResponse);
          if (
            dbResponse &&
            dbResponse.success &&
            Array.isArray(dbResponse.messages)
          ) {
            messages = dbResponse.messages;
            dbHasMessages = (messages || []).length > 0;
          } else if (Array.isArray(dbResponse)) {
            // Fallback if API returns array directly
            messages = dbResponse;
            dbHasMessages = (messages || []).length > 0;
          }

          if (!messages || messages.length === 0) {
            console.log(
              "DB history empty, falling back to conversation memory...",
            );
            messages = await listMessages(conversationId);
          }
        } catch (e) {
          console.warn("Fetch DB history failed, fallback to generic:", e);
          messages = await listMessages(conversationId);
        }
      } else {
        messages = await listMessages(conversationId);
      }

      if (
        (!messages || messages.length === 0) &&
        ["consultation", "medication", "summary", "health_records"].includes(
          this.data.agentType,
        )
      ) {
        try {
          console.log(
            "History still empty, trying consultation history for:",
            conversationId,
          );
          const historyList = await getConsultationHistory(0, 50);
          if (Array.isArray(historyList)) {
            const target = historyList.find(
              (item) =>
                item.consultation_id === conversationId ||
                item.id === conversationId,
            );
            if (target) {
              messages = [target];
            }
          }
        } catch (e) {
          console.warn("Consultation history fallback failed:", e);
        }
      }

      if (messages && messages.length > 0) {
        console.log("Raw history messages:", messages);
        const formattedMessages = this.normalizeHistoryMessages(messages);
        console.log("Normalized history messages:", formattedMessages);

        formattedMessages.sort((a, b) => a.timestamp - b.timestamp);
        const mergedFormattedMessages =
          this.mergeThinkingMessages(formattedMessages);
        console.log("Sorted formatted messages:", formattedMessages);

        const currentIds = new Set(this.data.messages.map((m) => m.id));
        const mergedMessages = [];
        mergedFormattedMessages.forEach((m) => {
          if (!currentIds.has(m.id)) {
            mergedMessages.push(m);
          }
        });

        const finalMessages =
          this.data.messages.length > 0
            ? this.data.messages.concat(mergedMessages)
            : mergedFormattedMessages;

        console.log("Final messages to render:", finalMessages);

        this.setData(
          {
            messages: finalMessages,
            shouldAutoScroll: true,
            showJumpToBottom: false,
            unreadCount: 0,
          },
          () => this.scheduleScrollToBottom(true),
        );

        if (
          !this.data.isHistorySynced &&
          dbHasMessages &&
          this.shouldPersistConversationToDb(this.data.agentType)
        ) {
          this.setData({ isHistorySynced: true });
        }
      }
    } catch (error) {
      console.error("Load history failed:", error);
    } finally {
      wx.hideLoading();
    }
  },

  async initializeAgent(agentType) {
    let title = "智能助手";
    let welcomeMsg = "您好，我是您的智能健康助手，有什么可以帮您？";
    let suggestions = [];
    let targetAgentName = "";

    // 智能体配置
    switch (agentType) {
      case "host":
        title = "智能协调助手";
        welcomeMsg =
          "您好！我是智能协调助手。我会根据您的问题自动调用健康档案、用药提醒、就诊摘要、健康顾问等能力来完成任务。";
        suggestions = [
          "我最近头痛发烧怎么办？",
          "查看我的健康档案",
          "帮我设置用药提醒",
          "生成最近一次就诊摘要",
        ];
        break;
      case "health_records":
        title = "健康档案管理员";
        targetAgentName = "健康档案管理员";
        welcomeMsg =
          "您好！我是您的健康档案管理员。您可以查询病史、添加记录或管理您的健康档案。";
        suggestions = [
          "如何添加新的健康记录？",
          "查看我的病史记录",
          "更新我的健康档案信息",
          "导出我的健康数据",
        ];
        break;
      case "medication":
        title = "用药提醒助手";
        targetAgentName = "用药提醒助手";
        welcomeMsg =
          "您好！我是您的用药助手。我可以帮您设置用药提醒、查询药物相互作用等。";
        suggestions = [
          "设置用药提醒",
          "管理药物清单",
          "检查药物相互作用",
          "用药时间安排",
        ];
        break;
      case "summary":
        title = "就诊摘要助手";
        targetAgentName = "就诊摘要生成器";
        welcomeMsg =
          "您好！我是就诊摘要助手。我可以帮您生成就诊摘要或解析医疗文档。";
        suggestions = ["生成最近的就诊摘要", "解析医疗报告", "总结检查结果"];
        break;
      case "consultation":
        title = "健康顾问";
        targetAgentName = "健康顾问";
        welcomeMsg = "您好！我是您的健康顾问。请告诉我您的症状或健康疑问。";
        suggestions = [
          "分析我的症状",
          "提供健康建议",
          "解释检查结果",
          "推荐治疗方案",
        ];
        break;
      default:
        title = "智能健康助手";
        suggestions = ["查看健康档案", "我要咨询", "用药提醒"];
    }

    wx.setNavigationBarTitle({ title });

    this.setData({
      suggestions,
      messages: [
        {
          id: "system_welcome",
          role: "assistant",
          contentParts: [
            { type: "text", content: this.formatTextToRichHtml(welcomeMsg) },
          ],
          rawText: welcomeMsg,
          isLong: this.isLongAssistantText(welcomeMsg),
          collapsed: this.isLongAssistantText(welcomeMsg),
          timestamp: Date.now() / 1000,
          timeString: this.formatTime(Date.now() / 1000),
        },
      ],
      agentUrl: targetAgentName ? "__HOST_API__" : "",
      selectedAgentName: targetAgentName || "",
    });
  },

  /**
   * Lifecycle function--Called when page show
   */
  // 阶段35: onLoad 启动时探测后端
  onLoad() {
    this.onLoadStage35Init();
  },

  onShow() {
    if (
      this.data.conversationId &&
      !this.data.isPolling &&
      !this.data.agentUrl
    ) {
      this.startPolling();
    }
  },

  /**
   * Lifecycle function--Called when page hide
   */
  onHide() {
    this.stopPolling();
  },

  /**
   * Lifecycle function--Called when page unload
   */
  onUnload() {
    this.stopPolling();
    if (this.requestTask) {
      this.requestTask.abort();
    }
    if (this.recorderManager && this.data.isRecording) {
      try {
        this.recorderManager.stop();
      } catch (e) {}
    }
    if (this.scrollTimer) {
      clearTimeout(this.scrollTimer);
      this.scrollTimer = null;
    }
    if (this.streamingUpdateTimer) {
      clearTimeout(this.streamingUpdateTimer);
      this.streamingUpdateTimer = null;
    }
  },

  // 生成UUID
  generateUUID() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(
      /[xy]/g,
      function (c) {
        var r = (Math.random() * 16) | 0,
          v = c == "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
      },
    );
  },

  // 格式化时间
  formatTime(timestamp) {
    const date = new Date(timestamp * 1000);
    const hours = date.getHours().toString().padStart(2, "0");
    const minutes = date.getMinutes().toString().padStart(2, "0");
    return `${hours}:${minutes}`;
  },

  handleInput(e) {
    this.setData({
      inputText: e.detail.value,
    });
  },

  async pickImageAttachment() {
    if (this.data.isSending || this.data.isRecording) return;
    try {
      const chooser = await wx.showActionSheet({
        itemList: ["拍照", "从相册选择"],
      });
      const sourceType = chooser.tapIndex === 0 ? ["camera"] : ["album"];
      const res = await wx.chooseMedia({
        count: 1,
        mediaType: ["image"],
        sourceType,
        camera: "back",
      });
      const tempFilePath =
        (res.tempFiles && res.tempFiles[0] && res.tempFiles[0].tempFilePath) ||
        (res.tempFilePaths && res.tempFilePaths[0]) ||
        "";
      if (!tempFilePath) return;
      await this.uploadAttachmentTempFile(tempFilePath, "image");
    } catch (e) {}
  },

  ensureRecorderManager() {
    if (this.recorderManager) return this.recorderManager;
    this.recorderManager = wx.getRecorderManager();
    this.recorderManager.onStop((res) => {
      const finalize = async () => {
        try {
          const tempFilePath = (res && res.tempFilePath) || "";
          if (tempFilePath) {
            const transcribed = await this.transcribeVoiceToInput(tempFilePath);
            if (!transcribed) {
              await this.uploadAttachmentTempFile(tempFilePath, "audio");
            }
          }
        } catch (e) {
          wx.showToast({ title: "语音上传失败", icon: "none" });
        } finally {
          this.setData({ isRecording: false });
          if (this.recorderStopPromiseResolve) {
            this.recorderStopPromiseResolve();
            this.recorderStopPromiseResolve = null;
          }
        }
      };
      finalize();
    });
    this.recorderManager.onError(() => {
      this.setData({ isRecording: false });
      if (this.recorderStopPromiseResolve) {
        this.recorderStopPromiseResolve();
        this.recorderStopPromiseResolve = null;
      }
      wx.showToast({ title: "录音失败", icon: "none" });
    });
    return this.recorderManager;
  },

  async transcribeVoiceToInput(tempFilePath) {
    wx.showLoading({ title: "语音识别中..." });
    try {
      const result = await transcribeAudioFile(tempFilePath);
      const text = String((result && result.text) || "").trim();
      if (!text) {
        throw new Error("empty transcript");
      }
      const current = String(this.data.inputText || "").trim();
      this.setData({ inputText: current ? `${current}\n${text}` : text });
      wx.showToast({ title: "语音已转文字", icon: "none" });
      return true;
    } catch (e) {
      wx.showToast({ title: "识别失败，已转为附件", icon: "none" });
      return false;
    } finally {
      wx.hideLoading();
    }
  },

  async toggleVoiceRecord() {
    if (this.data.isSending) return;
    const recorder = this.ensureRecorderManager();
    if (this.data.isRecording) {
      await new Promise((resolve) => {
        this.recorderStopPromiseResolve = resolve;
        recorder.stop();
      });
      return;
    }
    this.setData({ isRecording: true });
    try {
      recorder.start({
        duration: 60000,
        sampleRate: 16000,
        numberOfChannels: 1,
        encodeBitRate: 64000,
        format: "mp3",
      });
      wx.showToast({ title: "开始录音", icon: "none" });
    } catch (e) {
      this.setData({ isRecording: false });
      wx.showToast({ title: "无法开始录音", icon: "none" });
    }
  },

  async uploadAttachmentTempFile(tempFilePath, kind) {
    wx.showLoading({ title: "上传中..." });
    try {
      const uploadResult = await uploadFile(tempFilePath, "/upload");
      const urlPath = (uploadResult && uploadResult.url) || "";
      const name =
        (uploadResult && uploadResult.filename) ||
        `${kind === "audio" ? "语音" : "图片"}_${Date.now()}`;
      const mimeType =
        (uploadResult && uploadResult.mimeType) ||
        (kind === "audio" ? "audio/mpeg" : "image/jpeg");
      if (!urlPath) {
        throw new Error("upload url missing");
      }
      const uri = urlPath.startsWith("http")
        ? urlPath
        : `${SERVER_URL}${urlPath}`;
      const isImage = String(mimeType).startsWith("image/");
      const attachment = {
        id: `att_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        name,
        mimeType,
        uri,
        type: isImage ? "image" : "file",
      };
      this.setData({
        pendingAttachments: (this.data.pendingAttachments || []).concat([
          attachment,
        ]),
      });
    } catch (e) {
      wx.showToast({ title: "上传失败", icon: "none" });
    } finally {
      wx.hideLoading();
    }
  },

  removePendingAttachment(e) {
    const id = e.currentTarget.dataset.id;
    const next = (this.data.pendingAttachments || []).filter(
      (x) => x.id !== id,
    );
    this.setData({ pendingAttachments: next });
  },

  // 处理发送按钮点击
  handleSend() {
    this.sendMessage();
  },

  handleSuggestionTap(e) {
    const text = e.currentTarget.dataset.text;
    this.setData({ inputText: text }, () => {
      this.sendMessage();
    });
  },

  toggleThinking(e) {
    const index = e.currentTarget.dataset.index;
    const messages = Array.isArray(this.data.messages)
      ? this.data.messages
      : [];
    const msg = messages[index];
    if (!msg) return;
    const next = messages.map((m, i) => {
      if (i !== index) return m;
      return Object.assign({}, m, { showThinking: !m.showThinking });
    });
    this.setData({ messages: next });
  },

  // 阶段35/37: 统一发送入口（v1/v2/single/multi 自动选择）
  // 阶段37: 改用 v2 SSE 流式（sendMessageV2Stream）
  async _sendWithV2(payload) {
    const { useV2, v2ExecMode, conversationId } = this.data;
    if (useV2) {
      try {
        if (v2ExecMode === "multi") {
          this.setData({ v2ModeInfo: "v2 · 4 agent 并行..." });
          // multi 模式暂用同步接口
          const result = await sendMessageV2Multi(payload);
          this._handleV2Response(result);
          return result;
        } else {
          this.setData({ v2ModeInfo: "v2 · 单 agent · 流式..." });
          // 阶段37: 用 SSE 流式，直接显示 LLM 答案
          return await this._sendWithV2Stream(payload, conversationId);
        }
      } catch (e) {
        console.warn("[v2] sendMessageV2 failed, fallback to v1", e);
        this.setData({ useV2: false, v2ModeInfo: "v1 · A2A 私有" });
        // fallthrough to v1
      }
    }
    // v1 fallback
    this.setData({ v2ModeInfo: "v1 · A2A 私有..." });
    return await sendMessage(payload);
  },

  // 阶段37: v2 SSE 流式发送
  async _sendWithV2Stream(payload, conversationId) {
    return new Promise((resolve, reject) => {
      let pendingAssistantId = null;
      let fullContent = "";
      let agent = null;
      let routing = null;

      const task = sendMessageV2Stream(
        {
          ...payload,
          conversation_id: conversationId,
          mode: "single",
        },
        // onEvent
        (evt) => {
          const { event, data } = evt;
          console.log("[v2 stream]", event, data);
          if (event === "routing") {
            agent = data.agent;
            routing = data.routing;
            this.setData({ selectedAgent: agent, agentRouting: routing });
          } else if (event === "chunk") {
            if (!pendingAssistantId) {
              // 第一次收到 chunk，创建 assistant 消息
              pendingAssistantId = `v2-${Date.now()}-${Math.random()}`;
              // 阶段37: 替换原来的 pending_ai_xxx 消息（显示 "AI 思考中..."）
              const oldPendingId = this.currentPendingAssistantId;
              const newMsg = {
                id: pendingAssistantId,
                role: "assistant",
                // 阶段37: 修复 - WXML 用 part.content（不是 part.text）
                contentParts: [
                  { type: "text", content: data.text, text: data.text },
                ],
                rawText: data.text,
                isLong: false,
                collapsed: false,
                timestamp: Date.now() / 1000,
                timeString: this.formatTime(Date.now() / 1000),
                isStreaming: true,
                metadata: {
                  source: "pha-v2-host-graph",
                  agent: agent,
                  v2_routing: routing,
                },
              };
              this.setData({
                messages: (this.data.messages || [])
                  .filter((m) => m.id !== oldPendingId)
                  .concat([newMsg]),
                isSending: false,
                shouldAutoScroll: true,
              });
              this.currentPendingAssistantId = pendingAssistantId;
            } else {
              // 后续 chunk 累加
              const messages = (this.data.messages || []).map((m) => {
                if (m.id === pendingAssistantId) {
                  const newText = (m.rawText || "") + data.text;
                  return Object.assign({}, m, {
                    rawText: newText,
                    contentParts: [
                      { type: "text", content: newText, text: newText },
                    ],
                    isStreaming: true,
                  });
                }
                return m;
              });
              this.setData({ messages });
            }
            fullContent += data.text;
            this.scheduleScrollToBottom(true);
          } else if (event === "done") {
            // 流结束，标记消息完成
            if (pendingAssistantId) {
              const messages = (this.data.messages || []).map((m) => {
                if (m.id === pendingAssistantId) {
                  return Object.assign({}, m, {
                    rawText: data.content || fullContent,
                    contentParts: [
                      {
                        type: "text",
                        content: data.content || fullContent,
                        text: data.content || fullContent,
                      },
                    ],
                    isStreaming: false,
                  });
                }
                return m;
              });
              this.setData({ messages, isSending: false });
              this.currentPendingAssistantId = null;
            }
            this._updateV2ModeInfo();
            resolve({
              success: true,
              message: data.content || fullContent,
              selected_agent: data.agent,
              routing: routing,
            });
          } else if (event === "error") {
            console.error("[v2 stream error]", data);
            reject(new Error(data.error || "v2 stream error"));
          }
        },
        // onError
        (err) => {
          console.error("[v2 stream failed]", err);
          if (pendingAssistantId) {
            const messages = (this.data.messages || []).filter(
              (m) => m.id !== pendingAssistantId,
            );
            this.setData({ messages, isSending: false });
            this.currentPendingAssistantId = null;
          }
          reject(err);
        },
      );
      this.requestTask = task;
    });
  },

  // 阶段35: 处理 v2 响应
  _handleV2Response(result) {
    if (!result) return;
    // v2 返回字段：{ success, message, conversation_id, message_id, selected_agent, routing }
    if (result.selected_agent) {
      this.setData({ selectedAgent: result.selected_agent });
    }
    if (result.routing) {
      this.setData({ agentRouting: result.routing });
    }
    // 收到响应后副信息切回 idle
    this._updateV2ModeInfo();
  },

  async sendMessage() {
    const text = this.data.inputText.trim();
    const attachments = Array.isArray(this.data.pendingAttachments)
      ? this.data.pendingAttachments
      : [];
    if ((!text && attachments.length === 0) || this.data.isSending) return;

    const userContentParts = [];
    if (text) {
      userContentParts.push({
        type: "text",
        content: this.formatTextToRichHtml(text),
      });
    }
    attachments.forEach((a) => {
      if (!a || !a.uri) return;
      userContentParts.push({
        type: a.type === "image" ? "image" : "file",
        url: a.uri,
        name: a.name || "文件",
        mimeType: a.mimeType || "",
      });
    });

    const fallbackText =
      attachments.length > 0
        ? `用户发送了${attachments.length}个附件`
        : "用户发送了消息";

    const userMessage = {
      id: `user_${Date.now()}`,
      role: "user",
      contentParts: userContentParts,
      rawText: text || fallbackText,
      isLong: false,
      collapsed: false,
      timestamp: Date.now() / 1000,
      timeString: this.formatTime(Date.now() / 1000),
    };

    await new Promise((resolve) => {
      this.setData(
        {
          messages: (this.data.messages || []).concat([userMessage]),
          inputText: "",
          pendingAttachments: [],
          isSending: true,
          shouldAutoScroll: true,
          showJumpToBottom: false,
          unreadCount: 0,
        },
        resolve,
      );
    });
    this.scheduleScrollToBottom(true);

    try {
      // 1. 如果没有会话ID，先创建会话
      let convId = this.data.conversationId;
      if (!convId) {
        const conv = await createConversation();
        if (conv && (conv.id || conv.conversation_id)) {
          convId = conv.id || conv.conversation_id;
          this.setData({ conversationId: convId, sessionId: convId });
        } else if (typeof conv === "string" && conv) {
          convId = conv;
          this.setData({ conversationId: convId, sessionId: convId });
        } else {
          throw new Error("Failed to create conversation");
        }
      }
      if (convId) {
        try {
          wx.setStorageSync(
            `agent_chat:lastConversationId:${this.data.agentType}`,
            convId,
          );
          wx.setStorageSync("agent_chat:lastContext", {
            agentType: this.data.agentType,
            conversationId: convId,
          });
        } catch (e) {
          console.warn("Persist agent_chat lastConversationId failed:", e);
        }
      }

      const shouldPersist = this.shouldPersistConversationToDb(
        this.data.agentType,
      );

      // 同步到咨询历史（如果是新对话且属于咨询类）
      if (!this.data.isHistorySynced && shouldPersist) {
        try {
          const tags =
            String(this.data.agentType || "") === "default"
              ? ["health"]
              : [this.data.agentType];
          await createConsultation({
            question: text || fallbackText,
            consultation_id: convId,
            session_id: convId,
            tags,
          });
          console.log("Consultation history synced");
          this.setData({ isHistorySynced: true });
        } catch (err) {
          console.error("Failed to sync consultation history:", err);
          this.setData({ isHistorySynced: true });
          // 如果创建咨询记录失败，可能后续保存消息也会有问题，但我们尽量继续
        }
      }

      if (shouldPersist) {
        const dbFiles = attachments
          .filter((a) => a && a.uri)
          .map((a) => ({
            name: a.name || "附件",
            mimeType: a.mimeType || "",
            uri: a.uri,
          }));
        await this.saveMessageToDbOnce(
          convId,
          "user",
          text || fallbackText,
          userMessage.id,
          dbFiles,
        );
      }

      // 如果有 agentUrl，使用流式模式 (Emulating React)
      if (this.data.agentUrl) {
        // 添加 AI 思考中消息
        const aiMsgId = `ai_${Date.now()}`;
        const aiMessage = {
          id: aiMsgId,
          role: "assistant", // or "ai"
          contentParts: [],
          rawText: "",
          thinkingRaw: "",
          thinkingHtml: "",
          showThinking: false,
          isLong: false,
          collapsed: false,
          timestamp: Date.now() / 1000,
          timeString: this.formatTime(Date.now() / 1000),
          isStreaming: true,
        };

        this.setData({
          messages: (this.data.messages || []).concat([aiMessage]),
          shouldAutoScroll: true,
          showJumpToBottom: false,
          unreadCount: 0,
        });
        this.scheduleScrollToBottom(true);

        this.streamingContent = "";
        this.streamingThinkingRaw = "";
        this.currentStreamingId = aiMsgId;

        // 发送流式请求
        const selectedAgentName = this.data.selectedAgentName || "";
        const payloadParts = [];
        if (text) {
          payloadParts.push({ type: "text", text: text });
        }
        attachments.forEach((a) => {
          if (!a || !a.uri) return;
          payloadParts.push({
            type: "file",
            file: {
              name: a.name || "附件",
              mimeType: a.mimeType || "",
              uri: a.uri.replace(SERVER_URL, ""),
            },
          });
        });
        if (payloadParts.length === 0) {
          payloadParts.push({ type: "text", text: fallbackText });
        }
        const userInfo = wx.getStorageSync("userInfo") || {};
        const userId = userInfo.user_id || userInfo.id || "";
        const payload = {
          id: this.generateUUID(),
          sessionId: convId,
          message: {
            role: "user",
            parts: payloadParts,
            metadata: selectedAgentName
              ? {
                  selected_agent: selectedAgentName,
                  message_id: userMessage.id,
                  user_id: userId,
                }
              : { message_id: userMessage.id, user_id: userId },
          },
        };

        this.requestTask =
          this.data.agentUrl === "__HOST_API__"
            ? sendTaskStreamingViaHost(
                selectedAgentName,
                payload,
                (data) => {
                  // onMessage
                  // 处理流式数据
                  // 1. 思考过程 (Thinking)
                  const statusParts = data?.result?.status?.message?.parts;
                  if (statusParts) {
                    let thinkingText = "";
                    statusParts.forEach((p) => {
                      if (p.type === "text" && p.text) thinkingText += p.text;
                    });

                    if (thinkingText) {
                      this.streamingThinkingRaw =
                        (this.streamingThinkingRaw || "") + thinkingText;
                    }
                  }

                  const statusState = data?.result?.status?.state;
                  if (
                    statusState === "processing" ||
                    statusState === "pending" ||
                    statusState === "running"
                  ) {
                    this.tryRequestTaskSubscribe();
                  }

                  // 2. 回复内容 (Artifact/Message)
                  const artifact = data?.result?.artifact;
                  const msgParts = data?.result?.message?.parts;
                  let shouldUpdateContent = false;

                  if (artifact && artifact.parts) {
                    let artifactText = "";
                    artifact.parts.forEach((p) => {
                      if (p.type === "text" && p.text) artifactText += p.text;
                    });

                    if (artifactText) {
                      const appendFlag = artifact.append;
                      this.mergeStreamingText(artifactText, !appendFlag);
                      shouldUpdateContent = true;
                    }
                  } else if (msgParts) {
                    let newText = "";
                    msgParts.forEach((p) => {
                      if (p.type === "text" && p.text) newText += p.text;
                    });
                    if (newText) {
                      this.mergeStreamingText(newText, false);
                      shouldUpdateContent = true;
                    }
                  }

                  if (shouldUpdateContent) {
                    this.scheduleStreamingContentUpdate();
                  }

                  // 检查是否完成
                  if (
                    data?.result?.final ||
                    data?.result?.status?.state === "completed"
                  ) {
                    this.handleStreamingComplete(convId);
                  }
                },
                (err) => {
                  // onError
                  console.error("Streaming error:", err);
                  const updatedMessages = this.data.messages.map((m) => {
                    if (m.id === this.currentStreamingId) {
                      const finalText = this.normalizeStreamingText(
                        this.streamingContent || "抱歉，出错了。",
                      );
                      const finalThinkingRaw = this.normalizeStreamingText(
                        this.streamingThinkingRaw || "",
                      );
                      const isLong = this.isLongAssistantText(finalText);
                      return Object.assign({}, m, {
                        contentParts: [
                          {
                            type: "text",
                            content: this.formatTextToRichHtml(finalText),
                          },
                        ],
                        rawText: finalText,
                        thinkingRaw: finalThinkingRaw,
                        thinkingHtml: finalThinkingRaw
                          ? this.formatTextToRichHtml(finalThinkingRaw)
                          : "",
                        showThinking: false,
                        isLong,
                        collapsed: isLong,
                        isStreaming: false,
                      });
                    }
                    return m;
                  });
                  this.setData(
                    { messages: updatedMessages, isSending: false },
                    () => this.scheduleScrollToBottom(false, 0),
                  );
                },
                () => {
                  // onComplete
                  this.handleStreamingComplete(convId);
                },
              )
            : sendTaskStreaming(
                this.data.agentUrl,
                payload,
                (data) => {
                  // onMessage
                  // 处理流式数据
                  // 1. 思考过程 (Thinking)
                  const statusParts = data?.result?.status?.message?.parts;
                  if (statusParts) {
                    let thinkingText = "";
                    statusParts.forEach((p) => {
                      if (p.type === "text" && p.text) thinkingText += p.text;
                    });

                    if (thinkingText) {
                      this.streamingThinkingRaw =
                        (this.streamingThinkingRaw || "") + thinkingText;
                    }
                  }

                  const statusState = data?.result?.status?.state;
                  if (
                    statusState === "processing" ||
                    statusState === "pending" ||
                    statusState === "running"
                  ) {
                    this.tryRequestTaskSubscribe();
                  }

                  // 2. 回复内容 (Artifact/Message)
                  const artifact = data?.result?.artifact;
                  const msgParts = data?.result?.message?.parts;
                  let shouldUpdateContent = false;

                  if (artifact && artifact.parts) {
                    let artifactText = "";
                    artifact.parts.forEach((p) => {
                      if (p.type === "text" && p.text) artifactText += p.text;
                    });

                    if (artifactText) {
                      const appendFlag = artifact.append;
                      this.mergeStreamingText(artifactText, !appendFlag);
                      shouldUpdateContent = true;
                    }
                  } else if (msgParts) {
                    let newText = "";
                    msgParts.forEach((p) => {
                      if (p.type === "text" && p.text) newText += p.text;
                    });
                    if (newText) {
                      this.mergeStreamingText(newText, false);
                      shouldUpdateContent = true;
                    }
                  }

                  if (shouldUpdateContent) {
                    this.scheduleStreamingContentUpdate();
                  }

                  // 检查是否完成
                  if (
                    data?.result?.final ||
                    data?.result?.status?.state === "completed"
                  ) {
                    this.handleStreamingComplete(convId);
                  }
                },
                (err) => {
                  // onError
                  console.error("Streaming error:", err);
                  const updatedMessages = this.data.messages.map((m) => {
                    if (m.id === this.currentStreamingId) {
                      const finalText = this.normalizeStreamingText(
                        this.streamingContent || "抱歉，出错了。",
                      );
                      const finalThinkingRaw = this.normalizeStreamingText(
                        this.streamingThinkingRaw || "",
                      );
                      const isLong = this.isLongAssistantText(finalText);
                      return Object.assign({}, m, {
                        contentParts: [
                          {
                            type: "text",
                            content: this.formatTextToRichHtml(finalText),
                          },
                        ],
                        rawText: finalText,
                        thinkingRaw: finalThinkingRaw,
                        thinkingHtml: finalThinkingRaw
                          ? this.formatTextToRichHtml(finalThinkingRaw)
                          : "",
                        showThinking: false,
                        isLong,
                        collapsed: isLong,
                        isStreaming: false,
                      });
                    }
                    return m;
                  });
                  this.setData(
                    { messages: updatedMessages, isSending: false },
                    () => this.scheduleScrollToBottom(false, 0),
                  );
                },
                () => {
                  // onComplete
                  this.handleStreamingComplete(convId);
                },
              );
      } else {
        if (attachments.length > 0) {
          wx.showToast({
            title: "当前模式暂不支持附件",
            icon: "none",
          });
        }
        // 默认通用模式 (Polling)
        // 2. 发送消息
        let selectedAgent = "";
        switch (this.data.agentType) {
          case "health_records":
            selectedAgent = "健康档案管理员";
            break;
          case "medication":
            selectedAgent = "用药提醒助手";
            break;
          case "summary":
            selectedAgent = "就诊摘要生成器";
            break;
          case "consultation":
            selectedAgent = "健康顾问";
            break;
        }

        if (!this.currentPendingAssistantId) {
          const pendingId = `pending_ai_${Date.now()}`;
          this.currentPendingAssistantId = pendingId;
          const pendingMessage = {
            id: pendingId,
            role: "assistant",
            contentParts: [],
            rawText: "",
            thinkingRaw: "",
            thinkingHtml: "",
            showThinking: false,
            isLong: false,
            collapsed: false,
            timestamp: Date.now() / 1000,
            timeString: this.formatTime(Date.now() / 1000),
            isStreaming: true,
          };
          await new Promise((resolve) => {
            this.setData(
              {
                messages: (this.data.messages || []).concat([pendingMessage]),
                shouldAutoScroll: true,
                showJumpToBottom: false,
                unreadCount: 0,
              },
              resolve,
            );
          });
          this.scheduleScrollToBottom(true);
        }

        const sendResult = await this._sendWithV2({
          conversation_id: convId,
          role: "user",
          message: text,
          metadata: selectedAgent
            ? { selected_agent: selectedAgent, message_id: userMessage.id }
            : { message_id: userMessage.id },
        });

        // 3. 阶段37: 只在 v1 模式或异常时轮询
        // v2 流式模式下 _sendWithV2Stream 自己处理显示，不需要轮询
        if (!this.data.useV2) {
          this.startPolling();
        }
      }
    } catch (error) {
      console.error("Send message failed:", error);
      wx.showToast({
        title: "发送失败",
        icon: "none",
      });
      if (this.currentPendingAssistantId) {
        const pendingId = this.currentPendingAssistantId;
        this.currentPendingAssistantId = null;
        this.setData({
          messages: (this.data.messages || []).filter(
            (m) => m.id !== pendingId,
          ),
          isSending: false,
        });
        return;
      }
      this.setData({ isSending: false });
    }
  },

  async handleStreamingComplete(convId) {
    if (!this.currentStreamingId) return;

    if (this.streamingUpdateTimer) {
      clearTimeout(this.streamingUpdateTimer);
      this.streamingUpdateTimer = null;
    }

    // 标记完成
    const finalText = this.normalizeStreamingText(this.streamingContent || "");
    this.streamingContent = finalText;
    const finalThinkingRaw = this.normalizeStreamingText(
      this.streamingThinkingRaw || "",
    );
    const isLong = this.isLongAssistantText(finalText);
    const updatedMessages = this.data.messages.map((m) => {
      if (m.id === this.currentStreamingId) {
        return Object.assign({}, m, {
          isStreaming: false,
          rawText: finalText,
          thinkingRaw: finalThinkingRaw,
          thinkingHtml: finalThinkingRaw
            ? this.formatTextToRichHtml(finalThinkingRaw)
            : "",
          showThinking: false,
          isLong,
          collapsed: isLong,
          contentParts: finalText
            ? [{ type: "text", content: this.formatTextToRichHtml(finalText) }]
            : m.contentParts,
        });
      }
      return m;
    });
    this.setData({ messages: updatedMessages, isSending: false }, () =>
      this.scheduleScrollToBottom(),
    );

    if (
      this.streamingContent &&
      this.shouldPersistConversationToDb(this.data.agentType)
    ) {
      await this.saveMessageToDbOnce(
        convId,
        "assistant",
        this.streamingContent,
        this.currentStreamingId,
      );
    }

    this.currentStreamingId = null;
    this.requestTask = null;
    this.streamingThinkingRaw = "";
  },

  startPolling() {
    if (this.data.isPolling) return;
    this.setData({ isPolling: true });
    this.pollMessages();
  },

  stopPolling() {
    this.setData({ isPolling: false });
  },

  async pollMessages() {
    if (!this.data.isPolling || !this.data.conversationId) return;

    try {
      // 这里简化为轮询新消息，实际应该包含 queryEvents 和 getProcessingMessages
      // 为了保持简洁，这里假设后端会异步处理并写入消息历史
      // 实际项目中可能需要更复杂的事件处理逻辑

      // 暂时只获取最近的消息
      const messages = await listMessages(this.data.conversationId);

      if (messages && messages.length > 0) {
        // 阶段36: debug log
        console.log(
          "[pollMessages] got",
          messages.length,
          "messages:",
          messages.map((m) => ({
            role: m.role,
            text: (m.parts?.[0]?.text || "").slice(0, 50),
            source: m.metadata?.source,
            v2: !!m.metadata?.v2_routing,
          })),
        );
        // 转换消息格式
        const formattedMessages = messages.map((m) => {
          const id =
            m.id ||
            (m.metadata && m.metadata.message_id) ||
            `msg-${Date.now()}-${Math.random()}`;
          const role = this.isAssistantRole(m.role)
            ? "assistant"
            : String(m.role || "assistant");
          const rawText = this.extractTextFromMessage(m);
          const isLong =
            role === "assistant" && this.isLongAssistantText(rawText);
          return {
            id,
            role,
            contentParts: this.processMessageContent(m),
            rawText,
            isLong,
            collapsed: isLong,
            // 阶段36: 保留 metadata，让 isV2Msg 能识别 v2 注入
            metadata: m.metadata,
            timestamp: this.parseTimestampSeconds(m.created_at || m.createdAt),
            timeString: this.formatTime(
              this.parseTimestampSeconds(m.created_at || m.createdAt),
            ),
          };
        });

        // 合并消息，去重
        const baseMessagesSnapshot = this.data.messages || [];
        const currentIds = new Set(baseMessagesSnapshot.map((m) => m.id));
        const newMessages = formattedMessages.filter(
          (m) => !currentIds.has(m.id),
        );
        // 阶段36: 更详细的 debug
        console.log(
          "[pollMessages] formatted:",
          formattedMessages.map((m) => ({
            id: m.id,
            role: m.role,
            textLen: m.rawText?.length || 0,
            hasV2Meta: !!(
              m.metadata &&
              (m.metadata.source || m.metadata.v2_routing)
            ),
          })),
        );

        if (newMessages.length > 0) {
          // 阶段36: v2 注入消息早期显示（绕过 pending 过滤）
          const isV2Msg = (m) =>
            m &&
            m.metadata &&
            (m.metadata.source === "pha-v2-host-graph" ||
              m.metadata.v2_routing);
          const v2NewMessages = newMessages.filter(isV2Msg);
          if (v2NewMessages.length > 0) {
            console.log(
              "[v2] 早期显示 v2 注入消息:",
              v2NewMessages.map((m) => m.rawText?.slice(0, 50)),
            );
            // 删除 pending
            let baseMessages = baseMessagesSnapshot.filter(
              (m) => m.id !== this.currentPendingAssistantId,
            );
            const combined = this.mergeThinkingMessages(
              baseMessages.concat(v2NewMessages),
            );
            this.setData(
              {
                messages: combined,
                isSending: false,
              },
              () => this.scheduleScrollToBottom(false, v2NewMessages.length),
            );
            this.currentPendingAssistantId = null;
            // 阶段36: v2 完整 LLM 答案已显示，停止轮询（v2 不会再来更多）
            this.stopPolling();
            return; // 跳过下面的 pending 过滤逻辑和 setTimeout
          }

          let baseMessages = baseMessagesSnapshot;

          const pendingId = this.currentPendingAssistantId;
          const pendingMsg = pendingId
            ? baseMessages.find((m) => m && m.id === pendingId)
            : null;

          const isFinalAssistantReply = (m) => {
            if (!m || m.role !== "assistant" || !m.rawText) return false;
            const t = String(m.rawText).trim();
            if (!t) return false;
            if (t.length >= 200) return true;
            if (/^#{2,6}\s/m.test(t)) return true;
            if (/\n\s*-\s+/.test(t)) return true;
            if (/\n\s*\d+\.\s+/.test(t)) return true;
            if (t.length >= 60 && /[。！？!?]$/.test(t)) return true;
            return false;
          };

          let effectiveNewMessages = newMessages;
          let hasAssistantReply = effectiveNewMessages.some(
            isFinalAssistantReply,
          );

          if (pendingMsg) {
            const assistantNew = newMessages.filter(
              (m) => m && m.role === "assistant" && m.rawText,
            );
            // 阶段36: 检测 v2 注入消息（有 source=pha-v2-host-graph 标记）
            const isV2Msg = (m) =>
              m &&
              m.metadata &&
              (m.metadata.source === "pha-v2-host-graph" ||
                m.metadata.v2_routing);
            const finalCandidates = assistantNew.filter(isFinalAssistantReply);
            const v2Msgs = assistantNew.filter(isV2Msg);

            if (finalCandidates.length) {
              // v1 完整 final 答案
              baseMessages = baseMessages.filter(
                (m) => m && m.id !== pendingId,
              );
              effectiveNewMessages = newMessages.filter(
                (m) => m.role !== "assistant" || finalCandidates.includes(m),
              );
              hasAssistantReply = true;
            } else if (v2Msgs.length) {
              // 阶段36: v2 注入的消息（v2 manager 完整 LLM 答案）
              // 直接显示，不再等 isFinalAssistantReply 条件
              console.log(
                "[v2] 检测到 v2 注入消息，显示:",
                v2Msgs.map((m) => m.rawText?.slice(0, 50)),
              );
              baseMessages = baseMessages.filter(
                (m) => m && m.id !== pendingId,
              );
              effectiveNewMessages = newMessages;
              hasAssistantReply = true;
            } else {
              effectiveNewMessages = newMessages.filter(
                (m) => m.role !== "assistant",
              );
              hasAssistantReply = false;
            }
          }

          const combined = this.mergeThinkingMessages(
            (baseMessages || []).concat(effectiveNewMessages || []),
          );
          const patch = { messages: combined };
          if (hasAssistantReply) patch.isSending = false;
          // 阶段36: 详细 debug
          console.log("[pollMessages] setting patch:", {
            hasAssistantReply,
            effectiveNewCount: effectiveNewMessages.length,
            combinedLen: combined.length,
            effectiveRoles: effectiveNewMessages.map(
              (m) => m.role + ":" + (m.rawText?.length || 0),
            ),
          });
          this.setData(patch, () =>
            this.scheduleScrollToBottom(false, effectiveNewMessages.length),
          );
          if (hasAssistantReply) this.currentPendingAssistantId = null;

          if (this.shouldPersistConversationToDb(this.data.agentType)) {
            const assistantMsgs = effectiveNewMessages.filter(
              (m) =>
                m &&
                m.role === "assistant" &&
                m.rawText &&
                !this.isThinkingLikeMessage(m),
            );
            if (assistantMsgs.length) {
              await Promise.all(
                assistantMsgs.map((m) =>
                  this.saveMessageToDbOnce(
                    this.data.conversationId,
                    "assistant",
                    m.rawText,
                    m.id,
                  ),
                ),
              );
            }
          }
        }
      }
    } catch (error) {
      console.error("Poll error:", error);
    }

    // 继续轮询
    if (this.data.isPolling) {
      setTimeout(() => {
        this.pollMessages();
      }, 2000);
    }
  },
});
