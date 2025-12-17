// pages/visit-summary/visit-summary.js
const { request, SERVER_URL, uploadFile } = require("../../utils/api.js");

Page({
  data: {
    summaries: [],
    isLoading: false,
  },

  onLoad() {
    // Initial load handled by onShow
  },

  onShow() {
    this.loadSummaries();
  },

  async loadSummaries() {
    this.setData({ isLoading: true });
    try {
      // 调用后端API获取摘要列表
      const res = await request("/api/visit-summaries/history");

      if (res) {
        this.setData({
          summaries: res,
        });
      }
    } catch (err) {
      console.error("Failed to load summaries:", err);
      wx.showToast({
        title: "加载失败",
        icon: "none",
      });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  chooseImage() {
    const that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      success(res) {
        const tempFilePath = res.tempFiles[0].tempFilePath;
        that.uploadImage(tempFilePath);
      },
    });
  },

  async uploadImage(filePath) {
    const that = this;
    wx.showLoading({
      title: "识别整理中...",
      mask: true,
    });

    const userInfo = wx.getStorageSync("userInfo");

    try {
      const data = await uploadFile(
        filePath,
        "/api/visit-summaries/analyze-image",
        {
          user_id: userInfo.user_id || "",
        }
      );

      wx.hideLoading();
      wx.showToast({
        title: "整理完成",
        icon: "success",
      });
      // 刷新列表
      that.loadSummaries();
    } catch (err) {
      wx.hideLoading();
      console.error(err);
      // 401 is handled by uploadFile utility
      if (!err || err.statusCode !== 401) {
        wx.showToast({
          title: "上传失败",
          icon: "none",
        });
      }
    }
  },

  viewDetail(e) {
    const id = e.currentTarget.dataset.id;
    // TODO: 跳转到详情页，目前先打印
    console.log("View detail for:", id);
    wx.showModal({
      title: "提示",
      content: "详情页开发中，ID: " + id,
      showCancel: false,
    });
  },
});
