# PHA v2 运维指南

> 面向：部署、监控、灰度、回滚的运维 / SRE
>
> **最后更新**：2026-07-11（v2.0 阶段 17，含 K8s 运维）

---

## 1. 部署架构

### 1.1 端口分配

| 服务 | 端口 | 协议 | 用途 |
|------|------|------|------|
| hostAgentAPI (FastAPI) | 10010 | HTTP | 主入口（v1+v2 灰度）|
| a2a-sdk Server | 10020 | HTTP | a2a-sdk 标准客户端接入 |
| Admin Backend | 8000 | HTTP | 管理后台 API |
| Admin Frontend | 3002 | HTTP | 管理后台 Web |
| PostgreSQL | 5432 | TCP | 主数据库 |
| Redis (未来) | 6379 | TCP | 缓存（待接入）|

### 1.2 Docker Compose 部署

```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: pha
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: personal_health_assistant
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  hostapi:
    build: .
    command: python frontend/hostAgentAPI/server.py
    ports:
      - "10010:10010"
    environment:
      DATABASE_URL: postgresql://pha:${POSTGRES_PASSWORD}@postgres:5432/personal_health_assistant
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
      # PHA_USE_V2: "false"  # 默认 false，需手动开启
    depends_on:
      - postgres

  a2a-sdk:
    build: .
    command: python -m A2AServer.v2.a2a_sdk_server
    ports:
      - "10020:10020"
    environment:
      DATABASE_URL: postgresql://pha:${POSTGRES_PASSWORD}@postgres:5432/personal_health_assistant
      DEEPSEEK_API_KEY: ${DEEPSEEK_API_KEY}
      PHA_A2A_SDK_PORT: "10020"
    depends_on:
      - postgres

volumes:
  pgdata:
```

### 1.3 启动命令

```bash
# 1. 数据库
docker compose up -d postgres

# 2. 主 API
python frontend/hostAgentAPI/server.py

# 3. a2a-sdk server（独立）
python -m A2AServer.v2.a2a_sdk_server

# 4. 健康检查
curl http://localhost:10010/health
curl http://localhost:10020/health
```

---

## 2. 环境变量

### 2.1 必须配置

| 变量 | 说明 | 示例 |
|------|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek API key | `sk-xxx` |
| `OPENAI_API_KEY` | OpenAI 兼容 key（可同 DeepSeek）| `sk-xxx` |
| `DATABASE_URL` | PostgreSQL 连接 | `postgresql://...` |
| `JWT_SECRET_KEY` | JWT 签名密钥 | 32+ 字符随机 |
| `ADMIN_TOKEN` | Admin API 鉴权 | 32+ 字符随机 |

### 2.2 v2 开关

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PHA_USE_V2` | `false` | 全局开关，`true` = 所有请求走 v2 |
| `PHA_LLM_MODEL` | `deepseek-chat` | 使用的 LLM 模型 |
| `PHA_CHECKPOINT_DB_URL` | (空) | PostgresSaver 连接（生产用）|
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | LLM API base URL |

### 2.3 可选

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LANGSMITH_API_KEY` | (空) | LangSmith 追踪 |
| `LANGSMITH_PROJECT` | `pha-v2` | LangSmith 项目名 |
| `PHA_A2A_SDK_PORT` | `10020` | a2a-sdk server 端口 |
| `HOSTAPI_UPLOAD_MAX_CONCURRENCY` | `8` | 上传并发限制 |

---

## 3. 灰度切流

### 3.1 三种切流粒度

```bash
# 1. 全量切流（最激进）
# 在 .env 加：
PHA_USE_V2=true
docker compose restart hostapi

# 2. 单用户切流（推荐）
# 前端按用户判断是否带 header
if user.is_beta_tester:
    headers = {"X-Use-V2": "true"}
await fetch("/message/send", {headers: headers, ...})

# 3. 按请求类型切流（最精细）
# 例如：只对症状咨询切流
if request.type == "symptom_consultation":
    headers = {"X-PHA-Version": "v2"}
```

### 3.2 切流回滚（5 秒）

