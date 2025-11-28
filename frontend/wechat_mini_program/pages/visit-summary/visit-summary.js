import { getVisitSummaries, createVisitSummary } from "../../utils/api";

Page({
  data: {
    // 最近摘要
    recentSummaries: [],

    // 摘要分类
    categories: [
      { type: "outpatient", name: "门诊", icon: "🏥", count: 0 },
      { type: "emergency", name: "急诊", icon: "🚑", count: 0 },
      { type: "inpatient", name: "住院", icon: "🛏️", count: 0 },
      { type: "checkup", name: "体检", icon: "🔍", count: 0 },
      { type: "surgery", name: "手术", icon: "⚕️", count: 0 },
      { type: "followup", name: "复诊", icon: "📅", count: 0 },
    ],

    // 智能分析趋势
    trends: {
      visitFrequency: 60,
      visitCount: 8,
      healthIndex: 75,
      healthScore: 85,
      medicationAdherence: 90,
      adherenceRate: 92,
      summary: "您的健康状况总体良好，建议继续保持良好的生活习惯和按时用药。",
    },

    // 健康建议
    suggestions: [],

    // 弹窗状态
    showManualModal: false,

    // 新摘要表单
    newSummary: {
      type: "",
      typeIndex: 0,
      date: "",
      hospital: "",
      department: "",
      doctor: "",
      symptoms: "",
      diagnosis: "",
      treatment: "",
      medication: "",
      followUp: "",
    },

    // 选项数据
    visitTypes: ["门诊", "急诊", "住院", "体检", "手术", "复诊", "其他"],

    // 状态
    generating: false,
    loading: false,
  },

  onLoad() {
    this.loadData();
  },

  onShow() {
    this.loadRecentSummaries();
  },

  // 加载数据
  async loadData() {
    this.setData({ loading: true });

    try {
      await Promise.all([
        this.loadRecentSummaries(),
        this.loadCategories(),
        this.loadSuggestions(),
      ]);
    } catch (error) {
      console.error("加载数据失败:", error);
      wx.showToast({
        title: "加载失败",
        icon: "error",
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  // 加载最近摘要
  async loadRecentSummaries() {
    try {
      // 从API获取真实数据
      const summaries = await getVisitSummaries(0, 5); // 获取最近5条

      if (summaries && Array.isArray(summaries)) {
        const formattedSummaries = summaries.map((item) => {
          // 格式化日期
          const date =
            item.visit_date ||
            (item.created_at ? item.created_at.split("T")[0] : "");

          return {
            id: item.id,
            type: item.department || "门诊", // 优先显示科室，或者默认为门诊
            title: item.title || item.diagnosis || "就诊记录",
            hospital: item.hospital || "未知医院",
            date: date,
            summary:
              item.summary_content || item.chief_complaint || "暂无摘要内容",
            tags: [], // 后端目前没有tags字段
            status: "completed",
          };
        });

        if (formattedSummaries.length > 0) {
          this.setData({
            recentSummaries: formattedSummaries,
          });
        } else {
          // 如果没有数据，保持空或者显示空状态
          this.setData({
            recentSummaries: [],
          });
        }
      }
    } catch (error) {
      console.error("获取就诊摘要失败:", error);
      // 失败时不覆盖mock数据或者显示错误提示
      // 这里我们可以选择清空或者保留旧数据，暂时保持静默失败
    }
  },

  // 加载分类统计
  async loadCategories() {
    // 模拟API调用
    const categories = this.data.categories.map((cat) => ({
      ...cat,
      count: Math.floor(Math.random() * 10) + 1,
    }));

    this.setData({
      categories: categories,
    });
  },

  // 加载健康建议
  async loadSuggestions() {
    // 模拟API调用
    const mockSuggestions = [
      {
        id: 1,
        icon: "🏃",
        title: "增加运动量",
        description: "建议每周进行3-4次有氧运动，每次30分钟以上",
        priority: "high",
      },
      {
        id: 2,
        icon: "🥗",
        title: "调整饮食结构",
        description: "减少高盐高脂食物摄入，多吃蔬菜水果",
        priority: "medium",
      },
      {
        id: 3,
        icon: "💊",
        title: "按时服药",
        description: "严格按照医嘱服用降压药，不可随意停药",
        priority: "high",
      },
      {
        id: 4,
        icon: "😴",
        title: "改善睡眠质量",
        description: "保持规律作息，每天睡眠时间不少于7小时",
        priority: "medium",
      },
    ];

    this.setData({
      suggestions: mockSuggestions,
    });
  },

  // 对话生成（AI生成）
  chatToGenerate() {
    wx.navigateTo({
      url: "/pages/agent_chat/agent_chat?mode=summary",
    });
  },

  // 手工记录
  manualCreate() {
    this.setData({
      showManualModal: true,
      newSummary: {
        type: "",
        typeIndex: 0,
        date: "",
        hospital: "",
        department: "",
        doctor: "",
        symptoms: "",
        diagnosis: "",
        treatment: "",
        medication: "",
        followUp: "",
      },
    });
  },

  // 查看摘要详情
  viewSummaryDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/summary-detail/summary-detail?id=${id}`,
    });
  },

  // 查看全部摘要
  viewAllSummaries() {
    wx.navigateTo({
      url: "/pages/all-summaries/all-summaries",
    });
  },

  // 查看分类摘要
  viewCategorySummaries(e) {
    const type = e.currentTarget.dataset.type;
    wx.navigateTo({
      url: `/pages/category-summaries/category-summaries?type=${type}`,
    });
  },

  // 表单输入处理
  onInputChange(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;

    this.setData({
      [`newSummary.${field}`]: value,
    });
  },

  // 类型选择
  onTypeChange(e) {
    const index = e.detail.value;
    this.setData({
      "newSummary.typeIndex": index,
      "newSummary.type": this.data.visitTypes[index],
    });
  },

  // 日期选择
  onDateChange(e) {
    const date = e.detail.value;
    this.setData({
      "newSummary.date": date,
    });
  },

  // 生成摘要（手工提交）
  async generateSummary() {
    const summary = this.data.newSummary;

    // 验证必填字段
    if (
      !summary.type ||
      !summary.date ||
      !summary.hospital ||
      !summary.symptoms
    ) {
      wx.showToast({
        title: "请填写完整信息",
        icon: "none",
      });
      return;
    }

    this.setData({ generating: true });

    try {
      // 构造后端需要的 payload
      const payload = {
        title: `${summary.date} ${summary.hospital}就诊记录`,
        visit_date: summary.date,
        hospital: summary.hospital,
        department: summary.department,
        doctor: summary.doctor,
        symptoms: summary.symptoms,
        diagnosis: summary.diagnosis,
        treatment: summary.treatment,
        prescription: summary.medication, // 映射字段
        follow_up: summary.followUp, // 映射字段
        generated_by: "manual",
        summary_content: `主诉/症状: ${summary.symptoms}\n诊断: ${summary.diagnosis}\n治疗: ${summary.treatment}\n用药: ${summary.medication}`,
      };

      // 调用后端创建摘要接口
      await createVisitSummary(payload);

      wx.showToast({
        title: "保存成功",
        icon: "success",
      });

      this.setData({
        showManualModal: false,
        generating: false,
      });

      // 重新加载数据
      this.loadRecentSummaries();
    } catch (error) {
      console.error("生成摘要失败:", error);
      wx.showToast({
        title: "保存失败",
        icon: "error",
      });
      this.setData({ generating: false });
    }
  },

  closeManualModal() {
    this.setData({
      showManualModal: false,
    });
  },

  // 获取状态名称
  getStatusName(status) {
    const statusMap = {
      active: "进行中",
      completed: "已完成",
      pending: "待处理",
    };
    return statusMap[status] || status;
  },

  // 获取优先级名称
  getPriorityName(priority) {
    const priorityMap = {
      high: "重要",
      medium: "一般",
      low: "较低",
    };
    return priorityMap[priority] || priority;
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadData().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  // 分享功能
  onShareAppMessage() {
    return {
      title: "智能就诊摘要",
      path: "/pages/visit-summary/visit-summary",
    };
  },
});
