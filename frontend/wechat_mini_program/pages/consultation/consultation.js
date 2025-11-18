// consultation.js
import { request } from "../../utils/api";

Page({
  data: {
    consultationHistory: [],
    loading: false,
    showTypeModal: false,
    selectedType: '',
    
    consultationTypes: [
      {
        value: 'symptom',
        name: '症状咨询',
        icon: '🤒',
        description: '描述您的症状，获取专业建议'
      },
      {
        value: 'medication',
        name: '用药咨询',
        icon: '💊',
        description: '药物使用方法和注意事项'
      },
      {
        value: 'health',
        name: '健康管理',
        icon: '💪',
        description: '日常健康管理和生活建议'
      },
      {
        value: 'report',
        name: '报告解读',
        icon: '📊',
        description: '医疗检查报告专业解读'
      },
      {
        value: 'nutrition',
        name: '营养咨询',
        icon: '🥗',
        description: '饮食营养搭配建议'
      },
      {
        value: 'exercise',
        name: '运动指导',
        icon: '🏃',
        description: '运动健身计划制定'
      }
    ]
  },

  onLoad() {
    this.loadConsultationHistory();
  },

  onShow() {
    // 每次显示页面时刷新数据
    this.loadConsultationHistory();
  },

  // 加载咨询历史
  async loadConsultationHistory() {
    if (this.data.loading) return;
    
    this.setData({ loading: true });
    
    try {
      const response = await request("/consultations", "GET", null, {
        limit: 10,
        skip: 0
      });
      
      if (response && Array.isArray(response)) {
        const formattedHistory = response.map(item => ({
          ...item,
          formatted_date: this.formatDate(item.created_at),
          type_name: this.getTypeName(item.consultation_type),
          status_name: this.getStatusName(item.status),
          preview: this.getPreview(item.messages),
          message_count: item.messages ? item.messages.length : 0
        }));
        
        this.setData({
          consultationHistory: formattedHistory
        });
      }
    } catch (error) {
      console.error("加载咨询历史失败:", error);
      // 如果API失败，显示空状态而不是错误提示
      this.setData({
        consultationHistory: []
      });
    } finally {
      this.setData({ loading: false });
    }
  },

  // 开始咨询
  startConsultation(e) {
    const type = e.currentTarget.dataset.type;
    this.createNewConsultation(type);
  },

  // 创建新的咨询会话
  async createNewConsultation(type) {
    try {
      wx.showLoading({
        title: '创建咨询中...'
      });

      const typeName = this.getTypeName(type);
      const data = {
        consultation_type: type,
        title: `${typeName} - ${this.formatDate(new Date())}`,
        status: 'active'
      };

      const response = await request("/consultations", "POST", data);
      
      if (response && response.id) {
        // 跳转到聊天页面
        wx.navigateTo({
          url: `/pages/agent-chat/agent-chat?consultationId=${response.id}&type=${type}`
        });
      } else {
        throw new Error('创建咨询失败');
      }
    } catch (error) {
      console.error("创建咨询失败:", error);
      wx.showToast({
        title: "创建咨询失败",
        icon: "error"
      });
    } finally {
      wx.hideLoading();
    }
  },

  // 查看咨询详情
  viewConsultation(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/agent-chat/agent-chat?consultationId=${id}`
    });
  },

  // 查看全部历史
  viewAllHistory() {
    wx.navigateTo({
      url: '/pages/consultation-history/consultation-history'
    });
  },

  // 显示类型选择弹窗
  showTypeSelection() {
    this.setData({
      showTypeModal: true
    });
  },

  // 关闭类型选择弹窗
  closeTypeModal() {
    this.setData({
      showTypeModal: false
    });
  },

  // 选择咨询类型
  selectType(e) {
    const type = e.currentTarget.dataset.type;
    this.closeTypeModal();
    this.createNewConsultation(type);
  },

  // 获取类型名称
  getTypeName(type) {
    const typeMap = {
      'symptom': '症状咨询',
      'medication': '用药咨询',
      'health': '健康管理',
      'report': '报告解读',
      'nutrition': '营养咨询',
      'exercise': '运动指导'
    };
    return typeMap[type] || '健康咨询';
  },

  // 获取状态名称
  getStatusName(status) {
    const statusMap = {
      'active': '进行中',
      'completed': '已完成',
      'pending': '待回复'
    };
    return statusMap[status] || '未知';
  },

  // 获取预览内容
  getPreview(messages) {
    if (!messages || messages.length === 0) {
      return '暂无对话内容';
    }
    
    const lastMessage = messages[messages.length - 1];
    const content = lastMessage.content || '';
    
    // 截取前50个字符作为预览
    return content.length > 50 ? content.substring(0, 50) + '...' : content;
  },

  // 格式化日期
  formatDate(dateString) {
    if (!dateString) return '';
    
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;
    
    // 如果是今天
    if (diff < 86400000 && date.getDate() === now.getDate()) {
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      return `今天 ${hours}:${minutes}`;
    }
    
    // 如果是昨天
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.getDate() === yesterday.getDate() && 
        date.getMonth() === yesterday.getMonth() && 
        date.getFullYear() === yesterday.getFullYear()) {
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      return `昨天 ${hours}:${minutes}`;
    }
    
    // 其他日期
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${month}-${day}`;
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadConsultationHistory();
    wx.stopPullDownRefresh();
  },

  // 分享功能
  onShareAppMessage() {
    return {
      title: '智能健康咨询',
      path: '/pages/consultation/consultation'
    };
  }
});