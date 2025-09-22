import React from "react";

export default function ConversationList({ conversations, onSelect }) {
  return (
    <div className="w-1/3 border-r p-4 overflow-y-auto">
      <h2 className="text-xl font-bold mb-4">会话列表</h2>
      <ul>
        {conversations.map((conv) => (
          <li
            key={conv.conversation_id}
            className="mb-2 p-2 rounded hover:bg-gray-200 cursor-pointer"
            onClick={() => onSelect(conv)}
          >
            会话 {conv.conversation_id.slice(0, 8)} （{conv.messages?.length || 0} 条）
          </li>
        ))}
      </ul>
    </div>
  );
}