```bash
# 方式 1：改 .env
sed -i 's/PHA_USE_V2=true/PHA_USE_V2=false/' .env
docker compose restart hostapi

# 方式 2：直接清环境变量
unset PHA_USE_V2  # 但容器内仍生效，需重启

# 方式 3：紧急回滚
docker compose down hostapi
# 回滚到上一个稳定 tag
git checkout v2.0-stage4
python frontend/hostAgentAPI/server.py
```

### 3.3 切流监控

```bash
# 实时看 v2 路由日志
tail -f /var/log/pha-server.log | grep "PHA v2"

# 统计 v1 vs v2 流量
grep "PHA v2" /var/log/pha-server.log | wc -l     # v2 数量
grep -v "PHA v2" /var/log/pha-server.log | wc -l  # v1 数量
```

---

## 4. 监控告警

### 4.1 关键指标

| 指标 | 健康 | 警告 | 严重 |
|------|------|------|------|
| v2 错误率 | <1% | 1-5% | >5% |
| 端到端延迟 P50 | <5s | 5-15s | >15s |
| 端到端延迟 P99 | <30s | 30-60s | >60s |
| LLM API 错误率 | <0.5% | 0.5-2% | >2% |
| DB 连接池 | <70% | 70-90% | >90% |

### 4.2 关键日志

```bash
# v2 路由日志
[PHA v2] routing to v2 HostGraph
[PHA v2] success: agent=health_advisor
[PHA v2] error, fallback to v1: ...

# LangGraph 错误
[v2_agent:health_advisor] stream error: ...
[v2_runtime] LangChain 1.x 不可用: ...

# LLM 错误
openai.AuthenticationError: 401 Incorrect API key
```

### 4.3 告警示例（Prometheus + Alertmanager）

```yaml
# prometheus-rules.yml
groups:
  - name: pha-v2-alerts
    rules:
      - alert: PHAv2HighErrorRate
        expr: rate(pha_v2_errors_total[5m]) / rate(pha_v2_requests_total[5m]) > 0.05
        for: 2m
        annotations:
          summary: "PHA v2 错误率 > 5%"
          action: "检查 DeepSeek API 状态"

      - alert: PHAv2SlowResponse
        expr: histogram_quantile(0.99, pha_v2_request_duration_seconds_bucket) > 30
        for: 5m
        annotations:
          summary: "PHA v2 P99 > 30s"
          action: "检查 LLM 性能或工具调用"
```

---

## 5. 故障排查

### 5.1 v2 完全不工作

**症状**：所有 v2 请求 fallback 到 v1

**排查**：
```python
# 检查 v2 runtime 状态
python -c "
import sys
sys.path.insert(0, 'backend/A2AServer/src')
from A2AServer.v2.v2_runtime import get_runtime
r = get_runtime()
print('available:', r.available)
print('error:', r._error if hasattr(r, '_error') else None)
"
```

**常见原因**：
- LangChain 版本不对（必须 `1.2.10`）
- `langgraph-prebuilt` 版本不对（必须 `1.0.5`）
- Python 进程没重启

### 5.2 DeepSeek 401 错误

**症状**：`Incorrect API key provided: sk-5de39***********************9cdb`

**原因**：`.env` 里的 `OPENAI_API_KEY` 实际是 DeepSeek 的 key（DeepSeek 兼容 OpenAI 协议）

**解决**：
```python
# v2/v2_agent.py 的 _ensure_agent 已处理
# 检查环境变量优先级：DEEPSEEK_API_KEY > OPENAI_API_KEY
```

### 5.3 工具调用超时

**症状**：`analyze_health_concern` 10s+ 不返回

**排查**：
```python
# 检查模块加载时间
from A2AServer.v2.mcp_discover import load_mcp_tool_function
import time
t0 = time.time()
func = load_mcp_tool_function('health_advisor', 'diagnosis_tool', 'analyze_symptoms')
print(f'load: {time.time()-t0:.1f}s')
print(func)
# 直接调
t0 = time.time()
result = func(symptoms=['头痛'])
print(f'call: {time.time()-t0:.1f}s, result: {result}')
```

