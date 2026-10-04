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

import { useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Snackbar, Alert } from '@mui/material';
import { usePageUpdater } from './usePageUpdater';
import { PAGE_COMPONENTS, PAGE_ACTIONS } from '../ai/pageContract';
import { pageStateStore, usePageState } from '../ai/pageStateStore';

export default function PageRouter() {
  const navigate = useNavigate();
  const location = useLocation();
  const [toast, setToast] = useState(null);
  const { route } = usePageState();

  usePageUpdater(PAGE_COMPONENTS.PAGE_ROUTER, {
    [PAGE_ACTIONS.NAVIGATE_TO]: (params) => {
      if (params?.path) navigate(params.path);
    },
    // 比 alert() 好：不阻塞、不打断正在流式输出的回复
    [PAGE_ACTIONS.SHOW_ALERT]: (params) => {
      setToast(params?.message || '来自 AI 的提示');
    },
  });

  // 记录「已经处理过的 route 值」。没有它，下面的回写会和导航 effect 打架：
  // AI 把 route 设成 B 的同一提交里，回写 effect 会看到「route(B) != 当前位置(A)」
  // 而把 route 改回 A，于是导航永远不发生。
  const handledRouteRef = useRef(null);

  // ① 幂等状态通道：route 变了就跳。与上面的 navigateTo 动作并行 —— 两条通道
  //    都能导航，同路径重复 navigate 是 no-op，所以谁先到都无所谓。
  useEffect(() => {
    if (!route || route === handledRouteRef.current) return;
    handledRouteRef.current = route;
    if (route !== location.pathname) navigate(route);
  }, [route, location.pathname, navigate]);

  // ② 回写：让 store 里的 route 是**真实**位置，而不只是「AI 上次想去哪」。
  //    没有这一步，用户手动跳走后再让 AI「回到仪表盘」会失效 —— route 没变化，
  //    上面的 effect 就不会触发。
  //    不会死循环：回写后 route === pathname，effect ① 的比较直接短路。
  useEffect(() => {
    handledRouteRef.current = location.pathname;
    if (pageStateStore.getState().route !== location.pathname) {
      pageStateStore.set({ route: location.pathname });
    }
  }, [location.pathname]);

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
