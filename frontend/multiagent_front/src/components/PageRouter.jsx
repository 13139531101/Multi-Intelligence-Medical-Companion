/**
 * PageRouter — 让 AI 能跳转页面的全局代理
 *
 * 为什么需要它
 * ------------
 * AG-UI 的消费端 ChatPanel 挂在 <Router> **外面**（App.jsx 里它是 <Router> 的
 * 兄弟节点），因此拿不到 useNavigate —— SSE 事件处理函数里根本无从发起跳转。
 *
 * 这个组件渲染 null，但挂在 <Router> 内部且**始终挂载**，于是它注册的
 * navigateTo 在任何页面都可用。它也顺带给此前完全没有生产者的 navigateTo
 * 动作补上了真正的实现。
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Snackbar, Alert } from '@mui/material';
import { usePageUpdater } from './usePageUpdater';
import { PAGE_COMPONENTS, PAGE_ACTIONS } from '../ai/pageContract';

export default function PageRouter() {
  const navigate = useNavigate();
  const [toast, setToast] = useState(null);

  usePageUpdater(PAGE_COMPONENTS.PAGE_ROUTER, {
    [PAGE_ACTIONS.NAVIGATE_TO]: (params) => {
      if (params?.path) navigate(params.path);
    },
    // 比 alert() 好：不阻塞、不打断正在流式输出的回复
    [PAGE_ACTIONS.SHOW_ALERT]: (params) => {
      setToast(params?.message || '来自 AI 的提示');
    },
  });

  return (
    <Snackbar
      open={!!toast}
      autoHideDuration={4000}
      onClose={() => setToast(null)}
      anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
    >
      <Alert severity="info" onClose={() => setToast(null)}>
        {toast}
      </Alert>
    </Snackbar>
  );
}
