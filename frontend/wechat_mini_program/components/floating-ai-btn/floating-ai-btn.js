Component({
  properties: {
    agentType: {
      type: String,
      value: "default",
    },
  },

  data: {
    x: 0,
    y: 0,
  },

  lifetimes: {
    attached() {
      try {
        const info = wx.getSystemInfoSync();
        const screenWidth = info.windowWidth || 375;
        const screenHeight = info.windowHeight || 667;
        const sizeRpx = 110;
        const marginRpx = 30;
        const sizePx = Math.round((sizeRpx * screenWidth) / 750);
        const marginPx = Math.round((marginRpx * screenWidth) / 750);
        const bottomRpx = 180;
        const bottomPx = Math.round((bottomRpx * screenWidth) / 750);
        const x = Math.max(0, screenWidth - sizePx - marginPx);
        const y = Math.max(0, screenHeight - sizePx - bottomPx);
        this.setData({ x, y });
      } catch (e) {
        this.setData({ x: 0, y: 0 });
      }
    },
  },

  methods: {
    goToAIAssistant() {
      const agentType = this.data.agentType;
      wx.navigateTo({
        url: `/pages/agent_chat/agent_chat?agentType=${agentType}`,
      });
    },

    handleMove(e) {
      if (e && e.detail) {
        const { x, y } = e.detail;
        if (typeof x === "number" && typeof y === "number") {
          this.setData({ x, y });
        }
      }
    },
  },
});
