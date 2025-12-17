// register.js
const { checkApiStatus, register } = require("../../utils/api");

Page({
  data: {
    username: "",
    password: "",
    confirmPassword: "",
    email: "",
    phone: "",
    isLoading: false,
    apiStatus: "checking...",
  },

  onLoad() {
    this.checkApi();
  },

  async checkApi() {
    const status = await checkApiStatus();
    this.setData({ apiStatus: status ? "Connected" : "Disconnected" });
  },

  // 输入用户名
  onUsernameInput(e) {
    this.setData({
      username: e.detail.value,
    });
  },

  // 输入密码
  onPasswordInput(e) {
    this.setData({
      password: e.detail.value,
    });
  },

  // 确认密码
  onConfirmPasswordInput(e) {
    this.setData({
      confirmPassword: e.detail.value,
    });
  },

  // 输入邮箱
  onEmailInput(e) {
    this.setData({
      email: e.detail.value,
    });
  },

  // 输入手机号
  onPhoneInput(e) {
    this.setData({
      phone: e.detail.value,
    });
  },

  // 验证输入
  validateInput() {
    const { username, password, confirmPassword, email, phone } = this.data;

    if (!username || username.length < 3) {
      wx.showToast({
        title: "用户名至少3个字符",
        icon: "none",
      });
      return false;
    }

    if (!password || password.length < 6) {
      wx.showToast({
        title: "密码至少6个字符",
        icon: "none",
      });
      return false;
    }

    if (password !== confirmPassword) {
      wx.showToast({
        title: "两次密码输入不一致",
        icon: "none",
      });
      return false;
    }

    if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      wx.showToast({
        title: "请输入有效的邮箱地址",
        icon: "none",
      });
      return false;
    }

    if (!phone || !/^1[3-9]\d{9}$/.test(phone)) {
      wx.showToast({
        title: "请输入有效的手机号",
        icon: "none",
      });
      return false;
    }

    return true;
  },

  // 注册
  async onRegister() {
    if (!this.validateInput()) {
      return;
    }

    const { username, password, email, phone } = this.data;
    this.setData({ isLoading: true });

    try {
      const response = await register(username, password, email, phone);

      // API返回200状态码和token数据表示注册成功
      if (response && response.access_token) {
        wx.showToast({
          title: "注册成功",
          icon: "success",
        });

        // 注册成功后跳转到登录页面
        setTimeout(() => {
          wx.navigateBack();
        }, 1500);
      } else {
        wx.showToast({
          title: "注册失败，请重试",
          icon: "none",
        });
      }
    } catch (error) {
      console.error("注册请求失败:", error);
      
      // 处理API返回的错误信息
      let errorMessage = "网络错误，请重试";
      if (error.data && error.data.detail) {
        errorMessage = error.data.detail;
      } else if (error.statusCode === 400) {
        errorMessage = "注册信息有误，请检查后重试";
      }
      
      wx.showToast({
        title: errorMessage,
        icon: "none",
      });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  // 返回登录页面
  goToLogin() {
    wx.navigateBack();
  },
});
