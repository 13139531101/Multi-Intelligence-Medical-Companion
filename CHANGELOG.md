# 更新日志 (CHANGELOG)

PHA v2 的所有重大变更记录。

---

## v2.0-stage24 - 2026-07-11 (本日)

### ✨ 新增：多模型协同 (4 provider + 路由 + fallback)
- DeepSeek / Qwen / Claude / Local 4 个 provider 抽象
- ModelRouter：6 任务类型路由（chat/code/analysis/summary/translation/creative）
- Fallback 链：deepseek → qwen → claude → local
- 限流：每 provider 每分钟 60 次
- 统计：success/error/rate_limited/avg_latency_ms/total_tokens
- 4 个 HTTP 端点：`/v2/models/{chat,providers,stats,test-fallback}`
- **实际 LLM 调用验证通过**（DeepSeek 76 tokens + Qwen 2126ms）
- verify_stage24: **58/58 通过** ✅

---

## v2.0-stage23 - 2026-07-11

### 🐛 修复：build.yml 路径错误
- 原 matrix 路径全错（`backend/agents/*` 不存在）
- 修正为实际路径：`backend/HealthAdvisor` / `HealthRecordsManager` / `MedicationReminder` / `VisitSummaryGenerator`
- 加 `continue-on-error: true` + Dockerfile 存在性检查
- verify_stage23: **38/38 通过** ✅
- 实际 docker build 成功（test-hostapi:latest 1.46GB）

---

## v2.0-stage22 - 2026-07-11

### ✨ 新增：CI/CD 4 个 GitHub Actions 工作流
- `test.yml`：跑 15 个 verify_stage + pgvector/redis services
- `lint.yml`：ruff + black + mypy
- `build.yml`：5 镜像矩阵构建 + 推送阿里云容器镜像
- `release.yml`：tag 触发自动 GitHub Release + changelog
- 触发器：push / pull_request / tags v*.*.* / workflow_dispatch
- verify_stage22: **45/45 通过** ✅

---

## v2.0-stage21 - 2026-07-11

### ✨ 新增：RAG 索引/检索/反馈 (PGVector 业务层)
- 3 表：rag_documents + rag_chunks (vector(1024) + ivfflat) + memory_embeddings
- Embedding：DashScope text-embedding-v3（1024 维）
- chunk_text：中英文段落切分
- RAGStore：index/search/feedback/recall/stats
- 5 个 HTTP 端点：`/v2/rag/{index,search,feedback,recall,stats}`
- DB schema 修复：vector(384→1024) + id default gen_random_uuid() + pgcrypto
- verify_stage21: **37/37 通过** ✅

---

## v2.0-stage20 - 2026-07-10

### ✨ 新增：OAuth2 鉴权
- 授权码流程：/v2/oauth/authorize → GitHub → /v2/oauth/callback
- JWT access token (15 min) + refresh token (7 day) + 轮转
- 7 个 HTTP 端点：`/v2/oauth/*`
- verify_stage20: **47/47 通过** ✅

---

## v2.0-stage19 - 2026-07-10

### 🐛 修复：写操作安全审计
- write_audit.py：记录所有 POST/PUT/DELETE/PATCH
- 4 个 HTTP 端点：`/v2/audit/*`
- verify_stage19: **31/31 通过** ✅

---

## v2.0-stage18 - 2026-07-10

### 🐛 修复：/a2a 端点 400 错误
- a2a_sdk_compat.py 修复请求/响应格式
- verify_stage18: **通过** ✅

---

## v2.0-stage14 ~ stage12

详见 git tag 历史。

---

## v2.0-final - 2026-07-01

首版 v2.0-final 标签。

---

## v1.0.0 / v1.0.1

项目初始化版本。
