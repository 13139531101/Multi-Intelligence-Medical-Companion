import React, { useEffect } from 'react';
import Conversation from '../components/Conversation';
import Header from './Header';
import { useSetRecoilState } from 'recoil';
import { currentConversationIdState } from '../store/recoilState';
import * as api from '../api/api'; // 导入 API 函数

const StartConversationPage = () => {
    const setCurrentConversationId = useSetRecoilState(currentConversationIdState);

    useEffect(() => {
        const createInitialConversationId = async () => {
            try {
                // 1. 创建新的会话
                const conversationResponse = await api.createConversation();
                if (conversationResponse && conversationResponse.conversation_id) {
                    const newConversationId = conversationResponse.conversation_id;
                    setCurrentConversationId(newConversationId);
                    console.log('创建了新的会话，ID:', newConversationId);
                } else {
                    console.error('创建会话失败');
                }
            } catch (error) {
                console.error('启动页面时创建会话 ID 失败:', error);
            }
        };

        createInitialConversationId();
    }, [setCurrentConversationId]);

    return (
        <div className="flex flex-col h-screen bg-gray-100 dark:bg-gray-900">
            <Header />
            <div className="flex-grow overflow-hidden min-h-0">
                <Conversation />
            </div>
        </div>
    );
};

export default StartConversationPage;