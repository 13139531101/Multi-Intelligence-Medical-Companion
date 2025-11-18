// visit-summary.js
Page({
  data: {
    // 最近摘要
    recentSummaries: [],
    
    // 摘要分类
    categories: [
      { type: 'outpatient', name: '门诊', icon: '🏥', count: 0 },
      { type: 'emergency', name: '急诊', icon: '🚑', count: 0 },
      { type: 'inpatient', name: '住院', icon: '🛏️', count: 0 },
      { type: 'checkup', name: '体检', icon: '🔍', count: 0 },
      { type: 'surgery', name: '手术', icon: '⚕️', count: 0 },
      { type: 'followup', name: '复诊', icon: '📅', count: 0 }
    ],
    
    // 智能分析趋势
    trends: {
      visitFrequency: 60,
      visitCount: 8,
      healthIndex: 75,
      healthScore: 85,
      medicationAdherence: 90,
      adherenceRate: 92,
      summary: '您的健康状况总体良好，建议继续保持良好的生活习惯和按时用药。'
    },
    
    // 健康建议
    suggestions: [],
    
    // 弹窗状态
    showCreateModal: false,
    showManualModal: false,
    showUploadModal: false,
    
    // 新摘要表单
    newSummary: {
      type: '',
      typeIndex: 0,
      date: '',
      hospital: '',
      department: '',
      doctor: '',
      symptoms: '',
      diagnosis: '',
      treatment: '',
      medication: '',
      followUp: ''
    },
    
    // 上传表单
    uploadForm: {
      type: '',
      typeIndex: 0,
      date: '',
      notes: ''
    },
    
    // 上传的图片
    uploadedImages: [],
    
    // 选项数据
    visitTypes: ['门诊', '急诊', '住院', '体检', '手术', '复诊', '其他'],
    reportTypes: ['血常规', '尿常规', '生化检查', 'X光片', 'CT扫描', 'MRI', '超声检查', '心电图', '其他'],
    
    // 状态
    generating: false,
    uploading: false,
    loading: false
  },

  onLoad() {
    this.loadData();
  },

  onShow() {
    this.loadRecentSummaries();
  },

  // 加载数据
  async loadData() {
    this.setData({ loading: true });
    
    try {
      await Promise.all([
        this.loadRecentSummaries(),
        this.loadCategories(),
        this.loadSuggestions()
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

  // 加载最近摘要
  async loadRecentSummaries() {
    // 模拟API调用
    const mockData = [
      {
        id: 1,
        type: '门诊',
        title: '感冒发烧就诊',
        hospital: '市人民医院',
        date: '2024-01-20',
        summary: '患者因发热、咳嗽就诊，诊断为上呼吸道感染，给予抗感染治疗，症状好转。',
        tags: ['发热', '咳嗽', '上呼吸道感染'],
        status: 'completed'
      },
      {
        id: 2,
        type: '体检',
        title: '年度健康体检',
        hospital: '体检中心',
        date: '2024-01-15',
        summary: '年度体检结果显示各项指标基本正常，血压略高，建议注意饮食和运动。',
        tags: ['体检', '血压', '健康'],
        status: 'completed'
      },
      {
        id: 3,
        type: '复诊',
        title: '高血压复诊',
        hospital: '社区医院',
        date: '2024-01-10',
        summary: '血压控制良好，继续服用降压药，定期监测血压变化。',
        tags: ['高血压', '复诊', '降压药'],
        status: 'active'
      }
    ];
    
    this.setData({
      recentSummaries: mockData
    });
  },

  // 加载分类统计
  async loadCategories() {
    // 模拟API调用
    const categories = this.data.categories.map(cat => ({
      ...cat,
      count: Math.floor(Math.random() * 10) + 1
    }));
    
    this.setData({
      categories: categories
    });
  },

  // 加载健康建议
  async loadSuggestions() {
    // 模拟API调用
    const mockSuggestions = [
      {
        id: 1,
        icon: '🏃',
        title: '增加运动量',
        description: '建议每周进行3-4次有氧运动，每次30分钟以上',
        priority: 'high'
      },
      {
        id: 2,
        icon: '🥗',
        title: '调整饮食结构',
        description: '减少高盐高脂食物摄入，多吃蔬菜水果',
        priority: 'medium'
      },
      {
        id: 3,
        icon: '💊',
        title: '按时服药',
        description: '严格按照医嘱服用降压药，不可随意停药',
        priority: 'high'
      },
      {
        id: 4,
        icon: '😴',
        title: '改善睡眠质量',
        description: '保持规律作息，每天睡眠时间不少于7小时',
        priority: 'medium'
      }
    ];
    
    this.setData({
      suggestions: mockSuggestions
    });
  },

  // 创建摘要
  createSummary() {
    this.setData({
      showCreateModal: true
    });
  },

  // 上传报告
  uploadReport() {
    this.setData({
      showUploadModal: true,
      uploadedImages: [],
      uploadForm: {
        type: '',
        typeIndex: 0,
        date: '',
        notes: ''
      }
    });
  },

  // 选择创建类型
  selectCreateType(e) {
    const type = e.currentTarget.dataset.type;
    
    this.setData({
      showCreateModal: false
    });
    
    if (type === 'manual') {
      this.setData({
        showManualModal: true,
        newSummary: {
          type: '',
          typeIndex: 0,
          date: '',
          hospital: '',
          department: '',
          doctor: '',
          symptoms: '',
          diagnosis: '',
          treatment: '',
          medication: '',
          followUp: ''
        }
      });
    } else if (type === 'upload') {
      this.uploadReport();
    } else if (type === 'chat') {
      wx.navigateTo({
        url: '/pages/agent_chat/agent_chat?mode=summary'
      });
    }
  },

  // 查看摘要详情
  viewSummaryDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/summary-detail/summary-detail?id=${id}`
    });
  },

  // 查看全部摘要
  viewAllSummaries() {
    wx.navigateTo({
      url: '/pages/all-summaries/all-summaries'
    });
  },

  // 查看分类摘要
  viewCategorySummaries(e) {
    const type = e.currentTarget.dataset.type;
    wx.navigateTo({
      url: `/pages/category-summaries/category-summaries?type=${type}`
    });
  },

  // 表单输入处理
  onInputChange(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;
    
    this.setData({
      [`newSummary.${field}`]: value
    });
  },

  onUploadInputChange(e) {
    const field = e.currentTarget.dataset.field;
    const value = e.detail.value;
    
    this.setData({
      [`uploadForm.${field}`]: value
    });
  },

  // 类型选择
  onTypeChange(e) {
    const index = e.detail.value;
    this.setData({
      'newSummary.typeIndex': index,
      'newSummary.type': this.data.visitTypes[index]
    });
  },

  onReportTypeChange(e) {
    const index = e.detail.value;
    this.setData({
      'uploadForm.typeIndex': index,
      'uploadForm.type': this.data.reportTypes[index]
    });
  },

  // 日期选择
  onDateChange(e) {
    const date = e.detail.value;
    this.setData({
      'newSummary.date': date
    });
  },

  onReportDateChange(e) {
    const date = e.detail.value;
    this.setData({
      'uploadForm.date': date
    });
  },

  // 选择图片
  chooseImage() {
    const maxCount = 5 - this.data.uploadedImages.length;
    
    wx.chooseImage({
      count: maxCount,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const images = [...this.data.uploadedImages, ...res.tempFilePaths];
        this.setData({
          uploadedImages: images
        });
      },
      fail: (error) => {
        console.error('选择图片失败:', error);
        wx.showToast({
          title: '选择图片失败',
          icon: 'error'
        });
      }
    });
  },

  // 删除图片
  deleteImage(e) {
    const index = e.currentTarget.dataset.index;
    const images = this.data.uploadedImages.filter((_, i) => i !== index);
    this.setData({
      uploadedImages: images
    });
  },

  // 生成摘要
  async generateSummary() {
    const summary = this.data.newSummary;
    
    // 验证必填字段
    if (!summary.type || !summary.date || !summary.hospital || !summary.symptoms) {
      wx.showToast({
        title: '请填写完整信息',
        icon: 'none'
      });
      return;
    }
    
    this.setData({ generating: true });
    
    try {
      // 模拟AI生成摘要
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      wx.showToast({
        title: '摘要生成成功',
        icon: 'success'
      });
      
      this.setData({
        showManualModal: false,
        generating: false
      });
      
      // 重新加载数据
      this.loadRecentSummaries();
    } catch (error) {
      console.error('生成摘要失败:', error);
      wx.showToast({
        title: '生成失败',
        icon: 'error'
      });
      this.setData({ generating: false });
    }
  },

  // 上传并生成
  async uploadAndGenerate() {
    const form = this.data.uploadForm;
    const images = this.data.uploadedImages;
    
    // 验证必填字段
    if (!form.type || !form.date || images.length === 0) {
      wx.showToast({
        title: '请填写完整信息',
        icon: 'none'
      });
      return;
    }
    
    this.setData({ uploading: true });
    
    try {
      // 模拟上传和AI分析
      await new Promise(resolve => setTimeout(resolve, 3000));
      
      wx.showToast({
        title: '上传成功，摘要已生成',
        icon: 'success'
      });
      
      this.setData({
        showUploadModal: false,
        uploading: false
      });
      
      // 重新加载数据
      this.loadRecentSummaries();
    } catch (error) {
      console.error('上传失败:', error);
      wx.showToast({
        title: '上传失败',
        icon: 'error'
      });
      this.setData({ uploading: false });
    }
  },

  // 关闭弹窗
  closeCreateModal() {
    this.setData({
      showCreateModal: false
    });
  },

  closeManualModal() {
    this.setData({
      showManualModal: false
    });
  },

  closeUploadModal() {
    this.setData({
      showUploadModal: false
    });
  },

  // 获取状态名称
  getStatusName(status) {
    const statusMap = {
      active: '进行中',
      completed: '已完成',
      pending: '待处理'
    };
    return statusMap[status] || status;
  },

  // 获取优先级名称
  getPriorityName(priority) {
    const priorityMap = {
      high: '重要',
      medium: '一般',
      low: '较低'
    };
    return priorityMap[priority] || priority;
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
      title: '智能就诊摘要',
      path: '/pages/visit-summary/visit-summary'
    };
  }
});