# PHA v2.0 用户使用手册

> 📅 文档版本：v2.0-stage33
> 📝 最后更新：2026-07-15
> 👥 适用人群：最终用户 / 业务方 / 产品经理

---

## 一、PHA 是什么

**PHA (Personal Health Assistant)** 是一个**个人智能健康助手**，通过多个 AI Agent 帮助您：

- 🩺 **健康咨询**：头疼、发烧等日常症状咨询
- 📋 **健康档案管理**：检查报告 OCR、存储、检索
- 💊 **用药提醒**：药品安全、用药计划、提醒通知
- 📝 **就诊摘要**：自动生成就诊记录摘要

**核心理念**：PHA 是**辅助性工具**，**不替代医生诊断**。

---

## 二、4 个 sub-agent 介绍

| Agent | 名称 | 擅长 | 何时使用 |
|-------|------|------|---------|
| 🩺 **health_advisor** | 健康顾问 | 症状分析、健康教育 | "我头疼"、"发烧怎么办" |
| 📋 **health_records** | 健康档案 | OCR、报告存储、检索 | "查看我的体检报告"、"上传检查单" |
| 💊 **medication_reminder** | 用药提醒 | 药品安全、用药计划 | "提醒我晚上9点吃药"、"这药能一起吃吗" |
| 📝 **visit_summary** | 就诊摘要 | 自动生成就诊摘要 | "生成这次就诊的摘要" |

---

## 三、如何使用 PHA

### 方式 1：微信公众号 / 小程序（推荐普通用户）

> ⚠️ 微信小程序代码已存在，部署后即可用。
> 路径：`frontend/wechat_mini_program/`

#### 操作步骤
1. 打开微信，搜索 PHA 小程序
2. 点击"健康咨询"图标
3. 输入问题（如"我头疼 3 天了"）
4. PHA 自动路由到合适的 agent 并回复

#### 小程序 4 个 tab
- **首页**：快捷入口 + 健康资讯
- **健康档案**：查看/上传检查报告
- **用药提醒**：管理用药计划
- **我的**：个人设置

---

### 方式 2：Web 后台（推荐管理员）

> ✅ Admin Dashboard 已存在
> 路径：`frontend/admin-dashboard/`

#### 功能
- 用户管理
- 智能体状态监控
- 用量统计
- 写操作审计

#### 启动
```bash
cd frontend/admin-dashboard
npm install
npm run dev
# 访问 http://localhost:5173
```

---

### 方式 3：HTTP API（推荐开发者）

#### 3.1 健康咨询

```bash
# 简单对话
curl -X POST http://localhost:13002/smart_chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "我头疼",
    "user_id": "user_123",
    "conversation_id": "conv_001"
  }'

# 响应
{
  "role": "agent",
  "content": "头疼可能由多种原因引起...",
  "agent": "health_advisor",
  "routing": {"layer": 2, "target": "health_advisor"},
  "tool_calls": [...]
}
```

#### 3.2 多 agent 并行（综合查询）

```bash
# 同时调用 4 个 agent
curl -X POST http://localhost:13002/smart_chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "综合分析我的健康状况",
    "metadata": {"v2_mode": "multi"}
  }'
```

#### 3.3 查询所有 agent 状态

```bash
curl http://localhost:13002/v2/agents/status
```

#### 3.4 列出所有模型

```bash
curl http://localhost:13002/v2/models/providers
```

---

### 方式 4：ANP 协议（推荐跨组织 / 第三方集成）

> ✅ ANP 协议是开放标准，第三方 agent 可以直接发现并调用 PHA

#### 4.1 发现 PHA agent

```bash
curl http://localhost:13002/anp/agent/ad.json
# 返回完整 ANP Agent Description
```

#### 4.2 通过 ANP JSON-RPC 调用

```bash
curl -X POST http://localhost:13002/anp/agent/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "route_query",
    "params": {
      "user_id": "user_123",
      "query": "我头疼"
    },
    "id": 1
  }'
```

#### 4.3 PHA 的 DID:WBA 身份

```
did:wba:pha.local:hostapi
did:wba:pha.local:health_advisor
did:wba:pha.local:health_records
did:wba:pha.local:medication_reminder
did:wba:pha.local:visit_summary
```

---

## 四、典型使用场景

### 场景 1：日常健康咨询

> **用户**：我最近老是头疼，怎么办？

