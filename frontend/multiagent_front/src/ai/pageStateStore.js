/**
 * pageStateStore — AI 可控页面的**幂等状态**，AG-UI 标准 STATE_DELTA 的落点
 *
 * 为什么要有这个文件
 * ----------------
 * 「AI 操控页面」原来只有一条通道：自建的 PAGE_UPDATE 事件 → componentRegistry.call()。
 * 那是**动作派发**语义（「执行 X，现在」），对瞬态副作用（toast / 刷新 / 打开弹窗）
 * 是对的；但对「我在哪、我在看什么」这类**幂等状态**就绕了 —— 明明可以走 AG-UI
 * 原生的 STATE_DELTA 状态通道。
 *
 * 阶段48-31 加了第二条通道，两条并行、互不替代：
 *
 *   幂等状态  →  STATE_DELTA  →  pageStateStore（本文件）→ 页面订阅
 *   瞬态动作  →  PAGE_UPDATE  →  componentRegistry.call()   ← 原样不动
 *
 * 分栏依据是**幂等性**，不是随手切的：状态重放一次无害（「筛到检查」说两遍还是
 * 筛到检查）；动作重放一次会出事（弹窗重弹、toast 卡住）。所以 refresh 没有状态
 * 可收敛、showAlert 是瞬态事件，它们留在动作通道。详见
 * docs/Chinese/INTERVIEW_PREP.md 的「12 动作映射表」。
 *
 * 状态形状（刻意扁平、按页面命名空间化）
 * ------------------------------------
 *   {
 *     route: "/v2/health-records",                          // 全局路由
 *     healthRecords: { filter: "exam", search: "血压" },     // /v2/health-records
 *     medication:    { view: "week" },                       // /v2/medication
 *   }
 *
 * 单一真相（重要）
 * --------------
 * 页面**读**这里；页面上的用户交互（点 tab、打字搜索）也**写回**这里。
 * usePageUpdater 里注册的 setFilter / setSearch / setView 同样改成写这里 ——
 * 于是两条通道（STATE_DELTA 与 PAGE_UPDATE）汇聚到同一个 store，不会出现
 * 「AI 改了一份、用户改的是另一份」的双真相。
 */

import { useSyncExternalStore } from 'react';

/** 空状态。页面读不到键时各自用默认值，所以这里不给默认值。 */
const EMPTY = Object.freeze({});

/**
 * RFC 6901 JSON Pointer 反转义：~1 → /、~0 → ~。
 *
 * 顺序不能反 —— 必须先解 ~1 再解 ~0。反过来的话，字符串 "~01" 会被先解成
 * "~1"、再被当成转义符解成 "/"，而正确答案是 "~1"。
 */
function unescapePointer(token) {
  return token.replace(/~1/g, '/').replace(/~0/g, '~');
}

/**
 * 极简 RFC 6902 JSON Patch 应用器。
 *
 * 为什么手写而不是装 fast-json-patch
 * --------------------------------
 * 项目里没有这个依赖，而我们只需要 add / replace / remove 三个 op、路径全是
 * 普通对象键。引一个库不值当。后端 bridge._page_state_to_json_patch 实际只产出
 * add（RFC 6902 规定 add 到**已存在的对象成员**即等于替换），另两个是容错保留。
 *
 * 返回**新的** state 对象（不可变），让 useSyncExternalStore 的快照引用稳定。
 */
export function applyJsonPatch(target, ops) {
  if (!Array.isArray(ops) || !ops.length) return target;

  const next = { ...(target || EMPTY) };

  for (const op of ops) {
    if (!op || typeof op.path !== 'string') continue;
    const segs = op.path.split('/').slice(1).map(unescapePointer);
    if (!segs.length || !segs[0]) continue;

    if (segs.length === 1) {
      const key = segs[0];
      if (op.op === 'remove') {
        delete next[key];
      } else {
        next[key] = op.value;
      }
      continue;
    }

    // 多级路径：逐层拷贝出新对象（本项目状态只有一层嵌套）
    const [head, ...rest] = segs;
    const branch = { ...(next[head] && typeof next[head] === 'object' ? next[head] : {}) };
    let cursor = branch;
    for (let i = 0; i < rest.length - 1; i++) {
      const k = rest[i];
      cursor[k] = { ...(cursor[k] && typeof cursor[k] === 'object' ? cursor[k] : {}) };
      cursor = cursor[k];
    }
    const last = rest[rest.length - 1];
    if (op.op === 'remove') {
      delete cursor[last];
    } else {
      cursor[last] = op.value;
    }
    next[head] = branch;
  }

  return next;
}

class PageStateStore {
  constructor() {
    this.state = EMPTY;
    this.listeners = new Set();
  }

  /** useSyncExternalStore 的订阅入口。返回 unsubscribe。 */
  subscribe = (listener) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  /** useSyncExternalStore 的快照入口。引用稳定 —— 只在变更时整体替换。 */
  getState = () => this.state;

  _emit() {
    for (const l of this.listeners) l();
  }

  /** 顶层浅合并写入。页面自身的用户交互走这里。 */
  set(patch) {
    if (!patch || typeof patch !== 'object') return;
    this.state = { ...this.state, ...patch };
    this._emit();
  }

  /** 应用一条 AG-UI STATE_DELTA 的 JSON Patch ops。AI 通道走这里。 */
  applyPatch(ops) {
    const next = applyJsonPatch(this.state, ops);
    if (next === this.state) return;
    this.state = next;
    this._emit();
  }

  /** 清空。登出或换用户时用。 */
  reset() {
    if (this.state === EMPTY) return;
    this.state = EMPTY;
    this._emit();
  }
}

export const pageStateStore = new PageStateStore();

/**
 * 订阅页面状态，返回**整个** state 对象。
 *
 * 注意：这里刻意不做 selector。getState 返回的引用是稳定的，但 selector 每次
 * 会构造新对象，useSyncExternalStore 会因此无限重渲染。顶层只有 3 个键，
 * 全量订阅足够便宜 —— 要哪个字段直接解构：
 *
 *   const { medication } = usePageState();
 *   const view = medication?.view ?? 'today';
 */
export function usePageState() {
  return useSyncExternalStore(pageStateStore.subscribe, pageStateStore.getState);
}

export default pageStateStore;
