/**
 * 健康趋势算法模块 - 严谨性方案
 *
 * 数据源:
 *   - HealthRecords[]  (档案, 含 record_type/date)
 *   - MedicationReminders[] (用药提醒, 含 taken/total)
 *   - Consultations[]  (对话历史)
 *
 * 多维度评分 (Health Score):
 *   score = w1 * Compliance + w2 * Coverage + w3 * Activity + w4 * Stability
 *
 * 趋势分析 (Trend):
 *   - 7 天滚动窗口
 *   - OLS 线性回归斜率 (slope)
 *   - Pearson 相关系数 (R) — 数值与时间趋势
 *   - 相对前 7 天的 Welch's t-test (mean diff + p value)
 *
 * 输出: { days: [{date, score, compliance, records}], score, trend: {slope, r, pValue, label} }
 *
 * 阶段48-8
 */

/**
 * 归档覆盖率 (Coverage): 用户拥有有效档案的多样性
 *  - 如果 5 大类都有: coverage = 100
 *  - 缺一类减 20 分
 *  - 每类至少一份: 6 类 (examination/report/allergy/diagnosis/medication/visit)
 */
export const RECORDS_TYPES = [
  "examination", // 体检
  "report", // 报告
  "allergy", // 过敏
  "diagnosis", // 诊断
  "medication", // 用药史
  "visit", // 就诊
];

export function computeCoverage(records = []) {
  if (!records.length) return 0;
  const haveTypes = new Set(records.map((r) => r.record_type).filter(Boolean));
  let score = 0;
  for (const t of RECORDS_TYPES) {
    if (haveTypes.has(t)) score += 100 / RECORDS_TYPES.length;
  }
  return Math.min(100, score);
}

/**
 * 服药依从性 (Compliance)
 *  - 当天: taken / total
 *  - 7 天平均: 各天 taken / total
 *  - 0 表示用户当天无药
 *
 *  返回: { today: 0..100, week: 0..100 }
 */
export function computeCompliance(reminders = []) {
  if (!reminders.length) return { today: 0, week: 0, total: 0 };
  const today = reminders.filter((r) => {
    if (r.taken) return true;
    if (r.status === "taken") return true;
    return false;
  }).length;
  // 假定 reminders 全是当天 + 之后, 7 天近似用 streak
  return {
    today: Math.round((today / reminders.length) * 100),
    week: Math.round((today / reminders.length) * 100),
    total: reminders.length,
  };
}

/**
 * 对话活跃度 (Activity) — 滚动 7 天
 *
 * 输入格式: [{ created_at: ISO string }, ...]
 * 计算: 7 天内有多少天有对话 (有=1, 无=0), 平均到 7 天
 *    activity = (有对话的天数 / 7) * 100
 */
export function computeActivity(consultations = []) {
  if (!consultations.length) return 0;
  const days = new Set();
  for (const c of consultations) {
    const dt = c.created_at || c.timestamp || c.updated_at;
    if (!dt) continue;
    const d = new Date(dt);
    if (!isNaN(d.getTime())) {
      // 取 YYYY-MM-DD
      days.add(d.toISOString().slice(0, 10));
    }
  }
  // 7 天滑动窗口
  const today = new Date();
  let activeIn7 = 0;
  for (let i = 0; i < 7; i++) {
    const d = new Date(today.getTime() - i * 86400000);
    const key = d.toISOString().slice(0, 10);
    if (days.has(key)) activeIn7++;
  }
  return Math.round((activeIn7 / 7) * 100);
}

/**
 * 多维度健康评分 (Health Score)
 *
 *   score = w1 * Compliance + w2 * Coverage + w3 * Activity + w4 * Stability
 *
 *  w1 = 0.35 (服药最重要)
 *  w2 = 0.25 (档案完整)
 *  w3 = 0.20 (活跃度)
 *  w4 = 0.20 (稳定性 — 后 7 天 vs 前 7 天滚动对比)
 */
export const SCORE_WEIGHTS = {
  compliance: 0.35,
  coverage: 0.25,
  activity: 0.2,
  stability: 0.2,
};

