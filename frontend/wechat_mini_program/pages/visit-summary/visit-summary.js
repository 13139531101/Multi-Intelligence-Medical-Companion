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
          const readDisplayFields = (testsArr) => {
            const tests = Array.isArray(testsArr) ? testsArr : [];
            const block = tests.find(
              (t) => t && t.type === "display_fields_v1" && t.data,
            );
            if (!block) return null;
            const data = block.data;
            return data && typeof data === "object" ? data : null;
          };

          const fmtDate = (v) => {
            const s = String(v || "").trim();
            if (!s || s === "null" || s === "undefined") return "";
            return s;
          };
          const fmtDateTime = (v) => {
            const s = String(v || "").trim();
            if (!s || s === "null" || s === "undefined") return "";
            const m = s.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/);
            if (m) return `${m[1]} ${m[2]}`;
            return s.replace("T", " ").slice(0, 16);
          };

          const compactText = (raw, maxLen) => {
            const s = String(raw || "").trim();
            if (!s) return "";
            const first = s.split(/\n|；|;|，|,/g)[0].trim();
            if (first.length <= maxLen) return first;
            return first.slice(0, maxLen) + "…";
          };

          const extractKeyPoints = (raw, maxItems = 3) => {
            const text = String(raw || "").trim();
            if (!text) return [];
            const pieces = text
              .split(/\n|。|；|;|，|,/g)
              .map((s) => String(s || "").trim())
              .filter(Boolean)
              .map((s) => (s.length > 40 ? s.slice(0, 40) + "…" : s));
            const uniq = [];
            for (const p of pieces) {
              if (!p) continue;
              if (uniq.includes(p)) continue;
              uniq.push(p);
              if (uniq.length >= maxItems) break;
            }
            return uniq;
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
            (id) => `${SERVER_URL}/api/health-records/files/${id}`,
          );

          let agentMedNames = [];
          const tests = Array.isArray(item.tests) ? item.tests : [];
          const df = readDisplayFields(tests);
          const agentBlock = tests.find(
            (t) => t && t.type === "agent_summary" && t.data && t.data.content,
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
          if (df && Array.isArray(df.medications) && df.medications.length) {
            medTags = df.medications
              .map((s) => String(s || "").trim())
              .filter(Boolean);
          } else if (agentMedNames.length) {
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
            (item.summary_content || item.notes || "").trim(),
          );
          const hospitalFromDf = df ? String(df.hospital || "").trim() : "";
          const departmentFromDf = df ? String(df.department || "").trim() : "";
          const doctorFromDf = df ? String(df.doctor || "").trim() : "";
          const hospitalDisplay =
            compactText(hospitalFromDf || item.hospital, 16) ||
            (item.hospital ? "未知医院" : "未知医院");
          const followUpFromDf =
            df && Array.isArray(df.follow_up) ? df.follow_up : [];
          const followUpText =
            followUpFromDf
              .map((s) => String(s || "").trim())
              .filter(Boolean)
              .join("；") || item.follow_up;
          const followUpDisplay = compactText(followUpText, 26);

          const statusRaw = String(item.status || "")
            .trim()
            .toLowerCase();
          let statusDisplay = "";
          let statusClass = "";
          if (statusRaw === "processing" || statusRaw === "pending") {
            statusDisplay = "整理中";
            statusClass = "processing";
          } else if (statusRaw === "failed") {
            statusDisplay = "失败";
            statusClass = "failed";
          }

          const visitDateDisplay =
            fmtDate(item.visit_date) ||
            fmtDateTime(item.created_at) ||
            fmtDateTime(item.updated_at) ||
            "";

          const diagnosisFromDf =
            df && Array.isArray(df.diagnosis) ? df.diagnosis : [];
          const diagnosisText =
            diagnosisFromDf
              .map((s) => String(s || "").trim())
              .filter(Boolean)
              .join("；") || String((item.diagnosis || "").trim());
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
              `用药：${medShort}${medTags.length > 2 ? "等" : ""}`,
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
          const keyPointsFromDf =
            df && Array.isArray(df.key_points) ? df.key_points : [];
          const adviceFromDf = df && Array.isArray(df.advice) ? df.advice : [];
          const keyPoints = [
            ...keyPointsFromDf
              .map((s) => String(s || "").trim())
              .filter(Boolean),
            ...adviceFromDf.map((s) => String(s || "").trim()).filter(Boolean),
          ]
            .filter(Boolean)
            .slice(0, 3);
          const keyPointsFallback = extractKeyPoints(summaryText, 3);

          return {
            ...item,
            hospitalDisplay,
            departmentDisplay: compactText(departmentFromDf, 18),
            doctorDisplay: compactText(doctorFromDf, 18),
            visitDateDisplay,
            statusDisplay,
            statusClass,
            diagnosisDisplay,
            fileIds,
            fileUrls,
            medTags,
            summaryText,
            summaryPreview,
            canExpand,
            followUpDisplay,
            keyPoints: keyPoints.length ? keyPoints : keyPointsFallback,
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

  async pollSummary(summaryId) {
    const id = String(summaryId || "").trim();
    if (!id) return;

    const startTs = Date.now();
    const pollOnce = async () => {
      if (Date.now() - startTs > 3 * 60 * 1000) return;
      try {
        const detail = await request(`/api/visit-summaries/${id}`);
        const status = String((detail && detail.status) || "")
          .trim()
          .toLowerCase();
        if (status === "done") {
          await this.loadSummaries();
          wx.showToast({ title: "整理完成", icon: "success" });
          return;
        }
        if (status === "failed") {
          await this.loadSummaries();
          wx.showToast({ title: "整理失败", icon: "none" });
          return;
        }
      } catch (e) {
        // ignore
      }
      setTimeout(pollOnce, 3000);
    };

    setTimeout(pollOnce, 2000);
  },

  chooseImage() {
    const that = this;
    wx.showActionSheet({
      itemList: ["从相册选择(可多选)", "拍照(单张)"],
      success(res) {
        if (res.tapIndex === 0) {
          wx.chooseImage({
            count: 9,
            sizeType: ["compressed"],
            sourceType: ["album"],
            success(imgRes) {
              const paths = (imgRes.tempFilePaths || []).filter(Boolean);
              if (!paths.length) return;
              that.uploadImages(paths);
            },
          });
          return;
        }

        wx.chooseImage({
          count: 1,
          sizeType: ["compressed"],
          sourceType: ["camera"],
          success(imgRes) {
            const paths = (imgRes.tempFilePaths || []).filter(Boolean);
            if (!paths.length) return;
            that.uploadImages(paths);
          },
        });
      },
    });
  },

  async uploadImage(filePath) {
    return this.uploadImages([filePath]);
  },

  async uploadImages(filePaths) {
    const that = this;

    const userInfo = wx.getStorageSync("userInfo");

    try {
      const paths = Array.isArray(filePaths) ? filePaths.filter(Boolean) : [];
      if (!paths.length) return;

      const batchId = `batch_${Date.now()}_${Math.random()
        .toString(36)
        .substr(2, 8)}`;

      for (let i = 0; i < paths.length; i++) {
        wx.showLoading({
          title: `上传中(${i + 1}/${paths.length})...`,
          mask: true,
        });
        await uploadFile(paths[i], "/api/visit-summaries/batch/collect-image", {
          user_id: (userInfo && userInfo.user_id) || "",
          batch_id: batchId,
        });
      }

      wx.showLoading({ title: "提交中...", mask: true });
      const created = await request("/api/visit-summaries/batch/complete", {
        method: "POST",
        data: { batch_id: batchId },
      });

      wx.hideLoading();
      wx.showToast({
        title: "已提交",
        icon: "success",
      });
      // 刷新列表
      await that.loadSummaries();
      if (created && created.id) {
        that.pollSummary(created.id);
      }
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
