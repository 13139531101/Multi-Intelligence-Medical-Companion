// medication.js
Page({
  data: {
    // 今日日期
    todayDate: '',
    
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
      onTimeRate: 0
    },
    
    // 弹窗状态
    showAddModal: false,
    showReminderModal: false,
    
    // 新增用药表单
    newMedication: {
      name: '',
      type: '',
      typeIndex: 0,
      dose: '',
      unit: '',
      unitIndex: 0,
      frequency: '',
      frequencyIndex: 0,
      times: [''],
      duration: '',
      notes: ''
    },
    
    // 新增提醒表单
    newReminder: {
      medicationIndex: 0,
      time: '',
      frequency: '',
      frequencyIndex: 0,
      message: ''
    },
    
    // 选项数据
    medicationTypes: ['片剂', '胶囊', '口服液', '注射剂', '外用药', '滴剂', '其他'],
    doseUnits: ['片', '粒', '毫升', '毫克', '克', '支', '滴'],
    frequencies: ['每日一次', '每日两次', '每日三次', '每日四次', '每周一次', '每周两次', '按需服用'],
    reminderFrequencies: ['每天', '每周', '每月', '自定义'],
    
    // 可用药品列表
    availableMedications: [],
    
    // 加载状态
    loading: false
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
      todayDate: todayStr
    });
  },

  // 加载数据
  async loadData() {
    this.setData({ loading: true });
    
    try {
      await Promise.all([
        this.loadTodayMedications(),
        this.loadMedicationRecords(),
        this.loadReminders(),
        this.loadStats(),
        this.loadAvailableMedications()
      ]);
    } catch (error) {
      console.error('加载数据失败:', error);
      wx.showToast({
        title: '加载失败',
        icon: 'error'
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  // 加载今日用药
  async loadTodayMedications() {
    // 模拟API调用
    const mockData = [
      {
        id: 1,
        name: '阿莫西林胶囊',
        dose: '500',
        unit: '毫克',
        type: '抗生素',
        time: '08:00',
        status: 'taken'
      },
      {
        id: 2,
        name: '维生素C片',
        dose: '100',
        unit: '毫克',
        type: '维生素',
        time: '12:00',
        status: 'pending'
      },
      {
        id: 3,
        name: '降压药',
        dose: '5',
        unit: '毫克',
        type: '心血管药物',
        time: '18:00',
        status: 'pending'
      }
    ];
    
    this.setData({
      todayMedications: mockData
    });
  },

  // 加载用药记录
  async loadMedicationRecords() {
    // 模拟API调用
    const mockData = [
      {
        id: 1,
        name: '阿莫西林胶囊',
        dose: '500',
        unit: '毫克',
        frequency: '每日三次',
        duration: '7天',
        date: '2024-01-15',
        progress: 85,
        status: 'active'
      },
      {
        id: 2,
        name: '维生素C片',
        dose: '100',
        unit: '毫克',
        frequency: '每日一次',
        duration: '30天',
        date: '2024-01-10',
        progress: 60,
        status: 'active'
      },
      {
        id: 3,
        name: '感冒灵颗粒',
        dose: '1',
        unit: '袋',
        frequency: '每日三次',
        duration: '5天',
        date: '2024-01-05',
        progress: 100,
        status: 'completed'
      }
    ];
    
    this.setData({
      medicationRecords: mockData
    });
  },

  // 加载提醒设置
  async loadReminders() {
    // 模拟API调用
    const mockData = [
      {
        id: 1,
        medicationName: '阿莫西林胶囊',
        time: '08:00',
        frequency: '每天',
        enabled: true
      },
      {
        id: 2,
        medicationName: '维生素C片',
        time: '12:00',
        frequency: '每天',
        enabled: true
      },
      {
        id: 3,
        medicationName: '降压药',
        time: '18:00',
        frequency: '每天',
        enabled: false
      }
    ];
    
    this.setData({
      reminders: mockData
    });
  },

  // 加载统计数据
  async loadStats() {
    // 模拟API调用
    const mockStats = {
      totalDays: 15,
      adherenceRate: 92,
      missedDoses: 3,
      onTimeRate: 88
    };
    
    this.setData({
      stats: mockStats
    });
  },

  // 加载可用药品
  async loadAvailableMedications() {
    const medications = this.data.medicationRecords.filter(record => record.status === 'active');
    this.setData({
      availableMedications: medications
    });
  },

  // 添加用药
  addMedication() {
    this.setData({
      showAddModal: true,
      newMedication: {
        name: '',
        type: '',
        typeIndex: 0,
        dose: '',
        unit: '',
        unitIndex: 0,
        frequency: '',
        frequencyIndex: 0,
        times: [''],
        duration: '',
        notes: ''
      }
    });
  },

  // 设置提醒
  setReminder() {
    if (this.data.availableMedications.length === 0) {
      wx.showToast({
        title: '请先添加用药记录',
        icon: 'none'
      });
      return;
    }
    
    this.setData({
      showReminderModal: true,
      newReminder: {
        medicationIndex: 0,
        time: '',
        frequency: '',
        frequencyIndex: 0,
        message: ''
      }
    });
  },

  // 服用药物
  takeMedication(e) {
    const id = e.currentTarget.dataset.id;
    const medications = this.data.todayMedications.map(item => {
      if (item.id === id) {
        return { ...item, status: 'taken' };
      }
      return item;
    });
    
    this.setData({
      todayMedications: medications
    });
    
    wx.showToast({
      title: '已记录服用',
      icon: 'success'
    });
  },

  // 跳过药物
  skipMedication(e) {
    const id = e.currentTarget.dataset.id;
    const medications = this.data.todayMedications.map(item => {
      if (item.id === id) {
        return { ...item, status: 'missed' };
      }
      return item;
    });
    
    this.setData({
      todayMedications: medications
    });
    
    wx.showToast({
      title: '已标记跳过',
      icon: 'none'
    });
  },

  // 查看用药详情
  viewMedicationDetail(e) {
    const id = e.currentTarget.dataset.id;
    // 跳转到详情页面
    wx.navigateTo({
      url: `/pages/medication-detail/medication-detail?id=${id}`
    });
  },

  // 查看记录详情
  viewRecordDetail(e) {
    const id = e.currentTarget.dataset.id;
    // 跳转到记录详情页面
    wx.navigateTo({
      url: `/pages/medication-record/medication-record?id=${id}`
    });
  },

  // 查看全部记录
  viewAllRecords() {
    wx.navigateTo({
      url: '/pages/medication-records/medication-records'
    });
  },

  // 管理提醒
  manageReminders() {
    wx.navigateTo({
      url: '/pages/medication-reminders/medication-reminders'
    });
  },

  // 切换提醒开关
  toggleReminder(e) {
    const id = e.currentTarget.dataset.id;
    const enabled = e.detail.value;
    
    const reminders = this.data.reminders.map(item => {
      if (item.id === id) {
        return { ...item, enabled };
      }
      return item;
    });
    
    this.setData({
      reminders: reminders
    });
    
    wx.showToast({
      title: enabled ? '提醒已开启' : '提醒已关闭',
      icon: 'success'
    });
  },

  // 表单输入处理
  onInputChange(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;
    
    this.setData({
      [`newMedication.${field}`]: value
    });
  },

  // 药品类型选择
  onTypeChange(e) {
    const index = e.detail.value;
    this.setData({
      'newMedication.typeIndex': index,
      'newMedication.type': this.data.medicationTypes[index]
    });
  },

  // 剂量单位选择
  onUnitChange(e) {
    const index = e.detail.value;
    this.setData({
      'newMedication.unitIndex': index,
      'newMedication.unit': this.data.doseUnits[index]
    });
  },

  // 服用频率选择
  onFrequencyChange(e) {
    const index = e.detail.value;
    const frequency = this.data.frequencies[index];
    
    // 根据频率设置时间数组
    let times = [''];
    if (frequency.includes('两次')) {
      times = ['', ''];
    } else if (frequency.includes('三次')) {
      times = ['', '', ''];
    } else if (frequency.includes('四次')) {
      times = ['', '', '', ''];
    }
    
    this.setData({
      'newMedication.frequencyIndex': index,
      'newMedication.frequency': frequency,
      'newMedication.times': times
    });
  },

  // 服用时间选择
  onTimeChange(e) {
    const index = e.currentTarget.dataset.index;
    const time = e.detail.value;
    const times = [...this.data.newMedication.times];
    times[index] = time;
    
    this.setData({
      'newMedication.times': times
    });
  },

  // 提醒相关处理
  onReminderInputChange(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;
    
    this.setData({
      [`newReminder.${field}`]: value
    });
  },

  onReminderMedicationChange(e) {
    const index = e.detail.value;
    this.setData({
      'newReminder.medicationIndex': index
    });
  },

  onReminderTimeChange(e) {
    const time = e.detail.value;
    this.setData({
      'newReminder.time': time
    });
  },

  onReminderFrequencyChange(e) {
    const index = e.detail.value;
    this.setData({
      'newReminder.frequencyIndex': index,
      'newReminder.frequency': this.data.reminderFrequencies[index]
    });
  },

  // 保存用药
  async saveMedication() {
    const medication = this.data.newMedication;
    
    // 验证必填字段
    if (!medication.name || !medication.dose || !medication.duration) {
      wx.showToast({
        title: '请填写完整信息',
        icon: 'none'
      });
      return;
    }
    
    // 验证时间
    const validTimes = medication.times.filter(time => time);
    if (validTimes.length === 0) {
      wx.showToast({
        title: '请设置服用时间',
        icon: 'none'
      });
      return;
    }
    
    try {
      // 模拟API调用
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      wx.showToast({
        title: '添加成功',
        icon: 'success'
      });
      
      this.setData({
        showAddModal: false
      });
      
      // 重新加载数据
      this.loadData();
    } catch (error) {
      console.error('保存用药失败:', error);
      wx.showToast({
        title: '保存失败',
        icon: 'error'
      });
    }
  },

  // 保存提醒
  async saveReminder() {
    const reminder = this.data.newReminder;
    
    // 验证必填字段
    if (!reminder.time || !reminder.frequency) {
      wx.showToast({
        title: '请填写完整信息',
        icon: 'none'
      });
      return;
    }
    
    try {
      // 模拟API调用
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      wx.showToast({
        title: '设置成功',
        icon: 'success'
      });
      
      this.setData({
        showReminderModal: false
      });
      
      // 重新加载数据
      this.loadReminders();
    } catch (error) {
      console.error('保存提醒失败:', error);
      wx.showToast({
        title: '保存失败',
        icon: 'error'
      });
    }
  },

  // 关闭弹窗
  closeAddModal() {
    this.setData({
      showAddModal: false
    });
  },

  closeReminderModal() {
    this.setData({
      showReminderModal: false
    });
  },

  // 获取状态名称
  getStatusName(status) {
    const statusMap = {
      active: '进行中',
      completed: '已完成',
      paused: '已暂停',
      stopped: '已停止'
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
      title: '智能用药管理',
      path: '/pages/medication/medication'
    };
  }
});