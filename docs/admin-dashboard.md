# PHA v2 管理端功能说明

## 概览

管理端地址：`http://localhost:3002/`

通过 nginx 反向代理到后端 `hostapi:13002`，前端基于 React + Vite 构建，UI 框架为 Tailwind CSS。

---

## 功能列表

### 1. 概览（默认页面）
- 系统状态：CPU、内存、磁盘使用率（通过 `/proc` 读取）
- 数据库状态：PostgreSQL 连接是否正常
- 向量模型信息：模型名称、维度（从环境变量读取）
- RAG 配置：chunk_size、chunk_overlap、max_chunks
- 运行时指标：Uptime、Tool Cache 命中率、请求数、LLM API 调用统计

> 数据来源：`GET /v2/overview`

---

### 2. 智能体（Agents）
显示所有注册的 Agent 及其状态，支持灰度开关。

| 字段 | 说明 |
|------|------|
| Name | Agent 名称（如 health_advisor） |
| Enabled | ON / OFF 状态 |
| Description | Agent 描述 |
| Tools | 关联工具数量 |

**操作**：
- 点击「启用」/「禁用」切换 Agent 开关状态

> 数据来源：`GET /v2/agents/registry`
> 操作：`POST /v2/agents/registry/{name}/enable` 或 `/disable`

---

### 3. 多 LLM（Multi-Model）
多模型路由配置和测试。

- 查看已配置的模型提供商（Provider）
- 实时请求统计（调用次数、错误率）
- 模型对话测试（输入文本，查看返回结果）
- LLM 缓存管理（查看缓存条目、命中率统计、清除缓存）

> 数据来源：`GET /v2/models/providers`、`GET /v2/models/stats`、`GET /v2/models/cache/stats`

---

### 4. LLM 缓存
查看语义缓存的统计和条目。

- 缓存命中率、条目数量
- 缓存条目列表（key、创建时间）
- 一键清空缓存

> 数据来源：`GET /v2/models/cache/stats`、`GET /v2/models/cache/entries`
> 操作：`POST /v2/models/cache/clear`

---

### 5. 工具权限
查看所有工具的默认角色要求和当前生效角色，支持覆盖。

| 字段 | 说明 |
|------|------|
| 工具 | 工具名称 |
| 分类 | 所属分类 |
| 默认角色 | 工具注册时的默认权限要求 |
| 当前角色 | 当前生效的角色要求（可被覆盖） |
| 覆盖 | 是否被管理员手动覆盖 |

**操作**：
- 选择工具 → 编辑角色（guest / user / admin）→ 保存
- 点击「重置」恢复默认角色

> 数据来源：`GET /v2/admin/tools/permissions`（需要 admin 认证）
> 操作：`PUT /v2/admin/tools/{tool_name}/permission`、`DELETE /v2/admin/tools/{tool_name}/permission`

---

### 6. Skills
Skill 管理面板（增删改查）。

**操作**：
- 新建 Skill：填写 name、display_name、description、category、keywords、priority、关联 tools
- 启用 / 禁用 Skill
- 删除 Skill（确认后不可恢复）

> 数据来源：`GET /v2/registry/skills`
> 操作：`POST /v2/registry/skills`、`POST /v2/registry/skills/{name}/enable`、 `DELETE /v2/registry/skills/{name}`

**Skill 动态选择机制**：根据用户查询的关键词与 Skill 的 `keywords` 字段匹配，BM25 评分高的 Skill 被自动选中并注入系统提示词。

---

### 7. 用户管理（RBAC）
用户和角色管理面板。

| 字段 | 说明 |
|------|------|
| 用户ID | 唯一标识（如 admin、gh:majiahui） |
| 用户名 | 显示名称 |
| 角色 | guest / user / admin |
| 创建时间 | 账户创建时间 |
| 操作 | 编辑角色、删除用户 |

**操作**：
- 编辑角色：选择新角色 guest / user / admin → 保存
- 新增用户：填写 user_id、username、角色 → 确认创建
- 删除用户（不可删除 admin 用户）

> 数据来源：`GET /v2/admin/users`（需要 admin 认证）
> 操作：`PUT /v2/admin/users/{user_id}/role`、`POST /v2/admin/users/upsert`、`DELETE /v2/admin/users/{user_id}`

**dev 认证**：管理端内置 `/v2/admin/dev-token` 端点，开发环境自动获取 admin JWT token，无需 GitHub OAuth 登录。

---

### 8. MCP
MCP（Model Context Protocol）服务器管理。

- 查看已注册的 MCP 服务器列表
- 健康检查
- 启用 / 禁用
- 新增 MCP 服务器（填写名称、URL 等）
- 删除 MCP 服务器

