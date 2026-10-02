/**
 * usePageUpdater - 让页面组件注册到 ComponentRegistry
 *
 * 用法:
 *   import { PAGE_COMPONENTS, PAGE_ACTIONS } from '../ai/pageContract';
 *   import { usePageUpdater } from '../components/usePageUpdater';
 *
 *   function MyPage() {
 *     const [data, setData] = useState([]);
 *     usePageUpdater(PAGE_COMPONENTS.MY_PAGE, {
 *       [PAGE_ACTIONS.SET_DATA]: (params) => setData(params.data || []),
 *     });
 *     return <div>...</div>;
 *   }
 *
 * 关于 methods 的稳定性
 * ---------------------
 * 调用方通常传对象字面量（每次渲染都是新引用）。若把它放进 effect 依赖，
 * 每次渲染都会走一遍 unregister → register。加了待执行队列之后这不再是"无害的
 * 抖动"而是**正确性风险**：注销/注册发生在渲染提交期，可能在渲染周期中途
 * 排空队列。
 *
 * 所以这里用 ref 持有最新的 methods，只注册一个**引用恒定**的代理对象，
 * effect 依赖收敛为 [name]。
 */

import { useEffect, useRef } from 'react';
import { componentRegistry } from './ComponentRegistry';

export function usePageUpdater(name, methods) {
  // 每次渲染刷新，保证代理调用到的永远是最新闭包
  const methodsRef = useRef(methods);
  methodsRef.current = methods;

  // 引用恒定的代理：属性读取转发到 methodsRef.current
  const proxyRef = useRef(null);
  if (!proxyRef.current) {
    proxyRef.current = new Proxy(
      {},
      {
        get: (_, prop) =>
          typeof prop === 'string' ? methodsRef.current?.[prop] : undefined,
        has: (_, prop) => typeof methodsRef.current?.[prop] === 'function',
        ownKeys: () => Reflect.ownKeys(methodsRef.current || {}),
        getOwnPropertyDescriptor: () => ({
          enumerable: true,
          configurable: true,
        }),
      },
    );
  }

  useEffect(() => {
    if (!name) return undefined;
    componentRegistry.register(name, proxyRef.current);
    return () => {
      componentRegistry.unregister(name);
    };
  }, [name]);
}

export default usePageUpdater;
