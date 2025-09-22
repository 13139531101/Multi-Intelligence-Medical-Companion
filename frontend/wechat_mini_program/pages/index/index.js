// index.js
import { checkApiStatus, uploadFile } from "../../utils/api";
// 获取应用实例
const app = getApp();

Page({
  data: {
    motto: "智能健康助手",
    userInfo: {},
    hasUserInfo: false,
    isLoggedIn: false,
    loginUserInfo: null,
    canIUse: wx.canIUse("button.open-type.getUserInfo"),
    canIUseGetUserProfile: false,
    canIUseOpenData:
      wx.canIUse("open-data.type.userAvatarUrl") &&
      wx.canIUse("open-data.type.userNickName"), // 如需尝试获取用户信息可改为false
    uploadedImage: "",
    apiStatus: "checking...",
  },
  // 事件处理函数
  bindViewTap() {
    wx.navigateTo({
      url: "../logs/logs",
    });
  },
  onLoad() {
    if (wx.getUserProfile) {
      this.setData({
        canIUseGetUserProfile: true,
      });
    }
    this.checkApi();
    this.checkLoginStatus();
  },

  // 检查登录状态
  checkLoginStatus() {
    const loginUserInfo = wx.getStorageSync("userInfo");
    if (loginUserInfo && loginUserInfo.token) {
      this.setData({
        isLoggedIn: true,
        loginUserInfo: loginUserInfo,
      });
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
  getUserProfile(e) {
    // 推荐使用wx.getUserProfile获取用户信息，开发者每次通过该接口获取用户个人信息均需用户确认，开发者妥善保管用户快速填写的头像昵称，避免重复弹窗
    wx.getUserProfile({
      desc: "展示用户信息", // 声明获取用户个人信息后的用途，后续会展示在弹窗中，请谨慎填写
      success: (res) => {
        console.log(res);
        this.setData({
          userInfo: res.userInfo,
          hasUserInfo: true,
        });
      },
    });
  },
  getUserInfo(e) {
    // 不推荐使用getUserInfo获取用户信息，预计自2021年4月13日起，getUserInfo将不再弹出弹窗，并直接返回匿名的用户个人信息
    console.log(e);
    this.setData({
      userInfo: e.detail.userInfo,
      hasUserInfo: true,
    });
  },

  uploadImage() {
    wx.chooseMedia({
      count: 1,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      success: async (res) => {
        const tempFilePath = res.tempFiles[0].tempFilePath;
        this.setData({
          uploadedImage: tempFilePath,
        });

        try {
          const result = await uploadFile(tempFilePath);
          console.log("Upload success", result);
          wx.showToast({
            title: "上传成功",
            icon: "success",
          });
        } catch (error) {
          console.error("Upload failed", error);
          wx.showToast({
            title: "上传失败",
            icon: "error",
          });
        }
      },
    });
  },

  previewImage() {
    wx.previewImage({
      current: this.data.uploadedImage, // 当前显示图片的http链接
      urls: [this.data.uploadedImage], // 需要预览的图片http链接列表
    });
  },

  goToAgentChat() {
    wx.navigateTo({
      url: "/pages/agent_chat/agent_chat",
    });
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