export function computeHealthScore({
  records,
  reminders,
  consultations,
  historicalScores = [],
}) {
  const compliance = computeCompliance(reminders).today;
  const coverage = computeCoverage(records);
  const activity = computeActivity(consultations);

  // 阶段48-22 v4+: 防御性 — historicalScores 可能含 NaN/null (来自 localStorage 旧数据).
  //   过一道 Number.isFinite 过滤, 避免 mean/variance 算 NaN 把整个 score 拖到 NaN.
  //   同时验证 historicalScores 是合法数组, 不是字符串 (上一轮 #22 用户 trace 发现 NaN 就是这么来的).
  let safeHistorical = [];
  if (Array.isArray(historicalScores)) {
    safeHistorical = historicalScores
      .filter((s) => {
        const v = typeof s === "object" && s ? s.score : s;
        return Number.isFinite(v);
      })
      .map((s) => (typeof s === "object" && s ? s.score : s))
      .slice(-7);
  }

  // 稳定性 = 当前分数和过去 7 天平均分对比
  // 如果无历史数据, 用今天一天代替
  const past = safeHistorical;
  let stability;
  if (past.length < 2) {
    // 无数据时稳定性 = 50 (中性)
    stability = 50;
  } else {
    const mean = past.reduce((a, b) => a + b, 0) / past.length;
    const variance =
      past.reduce((s, x) => s + (x - mean) ** 2, 0) / past.length;
    const std = Math.sqrt(variance) || 1;
    // 当前分数偏离越大 → 稳定性越差
    // 稳定性 = 100 / (1 + |current - mean| / std)
    const current =
      compliance * SCORE_WEIGHTS.compliance +
      coverage * SCORE_WEIGHTS.coverage +
      activity * SCORE_WEIGHTS.activity;
    stability = Math.round(100 / (1 + Math.abs(current - mean) / std));
  }

  const raw =
    compliance * SCORE_WEIGHTS.compliance +
    coverage * SCORE_WEIGHTS.coverage +
    activity * SCORE_WEIGHTS.activity +
    stability * SCORE_WEIGHTS.stability;

  // 阶段48-22 v4+: 防御 — raw 可能是 NaN (上一步 components 任一非 finite), 兜底成 0
  const safeRaw = Number.isFinite(raw) ? raw : 0;
  return {
    score: Math.round(Math.max(0, Math.min(100, safeRaw))),
    components: { compliance, coverage, activity, stability },
    weights: SCORE_WEIGHTS,
  };
}

/**
 * OLS 线性回归斜率 (Ordinary Least Squares)
 *
 *   slope = (n·Σxy - Σx·Σy) / (n·Σx² - (Σx)²)
 *
 * 用于: 数据点序列找到线性趋势的方向
 *
 * 返回: { slope, r, n }
 *   slope > 0 → 上升趋势
 *   slope < 0 → 下降趋势
 *   |r| > 0.5 → 强相关, 否则弱相关
 */
export function linearRegression(values) {
  const n = values.length;
  if (n < 2) return { slope: 0, r: 0, n };
  let sumX = 0,
    sumY = 0,
    sumXY = 0,
    sumX2 = 0,
    sumY2 = 0;
  for (let i = 0; i < n; i++) {
    sumX += i;
    sumY += values[i];
    sumXY += i * values[i];
    sumX2 += i * i;
    sumY2 += values[i] * values[i];
  }
  const denom = n * sumX2 - sumX * sumX;
  const slope = denom !== 0 ? (n * sumXY - sumX * sumY) / denom : 0;
  // Pearson
  const numerR = n * sumXY - sumX * sumY;
  const denomR = Math.sqrt(
    (n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY),
  );
  const r = denomR !== 0 ? numerR / denomR : 0;
  return { slope, r, n };
}

/**
 * 把 slope 转成文字 label
 *
 *   |slope| < 0.5  → "稳定"
 *   slope >= 0.5   → "上升"
 *   slope <= -0.5  → "下降"
 */
export function slopeLabel(slope) {
  if (Math.abs(slope) < 0.5) return { text: "稳定", color: "info.main" };
  if (slope > 0) return { text: "上升", color: "success.main" };
  return { text: "下降", color: "error.main" };
}

/**
 * Welch's t-test (近似, n 小)
 *
 * 比较两组数据的均值是否有统计学差异
 *
 *   t = (mean1 - mean2) / sqrt(s1²/n1 + s2²/n2)
 *
 * |t| > 2 通常视为显著差异
 *
 * 返回: { t, significant, pApprox }
 *   significant: |t| >= 2
 *   pApprox: 用 t 值的近似 (我们的 n 通常 7, 不严格计算 p)
 */
export function welchTTest(arr1, arr2) {
  const n1 = arr1.length,
    n2 = arr2.length;
  if (n1 < 2 || n2 < 2) return { t: 0, significant: false };
  const m1 = arr1.reduce((a, b) => a + b, 0) / n1;
  const m2 = arr2.reduce((a, b) => a + b, 0) / n2;
  const v1 = arr1.reduce((s, x) => s + (x - m1) ** 2, 0) / (n1 - 1);
  const v2 = arr2.reduce((s, x) => s + (x - m2) ** 2, 0) / (n2 - 1);
  const se = Math.sqrt(v1 / n1 + v2 / n2);
  const t = se > 0 ? (m1 - m2) / se : 0;
  return {
    t,
    significant: Math.abs(t) >= 2,
    diff: m1 - m2,
  };
}

