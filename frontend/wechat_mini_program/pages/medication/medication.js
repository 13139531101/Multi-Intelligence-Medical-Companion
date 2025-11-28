import {
  getMedications,
  createMedication,
  getMedicationReminders,
  markMedicationTaken,
  createMedicationReminder,
  uploadMedicationImage,
} from "../../utils/api";

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

  // 初始化页面
  initPage() {
    const today = new Date();
    const todayStr = `${today.getMonth() + 1}月${today.getDate()}日`;
    this.setData({
      todayDate: todayStr,
    });
  },

  getUserId() {
    return app.globalData?.userInfo?.id || null;
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
      const remindersToday = await getMedicationReminders(today, userId);

      // 4. 映射为 todayMedications
      const todayMedications = this.mapRemindersToToday(
        remindersToday,
        medications
      );

      // 5. 映射为 reminders 设置
      const reminders = this.mapMedicationsToReminders(medications);

      // 6. 计算统计数据
      const stats = this.calculateStats(todayMedications, medicationRecords);

      this.setData({
        medicationRecords,
        todayMedications,
        reminders,
        availableMedications: medicationRecords.filter(
          (m) => m.status === "active"
        ),
        stats,
      });
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

      return {
        id: m.id,
        name: m.name,
        dose,
        unit,
        frequency: m.frequency,
        duration: m.startDate ? `开始于 ${m.startDate}` : "",
        date: m.startDate || "",
        progress: 0, // 暂无法计算精确进度
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
        const med = medMap[r.medicationId] || {};

        // 解析剂量
        let dose = med.dosage || "";
        let unit = "";
        const unitMatch = dose.match(/([0-9.]+)(.*)/);
        if (unitMatch) {
          dose = unitMatch[1];
          unit = unitMatch[2];
        }

        // 解析时间
        let time = "";
        if (r.scheduledTime) {
          const parts = r.scheduledTime.split(" ");
          if (parts.length > 1) {
            time = parts[1].substring(0, 5); // HH:MM
          }
        }

        return {
          id: r.id, // reminder instance id
          medicationId: r.medicationId,
          name: med.name || "未知药物",
          dose,
          unit,
          type: "药物", // 后端暂未返回类型
          time,
          status: r.taken ? "taken" : "pending",
        };
      })
      .sort((a, b) => a.time.localeCompare(b.time));
  },

  mapMedicationsToReminders(medications) {
    if (!medications || !Array.isArray(medications)) return [];

    const reminders = [];
    medications.forEach((m) => {
      if (m.reminderEnabled && m.times && m.times.length > 0) {
        m.times.forEach((t) => {
          reminders.push({
            id: m.id, // 这里使用 medication id，实际上 UI 可能需要 unique key
            medicationName: m.name,
            time: t,
            frequency: "每天", // 简化处理
            enabled: true,
          });
        });
      }
    });
    return reminders.sort((a, b) => a.time.localeCompare(b.time));
  },

  calculateStats(todayMedications, medicationRecords) {
    const totalToday = todayMedications.length;
    const takenToday = todayMedications.filter(
      (m) => m.status === "taken"
    ).length;

    return {
      totalDays: Math.floor(
        (new Date() - new Date(2024, 0, 1)) / (1000 * 60 * 60 * 24)
      ), // 示例
      adherenceRate:
        totalToday > 0 ? Math.round((takenToday / totalToday) * 100) : 100,
      missedDoses: totalToday - takenToday,
      onTimeRate: 90, // 示例
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
    const id = e.currentTarget.dataset.id;

    try {
      await markMedicationTaken(id, this.getUserId());

      const medications = this.data.todayMedications.map((item) => {
        if (item.id === id) {
          return { ...item, status: "taken" };
        }
        return item;
      });

      this.setData({
        todayMedications: medications,
      });

      wx.showToast({
        title: "已记录服用",
        icon: "success",
      });

      // 更新统计
      this.setData({
        stats: this.calculateStats(medications, this.data.medicationRecords),
      });
    } catch (error) {
      console.error("标记服用失败:", error);
      wx.showToast({ title: "操作失败", icon: "error" });
    }
  },

  // 跳过药物
  skipMedication(e) {
    // 后端暂无跳过接口，暂时仅前端更新
    const id = e.currentTarget.dataset.id;
    const medications = this.data.todayMedications.map((item) => {
      if (item.id === id) {
        return { ...item, status: "missed" };
      }
      return item;
    });

    this.setData({
      todayMedications: medications,
    });

    wx.showToast({
      title: "已标记跳过",
      icon: "none",
    });
  },

  // 查看用药详情
  viewMedicationDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/medication-detail/medication-detail?id=${id}`,
    });
  },

  // 查看记录详情
  viewRecordDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/medication-record/medication-record?id=${id}`,
    });
  },

  // 查看全部记录
  viewAllRecords() {
    wx.navigateTo({
      url: "/pages/medication-records/medication-records",
    });
  },

  // 管理提醒
  manageReminders() {
    wx.navigateTo({
      url: "/pages/medication-reminders/medication-reminders",
    });
  },

  // 切换提醒开关
  toggleReminder(e) {
    // 暂未实现后端开关
    const id = e.currentTarget.dataset.id;
    const enabled = e.detail.value;

    const reminders = this.data.reminders.map((item) => {
      if (item.id === id) {
        return { ...item, enabled };
      }
      return item;
    });

    this.setData({
      reminders: reminders,
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
      times = ["", ""];
    } else if (frequency.includes("三次")) {
      times = ["", "", ""];
    } else if (frequency.includes("四次")) {
      times = ["", "", "", ""];
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

    const validTimes = medication.times.filter((time) => time);

    try {
      const payload = {
        name: medication.name,
        dosage: `${medication.dose}${medication.unit}`,
        frequency: medication.frequency,
        times: validTimes,
        startDate: new Date().toISOString().split("T")[0],
        notes: medication.notes,
        reminderEnabled: validTimes.length > 0,
      };

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
        medication_name: selectedMed.name,
        // 注意：后端 createMedicationReminder 实际上是 createMedication 的逻辑，
        // 如果要给已有药物加提醒，可能需要更新药物或创建一个"仅提醒"的条目。
        // 这里我们假设创建一个新的提醒条目
        name: selectedMed.name,
        times: [reminder.time],
        startDate: new Date().toISOString().split("T")[0],
        notes: reminder.message,
        reminderEnabled: true,
      };

      await createMedicationReminder(payload, this.getUserId());

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
