const { request, SERVER_URL } = require("../../utils/api");

Page({
  data: {
    record: null,
    isLoading: false,
    fileUrls: [],
  },

  onLoad(options) {
    if (options && options.id) {
      this.loadRecord(options.id);
    }
  },

  async loadRecord(id) {
    this.setData({ isLoading: true });
    try {
      const record = await request(`/api/health-records/${id}`, {
        method: "GET",
      });
      const typeLabel = this.getTypeLabel(record.type);
      const createdAt = record.date || record.created_at;
      const formattedDate = this.formatDate(createdAt);
      const tags = Array.isArray(record.tags) ? record.tags : [];
      const files = Array.isArray(record.files) ? record.files : [];
      const fileUrls = files
        .map((f) => this.resolveFileUrl(f))
        .filter(Boolean);

      this.setData({
        record: {
          ...record,
          record_type_label: typeLabel,
          formatted_date: formattedDate,
          tags,
        },
        fileUrls,
      });
    } catch (error) {
      wx.showToast({
        title: "加载失败",
        icon: "error",
      });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  resolveFileUrl(fileId) {
    if (!fileId) return "";
    const s = String(fileId);
    if (s.startsWith("http://") || s.startsWith("https://")) return s;
    return `${SERVER_URL}/api/health-records/files/${s}`;
  },

  onFileTap(e) {
    const url = e.currentTarget.dataset.url;
    if (!url) return;
    wx.downloadFile({
      url,
      success: (res) => {
        const filePath = res.tempFilePath;
        wx.openDocument({
          filePath,
          showMenu: true,
          fail: () => {
            wx.previewImage({ urls: [url] });
          },
        });
      },
      fail: () => {
        wx.previewImage({ urls: [url] });
      },
    });
  },

  formatDate(dateString) {
    if (!dateString) return "";
    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  },

  getTypeLabel(type) {
    const mapping = {
      examination: "检查报告",
      prescription: "处方单",
      diagnosis: "病历",
      surgery: "病历",
      other: "其他",
    };
    return mapping[type] || "其他";
  },
});
