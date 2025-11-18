// index.js
import { checkApiStatus, request } from "../../utils/api";
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
      const response = await request("/api/health-records", "GET", null, {
        limit: 1,
        skip: 0
      });
      if (response && response.records) {
        this.setData({
          healthRecordsCount: response.total || response.records.length
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
      const response = await request("/api/medications", "GET");
      if (response && Array.isArray(response)) {
        this.setData({
          medicationCount: response.length
        });
      }
    } catch (error) {
      console.error("加载用药记录数量失败:", error);
      this.setData({ medicationCount: 0 });
    }
  },

  // 加载就诊摘要数量
  async loadSummaryCount() {
    try {
      const response = await request("/summaries", "GET");
      if (response && Array.isArray(response)) {
        this.setData({
          summaryCount: response.length
        });
      }
    } catch (error) {
      console.error("加载就诊摘要数量失败:", error);
      this.setData({ summaryCount: 0 });
    }
  },

  // 加载最近活动
  async loadRecentActivities() {
    try {
      const activities = [];
      
      // 获取最近的健康档案
      try {
        const healthRecords = await request("/api/health-records", "GET", null, {
          limit: 2,
          skip: 0
        });
        if (healthRecords && healthRecords.records) {
          healthRecords.records.forEach(record => {
            activities.push({
              id: `health_${record.id}`,
              icon: "📋",
              title: `上传了新的检查报告`,
              time: this.formatTime(record.created_at)
            });
          });
        }
      } catch (error) {
        console.log("获取健康档案活动失败:", error);
      }

      // 获取最近的用药记录
      try {
        const medications = await request("/api/medications", "GET");
        if (medications && Array.isArray(medications)) {
          medications.slice(0, 2).forEach(med => {
            activities.push({
              id: `med_${med.id}`,
              icon: "💊",
              title: `添加了用药规划`,
              time: this.formatTime(med.created_at)
            });
          });
        }
      } catch (error) {
        console.log("获取用药记录活动失败:", error);
      }

      // 获取最近的就诊摘要
      try {
        const summaries = await request("/summaries", "GET");
        if (summaries && Array.isArray(summaries)) {
          summaries.slice(0, 2).forEach(summary => {
            activities.push({
              id: `summary_${summary.id}`,
              icon: "📝",
              title: `完成了健康咨询`,
              time: this.formatTime(summary.created_at)
            });
          });
        }
      } catch (error) {
        console.log("获取就诊摘要活动失败:", error);
      }

      // 按时间排序并取前5个
      activities.sort((a, b) => new Date(b.time) - new Date(a.time));
      this.setData({
        recentActivities: activities.slice(0, 5)
      });
    } catch (error) {
      console.error("加载最近活动失败:", error);
      this.setData({ recentActivities: [] });
    }
  },

  // 格式化时间
  formatTime(dateString) {
    if (!dateString) return "刚刚";
    
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return "刚刚";
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`;
    
    return date.toLocaleDateString();
  },
  // 页面跳转函数
  // 跳转到健康档案页面
  goToHealthRecords() {
    wx.navigateTo({
      url: "/pages/health-records/health-records",
    });
  },

  // 跳转到健康咨询页面
  goToConsultation() {
    wx.navigateTo({
      url: "/pages/consultation/consultation",
    });
  },

  // 跳转到用药管理页面
  goToMedication() {
    wx.navigateTo({
      url: "/pages/medication/medication",
    });
  },

  // 跳转到就诊摘要页面
  goToSummary() {
    wx.navigateTo({
      url: "/pages/summary/summary",
    });
  },

  // 跳转到AI智能助手
  goToAIAssistant() {
    wx.navigateTo({
      url: "/pages/agent-chat/agent-chat",
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

  // 刷新数据
  async refreshData() {
    wx.showLoading({
      title: "刷新中...",
    });
    
    try {
      await this.loadDashboardData();
      wx.showToast({
        title: "刷新成功",
        icon: "success",
      });
    } catch (error) {
      console.error("刷新数据失败:", error);
      wx.showToast({
        title: "刷新失败",
        icon: "error",
      });
    } finally {
      wx.hideLoading();
    }
  },

  // 退出登录
  logout() {
    wx.showModal({
      title: "确认退出",
      content: "确定要退出登录吗？",
      success: (res) => {
        if (res.confirm) {
          // 清除本地存储的用户信息
          wx.removeStorageSync("userInfo");
          // 跳转到登录页面
          wx.redirectTo({
            url: "/pages/login/login",
          });
        }
      },
    });
  },
});