**PHA 路由**：
1. 关键词 "头疼" → 路由到 `health_advisor`
2. `health_advisor` 调用 RAG 检索知识库
3. 返回健康建议（**不是医疗诊断**）

**示例回复**：
> 头疼可能由多种原因引起：紧张性头痛、偏头痛、颈椎问题、血压异常等。建议：
> 1. 记录头疼频率和持续时间
> 2. 注意休息，避免长时间看屏幕
> 3. 如持续 3 天以上或加重，请就医
> 
> ⚠️ **本建议仅供参考，不替代医生诊断。**

---

### 场景 2：上传检查报告

> **用户**：我刚做了体检，能帮我看看吗？

**操作**：
1. 在小程序/网页上传体检报告 PDF/图片
2. PHA 自动 OCR 识别（`health_records`）
3. 提取关键指标（血糖、血压、血脂等）
4. 存入个人健康档案
5. 可随时查询历史

---

### 场景 3：用药提醒

> **用户**：我每天早上 8 点吃降压药，晚上 9 点吃维生素 D，能一起吃吗？

**PHA 路由**：
1. "药"、"吃药" → 路由到 `medication_reminder`
2. 查询药物相互作用数据库
3. 给出安全建议

**PHA 还可以**：
- 设置定时提醒
- 推送微信通知
- 跟踪用药依从性

---

### 场景 4：综合健康分析（多 agent 并行）

> **用户**：帮我综合分析一下我的健康状况

**PHA 路由**：
1. 同时启动 4 个 agent
2. `health_advisor`：分析症状
3. `health_records`：查询历史报告
4. `medication_reminder`：检查用药
5. `visit_summary`：生成综合摘要
6. 汇总 4 个结果

---

## 五、用户隐私保护

| 措施 | 说明 |
|------|------|
| **本地优先处理** | PHA 在 hostapi 进程内处理数据，不外传 |
| **端到端加密（ANP）** | 阶段33+ 用 DID:WBA 签名 |
| **OAuth2 + JWT** | 用户身份验证，不存密码 |
| **写操作审计** | 所有写操作记录到审计日志 |
| **3 层限流** | 防滥用、防暴力破解 |
| **数据隔离** | 多用户数据完全隔离 |

---

## 六、常见问题

### Q1：PHA 会替代医生吗？

**不会**。PHA 是**辅助性工具**，**所有医疗建议仅供参考**。请在做出医疗决策前咨询专业医生。

### Q2：数据安全吗？

- ✅ 用户数据存在你自己的 PostgreSQL 数据库
- ✅ OAuth2 + JWT 身份验证
- ✅ 写操作审计可追溯
- ✅ 限流防滥用

### Q3：如何申请新功能？

- 提 issue：https://github.com/13139531101/Multi-Intelligence-Medical-Companion/issues
- 或联系管理员

### Q4：PHA 支持哪些语言？

- ✅ 中文（主要）
- ⚠️ 英文基础支持（i18n 待完善）

### Q5：PHA 部署在哪里？

- 本地开发：localhost:13002
- 生产：K8s / Docker Compose（详见 [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md)）

### Q6：为什么我的请求很慢？

可能原因：
1. **首次请求**（agent lazy load）— 30-60 秒
2. **大模型推理** — 通常 3-15 秒
3. **多 agent 并行**（multi 模式）— 30-60 秒（因为同时跑 4 个）
4. **工具调用多** — 取决于 DB 性能

### Q7：可以离线使用吗？

- ❌ 暂不支持（需要 LLM API + PostgreSQL + Redis）
- 未来可考虑本地小模型

---

## 七、用户反馈

如果遇到问题或有建议：
- **Bug 报告**：GitHub Issues
- **功能建议**：GitHub Discussions
- **安全漏洞**：邮箱（待设置）

---

## 八、版本历史

| 版本 | 日期 | 主要变化 |
|------|------|----------|
| v2.0-stage33 | 2026-07-15 | ANP 协议 + DID:WBA |
| v2.0-stage30 | 2026-07-13 | 多 agent 并行 + 状态查询 |
| v2.0-stage28 | 2026-07-08 | v2 LangGraph |
| v2.0-stage24 | 2026-07-11 | 多模型 + OAuth2 + RAG |

---

**最后更新**：2026-07-15
**对应版本**：v2.0-stage33
**对应 tag**：v2.0-stage33-anp
