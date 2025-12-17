// consultation.js
const {
  request,
  getConsultationHistory,
  deleteConsultation,
} = require("../../utils/api");

Page({
  data: {
    consultationHistory: [],
    loading: false,
    showTypeModal: false,
    showInputModal: false,
    showSidebar: false,
    inputContent: "",
    selectedType: "",

    consultationTypes: [
      {
        value: "symptom",
        name: "症状咨询",
        icon: "🤒",
        description: "描述您的症状，获取专业建议",
      },
      {
        value: "medication",
        name: "用药咨询",
        icon: "💊",
        description: "药物使用方法和注意事项",
      },
      {
        value: "health",
        name: "健康管理",
        icon: "💪",
        description: "日常健康管理和生活建议",
      },
      {
        value: "report",
        name: "报告解读",
        icon: "📊",
        description: "医疗检查报告专业解读",
      },
      {
        value: "nutrition",
        name: "营养咨询",
        icon: "🥗",
        description: "饮食营养搭配建议",
      },
      {
        value: "exercise",
        name: "运动指导",
        icon: "🏃",
        description: "运动健身计划制定",
      },
    ],
  },

  onLoad() {
    this.loadConsultationHistory();
  },

  onShow() {
    // 每次显示页面时刷新数据
    this.loadConsultationHistory();
  },

  // 加载咨询历史
  async loadConsultationHistory() {
    if (this.data.loading) return;

    this.setData({ loading: true });

    try {
      // 使用新的API helper
      console.log("Fetching consultation history...");
      const response = await getConsultationHistory(0, 10);
      console.log("Consultation history response:", response);

      if (response && Array.isArray(response)) {
        const formattedHistory = response.map((item) => {
          let tags = [];
          if (Array.isArray(item.tags)) {
            tags = item.tags;
          } else if (typeof item.tags === "string" && item.tags.trim()) {
            try {
              const parsed = JSON.parse(item.tags);
              tags = Array.isArray(parsed) ? parsed : [];
            } catch (e) {
              tags = [];
            }
          }

          const inferModeFromTags = (t) => {
            if (!Array.isArray(t) || t.length === 0) return "";
            if (t.includes("consultation")) return "consultation";
            if (t.includes("medication")) return "medication";
            if (t.includes("summary")) return "summary";
            if (t.includes("health_records")) return "health_records";
            return "";
          };

          const inferredMode =
            inferModeFromTags(tags) ||
            ([
              "consultation",
              "medication",
              "summary",
              "health_records",
            ].includes(item.consultation_type)
              ? item.consultation_type
              : "");

          // 解析类型
          let type = "health";
          if (tags.length > 0) {
            const tag = tags[0];
            if (tag === "consultation") type = "symptom";
            else if (tag === "summary") type = "report";
            else if (tag === "health_records") type = "health";
            else type = tag;
          } else if (item.consultation_type) {
            type = item.consultation_type;
          }

          const agentMode =
            inferredMode ||
            (type === "symptom"
              ? "consultation"
              : type === "report"
              ? "summary"
              : type === "medication"
              ? "medication"
              : type === "health"
              ? "default"
              : "consultation");

          return {
            ...item,
            tags,
            consultation_type: type, // Ensure it's available for navigation
            agent_mode: agentMode,
            formatted_date: this.formatDate(item.created_at),
            type_name: this.getTypeName(type),
            status_name: this.getStatusName(item.status || "completed"), // 默认为已完成
            preview:
              item.question ||
              (item.answer ? item.answer.substring(0, 50) : "无内容"),
            message_count: 2, // 问答对默认为2条消息
          };
        });

        this.setData({
          consultationHistory: formattedHistory,
        });
      }
    } catch (error) {
      console.error("加载咨询历史失败:", error);
      // 如果API失败，显示空状态而不是错误提示
      this.setData({
        consultationHistory: [],
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  // 开始咨询
  startConsultation(e) {
    const type = e.currentTarget.dataset.type;
    this.setData({
      selectedType: type,
      showInputModal: true,
      inputContent: "",
    });
  },

  // 处理输入
  handleInput(e) {
    this.setData({
      inputContent: e.detail.value,
    });
  },

  // 关闭输入弹窗
  closeInputModal() {
    this.setData({
      showInputModal: false,
      inputContent: "",
    });
  },

  // 提交咨询
  submitConsultation() {
    const { selectedType, inputContent } = this.data;
    if (!inputContent.trim()) {
      wx.showToast({
        title: "请输入咨询内容",
        icon: "none",
      });
      return;
    }

    this.navigateToChat(selectedType, inputContent);
    this.setData({
      showInputModal: false,
      inputContent: "",
    });
  },

  // 跳转到聊天页面
  navigateToChat(type, query) {
    // 根据类型选择对应的 agent
    let agentType = "default";
    switch (type) {
      case "symptom":
        agentType = "consultation";
        break;
      case "medication":
        agentType = "medication";
        break;
      case "health":
        agentType = "default";
        break;
      case "report":
        agentType = "summary";
        break;
      default:
        agentType = "default";
    }

    wx.navigateTo({
      url: `/pages/agent_chat/agent_chat?mode=${agentType}&type=${type}&query=${encodeURIComponent(
        query
      )}`,
    });
  },

  // 查看咨询详情
  viewConsultation(e) {
    const id = e.currentTarget.dataset.id;
    const type = e.currentTarget.dataset.type;
    const mode = e.currentTarget.dataset.mode;

    let agentType = mode || "default";
    if (!mode) {
      switch (type) {
        case "symptom":
          agentType = "consultation";
          break;
        case "medication":
          agentType = "medication";
          break;
        case "health":
          agentType = "default";
          break;
        case "report":
          agentType = "summary";
          break;
        default:
          agentType = "consultation";
      }
    }

    wx.navigateTo({
      url: `/pages/agent_chat/agent_chat?id=${id}&mode=${agentType}`,
    });
  },

  deleteHistoryConsultation(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;

    wx.showModal({
      title: "删除咨询",
      content: "确定要删除这条咨询历史吗？",
      confirmText: "删除",
      confirmColor: "#ff3b30",
      cancelText: "取消",
      success: async (res) => {
        if (!res.confirm) return;

        wx.showLoading({ title: "删除中..." });
        try {
          const result = await deleteConsultation(id);
          if (result && result.success === false) {
            throw new Error(result.message || "删除失败");
          }

          const next = (this.data.consultationHistory || []).filter(
            (item) =>
              item &&
              item.consultation_id !== id &&
              item.id !== id &&
              item.consultationId !== id
          );
          this.setData({ consultationHistory: next });

          wx.showToast({ title: "已删除", icon: "success" });
        } catch (err) {
          wx.showToast({
            title: err && err.message ? err.message : "删除失败",
            icon: "none",
          });
        } finally {
          wx.hideLoading();
        }
      },
    });
  },

  // 查看所有历史
  viewAllHistory() {
    // 可以跳转到专门的历史列表页，这里暂时只刷新
    this.loadConsultationHistory();
  },

  // 格式化日期
  formatDate(dateStr) {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(
      2,
      "0"
    )}-${String(date.getDate()).padStart(2, "0")}`;
  },

  // 获取类型名称
  getTypeName(type) {
    const typeMap = {
      symptom: "症状咨询",
      medication: "用药咨询",
      health: "健康管理",
      report: "报告解读",
      nutrition: "营养咨询",
      exercise: "运动指导",
    };
    return typeMap[type] || "健康咨询";
  },

  // 获取状态名称
  getStatusName(status) {
    const statusMap = {
      completed: "已完成",
      pending: "进行中",
      failed: "失败",
    };
    return statusMap[status] || status;
  },

  // 打开/关闭侧边栏
  toggleSidebar() {
    this.setData({ showSidebar: !this.data.showSidebar });
  },

  // 关闭侧边栏
  closeSidebar() {
    this.setData({ showSidebar: false });
  },

  // 跳转到咨询详情（历史记录）
  goToHistoryDetail(e) {
    const id = e.currentTarget.dataset.id;
    const type = e.currentTarget.dataset.type;
    const mode = e.currentTarget.dataset.mode;

    let agentType = mode || "default";
    if (!mode) {
      switch (type) {
        case "symptom":
          agentType = "consultation";
          break;
        case "medication":
          agentType = "medication";
          break;
        case "health":
          agentType = "default";
          break;
        case "report":
          agentType = "summary";
          break;
        default:
          agentType = "consultation";
      }
    }

    wx.navigateTo({
      url: `/pages/agent_chat/agent_chat?id=${id}&mode=${agentType}`,
    });
  },

  // 通用新建对话（默认健康咨询）
  startGeneralConsultation() {
    this.setData({
      selectedType: "health",
      showInputModal: true,
      inputContent: "",
    });
  },

  // 打开类型选择弹窗
  openTypeModal() {
    this.setData({ showTypeModal: true });
  },

  // 关闭类型选择弹窗
  closeTypeModal() {
    this.setData({ showTypeModal: false });
  },

  // 选择类型
  selectType(e) {
    const type = e.currentTarget.dataset.type;
    this.setData({
      selectedType: type,
      showTypeModal: false,
      showInputModal: true,
      inputContent: "",
    });
  },

  // 空函数，用于阻止冒泡
  noop() {},
});
