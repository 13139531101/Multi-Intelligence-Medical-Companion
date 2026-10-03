/**
 * pageContract — 「AI 操控页面」的唯一词汇表
 *
 * 背景
 * ----
 * 此前这套协议有**三套互不兼容且全是死的**词汇表：
 *   - ComponentRegistry.jsx 的 COMPONENT_TYPES / ACTIONS（下划线小写，如 'health_records_table'）
 *   - usePageUpdater.jsx 的 PAGE_COMPONENTS（PascalCase，里面还有个从未存在过的 'PageRouter'）
 *   - 实际注册的 'TodayDashboard'
 * 三套谁也没引用谁，读代码的人无从判断哪个才是真契约。
 *
 * 现在收敛到这里：前端所有注册/调用都从这里取名字。
 *
 * 后端没有对应的 Python 模块 —— 产出 page_update 的工具散落在三个互不依赖的
 * 包里（HealthAdvisor / MedicationReminder / HealthRecordsManager），它们没法
 * 从 A2AServer 里 import 常量。所以后端是**字面量复制**，改名字时要一起改：
 *   - HealthAdvisor/mcpserver/a2a_integration_tool.py   (AiInfoCard)
 *   - MedicationReminder/mcpserver/reminder_tool.py     (AiInfoCard)
 *   - HealthRecordsManager/mcpserver/page_control_tool.py
 *       (PageRouter / HealthRecordsPage)
 * 用 `grep -rn '"component":' backend --include='*_tool.py'` 可以一次列全。
 * （注意别在注释里写 backend 斜杠星号 斜杠mcpserver —— 那个 "星号斜杠" 会提前
 *   结束本注释块，把后面的中文当成代码解析，报一个莫名其妙的 EOF 语法错。）
 *
 * 改动约定
 * --------
 * - 新增可被 AI 操控的页面：在 PAGE_COMPONENTS 加名字，页面里 usePageUpdater 注册同名
 * - 后端工具产出 page_update 时，component/action 必须取自本表
 * - 'TodayDashboard' 不要改名：它是跨 5 个文件的活跃生产者/消费者对
 */

export const PAGE_COMPONENTS = {
  /** 全局路由代理，挂在 <Router> 内、始终挂载 —— 导航因此永远可用 */
  PAGE_ROUTER: 'PageRouter',
  /** 页面无关的 AI 信息卡片区。TodayDashboard 和 Dashboard 都注册它，
   *  所以同一个工具在哪个页面都能把卡片投出来 */
  AI_INFO_CARD: 'AiInfoCard',
  /** /v2/today —— 历史遗留名，勿改 */
  TODAY_DASHBOARD: 'TodayDashboard',
  /** /v2/dashboard */
  DASHBOARD: 'Dashboard',
  /** /v2/health-records */
  HEALTH_RECORDS: 'HealthRecordsPage',
};

export const PAGE_ACTIONS = {
  /** 往卡片区追加一张结构化结果卡片 */
  SET_DATA: 'setData',
  /** 路由跳转 */
  NAVIGATE_TO: 'navigateTo',
  /** 全局提示 */
  SHOW_ALERT: 'showAlert',
  /** 重新拉取页面数据 */
  REFRESH: 'refresh',
  /** 打开某条健康档案的详情弹窗 */
  OPEN_RECORD: 'openRecord',
  /** 设置档案页的分类筛选 */
  SET_FILTER: 'setFilter',
  /** 设置档案页的搜索词 */
  SET_SEARCH: 'setSearch',
  /** 把 AI 抽取的字段填进「新增档案」表单。
   *  注意：只填表，**不提交** —— 用户核对后自己点「创建」才真正入库。
   *  这是「AI 填 → 人确认」这条链路的落点，也是它安全的原因。 */
  FILL_FORM: 'fillForm',
  /** 驱动页面内嵌对话框发起一次提问 */
  ASK_AGENT: 'askAgent',
  /** 高亮某张 agent 卡片 */
  HIGHLIGHT_AGENT: 'highlightAgent',
};

/** 单条待执行指令在注册表里的存活时长。短一点，避免陈旧指令突然触发。 */
export const PENDING_TTL_MS = 10000;

/** 待执行队列上限，超出丢最旧 */
export const PENDING_MAX = 20;

export default PAGE_COMPONENTS;
