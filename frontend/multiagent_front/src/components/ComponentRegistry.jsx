/**
 * ComponentRegistry - AI 页面组件控制注册表
 *
 * 页面组件注册自己，让 AI 可以通过指令操作页面：
 * - setData(data)        设置数据
 * - refresh()            刷新
 * - navigateTo(path)     跳转页面
 * - showModal(content)    弹窗
 * - highlight(id)        高亮
 *
 * 用法:
 *   import { componentRegistry } from './ComponentRegistry';
 *
 *   // 注册
 *   componentRegistry.register('HealthRecordsTable', {
 *     setData: (data) => setRecords(data),
 *     navigateTo: (path) => navigate(path),
 *   });
 *
 *   // 注销
 *   componentRegistry.unregister('HealthRecordsTable');
 */

class ComponentRegistry {
  constructor() {
    this.components = new Map();
  }

  /**
   * 注册一个可被 AI 控制的组件
   * @param {string} name - 组件名称，如 'HealthRecordsTable'
   * @param {object} methods - 组件暴露的方法
   */
  register(name, methods) {
    this.components.set(name, methods);
    console.log(`[ComponentRegistry] Registered: ${name}`, Object.keys(methods));
  }

  /**
   * 注销组件
   */
  unregister(name) {
    this.components.delete(name);
    console.log(`[ComponentRegistry] Unregistered: ${name}`);
  }

  /**
   * 检查组件是否已注册
   */
  has(name) {
    return this.components.has(name);
  }

  /**
   * 调用组件的方法
   * @param {string} name - 组件名称
   * @param {string} method - 方法名
   * @param {any} params - 参数
   * @returns {any} 方法返回值
   */
  call(name, method, params) {
    const component = this.components.get(name);
    if (!component) {
      console.warn(`[ComponentRegistry] Component not found: ${name}`);
      return null;
    }
    if (typeof component[method] !== 'function') {
      console.warn(`[ComponentRegistry] Method not found: ${name}.${method}`);
      return null;
    }
    try {
      return component[method](params);
    } catch (e) {
      console.error(`[ComponentRegistry] Error calling ${name}.${method}:`, e);
      return null;
    }
  }

  /**
   * 获取所有注册的组件名称
   */
  list() {
    return Array.from(this.components.keys());
  }
}

// 单例
export const componentRegistry = new ComponentRegistry();

// 预定义的组件类型（用于 AI 指令识别）
export const COMPONENT_TYPES = {
  HEALTH_RECORDS_TABLE: 'health_records_table',
  MEDICATION_LIST: 'medication_list',
  VISIT_SUMMARY_LIST: 'visit_summary_list',
  CHART: 'chart',
  SUMMARY_CARD: 'summary_card',
  ALERT: 'alert',
};

// 预定义的操作类型
export const ACTIONS = {
  SET_DATA: 'setData',
  REFRESH: 'refresh',
  NAVIGATE: 'navigateTo',
  SHOW_MODAL: 'showModal',
  HIGHLIGHT: 'highlight',
  CLEAR: 'clear',
  SET_FILTER: 'setFilter',
};