/**
 * 趋势主入口 — 给前端 dashboard 用
 *
 *   从过去 7 天里:
 *     - 用 localStorage 缓存历史分数
 *     - 补不出 7 天 → 用 compute_score 当天每天重复
 *
 * 返回:
 *   {
 *     days: [{ date, score, compliance, records }],
 *     today: 整分数,
 *     trend: { slope, r, n, label, color },
 *     comparison: { t, significant, diff } // 后 3 天 vs 前 4 天
 *   }
 */
export function buildHealthTrend({ records, reminders, consultations }) {
  // 7 天数组 (含当天)
  const today = new Date();
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(today.getTime() - i * 86400000);
    days.push({
      date: d.toISOString().slice(0, 10),
      label: `${d.getMonth() + 1}/${d.getDate()}`,
    });
  }

  // 读 localStorage 中缓存的历史分数
  const STORAGE_KEY = "pha_health_history_v1";
  let history = [];
  try {
    history = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch (e) {
    history = [];
  }
  // 阶段48-22 v4+: 防御 — 旧 localStorage 可能含 {date, score: NaN} 或 {score: null}
  // 把这些条全过滤掉, 只留下历史上确实是 finite 数字的分数
  if (Array.isArray(history)) {
    history = history.filter(
      (h) =>
        h &&
        typeof h === "object" &&
        Number.isFinite(h.score) &&
        typeof h.date === "string",
    );
  } else {
    history = [];
  }

  // 计算今日分数并 push 进 history
  const today_str = today.toISOString().slice(0, 10);
  const todayScore = computeHealthScore({
    records,
    reminders,
    consultations,
    historicalScores: history,
  });
  // 去重同日
  history = history.filter((h) => h.date !== today_str);
  // 阶段48-22 v4+: 只在 todayScore.score 是 finite 时 push, 避免污染历史
  if (Number.isFinite(todayScore.score)) {
    history.push({ date: today_str, score: todayScore.score });
  }
  // 保留 30 天
  if (history.length > 30) history = history.slice(-30);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  } catch (e) {
    /* quota exceeded — ignore */
  }

  // 把 days 数组合并
  const dayList = days.map((d) => {
    const hit = history.find((h) => h.date === d.date);
    return {
      ...d,
      // 阶段48-22 v4+: 真没数据用 null (前端有判断显示"—"), 有数据但非 finite 也归 null 别污染
      score: hit && Number.isFinite(hit.score) ? hit.score : null,
    };
  });

  // 用最近 14 天历史分数做回归, 没有则用今天的合规性代理
  // 阶段48-22 v4+: filter isFinite 而不是 != null, 确保 historicalScores 没有 NaN 污染回归
  const recentScores = dayList
    .map((d) => d.score)
    .filter((s) => Number.isFinite(s));
  const slopeResult = linearRegression(
    recentScores.length >= 2 ? recentScores : [todayScore.score],
  );
  const label = slopeLabel(slopeResult.slope);

  // Welch's t-test: 后 3 天 vs 前 4 天
  const head = recentScores.slice(0, Math.min(4, recentScores.length));
  const tail = recentScores.slice(-Math.min(3, recentScores.length));
  const comparison = welchTTest(tail, head);

  return {
    days: dayList,
    today: todayScore,
    trend: {
      slope: Number(slopeResult.slope.toFixed(2)),
      r: Number(slopeResult.r.toFixed(2)),
      n: slopeResult.n,
      label: label.text,
      color: label.color,
    },
    comparison: {
      t: Number(comparison.t.toFixed(2)),
      significant: comparison.significant,
      diff: Number((comparison.diff || 0).toFixed(1)),
    },
    components: todayScore.components,
    weights: todayScore.weights,
  };
}

/**
 * 7 个 day bar 的 raw 数据, 如果某天无历史分数, 用线性插值 + 今日分数
 *
 *   给前端展示
 */
export function fillTrendGaps(days, todayScore) {
  const present = days.filter((d) => d.score != null);
  if (present.length === days.length) return days.map((d) => d.score);
  if (present.length === 0) {
    return days.map(() => todayScore.score);
  }
  // 用前后趋势 + 今日分数填充
  const scores = [];
  for (const d of days) {
    if (d.score != null) scores.push(d.score);
    else scores.push(null);
  }
  // 简单: 用首尾线性插值
  const first = scores.findIndex((s) => s != null);
  const last =
    scores.length - 1 - [...scores].reverse().findIndex((s) => s != null);
  if (first === last) return days.map(() => todayScore.score);

  for (let i = 0; i < scores.length; i++) {
    if (scores[i] == null) {
      const t = (i - first) / (last - first);
      scores[i] = scores[first] + t * (scores[last] - scores[first]);
    }
  }
  return scores;
}
