import React from 'react';
import ReactMarkdown from 'react-markdown'; // 引入 Markdown 渲染库
import { useRecoilValue } from 'recoil';
import { backgroundTasksState, messageAliasesState } from '../store/recoilState';

//单个消息气泡组件，单条信息
const ChatBubble = ({ message }) => {
  // --- Recoil State ---
  console.log("ChatBubble 渲染消息:", message);
  const backgroundTasks = useRecoilValue(backgroundTasksState);
  const messageAliases = useRecoilValue(messageAliasesState);
  // --- End Recoil State ---

  if (!message || !message.content) {
    console.warn("ChatBubble 收到无内容消息:", message);
    return null; // 不渲染空消息
  }

  const isAgent = message.actor !== 'user';
  // 根据角色调整对齐方式
  const alignment = isAgent ? 'justify-start' : 'justify-end';
  // 根据角色设置气泡颜色 (Tailwind 颜色类)
  const bubbleColor = isAgent
    ? 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100' // 模拟 secondary-container
    : 'bg-blue-600 dark:bg-blue-700 text-white'; // 模拟 primary-container
  // 气泡基础样式
  const bubbleStyles = `p-3 rounded-lg shadow-md max-w-xs sm:max-w-md md:max-w-lg lg:max-w-xl break-words ${bubbleColor}`; // 调整最大宽度

  // 检查此消息是否对应后台任务 (直接或通过别名)
  const aliasTargetId = Object.keys(messageAliases).find(key => messageAliases[key] === message.message_id);
  const effectiveTaskId = aliasTargetId || message.message_id;
  const showProgressBar = effectiveTaskId in backgroundTasks;
  const progressText = showProgressBar ? backgroundTasks[effectiveTaskId] || "处理中..." : "";

  return (
    <div className={`flex ${alignment} w-full my-1`} > {/* 增加垂直间距 */}
      <div className="flex flex-col gap-1 items-end"> {/* 内部元素间距，如果是用户消息则靠右 */}
        {/* 显示角色标识 */}
        <div className={`text-xs text-gray-500 mb-1 ${message.actor === 'user' ? 'self-end' : 'self-start'}`}>
          {message.actor === 'user' ? '👤 user' : `🤖 ${message.actor}`}
        </div>
        {message.content.map(([content, mediaType], index) => {
          const partKey = `${message.message_id}-part-${index}`; // 为每个部分生成唯一 key

          // --- 根据 mediaType 渲染不同内容 ---

          // 渲染图片
          if (mediaType.startsWith('image/')) {
              let src = content;
               // 处理 base64 或 URL
               if (typeof src === 'string' && !src.startsWith('data:') && !src.startsWith('http') && !src.includes('/message/file')) {
                    src = `data:${mediaType};base64,${content}`; // 假设是纯 base64
               } else if (typeof src !== 'string') {
                   console.warn("图片内容不是字符串:", src);
                   return <div key={partKey} className={bubbleStyles}>[无效图片数据]</div>;
               }
              return (
                 <img
                    key={partKey}
                    src={src}
                    alt={`聊天内容 ${index + 1}`}
                    // 使用 Tailwind 设置图片样式
                    className="max-w-full h-auto rounded-lg object-contain my-1" // 限制最大宽度，自动高度
                 />
              );
          }
          // 渲染纯文本或 JSON
          else if (mediaType === 'text/plain' || mediaType === 'application/json') {
             let textContent = content;
             if (mediaType === 'application/json' && typeof content === 'object') {
                 try {
                     textContent = JSON.stringify(content, null, 2); // 格式化 JSON
                     // 使用 pre 和 code 标签以等宽字体展示
                     return (
                        <div key={partKey} className={`${bubbleStyles} font-mono text-sm overflow-x-auto`}> {/* 允许水平滚动 */}
                            <pre><code>{textContent}</code></pre>
                        </div>
                    );
                 } catch (e) {
                     textContent = "[无法序列化的 JSON 数据]";
                 }
             } else if (typeof content !== 'string') {
                 textContent = String(content); // 强制转为字符串
             }
              // 渲染普通文本的气泡
              return (
                 <div key={partKey} className={bubbleStyles}>
                    <p className="whitespace-pre-wrap">{textContent}</p> {/* 保留换行和空格 */}
                 </div>
              );
          }
          // 处理表单类型 (理论上应由 FormRenderer 处理)
          else if (mediaType === 'form') {
              return <div key={partKey} className={bubbleStyles}>[表单内容]</div>; // 占位符
          }
          // 默认使用 Markdown 渲染
          else {
               let markdownContent = typeof content === 'string' ? content : '[不支持的内容类型]';
              return (
                 <div key={partKey} className={`${bubbleStyles} prose prose-sm dark:prose-invert max-w-none`}> {/* Tailwind prose 插件样式 */}
                     <ReactMarkdown children={markdownContent} />
                     {/* 重复消息 */}
                     {message.dupCount > 1 && (
                      <div className="text-xs text-gray-500 ml-2">+{message.dupCount - 1}</div>
                    )}
                 </div>
              );
          }
        })}

        {/* 进度条部分 - 如果需要则渲染在内容下方 */}
        {showProgressBar && (
          <div className={`flex ${isAgent ? 'justify-start' : 'justify-end'} w-full mt-1`}> {/* 根据角色对齐 */}
             <div className={`${bubbleStyles} !p-2 !text-xs !bg-opacity-80`} > {/* 调整样式 */}
                <p className="italic mb-1">{progressText}</p>
                {/* 使用 Tailwind 模拟简易进度条 */}
                <div className="w-full bg-gray-300 rounded-full h-1.5 dark:bg-gray-600 overflow-hidden">
                  <div className="bg-blue-500 h-1.5 rounded-full animate-pulse"></div> {/* 脉冲动画 */}
                </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ChatBubble;