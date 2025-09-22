import React from "react";

export default function ConversationDetail({ conversation }) {
  if (!conversation) return <div className="p-4">请选择一个会话</div>;

  return (
    <div className="w-2/3 p-4 overflow-y-auto">
      <h2 className="text-xl font-bold mb-4">会话详情</h2>
      <div className="space-y-4">
        {conversation.messages.map((msg, index) => (
          <div
            key={index}
            className={`p-3 rounded ${
              msg.role === "user" ? "bg-blue-100" : "bg-green-100"
            }`}
          >
            <p className="text-sm text-gray-600">{msg.role}</p>
            <p>{msg.parts[0]?.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
