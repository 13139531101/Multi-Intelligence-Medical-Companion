// 文件名: Home.jsx
import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import Header from "./Header";
import { checkApiStatus } from "../api/api"; // 引入 API 状态检测函数

export const Home = () => {
  const [apiAlive, setApiAlive] = useState(true); // 初始状态为存活
  const [showApiAlert, setShowApiAlert] = useState(false); // 控制是否显示警告

  useEffect(() => {
    const checkApi = async () => {
      const isAlive = await checkApiStatus();
      setApiAlive(isAlive);
      if (!isAlive) {
        setShowApiAlert(true); // API 未存活时显示警告
      } else {
        setShowApiAlert(false); // API 存活时隐藏警告
      }
    };

    checkApi(); // 在组件加载时执行 API 状态检测
  }, []);

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col">
      <Header />
      {showApiAlert && (
        <div className="bg-red-200 border border-red-400 text-red-700 px-4 py-3 rounded relative mb-4" role="alert">
          <strong className="font-bold">警告!</strong>
          <span className="block sm:inline">后端 HOSTAgent API 未启动，请先开启后再使用。</span>
        </div>
      )}
      <div className="flex-grow flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl p-10 max-w-md w-full text-center">
          <h1 className="text-4xl font-extrabold text-gray-800 mb-4">欢迎来到 A2A</h1>
          <p className="text-gray-500 text-lg mb-8">多 Agent 管理平台</p>
          <div className="grid gap-4">
            <Link to="/agents">
              <button className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-6 rounded-lg transition">
                查看 Agent
              </button>
            </Link>
            <Link to="/start_conversations">
              <button className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 px-6 rounded-lg transition">
                开始会话
              </button>
            </Link>
            <Link to="/conversations">
              <button className="w-full bg-gray-600 hover:bg-gray-700 text-white font-semibold py-3 px-6 rounded-lg transition">
                会话记录
              </button>
            </Link>
            <Link to="/events">
              <button className="w-full bg-purple-600 hover:bg-purple-700 text-white font-semibold py-3 px-6 rounded-lg transition">
                事件管理
              </button>
            </Link>
            <Link to="/settings">
              <button className="w-full bg-yellow-500 hover:bg-yellow-600 text-white font-semibold py-3 px-6 rounded-lg transition">
                系统设置
              </button>
            </Link>
            <Link to="/tasks">
              <button className="w-full bg-red-500 hover:bg-red-600 text-white font-semibold py-3 px-6 rounded-lg transition">
                任务管理
              </button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Home;