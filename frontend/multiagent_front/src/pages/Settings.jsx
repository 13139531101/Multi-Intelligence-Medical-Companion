import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getUserInfo, updateUserProfile } from '../api/healthApi';

const TABS = [
  { id: 'profile', label: '个人资料', icon: '👤' },
  { id: 'health', label: '健康偏好', icon: '💊' },
  { id: 'notifications', label: '通知设置', icon: '🔔' },
  { id: 'privacy', label: '隐私设置', icon: '🔒' },
];

export default function Settings() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('profile');
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState(null);

  // 个人资料
  const [nickname, setNickname] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [birthday, setBirthday] = useState('');
  const [gender, setGender] = useState('');

  // 健康偏好
  const [allergies, setAllergies] = useState('');
  const [chronicDiseases, setChronicDiseases] = useState('');

  // 通知设置
  const [medicationReminder, setMedicationReminder] = useState(true);
  const [visitReminder, setVisitReminder] = useState(true);

  useEffect(() => {
    loadUserInfo();
  }, []);

  const loadUserInfo = async () => {
    try {
      const data = await getUserInfo();
      setUser(data);
      setNickname(data.nickname || '');
      setEmail(data.email || '');
      setPhone(data.phone || '');
      setBirthday(data.birthday || '');
      setGender(data.gender || '');
      try {
        setAllergies(data.allergies ? JSON.parse(data.allergies).join('、') : '');
      } catch { setAllergies(''); }
      try {
        setChronicDiseases(data.chronic_diseases ? JSON.parse(data.chronic_diseases).join('、') : '');
      } catch { setChronicDiseases(''); }
      setMedicationReminder(data.medication_reminder_enabled !== false);
      setVisitReminder(data.visit_reminder_enabled !== false);
    } catch (e) {
      console.error('加载用户信息失败', e);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const profileData = {
        nickname: nickname || null,
        email: email || null,
        phone: phone || null,
        birthday: birthday || null,
        gender: gender || null,
        allergies: allergies ? allergies.split(/[,，、]/).map(s => s.trim()).filter(Boolean) : [],
        chronic_diseases: chronicDiseases ? chronicDiseases.split(/[,，、]/).map(s => s.trim()).filter(Boolean) : [],
        medication_reminder_enabled: medicationReminder,
        visit_reminder_enabled: visitReminder,
      };
      const updated = await updateUserProfile(profileData);
      setUser(updated);
      setStatus('success');
    } catch (e) {
      setStatus('error');
      console.error('保存失败', e);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-100 flex justify-center items-center">
        <div className="text-gray-500">加载中...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100">
      <div className="max-w-3xl mx-auto p-4 mt-4">
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={() => navigate(-1)}
            className="text-gray-500 hover:text-gray-700 text-sm"
          >
            ← 返回
          </button>
          <h1 className="text-2xl font-bold">个人中心</h1>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-200 mb-4 overflow-x-auto">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-1 px-4 py-3 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="bg-white rounded-2xl shadow-lg p-6">
          {activeTab === 'profile' && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">个人资料</h3>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">用户名</label>
                <input
                  type="text"
                  value={user?.username || ''}
                  disabled
                  className="w-full px-4 py-2 border border-gray-300 rounded-xl bg-gray-50 text-gray-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">昵称</label>
                <input
                  type="text"
                  value={nickname}
                  onChange={e => setNickname(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="设置你的昵称"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">邮箱</label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="example@email.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">手机号</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={e => setPhone(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="13800138000"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">生日</label>
                  <input
                    type="date"
                    value={birthday}
                    onChange={e => setBirthday(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">性别</label>
                  <select
                    value={gender}
                    onChange={e => setGender(e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="">未设置</option>
                    <option value="male">男</option>
                    <option value="female">女</option>
                    <option value="other">其他</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'health' && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">健康偏好</h3>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  过敏史 <span className="text-gray-400 text-xs">（用逗号分隔多个）</span>
                </label>
                <input
                  type="text"
                  value={allergies}
                  onChange={e => setAllergies(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="青霉素, 花粉, 海鲜"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  慢性病 <span className="text-gray-400 text-xs">（用逗号分隔多个）</span>
                </label>
                <input
                  type="text"
                  value={chronicDiseases}
                  onChange={e => setChronicDiseases(e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="高血压, 糖尿病"
                />
              </div>
              <div className="bg-blue-50 rounded-xl p-4 text-sm text-blue-700">
                💡 这些信息会帮助 AI 给你更精准的健康建议，请如实填写。
              </div>
            </div>
          )}

          {activeTab === 'notifications' && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">通知设置</h3>
              <div className="space-y-3">
                <label className="flex items-center justify-between p-4 border border-gray-200 rounded-xl cursor-pointer hover:bg-gray-50">
                  <div>
                    <div className="font-medium">服药提醒</div>
                    <div className="text-sm text-gray-500">收到服药时间提醒通知</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={medicationReminder}
                    onChange={e => setMedicationReminder(e.target.checked)}
                    className="w-5 h-5 text-blue-600 rounded focus:ring-blue-500"
                  />
                </label>
                <label className="flex items-center justify-between p-4 border border-gray-200 rounded-xl cursor-pointer hover:bg-gray-50">
                  <div>
                    <div className="font-medium">复诊提醒</div>
                    <div className="text-sm text-gray-500">收到复诊时间提醒通知</div>
                  </div>
                  <input
                    type="checkbox"
                    checked={visitReminder}
                    onChange={e => setVisitReminder(e.target.checked)}
                    className="w-5 h-5 text-blue-600 rounded focus:ring-blue-500"
                  />
                </label>
              </div>
            </div>
          )}

          {activeTab === 'privacy' && (
            <div className="space-y-4">
              <h3 className="text-lg font-semibold">隐私设置</h3>
              <div className="space-y-3">
                <div className="p-4 border border-gray-200 rounded-xl">
                  <div className="font-medium mb-1">账号信息</div>
                  <div className="text-sm text-gray-500 mb-3">注册时间：{user?.created_at ? new Date(user.created_at).toLocaleDateString() : '-'}</div>
                  <button
                    onClick={() => alert('请联系客服修改密码')}
                    className="text-blue-600 text-sm hover:underline"
                  >
                    修改密码 →
                  </button>
                </div>
                <div className="p-4 border border-red-200 rounded-xl bg-red-50">
                  <div className="font-medium text-red-700 mb-1">危险区域</div>
                  <div className="text-sm text-red-600 mb-3">导出或清除你的个人数据</div>
                  <div className="flex gap-3">
                    <button
                      onClick={() => alert('数据导出功能开发中')}
                      className="px-4 py-2 border border-red-300 text-red-600 rounded-xl text-sm hover:bg-red-100"
                    >
                      导出数据
                    </button>
                    <button
                      onClick={() => {
                        if (confirm('确定要清除所有咨询历史吗？此操作不可恢复。')) {
                          alert('功能开发中');
                        }
                      }}
                      className="px-4 py-2 border border-red-300 text-red-600 rounded-xl text-sm hover:bg-red-100"
                    >
                      清除历史
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Save Button */}
          <div className="mt-6 pt-4 border-t border-gray-200">
            {status === 'success' && (
              <p className="mb-3 text-green-600 text-sm text-center">✓ 保存成功</p>
            )}
            {status === 'error' && (
              <p className="mb-3 text-red-600 text-sm text-center">✗ 保存失败，请重试</p>
            )}
            <button
              onClick={handleSave}
              disabled={saving}
              className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-xl transition disabled:opacity-50"
            >
              {saving ? '保存中...' : '保存设置'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
