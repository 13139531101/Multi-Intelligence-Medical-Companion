// pages/agent_chat/agent_chat.js
const {
  sendMessage,
  createConversation,
  listMessages,
  getProcessingMessages,
  queryEvents,
  sendTaskStreaming,
  listRemoteAgents,
  getAgentCard,
  createConsultation,
  saveConsultationMessage,
  getConsultationMessages,
  getConsultationHistory,
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
    sessionId: "",
    suggestions: [],
    isHistorySynced: false,
  },

  // 在页面实例上维护已处理的事件ID集合
  processedEventIds: new Set(),
  // 维护流式请求任务
  requestTask: null,
  // 流式回复内容缓存
  streamingContent: "",
  currentStreamingId: null,
  scrollTimer: null,
  lastScrollDetail: null,

  /**
   * Lifecycle function--Called when page load
   */
  async onLoad(options) {
    const agentType = options.agentType || options.mode || "default";
    const conversationId = options.id || null;
    const sessionId = conversationId || this.generateUUID();

    this.setData({
      agentType,
      sessionId,
      conversationId: conversationId,
      isHistorySynced: !!conversationId,
    });

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

  onReady() {
    this.refreshScrollViewHeight();
  },

  formatTextToRichHtml(text) {
    const raw = text === undefined || text === null ? "" : String(text);
    let html = raw.replace(/\r\n/g, "\n");
    html = html
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    html = html.replace(/^#{1,6}\s*(.+)$/gm, "<b>$1</b>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    html = html.replace(
      /`([^`]+)`/g,
      '<span style="font-family: monospace;">$1</span>'
    );
    html = html.replace(/^\s*-\s+/gm, "&bull; ");
    html = html.replace(/\n/g, "<br/>");
    return `<div style="word-break: break-word;">${html}</div>`;
  },

  isLongAssistantText(text) {
    const raw = text === undefined || text === null ? "" : String(text);
    return raw.length >= 1200;
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
      const patch = { showJumpToBottom: true };
      if (newItems) {
        patch.unreadCount = (this.data.unreadCount || 0) + newItems;
      }
      this.setData(patch);
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
      () => this.scheduleScrollToBottom(true)
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
      if (!this.data.shouldAutoScroll || this.data.showJumpToBottom) {
        this.setData({
          shouldAutoScroll: true,
          showJumpToBottom: false,
          unreadCount: 0,
        });
      }
      return;
    }

    if (this.data.shouldAutoScroll) {
      this.setData({ shouldAutoScroll: false });
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
      return String(message.content);
    }
    if (Array.isArray(message.parts) && message.parts.length > 0) {
      let s = "";
      message.parts.forEach((p) => {
        if (p && p.type === "text" && p.text) s += String(p.text);
      });
      return s;
    }
    return "";
  },

  // 处理消息内容，返回结构化部分
  processMessageContent(message) {
    let parts = [];
    const toRichTextNodes = (text) => {
      return this.formatTextToRichHtml(text);
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
      message.parts.forEach((p) => {
        if (p.type === "text") {
          parts.push({ type: "text", content: toRichTextNodes(p.text) });
        } else if (p.type === "file") {
          const fileUrl = `${SERVER_URL}${p.file.uri}`;
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
    } else if (message.content) {
      parts.push({ type: "text", content: toRichTextNodes(message.content) });
    }

    if ((!parts || parts.length === 0) && message.files) {
      parts = parseFilesToParts(message.files);
    } else if (message.files) {
      parts = [...parts, ...parseFilesToParts(message.files)];
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
      if (r === "ai" || r === "assistant" || r === "model") return "assistant";
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
          const answerText = String(item.answer || "");
          const isLong = this.isLongAssistantText(answerText);
          result.push({
            id: item.id
              ? `${item.id}_a`
              : item.consultation_id
              ? `${item.consultation_id}_a_${index}`
              : `history_${index}_a`,
            role: "assistant",
            contentParts: [
              { type: "text", content: toRichTextNodes(item.answer) },
            ],
            rawText: answerText,
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
        isLong,
        collapsed: isLong,
        timestamp: baseTime,
        timeString: this.formatTime(baseTime),
      });
    });
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
      if (
        ["consultation", "medication", "summary", "health_records"].includes(
          this.data.agentType
        )
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
          } else if (Array.isArray(dbResponse)) {
            // Fallback if API returns array directly
            messages = dbResponse;
          }

          if (!messages || messages.length === 0) {
            console.log(
              "DB history empty, falling back to conversation memory..."
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
          this.data.agentType
        )
      ) {
        try {
          console.log(
            "History still empty, trying consultation history for:",
            conversationId
          );
          const historyList = await getConsultationHistory(0, 50);
          if (Array.isArray(historyList)) {
            const target = historyList.find(
              (item) =>
                item.consultation_id === conversationId ||
                item.id === conversationId
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
        console.log("Sorted formatted messages:", formattedMessages);

        const currentIds = new Set(this.data.messages.map((m) => m.id));
        const mergedMessages = [];
        formattedMessages.forEach((m) => {
          if (!currentIds.has(m.id)) {
            mergedMessages.push(m);
          }
        });

        const finalMessages =
          this.data.messages.length > 0
            ? [...this.data.messages, ...mergedMessages]
            : formattedMessages;

        console.log("Final messages to render:", finalMessages);

        this.setData(
          {
            messages: finalMessages,
            shouldAutoScroll: true,
            showJumpToBottom: false,
            unreadCount: 0,
          },
          () => this.scheduleScrollToBottom(true)
        );
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
    });

    // 查找对应 Agent 的 URL
    if (targetAgentName) {
      try {
        const agents = await listRemoteAgents();
        let target = agents.find(
          (a) => a.name === targetAgentName || a.name.includes(targetAgentName)
        );

        if (!target) {
          // 尝试不区分大小写匹配
          target = agents.find(
            (a) =>
              a.name.toLowerCase() === targetAgentName.toLowerCase() ||
              a.name.toLowerCase().includes(targetAgentName.toLowerCase())
          );
        }

        if (target && (target.url || target.base_url)) {
          const rawUrl = target.url || target.base_url;
          const resolvedUrl = resolveAgentUrl(rawUrl);

          // Temporary fix: Force Host API routing for Health Advisor to avoid direct connection issues
          if (targetAgentName === "健康顾问") {
            console.log("Using Host API for Health Advisor");
            this.setData({ agentUrl: "" });
          } else {
            this.setData({ agentUrl: resolvedUrl });
          }

          console.log(
            "Agent URL resolved:",
            resolvedUrl,
            "Final agentUrl:",
            this.data.agentUrl
          );
        } else {
          // Fallback: 手动映射如果已知 agent
          const svcMap = {
            健康顾问: "10011",
            健康档案管理员: "10010",
            用药提醒助手: "10012",
            就诊摘要生成器: "10013",
          };
          if (svcMap[targetAgentName]) {
            const fallbackUrl = `http://127.0.0.1:${svcMap[targetAgentName]}`;
            this.setData({ agentUrl: fallbackUrl });
            console.log(
              `Fallback resolved ${targetAgentName} to ${fallbackUrl}`
            );
          }
        }
      } catch (e) {
        console.warn("Failed to list remote agents:", e);
        // Fallback on error too
        const svcMap = {
          健康顾问: "10011",
          健康档案管理员: "10010",
          用药提醒助手: "10012",
          就诊摘要生成器: "10013",
        };
        if (svcMap[targetAgentName]) {
          const fallbackUrl = `http://127.0.0.1:${svcMap[targetAgentName]}`;
          this.setData({ agentUrl: fallbackUrl });
        }
      }
    }
  },

  /**
   * Lifecycle function--Called when page show
   */
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
    if (this.scrollTimer) {
      clearTimeout(this.scrollTimer);
      this.scrollTimer = null;
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
      }
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
    const messages = this.data.messages;
    const msg = messages[index];
    if (msg) {
      msg.showThinking = !msg.showThinking;
      this.setData({
        messages: messages,
      });
    }
  },

  async sendMessage() {
    const text = this.data.inputText.trim();
    if (!text || this.data.isSending) return;

    const userMessage = {
      id: `user_${Date.now()}`,
      role: "user",
      contentParts: [
        { type: "text", content: this.formatTextToRichHtml(text) },
      ],
      rawText: text,
      isLong: false,
      collapsed: false,
      timestamp: Date.now() / 1000,
      timeString: this.formatTime(Date.now() / 1000),
    };

    this.setData({
      messages: [...this.data.messages, userMessage],
      inputText: "",
      isSending: true,
      shouldAutoScroll: true,
      showJumpToBottom: false,
      unreadCount: 0,
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

      // 同步到咨询历史（如果是新对话且属于咨询类）
      if (
        !this.data.isHistorySynced &&
        ["consultation", "medication", "summary", "health_records"].includes(
          this.data.agentType
        )
      ) {
        try {
          await createConsultation({
            question: text,
            consultation_id: convId,
            session_id: convId,
            tags: [this.data.agentType],
          });
          console.log("Consultation history synced");
          this.setData({ isHistorySynced: true });
        } catch (err) {
          console.error("Failed to sync consultation history:", err);
          // 如果创建咨询记录失败，可能后续保存消息也会有问题，但我们尽量继续
        }
      }

      // 如果有 agentUrl，使用流式模式 (Emulating React)
      if (this.data.agentUrl) {
        // 保存用户消息到数据库
        try {
          console.log("Saving user message to DB...", { convId, text });
          await saveConsultationMessage({
            consultation_id: convId,
            role: "user",
            content: text,
          });
          console.log("User message saved to DB");
        } catch (e) {
          console.warn("Failed to save user message to DB:", e);
        }

        // 添加 AI 思考中消息
        const aiMsgId = `ai_${Date.now()}`;
        const aiMessage = {
          id: aiMsgId,
          role: "assistant", // or "ai"
          contentParts: [
            { type: "text", content: this.formatTextToRichHtml("...") },
          ],
          rawText: "",
          isLong: false,
          collapsed: false,
          timestamp: Date.now() / 1000,
          timeString: this.formatTime(Date.now() / 1000),
          isStreaming: true,
        };

        this.setData({
          messages: [...this.data.messages, aiMessage],
          shouldAutoScroll: true,
          showJumpToBottom: false,
          unreadCount: 0,
        });
        this.scheduleScrollToBottom(true);

        this.streamingContent = "";
        this.currentStreamingId = aiMsgId;

        // 发送流式请求
        const payload = {
          id: this.generateUUID(),
          sessionId: convId,
          message: {
            role: "user",
            parts: [{ type: "text", text: text }],
          },
        };

        this.requestTask = sendTaskStreaming(
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
                const updatedMessages = this.data.messages.map((m) => {
                  if (m.id === this.currentStreamingId) {
                    return {
                      ...m,
                      thinking: (m.thinking || "") + thinkingText,
                    };
                  }
                  return m;
                });
                this.setData({ messages: updatedMessages }, () =>
                  this.scheduleScrollToBottom(false, 0)
                );
              }
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
                const lastChunk = artifact.lastChunk;

                if (!appendFlag) {
                  this.streamingContent = artifactText;
                } else {
                  if (
                    lastChunk &&
                    this.streamingContent &&
                    artifactText.startsWith(this.streamingContent)
                  ) {
                    this.streamingContent = artifactText;
                  } else if (
                    this.streamingContent &&
                    artifactText &&
                    this.streamingContent.endsWith(artifactText)
                  ) {
                    // ignore duplicate delta
                  } else {
                    this.streamingContent += artifactText;
                  }
                }
                shouldUpdateContent = true;
              }
            } else if (msgParts) {
              let newText = "";
              msgParts.forEach((p) => {
                if (p.type === "text" && p.text) newText += p.text;
              });
              if (newText) {
                if (!this.streamingContent.endsWith(newText)) {
                  this.streamingContent += newText;
                }
                shouldUpdateContent = true;
              }
            }

            if (shouldUpdateContent) {
              const updatedMessages = this.data.messages.map((m) => {
                if (m.id === this.currentStreamingId) {
                  const isLong = this.isLongAssistantText(
                    this.streamingContent
                  );
                  return {
                    ...m,
                    contentParts: [
                      {
                        type: "text",
                        content: this.formatTextToRichHtml(
                          this.streamingContent
                        ),
                      },
                    ],
                    rawText: this.streamingContent,
                    isLong,
                    collapsed: false,
                  };
                }
                return m;
              });
              this.setData({ messages: updatedMessages }, () =>
                this.scheduleScrollToBottom(false, 0)
              );
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
                const finalText = this.streamingContent || "抱歉，出错了。";
                const isLong = this.isLongAssistantText(finalText);
                return {
                  ...m,
                  contentParts: [
                    {
                      type: "text",
                      content: this.formatTextToRichHtml(finalText),
                    },
                  ],
                  rawText: finalText,
                  isLong,
                  collapsed: isLong,
                  isStreaming: false,
                };
              }
              return m;
            });
            this.setData({ messages: updatedMessages, isSending: false }, () =>
              this.scheduleScrollToBottom(false, 0)
            );
          },
          () => {
            // onComplete
            this.handleStreamingComplete(convId);
          }
        );
      } else {
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

        const sendResult = await sendMessage({
          conversation_id: convId,
          role: "user",
          message: text,
          metadata: selectedAgent ? { selected_agent: selectedAgent } : {},
        });

        if (sendResult && sendResult.message_id) {
          const updatedMessages = this.data.messages.map((m) => {
            if (m.id === userMessage.id) {
              return { ...m, id: sendResult.message_id };
            }
            return m;
          });
          this.setData({
            messages: updatedMessages,
            shouldAutoScroll: true,
            showJumpToBottom: false,
            unreadCount: 0,
          });
          this.scheduleScrollToBottom(true);
        }

        // 3. 开始轮询回复
        this.startPolling();
      }
    } catch (error) {
      console.error("Send message failed:", error);
      wx.showToast({
        title: "发送失败",
        icon: "none",
      });
      this.setData({ isSending: false });
    }
  },

  async handleStreamingComplete(convId) {
    if (!this.currentStreamingId) return;

    // 标记完成
    const finalText = this.streamingContent || "";
    const isLong = this.isLongAssistantText(finalText);
    const updatedMessages = this.data.messages.map((m) => {
      if (m.id === this.currentStreamingId) {
        return {
          ...m,
          isStreaming: false,
          rawText: finalText,
          isLong,
          collapsed: isLong,
          contentParts: finalText
            ? [{ type: "text", content: this.formatTextToRichHtml(finalText) }]
            : m.contentParts,
        };
      }
      return m;
    });
    this.setData({ messages: updatedMessages, isSending: false }, () =>
      this.scheduleScrollToBottom()
    );

    // 保存 AI 消息到数据库
    if (this.streamingContent) {
      try {
        console.log("Saving AI message to DB...", {
          convId,
          content: this.streamingContent,
        });
        await saveConsultationMessage({
          consultation_id: convId,
          role: "assistant", // or "ai"
          content: this.streamingContent,
        });
        console.log("AI message saved to DB");
      } catch (e) {
        console.warn("Failed to save AI message to DB:", e);
      }
    }

    this.currentStreamingId = null;
    this.requestTask = null;
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
        // 转换消息格式
        const formattedMessages = messages.map((m) => {
          const id =
            m.id ||
            (m.metadata && m.metadata.message_id) ||
            `msg-${Date.now()}-${Math.random()}`;
          const role = m.role;
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
            timestamp: this.parseTimestampSeconds(m.created_at || m.createdAt),
            timeString: this.formatTime(
              this.parseTimestampSeconds(m.created_at || m.createdAt)
            ),
          };
        });

        // 合并消息，去重
        const currentIds = new Set(this.data.messages.map((m) => m.id));
        const newMessages = formattedMessages.filter(
          (m) => !currentIds.has(m.id)
        );

        if (newMessages.length > 0) {
          this.setData(
            {
              messages: [...this.data.messages, ...newMessages],
              isSending: false, // 收到新消息认为发送/回复完成
            },
            () => this.scheduleScrollToBottom(false, newMessages.length)
          );
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
