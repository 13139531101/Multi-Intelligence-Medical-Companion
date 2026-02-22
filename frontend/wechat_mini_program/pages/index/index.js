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
    trendIndicators: [],
    trendLoading: false,
    trendError: "",
    trendDays: 180,
    trendSelectedName: "",
    trendSelected: null,
    trendChartW: 320,
    trendChartH: 160,
  },

  formatActivityTime(t) {
    const s = (t ?? "").toString().trim();
    if (!s) return "";
    if (s.startsWith("今天") || s.startsWith("昨天")) return s;
    if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}/.test(s)) return s.slice(0, 16);
    if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s))
      return s.slice(0, 16).replace("T", " ");
    return s.length > 16 ? s.slice(0, 16).replace("T", " ") : s;
  },

  onLoad() {
    try {
      const sys = wx.getSystemInfoSync();
      const w = Math.max(260, (sys?.windowWidth || 320) - 60);
      this.setData({ trendChartW: w, trendChartH: 160 });
    } catch (e) {}
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
      await this.loadDashboardStats();
      await this.loadTrendIndicators(false);
    } catch (error) {
      console.error("加载仪表板数据失败:", error);
    }
  },

  // 统一加载仪表板统计与最近活动
  async loadDashboardStats() {
    try {
      const response = await request("/api/dashboard/stats", {
        method: "GET",
      });
      if (!response || typeof response !== "object") {
        this.setData({
          healthRecordsCount: 0,
          medicationCount: 0,
          summaryCount: 0,
          recentActivities: [],
        });
        return;
      }

      const healthRecordsCount =
        typeof response.health_records_count === "number"
          ? response.health_records_count
          : 0;
      const summaryCount =
        typeof response.summary_count === "number" ? response.summary_count : 0;
      const medicationCount =
        typeof response.medication_count === "number"
          ? response.medication_count
          : 0;

      const activities = Array.isArray(response.recent_activities)
        ? response.recent_activities.map((item, index) => ({
            id: item.id || `${index}`,
            title: item.title || "",
            time: this.formatActivityTime(
              item.time || item.created_at || item.timestamp,
            ),
            icon: item.icon || "📝",
          }))
        : [];

      this.setData({
        healthRecordsCount,
        summaryCount,
        medicationCount,
        recentActivities: activities,
      });
    } catch (error) {
      console.error("加载仪表板统计失败:", error);
      this.setData({
        healthRecordsCount: 0,
        medicationCount: 0,
        summaryCount: 0,
        recentActivities: [],
      });
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
    try {
      const response = await request("/api/visit-summaries/count", {
        method: "GET",
      });
      if (response && typeof response.count === "number") {
        this.setData({ summaryCount: response.count });
      } else {
        this.setData({ summaryCount: 0 });
      }
    } catch (error) {
      console.error("加载就诊摘要数量失败:", error);
      this.setData({ summaryCount: 0 });
    }
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
  refreshTrends() {
    this.loadTrendIndicators(true);
  },

  formatIndicatorLatest(item) {
    if (!item || !item.latest) return "";
    const latest = item.latest || {};
    const value =
      typeof latest.value === "number" ? latest.value : latest.value_text || "";
    const unit = latest.unit || item.unit || "";
    const date = latest.date || "";
    const valueText = value !== "" ? `${value}${unit}` : "暂无数值";
    return date ? `${valueText} · ${date}` : valueText;
  },

  normalizeIndicatorItem(item) {
    const latestText = this.formatIndicatorLatest(item);
    const stats = item && item.stats ? item.stats : null;
    return {
      name: item.name || "",
      unit: item.unit || "",
      count: item.count || 0,
      latestText,
      statsText: stats
        ? `均值 ${stats.avg} | 最低 ${stats.min} | 最高 ${stats.max}`
        : "",
    };
  },

  async loadTrendIndicators(showHint = false) {
    this.setData({ trendLoading: true, trendError: "" });
    try {
      const response = await request("/api/health-trends/indicators", {
        method: "GET",
        data: {
          days: this.data.trendDays,
          include_points: false,
        },
      });
      const indicators = Array.isArray(response?.indicators)
        ? response.indicators.map((item) => this.normalizeIndicatorItem(item))
        : [];
      const pending = Number(response?.ocr_pending_count || 0) || 0;
      const failed = Number(response?.ocr_failed_count || 0) || 0;
      const selectedName = this.data.trendSelectedName || "";
      const selectedStillExists =
        selectedName &&
        indicators.some((x) => String(x?.name || "") === String(selectedName));
      this.setData({
        trendIndicators: indicators,
        trendLoading: false,
        trendError: indicators.length ? "" : "暂无趋势数据",
      });
      if (!indicators.length || (selectedName && !selectedStillExists)) {
        this.setData({ trendSelectedName: "", trendSelected: null });
        this.clearTrendChart();
      }
      if (showHint) {
        if (pending > 0) {
          wx.showToast({
            title: `有${pending}份档案识别中，稍后刷新`,
            icon: "none",
          });
        } else if (failed > 0) {
          wx.showToast({
            title: `有${failed}份档案识别失败`,
            icon: "none",
          });
        }
      }
    } catch (error) {
      console.error("加载健康趋势失败:", error);
      this.setData({
        trendIndicators: [],
        trendLoading: false,
        trendError: "趋势加载失败",
      });
      this.setData({ trendSelectedName: "", trendSelected: null });
      this.clearTrendChart();
    }
  },

  async selectTrendIndicator(e) {
    const name = e.currentTarget.dataset.name || "";
    if (!name) return;
    if (this.data.trendSelectedName === name) {
      this.setData({ trendSelectedName: "", trendSelected: null });
      this.clearTrendChart();
      return;
    }
    this.setData({ trendSelectedName: name, trendSelected: null });
    this.clearTrendChart();
    try {
      const response = await request("/api/health-trends/indicator", {
        method: "GET",
        data: {
          name,
          days: this.data.trendDays,
        },
      });
      const indicator = response?.indicator || null;
      if (!indicator) {
        wx.showToast({ title: "暂无详细趋势", icon: "none" });
        this.setData({ trendSelected: null });
        return;
      }
      const points = Array.isArray(indicator.points) ? indicator.points : [];
      const chartPoints = points
        .filter((p) => typeof p?.value === "number")
        .map((p) => ({
          date: p.date || "",
          value: p.value,
        }))
        .filter((p) => p.date && typeof p.value === "number");
      const pointItems = points.map((point, index) => {
        const value =
          typeof point.value === "number"
            ? point.value
            : point.value_text || "";
        const unit = point.unit || indicator.unit || "";
        return {
          id: `${index}`,
          date: point.date || "",
          valueText: value !== "" ? `${value}${unit}` : "暂无数值",
          source: point.source || "",
        };
      });
      this.setData({
        trendSelected: {
          name: indicator.name || name,
          unit: indicator.unit || "",
          count: indicator.count || pointItems.length,
          stats: indicator.stats || null,
          points: pointItems,
          chartEnabled: chartPoints.length >= 2,
          chartPoints,
        },
      }, () => {
        const drawFn = () => this.drawTrendChart(chartPoints, indicator.unit || "");
        if (wx.nextTick) wx.nextTick(drawFn);
        else setTimeout(drawFn, 0);
      });
    } catch (error) {
      console.error("加载趋势详情失败:", error);
      wx.showToast({ title: "加载失败", icon: "none" });
      this.setData({ trendSelected: null });
    }
  },

  clearTrendChart() {
    const w = this.data.trendChartW || 320;
    const h = this.data.trendChartH || 160;
    try {
      const ctx = wx.createCanvasContext("trendChart", this);
      ctx.clearRect(0, 0, w, h);
      ctx.draw();
    } catch (e) {}
  },

  formatChartDateLabel(s) {
    const t = (s || "").toString();
    const m = t.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!m) return t.length > 10 ? t.slice(0, 10) : t;
    return `${m[2]}-${m[3]}`;
  },

  drawTrendChart(points, unit) {
    const items = Array.isArray(points) ? points : [];
    if (items.length < 2) return;
    const w = this.data.trendChartW || 320;
    const h = this.data.trendChartH || 160;
    const ctx = wx.createCanvasContext("trendChart", this);

    const left = 44;
    const right = 12;
    const top = 12;
    const bottom = 32;
    const plotW = Math.max(10, w - left - right);
    const plotH = Math.max(10, h - top - bottom);

    const values = items.map((p) => p.value);
    let minV = Math.min(...values);
    let maxV = Math.max(...values);
    if (!isFinite(minV) || !isFinite(maxV)) return;
    if (minV === maxV) {
      minV = minV - 1;
      maxV = maxV + 1;
    }
    const pad = (maxV - minV) * 0.08;
    minV = minV - pad;
    maxV = maxV + pad;

    const xAt = (i) => left + (plotW * i) / (items.length - 1);
    const yAt = (v) => top + ((maxV - v) * plotH) / (maxV - minV);

    ctx.clearRect(0, 0, w, h);
    ctx.setStrokeStyle("rgba(0,0,0,0.12)");
    ctx.setLineWidth(1);
    ctx.beginPath();
    ctx.moveTo(left, top);
    ctx.lineTo(left, top + plotH);
    ctx.lineTo(left + plotW, top + plotH);
    ctx.stroke();

    ctx.setFontSize(10);
    ctx.setFillStyle("rgba(0,0,0,0.55)");
    const maxText = `${maxV.toFixed(2)}${unit || ""}`;
    const minText = `${minV.toFixed(2)}${unit || ""}`;
    ctx.fillText(maxText, 6, top + 10);
    ctx.fillText(minText, 6, top + plotH);

    ctx.setStrokeStyle("rgba(0,122,255,0.95)");
    ctx.setLineWidth(2);
    ctx.beginPath();
    items.forEach((p, i) => {
      const x = xAt(i);
      const y = yAt(p.value);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    ctx.setFillStyle("rgba(0,122,255,0.95)");
    items.forEach((p, i) => {
      const x = xAt(i);
      const y = yAt(p.value);
      ctx.beginPath();
      ctx.arc(x, y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    });

    ctx.setFillStyle("rgba(0,0,0,0.55)");
    const first = this.formatChartDateLabel(items[0]?.date);
    const last = this.formatChartDateLabel(items[items.length - 1]?.date);
    ctx.fillText(first, left, top + plotH + 22);
    const lastWidth = last.length * 6;
    ctx.fillText(last, left + plotW - lastWidth, top + plotH + 22);

    ctx.draw();
  },
});
