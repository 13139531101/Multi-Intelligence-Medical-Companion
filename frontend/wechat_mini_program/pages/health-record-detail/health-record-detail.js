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
      const structuredDesc = this.buildStructuredSummary(record);
      const rawDesc = record.description || record.summary || "";
      const contentText = record.content ? String(record.content) : "";
      const rawTrimmed = String(rawDesc || "").trim();
      const contentTrimmed = contentText.trim();
      const useContentForSummary =
        rawTrimmed &&
        contentTrimmed &&
        contentTrimmed.startsWith(rawTrimmed) &&
        contentTrimmed.length > rawTrimmed.length;
      const displayDesc =
        structuredDesc && structuredDesc.trim()
          ? structuredDesc
          : rawDesc && rawDesc.trim()
            ? useContentForSummary
              ? contentTrimmed
              : rawDesc
            : record.content && String(record.content).trim()
              ? String(record.content).trim()
              : files.length
                ? "已上传附件，内容待识别"
                : "暂无摘要";
      const fileUrls = files.map((f) => this.resolveFileUrl(f)).filter(Boolean);

      this.setData({
        record: {
          ...record,
          record_type_label: typeLabel,
          formatted_date: formattedDate,
          tags,
          description: rawDesc,
          display_description: displayDesc,
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

  buildStructuredSummary(record) {
    const metadata =
      record && record.metadata && typeof record.metadata === "object"
        ? record.metadata
        : {};
    const storedSummary =
      typeof metadata.structured_summary === "string"
        ? metadata.structured_summary.trim()
        : "";
    if (storedSummary) return storedSummary;
    let info = metadata.extracted_info || metadata.extracted_data || {};
    if (typeof info === "string") {
      try {
        info = JSON.parse(info);
      } catch (e) {
        info = {};
      }
    }
    if (!info || typeof info !== "object") return "";

    const parts = [];
    const diagnosis = this.normalizeTextField(
      info.diagnosis || info.diagnoses,
      8,
    );
    if (diagnosis) parts.push(`诊断：${diagnosis}`);
    const meds = this.normalizeMedications(info.medications, 8);
    if (meds) parts.push(`用药：${meds}`);
    const tests = this.normalizeTests(info.test_results || info.tests, 8);
    if (tests) parts.push(`检查：${tests}`);
    const advice = this.normalizeTextField(
      info.medical_advice || info.advice,
      8,
    );
    if (advice) parts.push(`医嘱：${advice}`);
    return parts.join("\n");
  },

  normalizeTextField(value, limit = 8) {
    if (Array.isArray(value)) {
      const items = value.map((v) => String(v || "").trim()).filter((v) => v);
      return items.slice(0, limit).join("；");
    }
    if (typeof value === "string") {
      return value.trim();
    }
    return "";
  },

  normalizeMedications(value, limit = 8) {
    if (Array.isArray(value)) {
      const items = value
        .map((item) => {
          if (!item) return "";
          if (typeof item === "string") return item.trim();
          if (typeof item === "object") {
            const name = String(item.name || "").trim();
            const dosage = String(item.dosage || "").trim();
            const frequency = String(item.frequency || "").trim();
            const duration = String(item.duration || "").trim();
            const usage = String(item.usage_instruction || "").trim();
            const pieces = [name, dosage, frequency, duration, usage].filter(
              (v) => v,
            );
            return pieces.join(" ");
          }
          return "";
        })
        .filter((v) => v);
      return items.slice(0, limit).join("、");
    }
    if (typeof value === "string") {
      return value.trim();
    }
    return "";
  },

  normalizeTests(value, limit = 8) {
    if (Array.isArray(value)) {
      const items = value
        .map((item) => {
          if (!item) return "";
          if (typeof item === "string") return item.trim();
          if (typeof item === "object") {
            const name = String(item.name || item.test_name || "").trim();
            const val = String(item.value || "").trim();
            const unit = String(item.unit || "").trim();
            const pieces = [name, val, unit].filter((v) => v);
            return pieces.join(" ");
          }
          return "";
        })
        .filter((v) => v);
      return items.slice(0, limit).join("、");
    }
    if (value && typeof value === "object") {
      const entries = Object.entries(value)
        .map(([k, v]) => {
          if (!v || typeof v !== "object") return "";
          const val = String(v.value || "").trim();
          const unit = String(v.unit || "").trim();
          const parts = [String(k || "").trim(), val, unit].filter((x) => x);
          return parts.join(" ");
        })
        .filter((v) => v);
      return entries.slice(0, limit).join("、");
    }
    return "";
  },

  previewImage(e) {
    const urls = e.currentTarget.dataset.urls || [];
    const current = e.currentTarget.dataset.current;
    if (!Array.isArray(urls) || !urls.length) return;
    wx.previewImage({
      urls,
      current: current || urls[0],
    });
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
