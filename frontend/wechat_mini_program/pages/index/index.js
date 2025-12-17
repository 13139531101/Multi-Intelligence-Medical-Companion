// index.js
const { checkApiStatus, request } = require("../../utils/api");
// 获取应用实例
const app = getApp();

Page({
  data: {
    motto: "智能健康助手",
    isLoggedIn: false,
    loginUserInfo: null,
    apiStatus: "checking...",
    // 功能模块数据统计
    healthRecordsCount: 0,
    medicationCount: 0,
    summaryCount: 0,
    // 最近活动数据
    recentActivities: [],
  },

  onLoad() {
    this.checkApi();
    this.checkLoginStatus();
  },

  onShow() {
    // 每次显示页面时刷新数据
    if (this.data.isLoggedIn) {
      this.loadDashboardData();
      // 更新 TabBar 选中状态
      if (typeof this.getTabBar === "function" && this.getTabBar()) {
        this.getTabBar().setData({
          selected: 0,
        });
      }
    }
  },

  // 检查登录状态
  checkLoginStatus() {
    const loginUserInfo = wx.getStorageSync("userInfo");
    if (loginUserInfo && loginUserInfo.token) {
      this.setData({
        isLoggedIn: true,
        loginUserInfo: loginUserInfo,
      });
      this.loadDashboardData();
    } else {
      // 未登录，跳转到登录页面
      wx.redirectTo({
        url: "/pages/login/login",
      });
    }
  },

  async checkApi() {
    const status = await checkApiStatus();
    this.setData({ apiStatus: status ? "Connected" : "Disconnected" });
  },

  // 加载仪表板数据
  async loadDashboardData() {
    try {
      // 加载健康档案数量
      await this.loadHealthRecordsCount();
      // 加载用药记录数量
      await this.loadMedicationCount();
      // 加载就诊摘要数量
      await this.loadSummaryCount();
      // 加载最近活动
      await this.loadRecentActivities();
    } catch (error) {
      console.error("加载仪表板数据失败:", error);
    }
  },

  // 加载健康档案数量
  async loadHealthRecordsCount() {
    try {
      const response = await request("/api/health-records", {
        method: "GET",
        data: {
          limit: 1,
          skip: 0,
        },
      });
      if (response && response.records) {
        this.setData({
          healthRecordsCount: response.total || response.records.length,
        });
      }
    } catch (error) {
      console.error("加载健康档案数量失败:", error);
      this.setData({ healthRecordsCount: 0 });
    }
  },

  // 加载用药记录数量
  async loadMedicationCount() {
    try {
      const response = await request("/api/medications", {
        method: "GET",
      });
      if (response && Array.isArray(response)) {
        this.setData({
          medicationCount: response.length,
        });
      }
    } catch (error) {
      console.error("加载用药记录数量失败:", error);
      this.setData({ medicationCount: 0 });
    }
  },

  // 加载就诊摘要数量
  async loadSummaryCount() {
    // 模拟数据，实际应调用API
    this.setData({ summaryCount: 5 });
  },

  // 加载最近活动
  async loadRecentActivities() {
    // 模拟数据
    this.setData({
      recentActivities: [
        { id: 1, title: "新增健康档案", time: "今天 10:00", icon: "📋" },
        { id: 2, title: "完成每日服药", time: "今天 08:30", icon: "💊" },
      ],
    });
  },

  // 刷新数据
  refreshData() {
    this.loadDashboardData();
    this.checkApi();
  },

  // 跳转到健康咨询页面
  goToConsultation() {
    wx.navigateTo({
      url: "/pages/consultation/consultation",
    });
  },

  // 查看更多活动
  viewMoreActivities() {
    wx.showToast({
      title: "功能开发中",
      icon: "none",
    });
  },

  // 查看详细趋势
  viewDetailedTrends() {
    wx.showToast({
      title: "功能开发中",
      icon: "none",
    });
  },
});
