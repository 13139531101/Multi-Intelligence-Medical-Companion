// pages/visit-summary/visit-summary.js
const { request, SERVER_URL, uploadFile } = require("../../utils/api.js");

Page({
  data: {
    summaries: [],
    isLoading: false,
  },

  onLoad() {
    // Initial load handled by onShow
  },

  onShow() {
    this.loadSummaries();
  },

  async loadSummaries() {
    this.setData({ isLoading: true });
    try {
      // 调用后端API获取摘要列表
      const res = await request("/api/visit-summaries/history");

      if (res) {
        const normalized = (Array.isArray(res) ? res : []).map((item) => {
          const compactText = (raw, maxLen) => {
            const s = String(raw || "").trim();
            if (!s) return "";
            const first = s.split(/\n|；|;|，|,/g)[0].trim();
            if (first.length <= maxLen) return first;
            return first.slice(0, maxLen) + "…";
          };

          const files = Array.isArray(item.files) ? item.files : [];
          const fileIds = files
            .map((f) => {
              if (!f) return "";
              if (typeof f === "string") return f;
              return f.file_id || f.id || "";
            })
            .filter(Boolean);
          const fileUrls = fileIds.map(
            (id) => `${SERVER_URL}/api/health-records/files/${id}`
          );

          let agentMedNames = [];
          const tests = Array.isArray(item.tests) ? item.tests : [];
          const agentBlock = tests.find(
            (t) => t && t.type === "agent_summary" && t.data && t.data.content
          );
          const agentMeds =
            agentBlock &&
            agentBlock.data &&
            agentBlock.data.content &&
            Array.isArray(agentBlock.data.content.medications)
              ? agentBlock.data.content.medications
              : [];
          agentMedNames = agentMeds
            .map((m) => (m && m.name ? String(m.name).trim() : ""))
            .filter(Boolean);

          let medTags = [];
          if (agentMedNames.length) {
            medTags = agentMedNames;
          } else if (item.prescription) {
            const raw = String(item.prescription || "");
            const parts = raw
              .split(/[\n；;，,]/g)
              .map((s) => s.trim())
              .filter(Boolean);
            medTags = parts
              .map((s) => s.replace(/\s*\d.*$/, "").trim())
              .filter((s) => s.length >= 2 && s.length <= 20);
          }
          medTags = Array.from(new Set(medTags)).slice(0, 8);

          const summaryText = String(
            (item.summary_content || item.notes || "").trim()
          );
          const hospitalDisplay =
            compactText(item.hospital, 16) ||
            (item.hospital ? "未知医院" : "未知医院");
          const diagnosisText = String((item.diagnosis || "").trim());
          const diagnosisDisplay = compactText(diagnosisText, 22) || "未识别";
          const previewParts = [];
          if (
            diagnosisDisplay &&
            diagnosisDisplay !== "未识别" &&
            diagnosisDisplay !== "未提供"
          ) {
            previewParts.push(`诊断：${diagnosisDisplay.replace(/\s+/g, " ")}`);
          }
          if (medTags.length) {
            const medShort = medTags.slice(0, 2).join("、");
            previewParts.push(
              `用药：${medShort}${medTags.length > 2 ? "等" : ""}`
            );
          }
          const examinationText = String((item.examination || "").trim());
          if (examinationText) {
            const examShort = examinationText
              .split(/\n|；|;|，|,/g)[0]
              .trim()
              .slice(0, 30);
            if (examShort) previewParts.push(`检查：${examShort}`);
          }
          let summaryPreview = previewParts.filter(Boolean).join("；").trim();
          if (!summaryPreview) summaryPreview = summaryText;
          if (summaryPreview.length > 120)
            summaryPreview = summaryPreview.slice(0, 120) + "…";
          const canExpand =
            Boolean(summaryText) && summaryText.length > summaryPreview.length;

          return {
            ...item,
            hospitalDisplay,
            diagnosisDisplay,
            fileIds,
            fileUrls,
            medTags,
            summaryText,
            summaryPreview,
            canExpand,
            expanded: false,
          };
        });
        this.setData({
          summaries: normalized,
        });
      }
    } catch (err) {
      console.error("Failed to load summaries:", err);
      wx.showToast({
        title: "加载失败",
        icon: "none",
      });
    } finally {
      this.setData({ isLoading: false });
    }
  },

  chooseImage() {
    const that = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      success(res) {
        const tempFilePath = res.tempFiles[0].tempFilePath;
        that.uploadImage(tempFilePath);
      },
    });
  },

  async uploadImage(filePath) {
    const that = this;
    wx.showLoading({
      title: "识别整理中...",
      mask: true,
    });

    const userInfo = wx.getStorageSync("userInfo");

    try {
      const data = await uploadFile(
        filePath,
        "/api/visit-summaries/analyze-image",
        {
          user_id: userInfo.user_id || "",
        }
      );

      wx.hideLoading();
      wx.showToast({
        title: "整理完成",
        icon: "success",
      });
      // 刷新列表
      that.loadSummaries();
    } catch (err) {
      wx.hideLoading();
      console.error(err);
      // 401 is handled by uploadFile utility
      if (!err || err.statusCode !== 401) {
        wx.showToast({
          title: "上传失败",
          icon: "none",
        });
      }
    }
  },

  deleteSummary(e) {
    const id = e.currentTarget.dataset.id;
    if (!id) return;

    wx.showModal({
      title: "确认删除",
      content: "删除后不可恢复",
      confirmText: "删除",
      confirmColor: "#ff3b30",
      success: async (res) => {
        if (!res.confirm) return;
        wx.showLoading({ title: "删除中...", mask: true });
        try {
          await request(`/api/visit-summaries/delete/${id}`, {
            method: "DELETE",
          });
          wx.hideLoading();
          wx.showToast({ title: "已删除", icon: "success" });
          this.loadSummaries();
        } catch (err) {
          wx.hideLoading();
          console.error("Failed to delete summary:", err);
          wx.showToast({ title: "删除失败", icon: "none" });
        }
      },
    });
  },

  toggleExpand(e) {
    const id = e.currentTarget.dataset.id;
    const next = (this.data.summaries || []).map((s) => {
      if (!s || s.id !== id) return s;
      return { ...s, expanded: !s.expanded };
    });
    this.setData({ summaries: next });
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
});
