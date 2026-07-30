/**
 * PageDataContext - 页面数据共享上下文
 *
 * AI 通过 PAGE_UPDATE 指令设置的数据存储在这里
 * 页面组件可以订阅这些数据，实现"AI 控制页面"效果
 *
 * 用法:
 *   import { usePageData } from './PageDataContext';
 *
 *   // 在组件中订阅数据
 *   const { healthRecords, setHealthRecords } = usePageData();
 *
 *   // AI 发送 PAGE_UPDATE { component: 'page', action: 'setData', params: { healthRecords: [...] } }
 *   // -> setHealthRecords([...]) 被调用
 *   // -> 组件自动刷新
 */

import React, { createContext, useContext, useState, useCallback } from 'react';

const PageDataContext = createContext(null);

export function PageDataProvider({ children }) {
  // AI 想要展示的页面数据
  const [pageData, setPageData] = useState({
    healthRecords: null,     // 健康档案数据
    medications: null,       // 用药数据
    visitSummaries: null,    // 就诊摘要数据
    chartData: null,         // 图表数据
    alertMessage: null,      // 提示消息
  });

  // AI 操作摘要（用于浮窗显示）
  const [lastUpdate, setLastUpdate] = useState(null);

  // 设置数据
  const setData = useCallback((key, data) => {
    setPageData(prev => ({ ...prev, [key]: data }));
  }, []);

  // 清除所有数据
  const clearData = useCallback(() => {
    setPageData({
      healthRecords: null,
      medications: null,
      visitSummaries: null,
      chartData: null,
      alertMessage: null,
    });
    setLastUpdate(null);
  }, []);

  // 记录更新
  const recordUpdate = useCallback((component, action, summary) => {
    setLastUpdate({ component, action, summary, ts: Date.now() });
  }, []);

  const value = {
    pageData,
    setData,
    clearData,
    lastUpdate,
    recordUpdate,
    // 便捷方法
    setHealthRecords: (data) => setData('healthRecords', data),
    setMedications: (data) => setData('medications', data),
    setVisitSummaries: (data) => setData('visitSummaries', data),
    setChartData: (data) => setData('chartData', data),
    setAlertMessage: (msg) => setData('alertMessage', msg),
  };

  return (
    <PageDataContext.Provider value={value}>
      {children}
    </PageDataContext.Provider>
  );
}

export function usePageData() {
  const ctx = useContext(PageDataContext);
  if (!ctx) {
    throw new Error('usePageData must be used inside <PageDataProvider>');
  }
  return ctx;
}
