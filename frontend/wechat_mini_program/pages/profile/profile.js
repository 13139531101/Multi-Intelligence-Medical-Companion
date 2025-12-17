const app = getApp();

Page({
  data: {
    userInfo: null
  },

  onShow() {
    if (typeof this.getTabBar === 'function' &&
      this.getTabBar()) {
      this.getTabBar().setData({
        selected: 2 // 假设这是第三个tab
      })
    }
    this.checkLoginStatus();
  },

  checkLoginStatus() {
    const userInfo = wx.getStorageSync("userInfo");
    this.setData({ userInfo });
  },

  goToLogin() {
    wx.navigateTo({
      url: '/pages/login/login',
    });
  },

  goToHistory() {
      // 导航到咨询历史，这里需要确认咨询历史的页面路径
      // 假设暂时跳转到原来的 consultation 或者新建一个 history 页面
      // 暂时不做跳转，提示开发中
       wx.showToast({
        title: '功能开发中',
        icon: 'none'
      });
  },

  logout() {
    wx.removeStorageSync("userInfo");
    this.setData({ userInfo: null });
    wx.showToast({
      title: '已退出',
      icon: 'success'
    });
    setTimeout(() => {
        wx.reLaunch({
            url: '/pages/login/login'
        });
    }, 1000);
  }
});
