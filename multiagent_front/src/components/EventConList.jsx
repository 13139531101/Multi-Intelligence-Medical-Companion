import React from 'react';

function EventConList({ conversationIds, selectedConversationId, onSelectConversation }) {
  return (
    <ul>
      {conversationIds.map(convId => (
        <li
          key={convId}
          className={`p-3 cursor-pointer hover:bg-gray-100 border-b border-gray-200 ${selectedConversationId === convId ? 'bg-blue-100 font-semibold' : ''}`}
          onClick={() => onSelectConversation(convId)}
        >
          {/* 只显示 Conversation ID */}
          {convId}
        </li>
      ))}
    </ul>
  );
}

export default EventConList;