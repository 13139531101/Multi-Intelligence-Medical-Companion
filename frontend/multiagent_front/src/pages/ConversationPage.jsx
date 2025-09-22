import React, { useEffect, useState } from "react";
import { listConversations } from "../api/api";
import Header from "./Header";
import ConversationList from "../components/ConversationList";
import ConversationDetail from "../components/ConversationDetail";

// 显示会话记录
export default function ConversationPage() {
  const [conversations, setConversations] = useState([]);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    listConversations().then(setConversations);
  }, []);

  return (
    <div className="h-screen flex flex-col font-sans">
      <Header /> {/* 固定在顶部 */}
      <div className="flex flex-1 overflow-hidden">
        <ConversationList conversations={conversations} onSelect={setSelected} />
        <ConversationDetail conversation={selected} />
      </div>
    </div>
  );
}
