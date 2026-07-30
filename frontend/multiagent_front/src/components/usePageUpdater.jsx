/**
 * usePageUpdater - 让页面组件注册到 ComponentRegistry
 *
 * 用法:
 *   import { usePageUpdater } from './usePageUpdater';
 *   import { componentRegistry } from './ComponentRegistry';
 *
 *   function MyPage() {
 *     const [data, setData] = useState([]);
 *
 *     // 组件挂载时注册，卸载时注销
 *     usePageUpdater('MyPage', {
 *       setData: (params) => {
 *         setData(params.data || []);
 *       },
 *       refresh: () => { /* 刷新逻辑 *\/ },
 *     });
 *
 *     return <div>...</div>;
 *   }
 */

import { useEffect } from 'react';
import { componentRegistry } from './ComponentRegistry';

export function usePageUpdater(name, methods) {
  useEffect(() => {
    if (name && methods) {
      componentRegistry.register(name, methods);
    }
    return () => {
      if (name) {
        componentRegistry.unregister(name);
      }
    };
  }, [name, methods]);
}

// 预定义的组件注册配置，供 AI 使用
export const PAGE_COMPONENTS = {
  // 健康档案表格
  HealthRecordsTable: {
    description: '显示健康档案记录的表格',
    actions: ['setData', 'setFilter', 'refresh', 'highlight'],
    dataKey: 'healthRecords',
  },
  // 用药列表
  MedicationList: {
    description: '显示用药提醒列表',
    actions: ['setData', 'setFilter', 'refresh'],
    dataKey: 'medications',
  },
  // 就诊摘要
  VisitSummaryList: {
    description: '显示就诊摘要列表',
    actions: ['setData', 'setFilter', 'refresh'],
    dataKey: 'visitSummaries',
  },
  // 页面导航
  PageRouter: {
    description: '控制页面跳转',
    actions: ['navigateTo', 'showAlert'],
    dataKey: null,
  },
};

export default usePageUpdater;
