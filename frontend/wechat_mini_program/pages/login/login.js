// login.js
import { checkApiStatus, login } from "../../utils/api";

Page({
  data: {
    username: "",
    password: "",
    isLoading: false,
    apiStatus: "checking...",
  },

  onLoad() {
    this.checkApi();
    // 检查是否已经登录
    const userInfo = wx.getStorageSync("userInfo");
    if (userInfo && userInfo.token) {
      // 已登录，跳转到首页
      wx.switchTab({
        url: "/pages/index/index",
      });
    }
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

  // 登录
  async onLogin() {
    const { username, password } = this.data;

    if (!username || !password) {
      wx.showToast({
        title: "请输入用户名和密码",
        icon: "none",
      });
      return;
    }

    this.setData({ isLoading: true });

    try {
      const response = await login(username, password);

      // API返回200状态码和access_token表示登录成功
      if (response && response.access_token) {
        // 登录成功，保存用户信息
        const userInfo = {
          username: username,
          token: response.access_token,
          user_id: response.user.user_id,
          email: response.user.email,
          phone: response.user.phone,
        };

        wx.setStorageSync("userInfo", userInfo);

        wx.showToast({
          title: "登录成功",
          icon: "success",
        });

        // 跳转到首页
        setTimeout(() => {
          wx.switchTab({
            url: "/pages/index/index",
          });
        }, 1500);
      } else {
        wx.showToast({
          title: "登录失败，请重试",
          icon: "none",
        });
      }
    } catch (error) {
      console.error("登录请求失败:", error);
      
      // 处理API返回的错误信息
      let errorMessage = "网络错误，请重试";
      if (error.data && error.data.detail) {
        errorMessage = error.data.detail;
      } else if (error.statusCode === 400) {
        errorMessage = "用户名或密码错误";
      } else if (error.statusCode === 401) {
        errorMessage = "用户名或密码错误";
      }
      
      wx.showToast({
        title: errorMessage,
        icon: "none",
      });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  // 跳转到注册页面
  goToRegister() {
    wx.navigateTo({
      url: "/pages/register/register",
    });
  },
});
