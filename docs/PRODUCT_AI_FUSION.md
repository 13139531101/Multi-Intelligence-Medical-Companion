# AI 深度融合设计 — 让 AI 操作 UI, 不只是回答

> 日期: 2026-07-25
> 作者: 跟用户一起讨论
> 状态: 设计 (待确认后动手)

---

## 一、问题

现在 AI 助手 = 聊天框. 用户问问题 → AI 回答文字.
**没用上 "智能体 + 健康" 的核心** — AI 不操作 UI, 用户得自己跳页找.

例子:
- 用户问"近一个月的报告" → AI 回答文字"你最近一个月的报告有 3 份" → 用户得自己去 /v2/health-records 翻
- 应该: AI 在 NewHealthRecords 页面**就地显示**那 3 份, 同时说"我帮你显示了"

---

## 二、目标

AI 不只是回答 — **AI 操作 UI**:

1. **一直在** — 任意页面都有, 不用找
2. **能操作** — AI 让前端**就地渲染**内容, 不是跳页
3. **会总结** — AI 操作完告诉用户"我帮你干了啥"

---

## 三、用户体验 (user journey)

### 场景 A: 用户在 "我的报告" 页面, 心里想看最近 30 天

```
[页面: 我的报告]
                                                    [AI 一直在右边]
                                                    ┌──────────────┐
页面显示:                                            │ 你: 看一下最近 │
 ┌─────────────┐                                     │   一个月的报告 │
 │ 2026-07-20 │                                     │              │
 │ 血常规      │                                     │ AI: 找到 3 份 │
 ├─────────────┤                                     │   [已显示]    │
 │ 2026-07-15 │                                     │              │
 │ 胸片        │                                     └──────────────┘
 ├─────────────┤                                            │
 │ 2026-06-25 │ ← 这个以前要用户自己翻                     ▼ 收起
 │ 尿常规      │
 └─────────────┘
```

**操作**: 用户在右边 AI 输入框打"最近一个月的报告"
**结果**: 
- AI 说"找到 3 份, 已显示" + **左边的列表自动只剩 3 份**
- 不是跳到聊天页, 不是 AI 给一个 list 文字, 是**当前页面就地刷新**

### 场景 B: 用户问"今天血压高, 怎么办?"

**操作**: 用户在 /v2/chat 输入"今天血压高"
**结果**: AI 调用 health_advisor agent, 给出建议 + 同时显示用户最近的血压记录图

### 场景 C: 用户在"用药"页, 突然想问"这药能一起吃吗?"

**操作**: 用户在 /v2/medication 看到两种药, 心里有疑问, 在右边 AI 输入
**结果**: AI 读取用户当前用药, 给出回答"硝苯地平和阿司匹林可以一起吃, 但建议间隔 2 小时"

---

## 四、架构设计

### 4.1 组件层 (frontend)

```
┌─────────────────────────────────────────────────────────┐
│ App (App.jsx)                                           │
│  ├─ HealthHeader (顶栏)                                  │
│  ├─ <Routes> (页面)                                      │
│  │   ├─ /v2/today       → TodayDashboard                 │
│  │   ├─ /v2/health-records → NewHealthRecords           │
│  │   ├─ /v2/medication  → NewMedication                  │
│  │   ├─ /v2/chat        → NewChat                        │
│  │   └─ ...                                              │
│  └─ <ChatDrawer />  ← 一直在 (新)                        │
│       ├─ 浮在右侧, 可收起/展开                            │
│       ├─ 复用 NewChat 的对话能力                          │
│       └─ 监听 global store 触发 on-screen render          │
│                                                          │
│ <RenderPortal />  ← 新, 全局渲染挂载点                    │
│   ├─ 接收来自 store 的 render 请求                       │
│   └─ 在当前页面里弹 Dialog 或 刷新列表                     │
└─────────────────────────────────────────────────────────┘
```

### 4.2 数据流

```
用户在 ChatDrawer 输入 "看最近一个月的报告"
        │
        ▼
ChatDrawer → sendMessage(q) → POST /v2/chat
        │
        ▼  (后端改)
后端识别意图 (NLU/router): type="render_health_records", filter={days:30}
        │
        ▼  (响应: 不只 text, 还有 structured payload)
响应: {
  reply: "已找到 3 份报告, 我帮你显示",
  render: {
    target: "NewHealthRecords",
    action: "filter",
    params: { days: 30 }
  }
}
        │
        ▼
前端解析: 收到 render 字段 → 调 useAIAction().apply(render)
        │
        ▼
zustand store.aiAction = {target, action, params}
        │
        ▼
所有 listen 的组件 useEffect:
  - NewHealthRecords: aiAction.target === "NewHealthRecords" → 调自己的 fetchRecords({days:30})
  - TodayDashboard: aiAction.target === "TodayDashboard" → 调自己的 fetchMeds()
  - 其他页面: 收到不属于自己的 → no-op
```

