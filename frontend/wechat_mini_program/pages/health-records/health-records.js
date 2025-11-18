// health-records.js
import { request, uploadFile } from "../../utils/api";

Page({
  data: {
    records: [],
    filteredRecords: [],
    searchKeyword: '',
    activeFilter: 'all',
    loading: false,
    hasMore: true,
    page: 1,
    limit: 10,
    
    // 弹窗相关
    showModal: false,
    isEditing: false,
    currentRecordId: null,
    formData: {
      title: '',
      record_type: '',
      hospital: '',
      description: '',
      file_url: '',
      file_name: ''
    },
    typeOptions: ['检查报告', '处方单', '病历', '化验单', '影像资料', '其他'],
    typeIndex: 0
  },

  onLoad() {
    this.loadRecords();
  },

  onShow() {
    // 每次显示页面时刷新数据
    this.loadRecords();
  },

  // 加载健康档案列表
  async loadRecords(refresh = true) {
    if (this.data.loading) return;
    
    this.setData({ loading: true });
    
    try {
      const page = refresh ? 1 : this.data.page;
      const response = await request("/api/health-records", "GET", null, {
        skip: (page - 1) * this.data.limit,
        limit: this.data.limit
      });
      
      if (response && response.records) {
        const formattedRecords = response.records.map(record => ({
          ...record,
          formatted_date: this.formatDate(record.created_at)
        }));
        
        const records = refresh ? formattedRecords : [...this.data.records, ...formattedRecords];
        
        this.setData({
          records,
          page: page + 1,
          hasMore: response.records.length === this.data.limit
        });
        
        this.filterRecords();
      }
    } catch (error) {
      console.error("加载健康档案失败:", error);
      wx.showToast({
        title: "加载失败",
        icon: "error"
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  // 加载更多
  loadMore() {
    if (!this.data.hasMore || this.data.loading) return;
    this.loadRecords(false);
  },

  // 搜索输入
  onSearchInput(e) {
    this.setData({
      searchKeyword: e.detail.value
    });
    this.filterRecords();
  },

  // 设置筛选条件
  setFilter(e) {
    const filter = e.currentTarget.dataset.filter;
    this.setData({
      activeFilter: filter
    });
    this.filterRecords();
  },

  // 筛选档案
  filterRecords() {
    let filtered = [...this.data.records];
    
    // 按类型筛选
    if (this.data.activeFilter !== 'all') {
      const filterMap = {
        'report': '检查报告',
        'prescription': '处方单',
        'other': ['病历', '化验单', '影像资料', '其他']
      };
      
      const filterType = filterMap[this.data.activeFilter];
      if (Array.isArray(filterType)) {
        filtered = filtered.filter(record => filterType.includes(record.record_type));
      } else {
        filtered = filtered.filter(record => record.record_type === filterType);
      }
    }
    
    // 按关键词搜索
    if (this.data.searchKeyword) {
      const keyword = this.data.searchKeyword.toLowerCase();
      filtered = filtered.filter(record => 
        record.title.toLowerCase().includes(keyword) ||
        (record.description && record.description.toLowerCase().includes(keyword)) ||
        (record.hospital && record.hospital.toLowerCase().includes(keyword))
      );
    }
    
    this.setData({
      filteredRecords: filtered
    });
  },

  // 查看档案详情
  viewRecord(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/health-record-detail/health-record-detail?id=${id}`
    });
  },

  // 添加档案
  addRecord() {
    this.setData({
      showModal: true,
      isEditing: false,
      currentRecordId: null,
      formData: {
        title: '',
        record_type: '',
        hospital: '',
        description: '',
        file_url: '',
        file_name: ''
      },
      typeIndex: 0
    });
  },

  // 编辑档案
  editRecord(e) {
    const id = e.currentTarget.dataset.id;
    const record = this.data.records.find(r => r.id === id);
    
    if (record) {
      const typeIndex = this.data.typeOptions.indexOf(record.record_type);
      
      this.setData({
        showModal: true,
        isEditing: true,
        currentRecordId: id,
        formData: {
          title: record.title || '',
          record_type: record.record_type || '',
          hospital: record.hospital || '',
          description: record.description || '',
          file_url: record.file_url || '',
          file_name: record.file_name || ''
        },
        typeIndex: typeIndex >= 0 ? typeIndex : 0
      });
    }
  },

  // 删除档案
  deleteRecord(e) {
    const id = e.currentTarget.dataset.id;
    
    wx.showModal({
      title: '确认删除',
      content: '确定要删除这个健康档案吗？',
      success: async (res) => {
        if (res.confirm) {
          try {
            await request(`/api/health-records/${id}`, "DELETE");
            wx.showToast({
              title: "删除成功",
              icon: "success"
            });
            this.loadRecords();
          } catch (error) {
            console.error("删除档案失败:", error);
            wx.showToast({
              title: "删除失败",
              icon: "error"
            });
          }
        }
      }
    });
  },

  // 表单输入处理
  onTitleInput(e) {
    this.setData({
      'formData.title': e.detail.value
    });
  },

  onTypeChange(e) {
    const index = parseInt(e.detail.value);
    this.setData({
      typeIndex: index,
      'formData.record_type': this.data.typeOptions[index]
    });
  },

  onHospitalInput(e) {
    this.setData({
      'formData.hospital': e.detail.value
    });
  },

  onDescInput(e) {
    this.setData({
      'formData.description': e.detail.value
    });
  },

  // 上传文件
  async uploadFile() {
    try {
      const res = await wx.chooseMedia({
        count: 1,
        mediaType: ['image'],
        sourceType: ['album', 'camera'],
        maxDuration: 30,
        camera: 'back'
      });

      if (res.tempFiles && res.tempFiles.length > 0) {
        const tempFilePath = res.tempFiles[0].tempFilePath;
        
        wx.showLoading({
          title: '上传中...'
        });

        const uploadResult = await uploadFile(tempFilePath);
        
        if (uploadResult && uploadResult.file_url) {
          this.setData({
            'formData.file_url': uploadResult.file_url,
            'formData.file_name': uploadResult.file_name || '上传的文件'
          });
          
          wx.showToast({
            title: "上传成功",
            icon: "success"
          });
        } else {
          throw new Error('上传失败');
        }
      }
    } catch (error) {
      console.error("上传文件失败:", error);
      wx.showToast({
        title: "上传失败",
        icon: "error"
      });
    } finally {
      wx.hideLoading();
    }
  },

  // 移除文件
  removeFile() {
    this.setData({
      'formData.file_url': '',
      'formData.file_name': ''
    });
  },

  // 保存档案
  async saveRecord() {
    const { title, record_type, hospital, description, file_url } = this.data.formData;
    
    if (!title.trim()) {
      wx.showToast({
        title: "请输入档案标题",
        icon: "none"
      });
      return;
    }
    
    if (!record_type) {
      wx.showToast({
        title: "请选择档案类型",
        icon: "none"
      });
      return;
    }
    
    try {
      wx.showLoading({
        title: this.data.isEditing ? '保存中...' : '添加中...'
      });
      
      const data = {
        title: title.trim(),
        record_type,
        hospital: hospital.trim(),
        description: description.trim(),
        file_url
      };
      
      if (this.data.isEditing) {
        await request(`/api/health-records/${this.data.currentRecordId}`, "PUT", data);
        wx.showToast({
          title: "保存成功",
          icon: "success"
        });
      } else {
        await request("/api/health-records", "POST", data);
        wx.showToast({
          title: "添加成功",
          icon: "success"
        });
      }
      
      this.closeModal();
      this.loadRecords();
    } catch (error) {
      console.error("保存档案失败:", error);
      wx.showToast({
        title: "保存失败",
        icon: "error"
      });
    } finally {
      wx.hideLoading();
    }
  },

  // 关闭弹窗
  closeModal() {
    this.setData({
      showModal: false
    });
  },

  // 格式化日期
  formatDate(dateString) {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    
    return `${year}-${month}-${day}`;
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadRecords();
    wx.stopPullDownRefresh();
  }
});