> 数据来源：`GET /v2/registry/mcp/servers`
> 操作：`POST /v2/registry/mcp/servers`、`POST /v2/registry/mcp/servers/{name}/enable`、 `DELETE /v2/registry/mcp/servers/{name}`

---

### 9. 记忆（Memory）
记忆系统配置和状态。

> 数据来源：`GET /v2/status`

---

### 10. 聊天测试
在线测试对话功能。

> 数据来源：`POST /v2/chat/stream`

---

### 11. 报警（Alerts）
报警规则管理和触发状态。

- 查看当前触发的报警
- 报警历史
- 报警规则列表
- 手动触发报警评估
- 新增 / 删除报警规则

> 数据来源：`GET /v2/alerts/active`、`GET /v2/alerts/history`、`GET /v2/alerts/rules`

---

### 12. 指标（Metrics）
Prometheus 格式指标导出。

- 请求延迟百分位（p50/p95/p99）
- 请求总数和错误率
- Tool Cache 命中率
- LLM API 调用统计

> 数据来源：`GET /v2/metrics/json`、`GET /metrics`（Prometheus 格式）

---

### 13. ANP / DID
ANP（Agent Network Protocol）身份和路由配置。

- 查看已注册的 DID 列表
- ANP 路由配置

> 数据来源：`GET /anp/did/list`

---

### 14. OAuth2
OAuth2 认证配置和测试。

- 查看 OAuth 统计（签发次数、刷新次数、撤销次数、限流次数）
- 发起 GitHub OAuth 授权流程（测试用）

> 数据来源：`GET /v2/oauth/stats`

---

### 15. RAG
检索增强生成配置和检索测试。

- RAG 统计信息（索引数量、chunk 统计等）
- **上传文档到 RAG**：拖拽或点击上传文件（支持 txt、pdf、doc、docx、csv、md）
- RAG 语义搜索：输入查询词，返回相关文档片段和相似度分数

> 数据来源：`GET /v2/rag/stats`、`GET /v2/rag/search`
> 上传：`POST /v2/upload/file`（需要 admin 认证）

---

### 16. 审计（Audit）
写操作审计日志。

- 最近写操作记录（用户、操作类型、工具、时间）
- 写操作统计（总数、允许/拒绝数）

> 数据来源：`GET /v2/audit/recent`、`GET /v2/audit/stats`

---

### 17. API Explorer
在线 HTTP API 测试工具。

内置常用端点模板：`/health`、`/v2/skills`、`/v2/tools`、`/v2/mcp/servers`、`/v2/agents/registry`、`/v2/models/providers` 等，支持自定义请求方法、路径、Body。

---

## 技术架构

### 前端
- 框架：React 18 + Vite
- UI：Tailwind CSS + lucide-react 图标
- 图表：recharts
- 代理：开发环境 Vite proxy，生产环境 nginx

### 后端
- FastAPI（Python）
- 端口：13002（hostapi）
- 路由前缀：`/v2/`

### 认证机制
- 管理端使用 `/v2/admin/dev-token` 端点获取 JWT access token（开发环境）
- 所有 `/v2/admin/*` 端点需要 `Authorization: Bearer <token>` 且 role=admin
- JWT 有效期 15 分钟，支持 refresh token 续期

### nginx 代理配置
```
/api/v2/* → http://hostapi:13002/v2/*（剥离 /api 前缀）
/         → 静态文件（/usr/share/nginx/html）
```

---

## 环境变量参考

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DB_HOST` | PostgreSQL 主机 | postgres |
| `DB_USER` | 数据库用户 | pha |
| `PHA_EMBEDDING_MODEL` | 向量模型名称 | text-embedding-3-small |
| `PHA_EMBEDDING_DIMENSION` | 向量维度 | 1536 |
| `PHA_RAG_CHUNK_SIZE` | RAG 分块大小 | 512 |
| `PHA_RAG_CHUNK_OVERLAP` | RAG 块重叠大小 | 50 |
| `PHA_RAG_MAX_CHUNKS` | RAG 最大块数 | 1000 |
| `JWT_SECRET_KEY` | JWT 签名密钥 | pha-v2-default-secret-change-me |

---

## 待完善功能

1. **Agent 绑定 Skill/MCP**：当前 Agent 的 Skills 由各自 Agent 服务定义，管理端无法动态分配
2. **Skill 语义匹配升级**：当前基于关键词匹配，可升级为 embedding 语义相似度选择
3. **向量维度手动配置**：当前向量维度只能通过环境变量设置，管理界面无配置项
4. **完整登录流程**：当前使用 dev-token，生产环境需完整的 GitHub OAuth 流程
