import React from 'react';

function EventItem({ event }) {
  // 将 Unix 时间戳（秒）转换为毫秒，然后创建 Date 对象
  const timestamp = new Date(event.timestamp * 1000).toLocaleString();

  return (
    <div className={`p-4 rounded-lg shadow-md ${event.actor === 'user' ? 'bg-blue-50' : 'bg-gray-50'}`}>
      <div className="flex justify-between items-center mb-2">
        <span className="font-bold text-sm">{event.actor} ({event.content?.role})</span>
        <span className="text-xs text-gray-500">{timestamp}</span>
      </div>
      <div className="text-gray-800 text-sm">
        {/* 遍历 content.parts，显示文本或数据 */}
        {event.content?.parts?.map((part, index) => {
          if (part.type === 'text') {
            return <p key={index}>{part.text}</p>;
          } else if (part.type === 'data') {
            // 对于数据类型，以 Pre 格式显示 JSON
            return (
              <pre key={index} className="bg-gray-200 p-2 rounded text-xs overflow-auto">
                {JSON.stringify(part.data, null, 2)}
              </pre>
            );
          }
          return null; // 忽略其他类型的 parts
        })}
      </div>
    </div>
  );
}

export default EventItem;