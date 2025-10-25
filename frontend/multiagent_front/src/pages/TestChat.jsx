import React, { useState } from 'react';
import { smartChat } from '../api/healthApi';

const TestChat = () => {
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState([]);

  const addLog = (log) => {
    setLogs(prev => [...prev, `${new Date().toLocaleTimeString()}: ${log}`]);
  };

  const testSmartChat = async () => {
    if (!message.trim()) return;
    
    setLoading(true);
    setResponse('');
    setLogs([]);
    
    addLog('开始测试智能助手');
    
    try {
      addLog('调用smartChat函数...');
      const result = await smartChat(message);
      addLog('smartChat函数返回结果');
      console.log('smartChat结果:', result);
      
      if (result.success) {
        setResponse(result.message);
        addLog('成功获取响应: ' + result.message.substring(0, 50) + '...');
      } else {
        setResponse('请求失败');
        addLog('请求失败');
      }
    } catch (error) {
      console.error('测试失败:', error);
      setResponse('错误: ' + error.message);
      addLog('发生错误: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
      <h1>智能助手测试页面</h1>
      
      <div style={{ marginBottom: '20px' }}>
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="输入测试消息"
          style={{ 
            width: '300px', 
            padding: '10px', 
            marginRight: '10px',
            border: '1px solid #ccc',
            borderRadius: '4px'
          }}
        />
        <button 
          onClick={testSmartChat}
          disabled={loading || !message.trim()}
          style={{
            padding: '10px 20px',
            backgroundColor: loading ? '#ccc' : '#007bff',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: loading ? 'not-allowed' : 'pointer'
          }}
        >
          {loading ? '测试中...' : '测试'}
        </button>
      </div>
      
      <div style={{ marginBottom: '20px' }}>
        <h3>响应结果:</h3>
        <div style={{
          padding: '10px',
          border: '1px solid #ddd',
          borderRadius: '4px',
          backgroundColor: '#f9f9f9',
          minHeight: '100px',
          whiteSpace: 'pre-wrap'
        }}>
          {response || '暂无响应'}
        </div>
      </div>
      
      <div>
        <h3>调试日志:</h3>
        <div style={{
          padding: '10px',
          border: '1px solid #ddd',
          borderRadius: '4px',
          backgroundColor: '#f0f0f0',
          maxHeight: '300px',
          overflowY: 'auto'
        }}>
          {logs.map((log, index) => (
            <div key={index} style={{ marginBottom: '5px', fontSize: '12px' }}>
              {log}
            </div>
          ))}
        </div>
      </div>
      
      <div style={{ marginTop: '20px', fontSize: '12px', color: '#666' }}>
        <p>提示: 打开浏览器开发者工具查看更详细的控制台日志</p>
      </div>
    </div>
  );
};

export default TestChat;