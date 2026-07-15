# PHA v2.0 部署指南

> 📅 文档版本：v2.0-stage33
> 📝 最后更新：2026-07-15
> 👥 适用人群：运维 / 部署工程师

---

## 目录

1. [前置要求](#一前置要求)
2. [环境变量](#二环境变量)
3. [本地开发部署](#三本地开发部署)
4. [Docker Compose 部署](#四docker-compose-部署)
5. [Kubernetes 部署](#五kubernetes-部署)
6. [ANP 跨组织互联](#六anp-跨组织互联)
7. [生产环境清单](#七生产环境清单)
8. [回滚策略](#八回滚策略)

---

## 一、前置要求

### 硬件最低配置

| 部署类型 | CPU | 内存 | 存储 |
|----------|-----|------|------|
| 本地开发 | 4 核 | 8 GB | 20 GB |
| 演示 | 8 核 | 16 GB | 50 GB |
| 小生产 | 16 核 | 32 GB | 200 GB |
| 大生产 | 32+ 核 | 64+ GB | 500 GB+ |

### 软件依赖

| 软件 | 版本 | 必需 |
|------|------|------|
| Docker | 24.0+ | ✅ |
| Docker Compose | v2.20+ | ✅ |
| PostgreSQL | 16+ (with pgvector) | ✅ |
| Redis | 7+ | ⚠️ 微信通知才需要 |
| Kubernetes | 1.28+ | ❌ (生产可选) |

### LLM API Key（至少一个）

| Provider | API Key 来源 |
|----------|-------------|
| DeepSeek | https://platform.deepseek.com |
| Qwen (DashScope) | https://dashscope.aliyun.com |
| Claude (Anthropic) | https://console.anthropic.com |
| Local (Ollama) | 本地部署 |

---

## 二、环境变量

### 必需

```bash
# 数据库
DB_HOST=postgres
DB_USER=pha
DB_PASSWORD=<strong-password>
DB_NAME=personal_health_assistant

# 至少一个 LLM API Key
DEEPSEEK_API_KEY=sk-...
# 或
DASHSCOPE_API_KEY=sk-...
QWEN_API_KEY=sk-...

# JWT 鉴权
JWT_SECRET_KEY=<random-256-bit>
```

### 可选（增强功能）

```bash
# PostgresSaver 持久化（阶段30）
PHA_CHECKPOINT_DB_URL=postgresql://pha:password@postgres:5432/personal_health_assistant

# v2 模式（默认开启）
PHA_USE_V2=true

# Redis（微信通知）
REDIS_URL=redis://redis:6379/0

# ANP crawler 发现列表（逗号分隔）
PHA_ANP_AGENT_URLS=http://health_records:10010,http://health_advisor:10011,http://medication_reminder:10012,http://visit_summary:10013
```

### 完整环境变量清单

参考 `frontend/hostAgentAPI/env_template.txt`

---

## 三、本地开发部署

### 3.1 快速开始（5 分钟）

```bash
# 1. 克隆
git clone https://github.com/13139531101/Multi-Intelligence-Medical-Companion.git
cd Multi-Intelligence-Medical-Companion

# 2. 启动 PostgreSQL + Redis
docker compose up -d postgres redis

# 3. 启动 hostapi
cd frontend/hostAgentAPI
pip install -r requirements.txt
export PYTHONPATH=/app:/app/backend
export HOST_API_PORT=13002
export DB_HOST=localhost
export DEEPSEEK_API_KEY=sk-...
python -m uvicorn api:app --host 0.0.0.0 --port 13002

# 4. 启动 MCP agent（4 个）
cd backend/HealthAdvisor && python main.py &
cd backend/HealthRecordsManager && python main.py &
cd backend/MedicationReminder && python main.py &
cd backend/VisitSummaryGenerator && python main.py &
```

### 3.2 验证

```bash
# 健康检查
curl http://localhost:13002/health

# 智能对话
curl -X POST http://localhost:13002/smart_chat \
  -H "Content-Type: application/json" \
  -d '{"message":"我头疼"}'

# ANP 端点
curl http://localhost:13002/anp/agent/ad.json

# Agent 状态
curl http://localhost:13002/v2/agents/status
```

---

## 四、Docker Compose 部署

### 4.1 启动

```bash
# 1. 启动所有服务
docker compose up -d

# 2. 查看状态
docker compose ps

# 3. 查看日志
docker compose logs -f hostapi
```

### 4.2 服务清单

| 服务 | 端口 | 镜像 |
|------|------|------|
| postgres | 5432 | pgvector/pgvector:pg16 |
| redis | 6379 | redis:7-alpine |
| hostapi | 13002 | a2aserver-hostapi:latest |
| health_records | 10010 | health-records:latest |
| health_advisor | 10011 | health-advisor:latest |
| medication_reminder | 10012 | medication-reminder:latest |
| visit_summary | 10013 | visit-summary:latest |
| admin-dashboard | 5173 | admin-dashboard:latest |

### 4.3 常用命令

```bash
# 重启某个服务
docker compose restart hostapi

# 重新构建
docker compose build hostapi

# 停止
docker compose down

# 删除数据（慎用）
docker compose down -v
```

---

## 五、Kubernetes 部署

> 详细 Helm Chart 在 `docs/Chinese/K8S_DEPLOY.md`（待更新到 stage33）

### 5.1 命名空间

```bash
kubectl create namespace pha
```

### 5.2 ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: pha-config
  namespace: pha
data:
  DB_HOST: postgres
  DB_NAME: personal_health_assistant
  PHA_USE_V2: "true"
  PHA_CHECKPOINT_DB_URL: postgresql://pha:password@postgres:5432/personal_health_assistant
  PHA_ANP_AGENT_URLS: http://health-records.pha.svc.cluster.local:10010,http://health-advisor.pha.svc.cluster.local:10011
```

### 5.3 Secret

```bash
kubectl create secret generic pha-secrets \
  --from-literal=DB_PASSWORD=xxx \
  --from-literal=DEEPSEEK_API_KEY=sk-xxx \
  --from-literal=JWT_SECRET_KEY=xxx \
  -n pha
```

### 5.4 部署

```bash
kubectl apply -f k8s/postgres.yaml
kubectl apply -f k8s/hostapi.yaml
kubectl apply -f k8s/agents.yaml
```

---

## 六、ANP 跨组织互联

### 6.1 启用 ANP 服务

PHA 默认已挂载 ANP bridge。验证：

```bash
curl http://localhost:13002/anp/agent/ad.json
```

应返回完整 ANP Agent Description。

### 6.2 配置 PHA 发现其他组织 agent

```bash
# 环境变量
export PHA_ANP_AGENT_URLS=http://hospital-a.example.com:10011,http://pharmacy-b.example.com:10012
```

重启后 PHA 自动 GET 它们的 `/agent/ad.json` 并加入 Registry。

### 6.3 验证

```bash
# 列出所有已知 agent
curl http://localhost:13002/anp/agents

# 主动发现
curl http://localhost:13002/anp/agents/discover
```

---

## 七、生产环境清单

### 🔴 上线前必做

- [ ] 修改所有默认密码（DB_PASSWORD, JWT_SECRET_KEY, REDIS_PASSWORD）
- [ ] 启用 HTTPS（前置 nginx + Let's Encrypt）
- [ ] 配置数据库自动备份（每日）
- [ ] 配置日志聚合（Loki / ELK）
- [ ] 配置监控告警（Prometheus + Grafana）
- [ ] 配置 ANP DID:WBA 真实签名（阶段34）
- [ ] 配置资源 limits（K8s resource quotas）
- [ ] 配置 HPA（Horizontal Pod Autoscaler）
- [ ] 配置 Pod Disruption Budget
- [ ] 配置 Network Policy
- [ ] 配置 Secrets 加密（K8s secrets + sealed-secrets）
- [ ] 配置 WAF（Web Application Firewall）
- [ ] 配置 DDoS 防护
- [ ] 配置 rate limit（API 网关级别）
- [ ] 配置 audit log 持久化 + 远程存储
- [ ] 配置 error tracking（Sentry / Bugsnag）
- [ ] 配置 uptime monitoring（UptimeRobot）

### 🟡 上线后 1 周内做

- [ ] 性能压测（wrk / Locust / k6）
- [ ] 安全渗透测试
- [ ] 单元测试覆盖率 > 80%
- [ ] E2E 测试报告
- [ ] 灾备演练（数据库恢复）

---

## 八、回滚策略

### 8.1 Docker Compose 回滚

```bash
# 拉取上一版本
docker pull a2aserver-hostapi:v2.0-stage30-orchestration

# 改 docker-compose.yml 的 image tag
# 重新部署
docker compose up -d
```

### 8.2 K8s 回滚

```bash
# 查看历史
kubectl rollout history deployment/hostapi -n pha

# 回滚到上一版本
kubectl rollout undo deployment/hostapi -n pha

# 回滚到指定版本
kubectl rollout undo deployment/hostapi --to-revision=2 -n pha
```

### 8.3 数据库迁移回滚

> ⚠️ 谨慎操作，建议先备份

```bash
# 备份
docker exec pha-postgres pg_dump -U pha personal_health_assistant > backup.sql

# 回滚到上一版本 schema
docker exec -i pha-postgres psql -U pha personal_health_assistant < previous_schema.sql
```

---

## 九、监控端点

| 端点 | 用途 |
|------|------|
| `GET /health` | 简单健康检查 |
| `GET /health/deep` | 深度健康检查（DB + LLM + agents）|
| `GET /metrics` | Prometheus 格式 metrics |
| `GET /v2/status` | 详细状态（JSON） |
| `GET /v2/agents/status` | 所有 sub-agent 状态 |
| `GET /anp/health` | ANP 端点健康检查 |

### Prometheus 抓取配置

```yaml
scrape_configs:
  - job_name: 'pha-hostapi'
    static_configs:
      - targets: ['hostapi:13002']
    metrics_path: /metrics
    scrape_interval: 15s
```

---

## 十、联系 & 反馈

- **GitHub Issues**: https://github.com/13139531101/Multi-Intelligence-Medical-Companion/issues
- **文档问题**: docs/Chinese/CHANGELOG.md
- **架构问题**: docs/Chinese/V2_ARCHITECTURE.md

---

**最后更新**：2026-07-15
**对应版本**：v2.0-stage33
