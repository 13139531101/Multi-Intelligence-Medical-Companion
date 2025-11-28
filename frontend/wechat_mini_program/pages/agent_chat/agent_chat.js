// pages/agent_chat/agent_chat.js
import {
  sendMessage,
  createConversation,
  listMessages,
  getProcessingMessages,
  queryEvents,
  sendTaskStreaming,
  listRemoteAgents,
  getAgentCard,
} from "../../utils/api";

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
    isSending: false, // 确保初始状态为false，防止页面加载时就处于发送状态
    mode: "default", // default, summary, consultation
    agentUrl: "",
    sessionId: "",
  },

  // 在页面实例上维护已处理的事件ID集合（微信小程序data不支持Set类型）
  processedEventIds: new Set(),
  // 维护流式请求任务
  requestTask: null,

  /**
   * Lifecycle function--Called when page load
   */
  async onLoad(options) {
    const mode = options.mode || "default";
    let agentUrl = options.agentUrl || "";

    this.setData({
      mode,
      agentUrl,
      sessionId: this.generateUUID(),
    });

    if (mode === "summary") {
      wx.setNavigationBarTitle({ title: "就诊摘要助手" });

      // 如果没有提供 agentUrl，尝试自动查找
      if (!agentUrl) {
        try {
          const agents = await listRemoteAgents();
          let targetAgent = agents.find(
            (a) =>
              (a.url && a.url.includes("10013")) ||
              (a.name && a.name.includes("summary")) ||
              (a.name && a.name.includes("摘要"))
          );
          if (targetAgent) {
            agentUrl = targetAgent.url || targetAgent.address || "";
            this.setData({ agentUrl });
            console.log("Found summary agent:", agentUrl);
          } else {
            // Fallback default
            agentUrl = "http://localhost:10013";
            this.setData({ agentUrl });
          }
        } catch (e) {
          console.error("查找智能体失败:", e);
          // Fallback
          agentUrl = "http://localhost:10013";
          this.setData({ agentUrl });
        }
      }

      // Initial greeting for summary mode
      this.setData({
        messages: [
          {
            id: "system_welcome",
            role: "assistant",
            content:
              '您好！我是您的就诊摘要助手。您可以直接告诉我您的需求，例如："生成最近3个月的就诊摘要" 或 "总结上次在市一医院的检查结果"。',
            timestamp: Date.now() / 1000,
            timeString: this.formatTime(Date.now() / 1000),
          },
        ],
      });
    } else if (mode === "consultation") {
      wx.setNavigationBarTitle({ title: "健康顾问" });

      // 如果没有提供 agentUrl，尝试自动查找健康顾问
      if (!agentUrl) {
        try {
          const agents = await listRemoteAgents();
          let targetAgent = agents.find(
            (a) =>
              (a.url && a.url.includes("10011")) ||
              (a.name && a.name.includes("health")) ||
              (a.name && a.name.includes("顾问"))
          );
          if (targetAgent) {
            agentUrl = targetAgent.url || targetAgent.address || "";
            this.setData({ agentUrl });
            console.log("Found health advisor agent:", agentUrl);
          } else {
            // Fallback default
            agentUrl = "http://localhost:10011";
            this.setData({ agentUrl });
          }
        } catch (e) {
          console.error("查找智能体失败:", e);
          // Fallback
          agentUrl = "http://localhost:10011";
          this.setData({ agentUrl });
        }
      }

      // Initial greeting for consultation mode
      this.setData({
        messages: [
          {
            id: "system_welcome",
            role: "assistant",
            content:
              "您好！我是您的健康顾问。您可以咨询任何健康问题，我会为您提供初步的建议和指导。",
            timestamp: Date.now() / 1000,
            timeString: this.formatTime(Date.now() / 1000),
          },
        ],
      });
    } else {
      try {
        const conv = await createConversation();
        console.log("Conversation created:", conv);
        const conversationId = conv.conversation_id;
        this.setData({ conversationId: conversationId });
        const rawMessages = await listMessages(conversationId);
        this.setData({ messages: this.formatMessages(rawMessages) });
      } catch (error) {
        console.error("Failed to start conversation", error);
        wx.showToast({ title: "无法开始对话", icon: "error" });
      }
    }
  },

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

  /**
   * Lifecycle function--Called when page is initially rendered
   */
  onReady() {},

  /**
   * Lifecycle function--Called when page show
   */
  onShow() {},

  /**
   * Lifecycle function--Called when page hide
   */
  onHide() {},

  /**
   * Lifecycle function--Called when page unload
   */
  handleInput(e) {
    this.setData({ inputText: e.detail.value });
    console.log("Input changed:", e.detail.value);
  },

  // 调试状态
  debugState() {
    const state = {
      inputText: this.data.inputText,
      inputLength: this.data.inputText.length,
      trimmed: this.data.inputText.trim(),
      trimmedLength: this.data.inputText.trim().length,
      isSending: this.data.isSending,
      isPolling: this.data.isPolling,
      shouldDisable: !this.data.inputText.trim() || this.data.isSending,
    };
    console.log("Current state:", state);
    wx.showModal({
      title: "当前状态",
      content: `输入文本: "${state.inputText}"\n去空格后: "${state.trimmed}"\n长度: ${state.trimmedLength}\nisSending: ${state.isSending}\nisPolling: ${state.isPolling}\n按钮应该禁用: ${state.shouldDisable}`,
      showCancel: false,
    });
  },

  // 重置状态
  resetState() {
    this.setData({
      messages: [],
      conversationId: null,
      isPolling: false,
      isSending: false,
    });
    // 重置已处理事件ID集合
    this.processedEventIds = new Set();
    console.log("状态已重置");
  },

  // 强制发送方法（无disabled检查）
  async handleSendForce() {
    console.log("=== 强制发送方法调用 ===");
    const content = this.data.inputText.trim();
    console.log("输入内容:", content);
    console.log("当前状态:", {
      isSending: this.data.isSending,
      isPolling: this.data.isPolling,
    });

    if (!content) {
      wx.showToast({
        title: "请输入消息内容",
        icon: "none",
      });
      return;
    }

    try {
      // 直接调用发送逻辑，不检查isSending状态
      await this.performSend(content);
      console.log("强制发送完成");
    } catch (error) {
      console.error("强制发送出错:", error);
    }
  },

  // 执行发送的核心逻辑
  async performSend(messageContent) {
    // 添加弹窗确认方法被调用
    wx.showToast({
      title: "performSend被调用",
      icon: "success",
      duration: 2000,
    });

    console.log("🚀🚀🚀 performSend 方法被调用 🚀🚀🚀");
    console.log("=== performSend 开始执行 ===");
    console.log("消息内容:", messageContent);
    console.log("模式:", this.data.mode);

    const timestamp = Date.now() / 1000;

    const userMessage = {
      role: "user",
      content: messageContent,
      timestamp: timestamp,
      timeString: this.formatTime(timestamp),
      dupCount: 1,
    };

    this.setData({
      messages: [...this.data.messages, userMessage],
      inputText: "",
      isSending: true,
    });

    // 滚动到底部显示新消息
    this.scrollToBottom();

    // Handle Summary and Consultation Mode
    if (this.data.mode === "summary" || this.data.mode === "consultation") {
      console.log("进入智能体直连模式发送逻辑");
      if (!this.data.agentUrl) {
        wx.showToast({ title: "无法连接到智能体", icon: "none" });
        this.setData({ isSending: false });
        return;
      }

      // Add assistant placeholder
      const agentMsgId = `ai_${Date.now()}`;
      const agentMessage = {
        id: agentMsgId,
        role: "assistant",
        content: "",
        thinking: "",
        showThinking: false,
        timestamp: Date.now() / 1000,
        timeString: this.formatTime(Date.now() / 1000),
        isStreaming: true,
      };

      this.setData({
        messages: [...this.data.messages, agentMessage],
      });
      this.scrollToBottom();

      const payload = {
        session_id: this.data.sessionId,
        messages: [
          { role: "user", content: { type: "text", text: messageContent } },
        ],
      };

      try {
        this.requestTask = sendTaskStreaming(
          this.data.agentUrl,
          payload,
          (event) => {
            // onMessage
            if (event?.result?.delta) {
              const messages = this.data.messages;
              const msgIndex = messages.findIndex((m) => m.id === agentMsgId);
              if (msgIndex !== -1) {
                const updatedMsg = messages[msgIndex];
                updatedMsg.content += event.result.delta;
                updatedMsg.formattedContent = this.formatMarkdown(
                  updatedMsg.content
                );

                this.setData({
                  [`messages[${msgIndex}]`]: updatedMsg,
                });
                // 滚动到底部
                this.scrollToBottom();
              }
            }

            const statusParts = event?.result?.status?.message?.parts || [];
            if (statusParts.length) {
              const thinkingText = statusParts
                .filter((p) => p?.type === "text" && p.text)
                .map((p) => p.text)
                .join("");
              if (thinkingText) {
                const messages = this.data.messages;
                const msgIndex = messages.findIndex((m) => m.id === agentMsgId);
                if (msgIndex !== -1) {
                  const updatedMsg = messages[msgIndex];
                  updatedMsg.thinking = (updatedMsg.thinking || "") + thinkingText;
                  this.setData({ [`messages[${msgIndex}]`]: updatedMsg });
                }
              }
            }

            if (event?.result?.status === "completed" || event?.result?.final) {
              this.setData({ isSending: false });
            }
          },
          (error) => {
            // onError
            console.error("Streaming error:", error);
            this.setData({ isSending: false });
            wx.showToast({ title: "生成摘要失败", icon: "none" });
          },
          () => {
            // onComplete
            this.setData({ isSending: false });
          }
        );
      } catch (error) {
        console.error("Send message failed:", error);
        this.setData({ isSending: false });
      }
      return;
    }

    try {
      console.log("准备发送消息到API...");
      const response = await sendMessage({
        conversation_id: this.data.conversationId,
        message: messageContent,
        role: "user",
      });
      console.log("API响应:", response);

      // 从发送响应中获取message_id用于跟踪
      const trackedMessageId =
        response?.metadata?.message_id || `msg_${Date.now()}`;
      console.log("开始轮询消息, trackedMessageId:", trackedMessageId);
      this.pollForMessages(trackedMessageId);
    } catch (error) {
      console.error("发送消息失败 - 详细错误:", error);
      console.error("错误类型:", typeof error);
      console.error("错误信息:", error.message || error.errMsg || "未知错误");

      let errorMsg = "发送失败，请重试";
      if (error.errMsg) {
        if (error.errMsg.includes("request:fail")) {
          errorMsg = "网络连接失败，请检查网络";
        } else if (error.errMsg.includes("timeout")) {
          errorMsg = "请求超时，请重试";
        }
      }

      wx.showToast({ title: errorMsg, icon: "error" });
      // 移除发送失败的消息
      this.setData({
        messages: this.data.messages.slice(0, -1),
        isSending: false,
      });
    }
  },

  toggleThinking(e) {
    const idx = e.currentTarget.dataset.index;
    const messages = this.data.messages;
    if (idx >= 0 && idx < messages.length) {
      const updated = messages[idx];
      updated.showThinking = !updated.showThinking;
      this.setData({ [`messages[${idx}]`]: updated });
    }
  },

  async handleSend(e) {
    console.log(
      "发送按钮点击",
      "isSending:",
      this.data.isSending,
      "content:",
      this.data.inputText.trim().length
    );

    // 检查发送状态和内容
    if (this.data.isSending || !this.data.inputText.trim()) {
      wx.showToast({
        title: this.data.isSending ? "请等待当前消息发送" : "请输入内容",
        icon: "none",
      });
      return;
    }

    console.log("=== handleSend 方法被调用 ===");
    const content = this.data.inputText.trim();
    console.log("输入内容:", content);

    console.log("准备调用 performSend");
    try {
      // 使用统一的发送逻辑
      await this.performSend(content);
      console.log("performSend 调用完成");
    } catch (error) {
      console.error("handleSend 中捕获到错误:", error);
    }
  },

  // 轮询消息列表
  pollForMessages(trackedMessageId) {
    if (!this.data.conversationId || this.data.isPolling) {
      return;
    }

    // 开始新的轮询时，清理已处理的事件ID集合，避免重复过滤
    console.log(
      "开始新的轮询，清理processedEventIds，之前大小:",
      this.processedEventIds.size
    );
    this.processedEventIds.clear();

    this.setData({
      isPolling: true,
      isSending: true,
    });
    const maxPollingTime = 30000; // 30秒最大轮询时间，与React前端保持一致
    let pollingStartTime = Date.now(); // 改为let，允许重置

    const poll = () => {
      const elapsedTime = Date.now() - pollingStartTime;
      if (elapsedTime > maxPollingTime) {
        this.setData({
          isPolling: false,
          isSending: false,
        });
        wx.showToast({ title: "响应超时，请重试", icon: "none" });
        return;
      }

      // 注释掉每次轮询的清理，避免重复处理已处理的事件
      // this.processedEventIds.clear();
      // console.log('清理processedEventIds，开始新的轮询');

      // 检查消息处理状态
      let activeTrackedIdIsStillPending = false;

      Promise.all([
        getProcessingMessages(),
        queryEvents(this.data.conversationId),
      ])
        .then(([pendingResponse, eventsResponse]) => {
          console.log("pendingResponse:", pendingResponse);
          console.log(
            "eventsResponse length:",
            eventsResponse ? eventsResponse.length : 0
          );

          // 1. 检查是否还在处理中
          if (pendingResponse && trackedMessageId) {
            activeTrackedIdIsStillPending = pendingResponse.some((item) =>
              item.includes(trackedMessageId)
            );
          }

          console.log(
            `[${(elapsedTime / 1000).toFixed(
              1
            )}s] 轮询: Tracked ID ${trackedMessageId} 是否仍在处理中: ${activeTrackedIdIsStillPending}`
          );

          // 2. 处理事件响应
          let newMessages = []; // 将变量定义移到外层作用域
          if (eventsResponse) {
            const sortedEvents = [...eventsResponse].sort(
              (a, b) => a.timestamp - b.timestamp
            );

            console.log(`处理 ${sortedEvents.length} 个事件`);
            for (const event of sortedEvents) {
              console.log(
                "处理事件:",
                event.id,
                event.content?.role,
                event.content?.parts?.length
              );
              console.log(
                "事件会话ID:",
                event.content?.metadata?.conversation_id
              );
              console.log("当前会话ID:", this.data.conversationId);
              console.log(
                "ID是否已处理:",
                this.processedEventIds.has(event.id)
              );
              console.log(
                "会话ID匹配:",
                event.content?.metadata?.conversation_id ===
                  this.data.conversationId
              );
              console.log("事件ID存在:", !!event.id);

              const conversationMatches =
                event.content?.metadata?.conversation_id ===
                this.data.conversationId;
              const eventIdExists = !!event.id;
              const notProcessed = !this.processedEventIds.has(event.id);

              console.log(
                "条件检查 - 会话匹配:",
                conversationMatches,
                "事件ID存在:",
                eventIdExists,
                "未处理:",
                notProcessed
              );

              if (eventIdExists && conversationMatches && notProcessed) {
                this.processedEventIds.add(event.id);
                const formattedMessage = this.formatEventToMessage(event);
                console.log("格式化后的消息:", formattedMessage);
                if (formattedMessage && this.hasContent(formattedMessage)) {
                  console.log(
                    "添加消息到newMessages:",
                    formattedMessage.content
                  );
                  newMessages.push(formattedMessage);
                } else {
                  console.log("消息被过滤，原因: 无内容或格式化失败");
                }
              } else {
                console.log("事件被跳过，原因: ID重复或会话ID不匹配");
              }
            }

            if (newMessages.length > 0) {
              // 只有收到用户消息时才重置轮询计时器，收到assistant消息时不重置
              const hasUserMessage = newMessages.some(
                (msg) => msg.role === "user"
              );
              if (hasUserMessage) {
                pollingStartTime = Date.now();
                console.log(
                  `[${(elapsedTime / 1000).toFixed(
                    1
                  )}s] 收到用户消息，重置轮询计时器`
                );
              } else {
                console.log(
                  `[${(elapsedTime / 1000).toFixed(1)}s] 收到 ${
                    newMessages.length
                  } 条assistant消息`
                );
              }

              // 处理消息去重和合并
              this.setData({
                messages: this.mergeMessages(this.data.messages, newMessages),
              });
              this.scrollToBottom();
            }
          }

          // 3. 决定是否继续轮询 - 修复逻辑，确保收到AI回复后再停止
          console.log(
            `[${(elapsedTime / 1000).toFixed(
              1
            )}s] 轮询: Tracked ID ${trackedMessageId} 是否仍在处理中: ${activeTrackedIdIsStillPending}`
          );

          // 检查本次轮询是否收到了新的AI回复
          const hasNewAssistantReply = newMessages.some(
            (msg) =>
              msg.role === "assistant" && msg.content && msg.content.trim()
          );

          console.log(
            `[${(elapsedTime / 1000).toFixed(
              1
            )}s] 本次轮询收到新AI回复: ${hasNewAssistantReply}, 新消息数量: ${
              newMessages.length
            }`
          );

          // 停止条件：处理完成且本次轮询收到了AI回复
          if (!activeTrackedIdIsStillPending && hasNewAssistantReply) {
            console.log(
              `[${(elapsedTime / 1000).toFixed(
                1
              )}s] Tracked ID ${trackedMessageId} 已完成处理且收到新AI回复，停止轮询`
            );
            this.setData({
              isPolling: false,
              isSending: false,
            });
            return;
          }

          // 如果处理完成但本次轮询没有收到AI回复，继续轮询一小段时间
          if (!activeTrackedIdIsStillPending && !hasNewAssistantReply) {
            console.log(
              `[${(elapsedTime / 1000).toFixed(
                1
              )}s] 处理完成但本次轮询未收到AI回复，继续轮询等待回复`
            );
          }

          // 超时保护：30秒后强制停止
          if (elapsedTime > maxPollingTime) {
            console.log(
              `[${(elapsedTime / 1000).toFixed(1)}s] 轮询超时，停止轮询`
            );
            this.setData({
              isPolling: false,
              isSending: false,
            });
            return;
          }

          // 继续轮询
          if (this.data.isPolling && this.data.isSending) {
            setTimeout(poll, 500); // 每0.5秒轮询一次
          }
        })
        .catch((error) => {
          console.error("轮询消息失败:", error);
          if (this.data.isPolling && this.data.isSending) {
            setTimeout(poll, 2000); // 出错时降低轮询频率
          }
        });
    };

    poll();
  },

  // 将事件转换为消息格式
  formatEventToMessage(event) {
    if (!event || !event.content) {
      console.log("formatEventToMessage: 事件或内容为空", event);
      return null;
    }

    const content = event.content;
    const messageId = content.metadata?.message_id || "";
    const role = content.role || "assistant";
    const timestamp = event.timestamp || Date.now() / 1000;

    console.log("formatEventToMessage: 事件内容详情", {
      role: role,
      messageId: messageId,
      parts: content.parts,
      partsLength: content.parts?.length,
    });

    // 处理消息内容
    let text = "";
    if (content.parts && Array.isArray(content.parts)) {
      console.log("formatEventToMessage: 处理parts数组", content.parts);
      text = content.parts
        .filter((part) => {
          console.log(
            "formatEventToMessage: 检查part",
            part,
            "type:",
            part.type
          );
          return part.type === "text";
        })
        .map((part) => {
          console.log("formatEventToMessage: 提取text", part.text);
          return part.text;
        })
        .join("\n");
    }

    console.log("formatEventToMessage: 最终提取的文本", text);

    return {
      id: messageId,
      role: role,
      content: text,
      formattedContent: this.formatMarkdown(text),
      timestamp: timestamp,
      timeString: this.formatTime(timestamp),
      dupCount: 1,
    };
  },

  // 检查消息是否有内容
  hasContent(message) {
    return message && message.content && message.content.trim() !== "";
  },

  // 合并新消息，处理重复消息和assistant流式回复
  mergeMessages(currentMessages, newMessages) {
    let mergedMessages = [...currentMessages];
    console.log("合并消息前:", mergedMessages.length, "条消息");
    console.log("新消息数量:", newMessages.length);

    for (const newMsg of newMessages) {
      console.log("处理新消息:", newMsg.role, newMsg.content?.substring(0, 50));

      // 检查是否存在相同ID或相同内容的消息
      const existingMsgIndex = mergedMessages.findIndex((msg) => {
        // 优先检查消息ID
        if (msg.id && newMsg.id && msg.id === newMsg.id) {
          return true;
        }
        // 检查相同角色和内容的消息（考虑时间戳差异小于5秒的情况）
        if (
          msg.role === newMsg.role &&
          msg.content &&
          newMsg.content &&
          msg.content.trim() === newMsg.content.trim() &&
          Math.abs(msg.timestamp - newMsg.timestamp) < 5
        ) {
          return true;
        }
        return false;
      });

      if (existingMsgIndex !== -1) {
        // 如果找到重复消息，选择时间戳更新的消息
        const existingMsg = mergedMessages[existingMsgIndex];
        if (newMsg.timestamp >= existingMsg.timestamp) {
          console.log("替换重复消息:", newMsg.id || "无ID");
          mergedMessages[existingMsgIndex] = {
            ...newMsg,
            dupCount: 1,
          };
        } else {
          console.log("跳过较旧的重复消息");
        }
      } else {
        // 检查是否是流式回复的更新
        const lastMsg = mergedMessages[mergedMessages.length - 1];
        if (
          lastMsg &&
          newMsg.role === "assistant" &&
          lastMsg.role === "assistant" &&
          newMsg.content.length > lastMsg.content.length &&
          newMsg.content.includes(lastMsg.content) &&
          Math.abs(newMsg.timestamp - lastMsg.timestamp) < 10
        ) {
          // 如果新的assistant消息包含上一条assistant消息的内容且更长，说明是流式回复的更新
          console.log("更新流式回复");
          mergedMessages[mergedMessages.length - 1] = {
            ...newMsg,
            dupCount: 1,
          };
        } else {
          // 新消息，直接添加
          console.log("添加新消息到列表");
          mergedMessages.push({
            ...newMsg,
            dupCount: 1,
          });
        }
      }
    }

    console.log("合并消息后:", mergedMessages.length, "条消息");
    return mergedMessages;
  },

  // 格式化时间
  formatTime(timestamp) {
    const date = new Date(timestamp * 1000);
    const now = new Date();
    const diff = now - date;

    // 如果是今天
    if (diff < 24 * 60 * 60 * 1000 && date.getDate() === now.getDate()) {
      return date.toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
      });
    }

    // 如果是昨天
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.getDate() === yesterday.getDate()) {
      return (
        "昨天 " +
        date.toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
        })
      );
    }

    // 其他日期
    return date.toLocaleDateString("zh-CN", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  },

  // 简单的Markdown格式化（转换为rich-text支持的格式）
  formatMarkdown(text) {
    if (!text) return "";

    // 转义HTML特殊字符
    let formatted = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // 处理代码块
    formatted = formatted.replace(
      /```([\s\S]*?)```/g,
      '<div style="background:#f5f5f5;padding:10rpx;border-radius:8rpx;margin:10rpx 0;font-family:monospace;">$1</div>'
    );

    // 处理行内代码
    formatted = formatted.replace(
      /`([^`]+)`/g,
      '<span style="background:#f5f5f5;padding:2rpx 6rpx;border-radius:4rpx;font-family:monospace;">$1</span>'
    );

    // 处理粗体
    formatted = formatted.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

    // 处理斜体
    formatted = formatted.replace(/\*([^*]+)\*/g, "<em>$1</em>");

    // 处理换行
    formatted = formatted.replace(/\n/g, "<br/>");

    return formatted;
  },

  // 滚动到底部
  scrollToBottom() {
    // 使用scroll-view的scroll-into-view属性自动滚动到最新消息
    const messageCount = this.data.messages.length;
    if (messageCount > 0) {
      this.setData({
        scrollIntoView: `msg-${messageCount - 1}`,
      });
    }
  },

  formatMessages(messages) {
    if (!messages) return [];
    return messages.map((msg) => {
      let content = "";

      // 从parts中提取文本内容
      if (msg.parts && msg.parts.length > 0 && msg.parts[0].text) {
        content = msg.parts[0].text;
      } else if (msg.content) {
        content = msg.content;
      }

      return {
        ...msg,
        content: content,
        formattedContent: this.formatMarkdown(content),
        timeString: this.formatTime(msg.timestamp || Date.now() / 1000),
        dupCount: msg.dupCount || 1,
      };
    });
  },

  onUnload() {},

  /**
   * Page event handler function--Called when user drop down
   */
  onPullDownRefresh() {},

  /**
   * Called when page reach bottom
   */
  onReachBottom() {},

  /**
   * Called when user click on the top right corner to share
   */
  onShareAppMessage() {},
});
