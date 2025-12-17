Component({
  properties: {
    agentType: {
      type: String,
      value: 'default'
    }
  },

  methods: {
    goToAIAssistant() {
      const agentType = this.data.agentType;
      wx.navigateTo({
        url: `/pages/agent_chat/agent_chat?agentType=${agentType}`,
      });
    }
  }
});