/**
 * ComponentRegistry - AI 页面组件控制注册表
 *
 * 页面组件挂载时把自己注册进来，AI 通过 page_update 指令调用其方法操作页面。
 * 名字与动作取自 src/ai/pageContract.js（唯一契约）。
 *
 * 为什么要有"待执行队列"
 * ----------------------
 * 指令是随 SSE 流实时到达的，而目标页面**可能还没挂载**。最典型的场景是
 * "跳转到某条记录"：后端先发 navigateTo、紧接着发 openRecord，此时用户还停在
 * 原页面，openRecord 的目标组件压根不存在。
 *
 * 早先的实现遇到未注册组件只 console.warn 然后丢弃，于是这条链路必然失效。
 * 现在改为**入队**：组件一旦注册，队列里属于它的、未过期的指令立刻被排空执行。
 *
 * 队列的三条不变量：
 *   - 有 TTL（默认 10s）：几分钟前的陈旧指令不会突然触发
 *   - 单次消费：排空时直接内部调用，不再走 call()，避免回环
 *   - 按 (name, method, params) 去重：同一事件可能重投（且 dev 下 StrictMode
 *     会双调 effect），重复的 openRecord 会在用户关掉弹窗后又把它弹开
 */

import { PENDING_TTL_MS, PENDING_MAX } from '../ai/pageContract';

class ComponentRegistry {
  constructor() {
    this.components = new Map();
    /** @type {Array<{name:string, method:string, params:any, sig:string, expiresAt:number}>} */
    this.pending = [];
  }

  /**
   * 注册一个可被 AI 控制的组件；顺带排空队列里属于它的待执行指令
   * @param {string} name - 组件名称，取自 PAGE_COMPONENTS
   * @param {object} methods - 组件暴露的方法
   */
  register(name, methods) {
    this.components.set(name, methods);
    console.log(`[ComponentRegistry] Registered: ${name}`, Object.keys(methods));
    this._drain(name);
  }

  /**
   * 注销组件。
   * 注意**不清空**属于它的待执行指令 —— 页面重新挂载后仍应能排空
   * （典型场景：跳走又跳回）。只顺手清掉已过期的。
   */
  unregister(name) {
    this.components.delete(name);
    this._purgeExpired();
    console.log(`[ComponentRegistry] Unregistered: ${name}`);
  }

  /** 检查组件是否已注册 */
  has(name) {
    return this.components.has(name);
  }

  /**
   * 调用组件的方法。目标未注册时**入队**而非丢弃。
   *
   * @returns {{queued: true}} 目标未挂载，已排队等待
   *          {error: string}  组件在但方法不存在
   *          any              方法的返回值
   */
  call(name, method, params) {
    const component = this.components.get(name);
    if (!component) {
      this._enqueue(name, method, params);
      console.log(
        `[ComponentRegistry] ${name} 未挂载, 已排队: ${method}`,
      );
      return { queued: true };
    }
    return this._invoke(component, name, method, params);
  }

  /** 内部调用：不做入队。排空路径也走这里，保证单次消费。 */
  _invoke(component, name, method, params) {
    if (typeof component[method] !== 'function') {
      console.warn(`[ComponentRegistry] Method not found: ${name}.${method}`);
      return { error: 'method_not_found' };
    }
    try {
      return component[method](params);
    } catch (e) {
      console.error(`[ComponentRegistry] Error calling ${name}.${method}:`, e);
      return { error: 'call_failed' };
    }
  }

  _sig(name, method, params) {
    let p;
    try {
      p = JSON.stringify(params);
    } catch {
      // 参数里有循环引用等无法序列化的东西时退化为不去重，总比抛异常好
      p = String(params);
    }
    return `${name}|${method}|${p}`;
  }

  _enqueue(name, method, params) {
    this._purgeExpired();
    const sig = this._sig(name, method, params);
    if (this.pending.some((e) => e.sig === sig)) return; // 去重
    this.pending.push({
      name,
      method,
      params,
      sig,
      expiresAt: Date.now() + PENDING_TTL_MS,
    });
    if (this.pending.length > PENDING_MAX) {
      // 丢最旧
      this.pending.splice(0, this.pending.length - PENDING_MAX);
    }
  }

  _purgeExpired() {
    const now = Date.now();
    this.pending = this.pending.filter((e) => e.expiresAt > now);
  }

  /** 排空属于 name 的、未过期的指令，每条只执行一次 */
  _drain(name) {
    this._purgeExpired();
    const component = this.components.get(name);
    if (!component) return;
    const mine = this.pending.filter((e) => e.name === name);
    if (!mine.length) return;
    // 先摘除再执行：即使方法内部又触发注册/调用，也不会重放
    this.pending = this.pending.filter((e) => e.name !== name);
    for (const e of mine) {
      console.log(`[ComponentRegistry] 排空待执行: ${e.name}.${e.method}`);
      this._invoke(component, e.name, e.method, e.params);
    }
  }

  /** 获取所有注册的组件名称 */
  list() {
    return Array.from(this.components.keys());
  }

  /** 当前待执行队列快照（调试用） */
  pendingList() {
    this._purgeExpired();
    return this.pending.map((e) => `${e.name}.${e.method}`);
  }
}

// 单例
export const componentRegistry = new ComponentRegistry();

export default componentRegistry;
