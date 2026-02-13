const {
  getMedications,
  createMedication,
  getMedicationReminders,
  markMedicationTaken,
  getMedicationReminderPlans,
  setMedicationReminderActive,
  markMedicationSkipped,
  addMedicationRemindersToMedication,
  getMedicationStats,
  uploadMedicationImage,
  deleteMedication: deleteMedicationApi,
  getWeChatTemplateIds,
} = require("../../utils/api");

const app = getApp();

Page({
  data: {
    // 今日日期
    todayDate: "",

    // 今日用药
    todayMedications: [],

    // 用药记录
    medicationRecords: [],

    // 用药提醒
    reminders: [],

    todayWindowTab: "today",

    // 统计数据
    stats: {
      totalDays: 0,
      adherenceRate: 0,
      missedDoses: 0,
      onTimeRate: 0,
    },

    // 弹窗状态
    showAddModal: false,
    showReminderModal: false,

    // 新增用药表单
    newMedication: {
      name: "",
      type: "",
      typeIndex: 0,
      dose: "",
      unit: "",
      unitIndex: 0,
      frequency: "",
      frequencyIndex: 0,
      times: [""],
      startDate: "",
      endDate: "",
      duration: "",
      notes: "",
    },

    // 新增提醒表单
    newReminder: {
      medicationIndex: 0,
      time: "",
      frequency: "",
      frequencyIndex: 0,
      message: "",
    },

    // 选项数据
    medicationTypes: [
      "片剂",
      "胶囊",
      "口服液",
      "注射剂",
      "外用药",
      "滴剂",
      "其他",
    ],
    doseUnits: ["片", "粒", "毫升", "毫克", "克", "支", "滴"],
    frequencies: [
      "每日一次",
      "每日两次",
      "每日三次",
      "每日四次",
      "每周一次",
      "每周两次",
      "按需服用",
    ],
    reminderFrequencies: ["每天", "每周", "每月", "自定义"],

    // 可用药品列表
    availableMedications: [],

    // 加载状态
    loading: false,
  },

  onLoad() {
    this.initPage();
  },

  onShow() {
    this.loadData();
  },

  // 空函数，用于阻止冒泡
  noop() {},

  onMedicationNameInput(e) {
    this.setData({
      "newMedication.name": e.detail.value,
    });
  },

  scanMedicationBox() {
    return this.scanMedication();
  },

  submitMedication() {
    return this.saveMedication();
  },

  // 初始化页面
  initPage() {
    const today = new Date();
    const todayStr = `${today.getMonth() + 1}月${today.getDate()}日`;
    this.setData({
      todayDate: todayStr,
    });
  },

  getUserId() {
    const userInfo = wx.getStorageSync("userInfo") || {};
    return (
      userInfo.user_id ||
      userInfo.id ||
      app.globalData?.userInfo?.user_id ||
      app.globalData?.userInfo?.id ||
      null
    );
  },

  getToken() {
    const userInfo = wx.getStorageSync("userInfo") || {};
    return userInfo.token || "";
  },

  async ensureMedicationSubscribeAuth() {
    const cached = wx.getStorageSync("medicationSubscribeAccepted");
    if (cached) return true;

    let templateId = "";
    try {
      const ids = await getWeChatTemplateIds();
      templateId =
        (ids && (ids.medication_reminder || ids.medicationReminder)) || "";
    } catch (e) {
      templateId = "";
    }
    if (!templateId) return false;

    return await new Promise((resolve) => {
      wx.requestSubscribeMessage({
        tmplIds: [templateId],
        success: (res) => {
          const state = res ? res[templateId] : "";
          if (state === "accept") {
            try {
              wx.setStorageSync("medicationSubscribeAccepted", true);
            } catch (e) {}
            resolve(true);
            return;
          }
          resolve(false);
        },
        fail: () => resolve(false),
      });
    });
  },

  // 加载数据
  async loadData() {
    this.setData({ loading: true });

    try {
      const userId = this.getUserId();

      // 1. 获取所有药物记录
      const medications = await getMedications(userId);

      // 2. 映射为 medicationRecords
      const medicationRecords = this.mapMedicationsToRecords(medications);

      // 3. 获取今日提醒状态
      const today = new Date().toISOString().split("T")[0];
      const remindersTodayRaw = await getMedicationReminders(today, userId);
      const remindersToday = Array.isArray(remindersTodayRaw)
        ? remindersTodayRaw
        : remindersTodayRaw?.reminders || [];

      // 4. 映射为 todayMedications
      const todayMedications = this.mapRemindersToToday(
        remindersToday,
        medications,
      );

      let reminders = [];
      if ((medications || []).length > 0) {
        const plansRaw = await getMedicationReminderPlans(false, userId);
        const plans = Array.isArray(plansRaw)
          ? plansRaw
          : plansRaw?.plans || [];
        reminders = this.mapPlansToReminders(plans);
      }

      // 6. 获取统计数据（真实）
      let stats = this.calculateStats(todayMedications, medicationRecords);
      try {
        const statsRaw = await getMedicationStats(7, today, userId);
        if (statsRaw && statsRaw.success) {
          const hasAnySchedule =
            Number(statsRaw.totalScheduled || 0) > 0 ||
            (statsRaw.perDay || [] || []).some(
              (x) => Number(x?.scheduled || 0) > 0,
            );
          if (hasAnySchedule && todayMedications.length > 0) {
            stats = {
              totalDays: Number(statsRaw.totalDays || 0),
              adherenceRate: Number(statsRaw.adherenceRate || 0),
              missedDoses: Number(statsRaw.missedDoses || 0),
              onTimeRate: Number(statsRaw.onTimeRate || 0),
            };
          }
        }
      } catch (e) {
        stats = this.calculateStats(todayMedications, medicationRecords);
      }

      this.setData({
        medicationRecords,
        todayMedications,
        reminders,
        availableMedications: medicationRecords.filter(
          (m) => m.status === "active",
        ),
        stats,
      });

      const currentTab = this.data.todayWindowTab || "today";
      let nextTab = currentTab;
      if (currentTab === "reminders" && reminders.length === 0) {
        nextTab = "today";
      }
      if (currentTab === "today" && todayMedications.length === 0) {
        if (reminders.length > 0) nextTab = "reminders";
      }
      if (nextTab !== currentTab) {
        this.setData({ todayWindowTab: nextTab });
      }
    } catch (error) {
      console.error("加载数据失败:", error);
      wx.showToast({
        title: "加载失败",
        icon: "error",
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  switchTodayWindowTab(e) {
    const tab = String(e.currentTarget.dataset.tab || "");
    if (tab !== "today" && tab !== "reminders") return;
    this.setData({ todayWindowTab: tab });
  },

  mapMedicationsToRecords(medications) {
    if (!medications || !Array.isArray(medications)) return [];
    const now = new Date();

    return medications.map((m) => {
      // 解析剂量
      let dose = m.dosage || "";
      let unit = "";
      const unitMatch = dose.match(/([0-9.]+)(.*)/);
      if (unitMatch) {
        dose = unitMatch[1];
        unit = unitMatch[2];
      }

      // 判断状态
      let status = "active";
      if (m.endDate) {
        const end = new Date(m.endDate);
        if (end < now) status = "completed";
      }

      let progress = 0;
      if (m.startDate && m.endDate) {
        const start = new Date(m.startDate);
        const end = new Date(m.endDate);
        const total = Math.max(
          1,
          Math.floor((end - start) / (1000 * 60 * 60 * 24)) + 1,
        );
        const passed = Math.floor((now - start) / (1000 * 60 * 60 * 24)) + 1;
        progress = Math.min(
          100,
          Math.max(0, Math.round((passed / total) * 100)),
        );
      }

      return {
        id: m.id,
        name: m.name,
        dose,
        unit,
        frequency: m.frequency,
        duration:
          m.startDate && m.endDate
            ? `${m.startDate} 至 ${m.endDate}`
            : m.startDate
              ? `开始于 ${m.startDate}`
              : "",
        date: m.startDate || "",
        progress,
        status,
        original: m,
      };
    });
  },

  mapRemindersToToday(remindersToday, medications) {
    if (!remindersToday || !Array.isArray(remindersToday)) return [];

    // 创建 medication 查找表
    const medMap = {};
    if (medications && Array.isArray(medications)) {
      medications.forEach((m) => (medMap[m.id] = m));
    }

    return remindersToday
      .map((r) => {
        const medId = r.medicationId ?? r.medication_id ?? null;
        const med =
          (medId !== null && medId !== undefined ? medMap[medId] : null) || {};

        // 解析剂量
        let dose = r.dosage || med.dosage || "";
        let unit = "";
        const unitMatch = dose.match(/([0-9.]+)(.*)/);
        if (unitMatch) {
          dose = unitMatch[1];
          unit = unitMatch[2];
        }

        // 解析时间
        let time = r.time || "";
        if (!time && r.scheduledTime) {
          const parts = r.scheduledTime.split(" ");
          if (parts.length > 1) {
            time = parts[1].substring(0, 5); // HH:MM
          }
        }

        const statusRaw = String(r.status || "").toLowerCase();
        const status =
          statusRaw === "taken" || statusRaw === "completed"
            ? "taken"
            : statusRaw === "missed" || statusRaw === "skipped"
              ? "missed"
              : r.taken
                ? "taken"
                : "pending";

        return {
          id: r.id,
          medicationId: medId,
          name: r.medicationName || med.name || "未知药物",
          dose,
          unit,
          type: med.frequency || "",
          time,
          scheduledTime: r.scheduledTime || "",
          status,
        };
      })
      .sort((a, b) => a.time.localeCompare(b.time));
  },

  mapPlansToReminders(plans) {
    if (!plans || !Array.isArray(plans)) return [];
    const today = new Date().toISOString().split("T")[0];
    return plans
      .map((p) => ({
        id: p.id,
        medicationName: p.medicationName || p.medication_name || "",
        time: p.time || "",
        frequency: p.frequency || "",
        enabled: !!p.enabled,
        startDate: p.startDate || p.start_date || "",
        endDate: p.endDate || p.end_date || null,
      }))
      .filter((x) => x.id !== undefined && x.id !== null)
      .filter((x) => !x.endDate || String(x.endDate) >= today)
      .sort((a, b) => String(a.time || "").localeCompare(String(b.time || "")));
  },

  calculateStats(todayMedications, medicationRecords) {
    const totalToday = todayMedications.length;
    const takenToday = todayMedications.filter(
      (m) => m.status === "taken",
    ).length;
    const missedToday = todayMedications.filter(
      (m) => m.status === "missed",
    ).length;

    return {
      totalDays: 0,
      adherenceRate:
        totalToday > 0 ? Math.round((takenToday / totalToday) * 100) : 0,
      missedDoses:
        missedToday + Math.max(0, totalToday - takenToday - missedToday),
      onTimeRate: takenToday > 0 ? 100 : 0,
    };
  },

  // 拍照识别药品
  scanMedication() {
    const that = this;
    wx.chooseImage({
      count: 1,
      sizeType: ["compressed"],
      sourceType: ["camera", "album"],
      success(res) {
        const tempFilePaths = res.tempFilePaths;
        wx.showLoading({ title: "识别中...", mask: true });

        const userId = that.getUserId();
        uploadMedicationImage(tempFilePaths[0], userId)
          .then((data) => {
            wx.hideLoading();
            if (data.success && data.drug_name) {
              wx.showToast({ title: "识别成功", icon: "success" });

              // 自动填入识别到的信息
              const currentData = that.data.newMedication;
              that.setData({
                newMedication: {
                  ...currentData,
                  name: data.drug_name,
                  notes:
                    (currentData.notes ? currentData.notes + "\n" : "") +
                    "OCR识别内容: " +
                    (data.text || "").substring(0, 50) +
                    "...",
                },
              });
            } else {
              wx.showToast({ title: "未能识别药品名称", icon: "none" });
              if (data.text) {
                // 即使没有识别出 drug_name，也把 text 放入备注
                const currentData = that.data.newMedication;
                that.setData({
                  newMedication: {
                    ...currentData,
                    notes:
                      (currentData.notes ? currentData.notes + "\n" : "") +
                      "OCR原始内容: " +
                      data.text.substring(0, 100),
                  },
                });
              }
            }
          })
          .catch((err) => {
            wx.hideLoading();
            console.error("OCR error:", err);
            wx.showToast({ title: "识别失败", icon: "none" });
          });
      },
    });
  },

  // 添加用药
  addMedication() {
    const today = new Date().toISOString().split("T")[0];
    this.setData({
      showAddModal: true,
      newMedication: {
        name: "",
        type: "",
        typeIndex: 0,
        dose: "",
        unit: "",
        unitIndex: 0,
        frequency: "",
        frequencyIndex: 0,
        times: [""],
        startDate: today,
        endDate: "",
        duration: "",
        notes: "",
      },
    });
  },

  // 设置提醒
  setReminder() {
    if (this.data.availableMedications.length === 0) {
      wx.showToast({
        title: "请先添加用药记录",
        icon: "none",
      });
      return;
    }

    this.setData({
      showReminderModal: true,
      newReminder: {
        medicationIndex: 0,
        time: "",
        frequency: "",
        frequencyIndex: 0,
        message: "",
      },
    });
  },

  // 服用药物
  async takeMedication(e) {
    const token = this.getToken();
    if (!token) {
      wx.showToast({ title: "请先登录", icon: "none" });
      setTimeout(() => {
        wx.reLaunch({ url: "/pages/login/login" });
      }, 500);
      return;
    }

    const userId = this.getUserId();
    const id = String(e.currentTarget.dataset.id ?? "");
    const item = (this.data.todayMedications || []).find(
      (x) => String(x.id) === id,
    );
    const today = new Date().toISOString().split("T")[0];
    const scheduledTime =
      item?.scheduledTime || (item?.time ? `${today} ${item.time}:00` : "");

    try {
      await markMedicationTaken(id, scheduledTime, userId);

      wx.showToast({
        title: "已记录服用",
        icon: "success",
      });
      await this.loadData();
    } catch (error) {
      console.error("标记服用失败:", error);
      wx.showToast({ title: "操作失败", icon: "error" });
    }
  },

  // 跳过药物
  async skipMedication(e) {
    const id = String(e.currentTarget.dataset.id ?? "");
    const item = (this.data.todayMedications || []).find(
      (x) => String(x.id) === id,
    );

    const today = new Date().toISOString().split("T")[0];
    const scheduledTime =
      item?.scheduledTime || (item?.time ? `${today} ${item.time}:00` : "");

    try {
      await markMedicationSkipped(id, scheduledTime, this.getUserId());
      wx.showToast({ title: "已标记跳过", icon: "none" });
      await this.loadData();
    } catch (error) {
      console.error("标记跳过失败:", error);
      wx.showToast({ title: "操作失败", icon: "error" });
    }
  },

  // 查看用药详情
  viewMedicationDetail(e) {
    const id = String(e.currentTarget.dataset.id ?? "");
    const item = (this.data.todayMedications || []).find(
      (x) => String(x.id) === id,
    );
    if (!item) return;

    const statusText =
      item.status === "taken"
        ? "已服用"
        : item.status === "missed"
          ? "已错过"
          : "待服用";

    wx.showModal({
      title: item.name || "用药详情",
      content: `时间：${item.time || "-"}\n剂量：${item.dose || "-"}${
        item.unit ? ` ${item.unit}` : ""
      }\n状态：${statusText}`,
      showCancel: false,
    });
  },

  // 查看记录详情
  viewRecordDetail(e) {
    const id = String(e.currentTarget.dataset.id ?? "");
    const record = (this.data.medicationRecords || []).find(
      (x) => String(x.id) === id,
    );
    if (!record) return;

    const raw = record.original || {};
    const lines = [
      `剂量：${
        raw.dosage || `${record.dose || ""}${record.unit || ""}` || "-"
      }`,
      `频率：${raw.frequency || record.frequency || "-"}`,
      `开始：${raw.startDate || record.date || "-"}`,
      `结束：${raw.endDate || "-"}`,
      raw.notes ? `备注：${raw.notes}` : "",
    ].filter(Boolean);

    wx.showModal({
      title: record.name || "用药记录",
      content: lines.join("\n"),
      showCancel: false,
    });
  },

  // 查看全部记录
  viewAllRecords() {
    wx.showModal({
      title: "用药记录",
      content: `共 ${this.data.medicationRecords.length || 0} 条记录`,
      showCancel: false,
    });
  },

  // 管理提醒
  manageReminders() {
    wx.showModal({
      title: "用药提醒",
      content: `共 ${this.data.reminders.length || 0} 条提醒`,
      showCancel: false,
    });
  },

  editReminder(e) {
    const id = String(e.currentTarget.dataset.id ?? "");
    const item = (this.data.reminders || []).find((x) => String(x.id) === id);
    if (!item) return;

    wx.showModal({
      title: "提醒详情",
      content: `药物：${item.medicationName || "-"}\n时间：${
        item.time || "-"
      }\n频率：${item.frequency || "-"}\n状态：${
        item.enabled ? "已启用" : "已停用"
      }`,
      showCancel: false,
    });
  },

  // 切换提醒开关
  async toggleReminder(e) {
    const id = String(e.currentTarget.dataset.id ?? "");
    const enabled = !!e.detail.value;
    const userId = this.getUserId();

    const prev = this.data.reminders || [];
    const next = prev.map((item) => {
      if (String(item.id) === id) {
        return { ...item, enabled };
      }
      return item;
    });

    this.setData({ reminders: next });

    try {
      const res = await setMedicationReminderActive(id, enabled, userId);
      if (!res || res.success !== true) {
        throw new Error(res?.message || "set_active_failed");
      }
      await this.loadData();
    } catch (err) {
      console.error("切换提醒失败:", err);
      this.setData({ reminders: prev });
      wx.showToast({ title: "操作失败", icon: "error" });
    }
  },

  async deleteMedication(e) {
    const id = String(e.currentTarget.dataset.id ?? "");
    const record = (this.data.medicationRecords || []).find(
      (x) => String(x.id) === id,
    );

    wx.showModal({
      title: "删除用药",
      content: `确定删除“${record?.name || "该用药"}”吗？\n相关提醒也会停用。`,
      success: async (res) => {
        if (!res.confirm) return;
        try {
          const resp = await deleteMedicationApi(id, this.getUserId());
          if (!resp || resp.success !== true) {
            throw new Error(resp?.message || "delete_failed");
          }
          wx.showToast({ title: "已删除", icon: "success" });
          await this.loadData();
        } catch (error) {
          console.error("删除用药失败:", error);
          wx.showToast({ title: "删除失败", icon: "error" });
        }
      },
    });
  },

  // 表单输入处理
  onInputChange(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;

    this.setData({
      [`newMedication.${field}`]: value,
    });
  },

  // 药品类型选择
  onTypeChange(e) {
    const index = e.detail.value;
    this.setData({
      "newMedication.typeIndex": index,
      "newMedication.type": this.data.medicationTypes[index],
    });
  },

  // 剂量单位选择
  onUnitChange(e) {
    const index = e.detail.value;
    this.setData({
      "newMedication.unitIndex": index,
      "newMedication.unit": this.data.doseUnits[index],
    });
  },

  // 服用频率选择
  onFrequencyChange(e) {
    const index = e.detail.value;
    const frequency = this.data.frequencies[index];

    // 根据频率设置时间数组
    let times = [""];
    if (frequency.includes("两次")) {
      times = ["08:00", "20:00"];
    } else if (frequency.includes("三次")) {
      times = ["08:00", "13:00", "20:00"];
    } else if (frequency.includes("四次")) {
      times = ["08:00", "12:00", "18:00", "22:00"];
    } else if (frequency.includes("每日一次")) {
      times = ["08:00"];
    } else if (frequency.includes("按需")) {
      times = [];
    }

    this.setData({
      "newMedication.frequencyIndex": index,
      "newMedication.frequency": frequency,
      "newMedication.times": times,
    });
  },

  // 服用时间选择
  onTimeChange(e) {
    const index = e.currentTarget.dataset.index;
    const time = e.detail.value;
    const times = [...this.data.newMedication.times];
    times[index] = time;

    this.setData({
      "newMedication.times": times,
    });
  },

  onStartDateChange(e) {
    const startDate = e.detail.value;
    const currentEnd = this.data.newMedication.endDate || "";
    this.setData({
      "newMedication.startDate": startDate,
      "newMedication.endDate":
        currentEnd && currentEnd < startDate ? "" : currentEnd,
    });
  },

  onEndDateChange(e) {
    const endDate = e.detail.value;
    const startDate =
      this.data.newMedication.startDate ||
      new Date().toISOString().split("T")[0];

    if (endDate && endDate < startDate) {
      wx.showToast({ title: "结束日期不能早于开始日期", icon: "none" });
      this.setData({ "newMedication.endDate": "" });
      return;
    }

    this.setData({ "newMedication.endDate": endDate });
  },

  // 提醒相关处理
  onReminderInputChange(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;

    this.setData({
      [`newReminder.${field}`]: value,
    });
  },

  onReminderMedicationChange(e) {
    const index = e.detail.value;
    this.setData({
      "newReminder.medicationIndex": index,
    });
  },

  onReminderTimeChange(e) {
    const time = e.detail.value;
    this.setData({
      "newReminder.time": time,
    });
  },

  onReminderFrequencyChange(e) {
    const index = e.detail.value;
    this.setData({
      "newReminder.frequencyIndex": index,
      "newReminder.frequency": this.data.reminderFrequencies[index],
    });
  },

  // 保存用药
  async saveMedication() {
    const medication = this.data.newMedication;

    // 验证必填字段
    if (!medication.name || !medication.dose || !medication.unit) {
      wx.showToast({
        title: "请填写完整信息",
        icon: "none",
      });
      return;
    }

    let validTimes = (medication.times || []).filter((time) => time);
    if (
      validTimes.length === 0 &&
      typeof medication.frequency === "string" &&
      medication.frequency.includes("每日")
    ) {
      if (medication.frequency.includes("两次")) {
        validTimes = ["08:00", "20:00"];
      } else if (medication.frequency.includes("三次")) {
        validTimes = ["08:00", "13:00", "20:00"];
      } else if (medication.frequency.includes("四次")) {
        validTimes = ["08:00", "12:00", "18:00", "22:00"];
      } else if (medication.frequency.includes("一次")) {
        validTimes = ["08:00"];
      }
    }
    const today = new Date().toISOString().split("T")[0];
    const startDate = medication.startDate || today;
    const endDate =
      medication.endDate && medication.endDate >= startDate
        ? medication.endDate
        : "";

    try {
      const payload = {
        name: medication.name,
        dosage: `${medication.dose}${medication.unit}`,
        frequency: medication.frequency,
        times: validTimes,
        startDate,
        ...(endDate ? { endDate } : {}),
        notes: medication.notes,
        reminderEnabled: validTimes.length > 0,
      };

      if (payload.reminderEnabled) {
        try {
          await this.ensureMedicationSubscribeAuth();
        } catch (e) {}
      }

      await createMedication(payload, this.getUserId());

      wx.showToast({
        title: "添加成功",
        icon: "success",
      });

      this.setData({
        showAddModal: false,
      });

      // 重新加载数据
      this.loadData();
    } catch (error) {
      console.error("保存用药失败:", error);
      wx.showToast({
        title: "保存失败",
        icon: "error",
      });
    }
  },

  // 保存提醒
  async saveReminder() {
    const reminder = this.data.newReminder;

    // 验证必填字段
    if (!reminder.time) {
      wx.showToast({ title: "请选择时间", icon: "none" });
      return;
    }

    const selectedMed =
      this.data.availableMedications[reminder.medicationIndex];
    if (!selectedMed) {
      wx.showToast({ title: "请选择药物", icon: "none" });
      return;
    }

    try {
      const payload = {
        times: [reminder.time],
        startDate: new Date().toISOString().split("T")[0],
        notes: reminder.message,
      };

      try {
        await this.ensureMedicationSubscribeAuth();
      } catch (e) {}

      await addMedicationRemindersToMedication(
        selectedMed.id,
        payload,
        this.getUserId(),
      );

      wx.showToast({
        title: "设置成功",
        icon: "success",
      });

      this.setData({
        showReminderModal: false,
      });

      // 重新加载数据
      this.loadData();
    } catch (error) {
      console.error("保存提醒失败:", error);
      wx.showToast({
        title: "保存失败",
        icon: "error",
      });
    }
  },

  // 关闭弹窗
  closeAddModal() {
    this.setData({
      showAddModal: false,
    });
  },

  closeReminderModal() {
    this.setData({
      showReminderModal: false,
    });
  },

  // 获取状态名称
  getStatusName(status) {
    const statusMap = {
      active: "进行中",
      completed: "已完成",
      paused: "已暂停",
      stopped: "已停止",
    };
    return statusMap[status] || status;
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadData().then(() => {
      wx.stopPullDownRefresh();
    });
  },

  // 分享功能
  onShareAppMessage() {
    return {
      title: "智能用药管理",
      path: "/pages/medication/medication",
    };
  },
});