**超时保护**：mcp_discover 默认 3 秒超时，避免 DB 连接卡死拖垮整个 agent 加载。

### 5.4 a2a-sdk 协议不匹配

**症状**：`ValidationError: ... for Message`

**排查**：
```python
# 检查 SDK 版本
python -c "from importlib.metadata import version; print(version('a2a-sdk'))"
# 必须 0.3.25
```

**升级**：
```bash
pip install --upgrade a2a-sdk==0.3.25
```

---

## 6. 备份与恢复

### 6.1 数据库备份

```bash
# 每日全量备份
docker exec pha-postgres pg_dump -U pha personal_health_assistant \
  | gzip > /backup/pha-$(date +%Y%m%d).sql.gz

# 恢复
gunzip -c /backup/pha-20260709.sql.gz | \
  docker exec -i pha-postgres psql -U pha -d personal_health_assistant
```

### 6.2 配置备份

```bash
# .env 不能进 git（已在 .gitignore）
cp .env /backup/env-$(date +%Y%m%d).env

# LangGraph Checkpoint (PostgresSaver)
# 数据已在 PostgreSQL，无需单独备份
```

---

## 7. 容量规划

### 7.1 单实例容量

| 维度 | 容量 |
|------|------|
| 并发请求 | 50 (FastAPI 默认) |
| 每秒请求 | 5-10 (受 LLM 延迟限制) |
| 数据库连接 | 20 (psycopg pool) |
| 内存 | 2-4 GB (含 LangGraph 状态) |
| CPU | 4 核 (含 vLLM 备用) |

### 7.2 扩展策略

```bash
# 水平扩展：多个 hostapi 实例
docker compose up -d --scale hostapi=4

# 用 nginx 负载均衡
upstream pha-hostapi {
    server hostapi-1:10010;
    server hostapi-2:10010;
    server hostapi-3:10010;
    server hostapi-4:10010;
}

server {
    listen 80;
    location / {
        proxy_pass http://pha-hostapi;
    }
}
```

---

## 8. 安全

### 8.1 当前安全措施

- ✅ JWT 鉴权（user_id 必填）
- ✅ Admin token 鉴权
- ✅ HTTPS（生产 nginx 反代）
- ✅ 密码 bcrypt 加密
- ⚠️ LLM API key 在 .env（需加 secret manager）

### 8.2 待办（阶段7+）

- [ ] OAuth2 + OPA 鉴权
- [ ] Rate limiting（按 user_id）
- [ ] 审计日志（所有 v2 调用）
- [ ] PII 脱敏 Middleware

---

## 9. 升级流程

### 9.1 升级 LangChain / LangGraph

```bash
# 1. 锁版本（已在 requirements-v2.txt）
langchain==1.2.10
langgraph==1.0.10
langgraph-prebuilt==1.0.5  # 关键
langgraph-checkpoint==3.0.1  # 关键
langchain-openai==1.3.3

# 2. 测试环境先升级
pip install -U -r requirements-v2.txt
python scripts/verify_stage1.py
python scripts/verify_stage2.py
python scripts/verify_stage2_5.py
python scripts/verify_stage3.py
python scripts/verify_stage4.py
python scripts/verify_stage5.py

# 3. 灰度切流
PHA_USE_V2=true  # 测试环境先开

# 4. 监控 1 小时无异常，生产再切
```

### 9.2 升级 v2 自身（新 tag）

```bash
# 1. 拉新 tag
git fetch origin
git checkout v2.0-stageN

# 2. 重启服务
docker compose restart hostapi a2a-sdk

# 3. 跑验收
python scripts/verify_stage5.py

# 4. 监控 v2 路由日志
tail -f /var/log/pha-server.log | grep "PHA v2"
```

---

## 10. 联系 & 支持

- **GitHub Issues**: [项目 issues 页面]
- **Gitee Issues**: [项目 issues 页面]
- **文档**: `docs/Chinese/V2_*.md`
- **代码注释**: 所有 v2 模块都有中文 docstring
