import React, { useState } from 'react';
import { smartChat, matchTools, getReasoningStats, listReasoningTraces, getReasoningTrace } from '../api/api';

const TestChat = () => {
  const [message, setMessage] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState([]);
  const [debugInfo, setDebugInfo] = useState(null);
  const [showDebug, setShowDebug] = useState(false);

  const addLog = (log) => {
    setLogs(prev => [...prev, `${new Date().toLocaleTimeString()}: ${log}`]);
  };

  const testSmartChat = async () => {
    if (!message.trim()) return;

    setLoading(true);
    setResponse('');
    setLogs([]);
    setDebugInfo(null);

    addLog('开始测试智能助手');

    try {
      // PHASE 6: 先查询工具匹配
      addLog('PHASE 6: 查询动态工具匹配...');
      const toolMatch = await matchTools(message);
      addLog(`工具匹配结果: ${toolMatch.count} 个工具命中`);

      addLog('调用smartChat函数...');
      const result = await smartChat(message);
      addLog('smartChat函数返回结果');
      console.log('smartChat结果:', result);

      // PHASE 8: 获取推理追踪
      addLog('PHASE 8: 查询推理追踪...');
      const reasoningStats = await getReasoningStats();
      const traces = await listReasoningTraces(5);
      let traceDetail = null;
      if (traces.traces && traces.traces.length > 0) {
        traceDetail = await getReasoningTrace(traces.traces[0].trace_id);
      }

      if (result.success) {
        setResponse(result.message);
        addLog('成功获取响应: ' + result.message.substring(0, 50) + '...');
        setDebugInfo({
          phase6: toolMatch,
          phase7: {
            hint: '第二次发送相同消息会命中缓存，响应 latency 极低'
          },
          phase8: {
            stats: reasoningStats,
            recentTrace: traceDetail?.trace || null,
          },
        });
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
    <div style={{ padding: '20px', maxWidth: '1100px', margin: '0 auto' }}>
      <h1>🧪 智能助手测试页面（PHASE 6-8 调试）</h1>

      <div style={{ marginBottom: '20px' }}>
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="输入测试消息，如：我的血压有点高"
          style={{
            width: '400px',
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
        <button
          onClick={() => setShowDebug(!showDebug)}
          style={{
            marginLeft: '10px',
            padding: '10px 20px',
            backgroundColor: '#28a745',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer'
          }}
        >
          {showDebug ? '隐藏' : '显示'}调试信息
        </button>
      </div>

      {/* PHASE 6-8 调试面板 */}
      {showDebug && debugInfo && (
        <div style={{
          marginBottom: '20px',
          padding: '15px',
          border: '2px solid #17a2b8',
          borderRadius: '8px',
          backgroundColor: '#f8f9fa'
        }}>
          <h2 style={{ marginTop: 0 }}>📊 PHASE 6-8 调试面板</h2>

          {/* PHASE 6 */}
          <div style={{ marginBottom: '15px' }}>
            <h3 style={{ color: '#0066cc' }}>🔧 PHASE 6: 动态工具选择</h3>
            <div style={{ backgroundColor: '#e7f3ff', padding: '10px', borderRadius: '4px' }}>
              <div><strong>查询:</strong> {message}</div>
              <div><strong>命中工具数:</strong> {debugInfo.phase6?.count || 0}</div>
              {debugInfo.phase6?.matched?.map((tool, i) => (
                <div key={i} style={{ marginLeft: '20px', marginTop: '5px' }}>
                  • <strong>{tool.name}</strong> <span style={{ color: '#888' }}>({tool.category})</span>
                  <div style={{ color: '#666', fontSize: '12px', marginLeft: '15px' }}>{tool.description}</div>
                </div>
              ))}
            </div>
          </div>

          {/* PHASE 7 */}
          <div style={{ marginBottom: '15px' }}>
            <h3 style={{ color: '#9933ff' }}>⚡ PHASE 7: 语义缓存</h3>
            <div style={{ backgroundColor: '#f3e5ff', padding: '10px', borderRadius: '4px' }}>
              <div>💡 <em>{debugInfo.phase7?.hint}</em></div>
              <div style={{ marginTop: '5px' }}>
                <strong>提示:</strong> 连续发送两次相同消息，第二次会返回 <code>deepseek (cached)</code>
              </div>
            </div>
          </div>

          {/* PHASE 8 */}
          <div style={{ marginBottom: '15px' }}>
            <h3 style={{ color: '#cc6600' }}>🔍 PHASE 8: 推理过程可视化</h3>
            <div style={{ backgroundColor: '#fff3e0', padding: '10px', borderRadius: '4px' }}>
              <div><strong>总追踪数:</strong> {debugInfo.phase8?.stats?.total_traces || 0}</div>
              <div><strong>最大追踪数:</strong> {debugInfo.phase8?.stats?.max_traces || 0}</div>
              {debugInfo.phase8?.recentTrace && (
                <div style={{ marginTop: '10px' }}>
                  <strong>最新推理链:</strong>
                  <div style={{ backgroundColor: '#fff', padding: '8px', borderRadius: '4px', marginTop: '5px', fontFamily: 'monospace', fontSize: '12px' }}>
                    <div><strong>Trace ID:</strong> {debugInfo.phase8.recentTrace.trace_id}</div>
                    <div><strong>Query:</strong> {debugInfo.phase8.recentTrace.query}</div>
                    <div><strong>Agent:</strong> {debugInfo.phase8.recentTrace.agent_name}</div>
                    <div><strong>耗时:</strong> {debugInfo.phase8.recentTrace.duration_ms?.toFixed(2)}ms</div>
                    {debugInfo.phase8.recentTrace.steps?.length > 0 && (
                      <div style={{ marginTop: '8px' }}>
                        <strong>推理步骤:</strong>
                        {debugInfo.phase8.recentTrace.steps.map((step, i) => (
                          <div key={i} style={{ marginLeft: '15px', marginTop: '3px' }}>
                            {i + 1}. <em>{step.step_type}</em>: {step.content?.substring(0, 60)}
                            {step.tool_name && <span style={{ color: '#0066cc' }}> [工具: {step.tool_name}]</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 响应结果 */}
      <div style={{ marginBottom: '20px' }}>
        <h3>响应结果:</h3>
        <div style={{
          padding: '10px',
          border: '1px solid #ddd',
          borderRadius: '4px',
          backgroundColor: '#f9f9f9',
          minHeight: '100px',
          maxHeight: '500px',
          overflowY: 'auto',
          whiteSpace: 'pre-wrap'
        }}>
          {response || '暂无响应'}
        </div>
      </div>

      {/* 调试日志 */}
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
          {logs.length === 0 ? (
            <div style={{ color: '#888', fontStyle: 'italic' }}>暂无日志，请先点击"测试"按钮</div>
          ) : logs.map((log, index) => (
            <div key={index} style={{ marginBottom: '5px', fontSize: '12px' }}>
              {log}
            </div>
          ))}
        </div>
      </div>

      <div style={{ marginTop: '20px', fontSize: '12px', color: '#666' }}>
        <p>💡 提示: 打开浏览器开发者工具（F12）查看更详细的控制台日志</p>
      </div>
    </div>
  );
};

export default TestChat;