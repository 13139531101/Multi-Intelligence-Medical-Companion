// pages/agents_status/agents_status.js
// 阶段35: agent 状态页（v2 + ANP）
const {
  getV2AgentsStatus,
  getV2AgentStatus,
  getAnpAgents,
  getAnpHealth,
  getAnpAgentDescription,
  callAnpRpc,
  getV2ModelProviders,
  detectBackendVersion,
  SERVER_URL,
} = require("../../utils/api");

Page({
  data: {
    loading: false,
    backendVersion: "",
    v2Available: false,
    anpAvailable: false,
    // v2 agents
    v2Agents: [],
    registry: [],
    cacheSize: 0,
    metrics: {},
    // 选中详情
    selectedAgent: null,
    selectedDetail: null,
    // ANP
    anpAgents: [],
    anpHealth: null,
    anpDescription: null,
    // models
    modelProviders: [],
    // 错误
    errorMsg: "",
  },

  async onLoad() {
    await this.refreshAll();
  },

  async onPullDownRefresh() {
    await this.refreshAll();
    wx.stopPullDownRefresh();
  },

  async refreshAll() {
    this.setData({ loading: true, errorMsg: "" });
    try {
      // 1. 探测后端
      const probe = await detectBackendVersion();
      this.setData({
        backendVersion: probe.version || "unknown",
        v2Available: !!probe.v2_available,
      });

      // 2. v2 agents
      if (probe.v2_available) {
        try {
          const status = await getV2AgentsStatus();
          this.setData({
            v2Agents: status.agents || {},
            registry: status.registry || [],
            cacheSize: status.cache_size || 0,
            metrics: status.metrics || {},
          });
        } catch (e) {
          this.setData({ errorMsg: "拉取 v2 agents 失败: " + (e.errMsg || e.message || e) });
        }
      }

      // 3. ANP
      try {
        const anpHealth = await getAnpHealth();
        this.setData({ anpHealth: anpHealth.result || anpHealth, anpAvailable: true });
      } catch (e) {
        this.setData({ anpAvailable: false });
      }
      try {
        const anpAgents = await getAnpAgents();
        this.setData({ anpAgents: anpAgents.agents || [] });
      } catch (e) {}

      // 4. ANP Description
      try {
        const ad = await getAnpAgentDescription();
        this.setData({ anpDescription: ad });
      } catch (e) {}

      // 5. model providers
      try {
        const mp = await getV2ModelProviders();
        this.setData({ modelProviders: mp.providers || mp });
      } catch (e) {}

    } catch (e) {
      this.setData({ errorMsg: "刷新失败: " + (e.errMsg || e.message || e) });
    } finally {
      this.setData({ loading: false });
    }
  },

  // 点击 agent 显示详情
  async onAgentTap(e) {
    const name = e.currentTarget.dataset.name;
    if (!name) return;
    this.setData({ selectedAgent: name, selectedDetail: null });
    try {
      const detail = await getV2AgentStatus(name);
      this.setData({ selectedDetail: detail });
    } catch (err) {
      this.setData({ selectedDetail: { error: err.errMsg || err.message || String(err) } });
    }
  },

  closeDetail() {
    this.setData({ selectedAgent: null, selectedDetail: null });
  },

  // 复制 DID
  copyDid(e) {
    const did = e.currentTarget.dataset.did;
    if (!did) return;
    wx.setClipboardData({
      data: did,
      success: () => wx.showToast({ title: "DID 已复制", icon: "none" }),
    });
  },

  // ANP JSON-RPC 测试
  async testAnpRpc() {
    try {
      wx.showLoading({ title: "ANP RPC 调用中..." });
      const result = await callAnpRpc("list_agents", {}, 1);
      wx.hideLoading();
      wx.showModal({
        title: "ANP JSON-RPC 成功",
        content: JSON.stringify(result, null, 2).substring(0, 500),
        showCancel: false,
      });
    } catch (e) {
      wx.hideLoading();
      wx.showModal({
        title: "ANP RPC 失败",
        content: e.errMsg || e.message || JSON.stringify(e),
        showCancel: false,
      });
    }
  },
});