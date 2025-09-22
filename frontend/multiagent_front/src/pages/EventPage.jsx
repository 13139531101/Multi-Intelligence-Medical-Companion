import React, { useState, useEffect, useMemo } from 'react';
import Header from './Header';
import EventConList from '../components/EventConList';
import EventList from '../components/EventList';
import { getEvents } from "../api/api";

function EventPage() {
  // 存储原始事件数据
  const [events, setEvents] = useState([]);
  // 存储当前选中的 conversation_id
  const [selectedConversationId, setSelectedConversationId] = useState(null);

  // 模拟从后端获取数据 (使用 useEffect 在组件挂载时执行一次)
  useEffect(() => {
    getEvents()
      .then(data => setEvents(data))  // 直接使用数据
      .catch(error => console.error('Error fetching events:', error));
  }, []);
  

  // 使用 useMemo 来分组和排序事件，只有当 events 变化时才重新计算
  const groupedAndSortedEvents = useMemo(() => {
    if (!events || events.length === 0) {
      return {};
    }

    // 1. 按 conversation_id 分组
    const groups = events.reduce((acc, event) => {
      // 确保 metadata 和 conversation_id 存在
      const conversationId = event.content?.metadata?.conversation_id;
      if (conversationId) {
        if (!acc[conversationId]) {
          acc[conversationId] = [];
        }
        acc[conversationId].push(event);
      }
      return acc;
    }, {});

    // 2. 对每个分组内的事件按 timestamp 排序 (升序)
    Object.keys(groups).forEach(convId => {
      groups[convId].sort((a, b) => a.timestamp - b.timestamp);
    });

    return groups;
  }, [events]); // 依赖 events 状态

  // 在数据加载完成后，自动选择第一个对话
  useEffect(() => {
    const conversationIds = Object.keys(groupedAndSortedEvents);
    if (conversationIds.length > 0 && selectedConversationId === null) {
      setSelectedConversationId(conversationIds[0]);
    }
  }, [groupedAndSortedEvents, selectedConversationId]); // 依赖分组后的事件和当前选中的ID

  // 获取当前选中对话的事件列表
  const displayedEvents = selectedConversationId
    ? groupedAndSortedEvents[selectedConversationId] || []
    : [];

  return (
    <div className="h-screen flex flex-col bg-gray-100">
      <Header /> {/* 顶部 Header */}
      <div className="flex flex-1 overflow-hidden">
        {/* 左侧面板 */}
        <div className="w-1/4 bg-white border-r border-gray-200 overflow-y-auto">
          <h2 className="text-xl font-bold p-4 border-b border-gray-200">Conversations</h2>
          <EventConList
            conversationIds={Object.keys(groupedAndSortedEvents)}
            selectedConversationId={selectedConversationId}
            onSelectConversation={setSelectedConversationId}
          />
        </div>

        {/* 右侧面板 */}
        <div className="flex-1 overflow-y-auto p-4">
          <h2 className="text-xl font-bold mb-4">
            {selectedConversationId ? `Events for Conversation ID: ${selectedConversationId}` : 'Select a Conversation'}
          </h2>
          {selectedConversationId ? (
            <EventList events={displayedEvents} />
          ) : (
            <p className="text-gray-600">Please select a conversation from the left panel to view its events.</p>
          )}
        </div>
      </div>
    </div>
  );
}

export default EventPage;