### 4.3 后端协议扩展 (跟现有 hostapi 配合)

现有 `/v2/chat` 端点:
- 入参: `{message, agent_id}`
- 出参: `{reply: text}`

**扩展**:
- 出参增加 `render` 字段 (可选):
  ```json
  {
    "reply": "我帮你显示了 3 份报告",
    "render": {
      "target": "NewHealthRecords",
      "action": "filter",
      "params": { "days": 30 }
    }
  }
  ```

后端 **A2A agent** 已经能识别意图 + 调用 tool (健康顾问 agent 调用 health_records API 拿数据), 加一层**响应包装**:
- 在 hostapi 收到 agent reply 后, 用 LLM 做一次**意图分类** (如果还没识别)
- 把 reply + render action 一起返回前端

---

## 五、实现路径 (3 步)

### 第一步: 侧边浮窗 (今天能做的)

**目标**: 让 AI 一直在所有页面都能用

**改的文件**:
1. `frontend/multiagent_front/src/components/ChatDrawer.jsx` (新)
   - 浮在右侧, 可收起/展开
   - 复用 NewChat 的对话能力 (复用 streamChatWithAgent 或类似)
   - 跟当前页面共享用户上下文

2. `frontend/multiagent_front/src/App.jsx`
   - 在 `<Routes>` 之后挂 `<ChatDrawer />`
   - 所有页面都有, 不在底部 (用户确认)

3. `frontend/multiagent_front/src/components/HealthHeader.jsx`
   - 加一个"💬 跟小助手聊" 按钮, 触发 ChatDrawer 展开

**不动的**: AI 仍然只回文字, 不操作 UI

### 第二步: AI 操作 UI (需要后端)

**目标**: AI 收到特定问题, 让前端就地渲染

**改的文件**:
1. `frontend/multiagent_front/src/store/aiActions.js` (新, zustand)
   - 全局 store, 存 `{target, action, params}`
   - 提供 `apply(render)` 和 `consume()` (用一次清空)

2. `frontend/multiagent_front/src/components/RenderPortal.jsx` (新)
   - 全局监听 aiActions, 弹 Dialog 展示 AI 操作结果

3. `frontend/multiagent_front/src/pages/NewHealthRecords.jsx`
   - 加 useEffect 监听 aiActions.target === "NewHealthRecords"
   - 收到后 fetchRecords({days: aiActions.params.days}) 替换列表

4. `frontend/multiagent_front/src/pages/TodayDashboard.jsx`
   - 同样 listen, 收到 fetchMeds()

5. `backend/A2AServer/.../chat_endpoints.py` 或类似
   - 扩展响应格式, 加 `render` 字段
   - LLM 提示词加一段: 识别意图 → 给出 render 结构

### 第三步: 深度融合 (1-2 天)

**目标**: AI 主动建议, 不只被动回答

- AI 在用户进入页面时, **主动 push** "要不要看看最近报告?" (基于历史数据)
- 用户不用开口, AI 主动显示
- 撤回 / 关闭按钮给用户控制

**风险**: 用户体验可能从"工具感"变"骚扰感", 需要做开关

---

## 六、风险与决定

### 风险

1. **后端 LLM 意图识别不准** → render action 错误, 误导用户
   - 缓解: 范围限制 (只识别 5 类意图), 失败 fallback 到纯文字
2. **AI 操作 UI 覆盖用户当前操作** → 用户填了一半的表单被 AI 干掉了
   - 缓解: 只能刷新**列表**, 不能改**表单**; 表单 dirty 时拒绝
3. **侧边浮窗遮挡内容** → 在窄屏体验差
   - 缓解: 默认收起, 只露一个圆点; 移动端 < 600px 改为底部 sheet

### 决定 (跟你确认)

1. **第一步今天做不做?** (推荐做)
2. **侧边浮窗位置**: 右侧 / 底部 (你说按钮不放底部, 走右侧) — 默认收起一个圆点
3. **第一步先不动后端**, 只前端 — OK?

---

## 七、验证

**第一步验收**:
- 进 /v2/today → 右下角(右中)有个 AI 圆点按钮
- 点开 → 浮窗出现, 跟现在 /v2/chat 一样的对话
- 切到 /v2/medication → 浮窗还在, 不消失
- 输入消息 → 跟之前一样返回文字
- **不操作 UI** — 第二步才做

**第二步验收** (后):
- 在 /v2/health-records 输入"看最近 30 天" → 列表自动只剩 30 天内的
- AI 回复里说"已显示 N 份"

---

## 八、todo 顺序

- [ ] 第一步: ChatDrawer 浮窗 (1 文件新 + 2 文件改)
- [ ] 第二步: store + Portal + 后端协议 (5 文件)
- [ ] 第三步: AI 主动建议 (风险高, 看用户反馈决定)