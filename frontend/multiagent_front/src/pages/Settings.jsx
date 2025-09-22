import React, { useState } from 'react';
import Header from "./Header";
import { updateApiKey } from '../api/api';

export default function Settings() {
  const [apiKey, setApiKey] = useState('');
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState(null); // 'success' | 'error'

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setStatus(null);
    const success = await updateApiKey(apiKey);
    setStatus(success ? 'success' : 'error');
    setLoading(false);
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <Header /> {/* 放在页面最上方 */}
      <div className="flex items-center justify-center p-4">
        <div className="w-full max-w-md bg-white rounded-2xl shadow-lg p-6 mt-8">
          <h2 className="text-2xl font-bold mb-4 text-center">设置 API Key</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="apiKey" className="block text-sm font-medium text-gray-700">
                LLM API Key
              </label>
              <input
                id="apiKey"
                type="text"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="mt-1 block w-full px-4 py-2 border border-gray-300 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                required
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-xl transition disabled:opacity-50"
            >
              {loading ? '提交中...' : '保存'}
            </button>
          </form>
          {status === 'success' && (
            <p className="mt-4 text-green-600 text-center">保存成功！</p>
          )}
          {status === 'error' && (
            <p className="mt-4 text-red-600 text-center">保存失败，请检查控制台</p>
          )}
        </div>
      </div>
    </div>
  );
}
