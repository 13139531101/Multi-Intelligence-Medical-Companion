import React, { useEffect, useState } from 'react';
import Header from './Header';
import { getTasks } from '../api/api';

const TasksPage = () => {
  const [tasks, setTasks] = useState([]);
  const [selectedTask, setSelectedTask] = useState(null);

  useEffect(() => {
    const fetchTasks = async () => {
      const data = await getTasks();
      setTasks(data);
    };
    fetchTasks();
  }, []);

  return (
    <div className="flex flex-col h-screen">
      <Header />

      <div className="flex flex-1 overflow-hidden">
        {/* 左侧任务列表 */}
        <div className="w-1/3 border-r border-gray-200 overflow-y-auto">
          <h2 className="text-xl font-bold p-4">任务列表</h2>
          {tasks.map((task) => (
            <div
              key={task.id}
              className={`p-4 border-b cursor-pointer hover:bg-gray-100 ${
                selectedTask?.id === task.id ? 'bg-gray-100' : ''
              }`}
              onClick={() => setSelectedTask(task)}
            >
              <div className="text-sm font-medium text-gray-700">Session ID: {task.sessionId}</div>
              <div className="text-sm text-gray-500">状态: {task.status?.state}</div>
              <div className="text-xs text-gray-400">
                时间: {new Date(task.status?.timestamp).toLocaleString()}
              </div>
            </div>
          ))}
        </div>

        {/* 右侧对话详情 */}
        <div className="w-2/3 overflow-y-auto p-4">
          <h2 className="text-xl font-bold mb-4">对话详情</h2>
          {selectedTask ? (
            <div className="space-y-4">
              {selectedTask.history?.map((entry, index) => (
                <div key={index} className="border rounded p-3 shadow-sm">
                  <div className="text-sm text-gray-500 mb-1">
                    <span className="font-semibold">{entry.role === 'user' ? '用户' : '智能体'}:</span>
                  </div>
                  <div className="text-gray-800 whitespace-pre-wrap">
                    {entry.parts?.map((part, i) => (
                      <p key={i}>{part.text}</p>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-gray-500">点击左侧任务以查看详情</div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TasksPage;
