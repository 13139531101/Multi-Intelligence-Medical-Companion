const { request, SERVER_URL } = require("../../utils/api");

Page({
  data: {
    record: null,
    isLoading: false,
    fileUrls: [],
    tagLabelMap: {
      test_report: "检查报告",
      inspection_report: "检查报告",
      lab_result: "检查报告",
      medical_record: "病历",
      hospital_record: "住院记录",
      vaccination_record: "疫苗记录",
      prescription: "处方单",
      surgery: "手术记录",
      imaging: "影像资料",
      radiology: "影像资料",
      ocr: "OCR",
      auto_import: "自动导入",
    },
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
      const tags = this.normalizeTags(record.tags);
      const files = Array.isArray(record.files) ? record.files : [];
      const rawDesc = this.sanitizeSummary(
        record,
        record.description || record.summary || "",
      );
      const contentText = record.content ? String(record.content) : "";
      const contentTrimmed = contentText.trim();
      const rawTrimmed = String(rawDesc || "").trim();
      const displayDesc = contentTrimmed
        ? contentTrimmed
        : rawTrimmed
          ? rawTrimmed
          : files.length
            ? "已上传附件，内容待识别"
            : "暂无内容";
      const fileUrls = files.map((f) => this.resolveFileUrl(f)).filter(Boolean);

      const displayTitle = this.getDisplayTitle(record);

      this.setData({
        record: {
          ...record,
          record_type_label: typeLabel,
          formatted_date: formattedDate,
          tags,
          description: rawDesc,
          display_description: displayDesc,
          display_title: displayTitle,
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
    const cleanedStored = this.sanitizeSummaryText(storedSummary);
    if (cleanedStored && !this.isDocTypeToken(cleanedStored))
      return cleanedStored;
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
    return this.sanitizeSummaryText(parts.join("\n"));
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

  isDocTypeToken(value) {
    const key = String(value || "")
      .trim()
      .toLowerCase();
    if (!key) return false;
    const tokens = new Set([
      "test_report",
      "inspection_report",
      "lab_result",
      "medical_record",
      "hospital_record",
      "vaccination_record",
      "prescription",
      "surgery",
      "imaging",
      "radiology",
      "ocr",
      "auto_import",
      "检查报告",
      "病历",
      "住院记录",
      "疫苗记录",
      "处方单",
      "手术记录",
      "影像资料",
      "自动导入",
    ]);
    return tokens.has(key);
  },

  sanitizeSummaryText(value) {
    const text = String(value || "");
    if (!text.trim()) return "";
    const cleaned = text
      .replace(/test_report/gi, "")
      .replace(/\btest\b/gi, "")
      .replace(/[；;，,、]\s*(?=[；;，,、])/g, "")
      .replace(/\s{2,}/g, " ")
      .trim();
    return cleaned.replace(/^[\s；;，,、]+|[\s；;，,、]+$/g, "").trim();
  },

  sanitizeSummary(record, value) {
    const text = this.sanitizeSummaryText(value);
    if (!text) return "";
    if (this.isDocTypeToken(text)) return "";
    const metadata =
      record && record.metadata && typeof record.metadata === "object"
        ? record.metadata
        : {};
    const docType =
      metadata.document_type ||
      metadata.doc_type ||
      (metadata.extracted_info || {}).document_type ||
      (metadata.extracted_data || {}).document_type ||
      "";
    if (docType && text === String(docType).trim()) return "";
    return text;
  },

  normalizeTags(tags) {
    const items = Array.isArray(tags) ? tags : [];
    return items.filter((tag) => {
      const key = String(tag || "")
        .trim()
        .toLowerCase();
      return key && key !== "test";
    });
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

  getDocTypeLabel(value) {
    const key = String(value || "")
      .trim()
      .toLowerCase();
    const mapping = {
      test_report: "检查报告",
      inspection_report: "检查报告",
      lab_result: "检查报告",
      medical_record: "病历",
      hospital_record: "住院记录",
      vaccination_record: "疫苗记录",
      prescription: "处方单",
      surgery: "手术记录",
      imaging: "影像资料",
      radiology: "影像资料",
    };
    return mapping[key] || "";
  },

  getRecordDocumentType(record) {
    const metadata =
      record && record.metadata && typeof record.metadata === "object"
        ? record.metadata
        : {};
    const ocrInfo =
      metadata.ocr_info && typeof metadata.ocr_info === "object"
        ? metadata.ocr_info
        : {};
    const docType =
      ocrInfo.document_type ||
      metadata.document_type ||
      metadata.doc_type ||
      "";
    if (docType) return docType;
    const tags = Array.isArray(record && record.tags) ? record.tags : [];
    const match = tags.find((t) => this.getDocTypeLabel(t));
    return match || "";
  },

  getDisplayTitle(record) {
    const title = String((record && record.title) || "").trim();
    if (!title) return "";
    const docType = this.getRecordDocumentType(record);
    const label = this.getDocTypeLabel(docType);
    if (!label) return title;
    const lowerTitle = title.toLowerCase();
    const lowerDoc = String(docType || "").toLowerCase();
    if (!lowerDoc) return title;
    if (lowerTitle === lowerDoc) return label;
    if (lowerTitle.startsWith(lowerDoc)) {
      const rest = title.slice(lowerDoc.length);
      const restTrim = rest.trim();
      if (!restTrim) return label;
      const sepMatch = restTrim.match(/^[-—－]+/);
      if (sepMatch) {
        const restContent = restTrim.replace(/^[-—－]+/, "").trim();
        return restContent ? `${label} - ${restContent}` : label;
      }
    }
    return title;
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
