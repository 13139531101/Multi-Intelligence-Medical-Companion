// health-records.js
const { request, uploadFile } = require("../../utils/api");

Page({
  data: {
    records: [],
    filteredRecords: [],
    searchKeyword: "",
    activeFilter: "all",
    activeTag: "all",
    tagOptions: [],
    loading: false,
    hasMore: true,
    page: 1,
    limit: 10,

    // 弹窗相关
    showModal: false,
    isEditing: false,
    currentRecordId: null,
    formData: {
      title: "",
      type: "",
      hospital: "",
      description: "",
      tagsText: "",
      file_id: "",
      file_name: "",
      record_id: "",
    },
    typeOptions: ["检查报告", "处方单", "病历", "化验单", "影像资料", "其他"],
    typeValues: [
      "examination",
      "prescription",
      "diagnosis",
      "examination",
      "examination",
      "other",
    ],
    typeIndex: 0,
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

  onLoad() {
    this.loadRecords();
  },

  onShow() {
    // 每次显示页面时刷新数据
    this.loadRecords();
  },

  // 空函数，用于阻止冒泡
  noop() {},

  // 加载健康档案列表
  async loadRecords(refresh = true) {
    if (this.data.loading && !refresh) return;

    this.setData({ loading: true });

    try {
      const page = refresh ? 1 : this.data.page;
      const response = await request("/api/health-records", {
        method: "GET",
        data: {
          skip: (page - 1) * this.data.limit,
          limit: this.data.limit,
        },
      });

      let recordsData = [];
      if (Array.isArray(response)) {
        recordsData = response;
      } else if (response && response.records) {
        recordsData = response.records;
      }

      if (recordsData) {
        const formattedRecords = recordsData.map((record) => {
          const typeLabel = this.getTypeLabel(record.type);
          const createdAt = record.date || record.created_at;
          const rawDesc = this.sanitizeSummary(
            record,
            record.description || record.summary || "",
          );
          const contentText = record.content ? String(record.content) : "";
          const contentTrimmed = contentText.trim();
          const hasFiles =
            Array.isArray(record.files) && record.files.length > 0;
          const rawTrimmed = String(rawDesc || "").trim();
          const displayDesc = contentTrimmed
            ? contentTrimmed
            : rawTrimmed
              ? rawTrimmed
              : hasFiles
                ? "已上传附件，内容待识别"
                : "";
          const displayTitle = this.getDisplayTitle(record);
          return {
            ...record,
            record_type_label: typeLabel,
            formatted_date: this.formatDate(createdAt),
            tags: this.normalizeTags(record.tags),
            description: rawDesc,
            display_description: displayDesc,
            display_title: displayTitle,
          };
        });

        const records = refresh
          ? formattedRecords
          : [...this.data.records, ...formattedRecords];

        const tagSet = new Set();
        records.forEach((r) => {
          (r.tags || []).forEach((t) => {
            if (t) tagSet.add(t);
          });
        });

        this.setData({
          records,
          page: page + 1,
          hasMore: recordsData.length === this.data.limit,
          tagOptions: Array.from(tagSet),
        });

        this.filterRecords();
      }
    } catch (error) {
      console.error("加载健康档案失败:", error);
      wx.showToast({
        title: "加载失败",
        icon: "error",
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
      5,
    );
    if (diagnosis) parts.push(`诊断：${diagnosis}`);
    const meds = this.normalizeMedications(info.medications, 5);
    if (meds) parts.push(`用药：${meds}`);
    const tests = this.normalizeTests(info.test_results || info.tests, 5);
    if (tests) parts.push(`检查：${tests}`);
    const advice = this.normalizeTextField(
      info.medical_advice || info.advice,
      5,
    );
    if (advice) parts.push(`医嘱：${advice}`);
    return this.sanitizeSummaryText(parts.join("；"));
  },

  normalizeTextField(value, limit = 5) {
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

  normalizeMedications(value, limit = 5) {
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

  normalizeTests(value, limit = 5) {
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

  truncateText(text, maxLen) {
    const s = String(text || "").trim();
    if (!s) return "";
    if (!maxLen || s.length <= maxLen) return s;
    return `${s.slice(0, maxLen)}...`;
  },

  // 搜索输入
  onSearchInput(e) {
    this.setData({
      searchKeyword: e.detail.value,
    });
    this.filterRecords();
  },

  // 设置筛选条件
  setFilter(e) {
    const filter = e.currentTarget.dataset.filter;
    this.setData({
      activeFilter: filter,
    });
    this.filterRecords();
  },

  setTagFilter(e) {
    const tag = e.currentTarget.dataset.tag;
    this.setData({
      activeTag: tag,
    });
    this.filterRecords();
  },

  // 筛选档案
  filterRecords() {
    let filtered = [...this.data.records];

    // 按类型筛选
    if (this.data.activeFilter !== "all") {
      const filterMap = {
        report: ["examination"],
        prescription: ["prescription"],
        other: ["other", "diagnosis", "surgery"],
      };

      const filterType = filterMap[this.data.activeFilter];
      if (Array.isArray(filterType)) {
        filtered = filtered.filter((record) =>
          filterType.includes(record.type),
        );
      } else {
        filtered = filtered.filter((record) => record.type === filterType);
      }
    }

    if (this.data.activeTag !== "all") {
      filtered = filtered.filter((record) =>
        (record.tags || []).includes(this.data.activeTag),
      );
    }

    // 按关键词搜索
    if (this.data.searchKeyword) {
      const keyword = this.data.searchKeyword.toLowerCase();
      filtered = filtered.filter(
        (record) =>
          String(record.display_title || record.title || "")
            .toLowerCase()
            .includes(keyword) ||
          String(record.display_description || record.description || "")
            .toLowerCase()
            .includes(keyword) ||
          String(record.hospital || "")
            .toLowerCase()
            .includes(keyword),
      );
    }

    this.setData({
      filteredRecords: filtered,
    });
  },

  // 查看档案详情
  viewRecord(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({
      url: `/pages/health-record-detail/health-record-detail?id=${id}`,
    });
  },

  // 添加档案
  addRecord() {
    this.setData({
      showModal: true,
      isEditing: false,
      currentRecordId: null,
      formData: {
        title: "",
        type: "",
        hospital: "",
        description: "",
        tagsText: "",
        file_id: "",
        file_name: "",
        record_id: "",
      },
      typeIndex: 0,
    });
  },

  // 编辑档案
  editRecord(e) {
    const id = e.currentTarget.dataset.id;
    const record = this.data.records.find((r) => r.id === id);

    if (record) {
      const typeLabel = this.getTypeLabel(record.type);
      const typeIndex = this.data.typeOptions.indexOf(typeLabel);

      this.setData({
        showModal: true,
        isEditing: true,
        currentRecordId: id,
        formData: {
          title: record.title || "",
          type: record.type || "",
          hospital: record.hospital || "",
          description: record.description || "",
          tagsText: Array.isArray(record.tags) ? record.tags.join("，") : "",
          file_id: Array.isArray(record.files) ? record.files[0] || "" : "",
          file_name:
            record.file_name ||
            (Array.isArray(record.files) ? record.files[0] || "" : ""),
          record_id: record.id || "",
        },
        typeIndex: typeIndex >= 0 ? typeIndex : 0,
      });
    }
  },

  // 删除档案
  deleteRecord(e) {
    const id = e.currentTarget.dataset.id;

    wx.showModal({
      title: "确认删除",
      content: "确定要删除这个健康档案吗？",
      success: async (res) => {
        if (res.confirm) {
          try {
            await request(`/api/health-records/${id}`, { method: "DELETE" });
            wx.showToast({
              title: "删除成功",
              icon: "success",
            });
            this.loadRecords();
          } catch (error) {
            console.error("删除档案失败:", error);
            wx.showToast({
              title: "删除失败",
              icon: "error",
            });
          }
        }
      },
    });
  },

  // 表单输入处理
  onTitleInput(e) {
    this.setData({
      "formData.title": e.detail.value,
    });
  },

  onTypeChange(e) {
    const index = parseInt(e.detail.value);
    this.setData({
      typeIndex: index,
      "formData.type": this.data.typeValues[index],
    });
  },

  onHospitalInput(e) {
    this.setData({
      "formData.hospital": e.detail.value,
    });
  },

  onDescInput(e) {
    this.setData({
      "formData.description": e.detail.value,
    });
  },

  onTagsInput(e) {
    this.setData({
      "formData.tagsText": e.detail.value,
    });
  },

  // 上传文件
  async uploadFile() {
    try {
      const actionRes = await wx.showActionSheet({
        itemList: ["拍照", "从相册选择"],
      });
      const sourceType = actionRes.tapIndex === 0 ? ["camera"] : ["album"];
      const res = await wx.chooseMedia({
        count: 1,
        mediaType: ["image"],
        sourceType,
        maxDuration: 30,
        camera: "back",
      });

      const tempFilePath =
        (res.tempFiles && res.tempFiles[0] && res.tempFiles[0].tempFilePath) ||
        (res.tempFilePaths && res.tempFilePaths[0]) ||
        "";
      if (tempFilePath) {
        wx.showLoading({
          title: "上传中...",
        });

        const uploadResult = await uploadFile(
          tempFilePath,
          "/api/health-records/upload",
          { skip_ocr: "1" },
        );
        let parsedResult = uploadResult;
        if (typeof parsedResult === "string") {
          try {
            parsedResult = JSON.parse(parsedResult);
          } catch (e) {
            parsedResult = null;
          }
        }
        if (parsedResult && parsedResult.result !== undefined) {
          parsedResult = parsedResult.result;
        }
        const fileId =
          parsedResult && (parsedResult.file_id || parsedResult.file_url);

        if (fileId) {
          this.setData({
            "formData.file_id": fileId,
            "formData.file_name":
              parsedResult.original_filename ||
              parsedResult.file_name ||
              parsedResult.filename ||
              "上传的文件",
            "formData.record_id": parsedResult.record_id || "",
          });

          wx.showToast({
            title: "上传成功",
            icon: "success",
          });
          if (parsedResult.record_id) {
            await this.loadRecords();
          }
        } else {
          throw new Error("上传失败");
        }
      }
    } catch (error) {
      if (error && error.errMsg && error.errMsg.includes("cancel")) {
        return;
      }
      console.error("上传文件失败:", error);
      wx.showToast({
        title: "上传失败",
        icon: "error",
      });
    } finally {
      wx.hideLoading();
    }
  },

  // 移除文件
  removeFile() {
    this.setData({
      "formData.file_id": "",
      "formData.file_name": "",
      "formData.record_id": "",
    });
  },

  // 保存档案
  async saveRecord() {
    const { title, type, hospital, description, file_id, tagsText, record_id } =
      this.data.formData;
    if (!file_id && !record_id && !this.data.isEditing) {
      wx.showToast({
        title: "请先上传图片",
        icon: "none",
      });
      return;
    }

    let timedOut = false;
    const loadingTitle = this.data.isEditing ? "保存中..." : "添加中...";
    wx.showLoading({
      title: loadingTitle,
    });
    const loadingTimer = setTimeout(() => {
      timedOut = true;
      wx.hideLoading();
      wx.showToast({
        title: "请求超时",
        icon: "error",
      });
    }, 20000);

    try {
      const tags = String(tagsText || "")
        .split(/[,，\s]+/g)
        .map((t) => t.trim())
        .filter((t) => t);

      const data = { tags };
      const cleanTitle = (title || "").trim();
      if (cleanTitle) {
        data.title = cleanTitle;
      } else if (this.data.isEditing || record_id) {
        data.title = "";
      }
      if (type) {
        data.type = type;
      } else if (!record_id && !this.data.isEditing) {
        data.type = this.data.typeValues[this.data.typeIndex] || "other";
      }
      if (hospital && hospital.trim()) {
        data.hospital = hospital.trim();
      }
      if (description && description.trim()) {
        if (this.data.isEditing || record_id) {
          data.summary = description.trim();
        } else {
          data.description = description.trim();
        }
      }
      if (file_id) {
        data.files = [file_id];
      }

      if (this.data.isEditing || record_id) {
        const targetId =
          (this.data.isEditing && this.data.currentRecordId) || record_id;
        await request(`/api/health-records/${targetId}`, {
          method: "PUT",
          data,
        });
        if (timedOut) return;
        wx.showToast({
          title: "保存成功",
          icon: "success",
        });
      } else {
        await request("/api/health-records", { method: "POST", data });
        if (timedOut) return;
        wx.showToast({
          title: "添加成功",
          icon: "success",
        });
      }

      if (timedOut) return;
      this.closeModal();
      this.loadRecords();
    } catch (error) {
      if (timedOut) return;
      console.error("保存档案失败:", error);
      wx.showToast({
        title: "保存失败",
        icon: "error",
      });
    } finally {
      clearTimeout(loadingTimer);
      if (!timedOut) {
        wx.hideLoading();
      }
    }
  },

  // 关闭弹窗
  closeModal() {
    this.setData({
      showModal: false,
    });
  },

  // 格式化日期
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

  // 下拉刷新
  onPullDownRefresh() {
    this.loadRecords();
    wx.stopPullDownRefresh();
  },
});
