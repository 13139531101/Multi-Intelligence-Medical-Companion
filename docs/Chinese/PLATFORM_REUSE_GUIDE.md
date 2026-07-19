# PHA 平台复用指南 (阶段 48-20 + 48-21)

> 把 PHA 改成"多场景多智能体平台", 复用方式: **换 yaml 不改代码**.

阶段 48-21 加了: **`/v2/manifest` API + 前端 Domain Switcher + dangerous_tools 自动收集**, 让用户在前端就能切 domain.

---

## 0. TL;DR

```bash
# 1. 复制一份 manifest
cp examples/domain_configs/pha.health.yaml my_app.yaml
vim my_app.yaml             # 改 agent 名 / keywords / dangerously 等

# 2. 设置环境变量, 启动后端
PHA_DOMAIN_MANIFEST=my_app.yaml python backend/hostAgentAPI/api.py
```

零代码改动.

---

## 1. 为什么之前难复用?

阶段 48-19 之前:

- 4 个 agent 名 (`health_advisor / health_records / medication_reminder / visit_summary`) 硬编码在 `bridge.py / did_wba.py / anp_crawler.py`
- LLM 路由关键词全是健康词
- HITL 配置在 `dangerous_tools.py` 硬编码
- host_graph fallback 写死 `health_advisor`

→ 想换成电商 / HR / 教育 / 法律, 必须改代码.

## 2. 怎么改的 (阶段 48-20)

- ✅ 新建 `backend/A2AServer/src/A2AServer/v2/domain_manifest.py`
  - 用 yaml 描述整个 agent 拓扑
  - 4 个 dataclass: `DomainManifest / AgentSpec / HostConfig / ServiceDiscovery`
- ✅ `bridge.py` 的两个硬编码点改成从 `load_default().host_agent_name` 读
- ✅ `did_wba.py` 的 svc_port / DID list 改成从 manifest 读
- ✅ 4 个示例 yaml (`pha.health / hr.company / ecommerce.support / edu.tutor`)
- ✅ 兼容 fallback: 找不到 yaml 时用硬编码 PHA 默认 (向后兼容)

## 3. 一个 yaml 长什么样

```yaml
domain:
  name: "my_app"
  display_name: "我的应用"
  version: "0.1.0"

host:
  name: "triage" # 主入口 / fallback agent
  fallback_keywords: ["开始", "hello"]
  classify_model: "deepseek-chat"

agents:
  - name: "triage" # 必须全局唯一
    display_name: "智能分诊"
    description: "..."
    keywords: ["咨询", "想"]
    tools_module: "triage" # → load_mcp_tools("triage")
    phacore_modules: [] # 阶段48-19 PhaCore
    aliases: ["分诊员"]
    port: 9101 # K8s service port
    dangerously: false # HITL required?

  # ... 更多 agent

service_discovery:
  default_port_offset: 10010
  services:
    triage: 10101
    agent_a: 10102

did:
  domain: "mycompany.local"
  prefix: "did:wba"

mcp_transport: "streamable_http"
```

详见 `examples/domain_configs/pha.health.yaml` (full).

## 4. 怎么切换 domain

```bash
# 4 种方法
PHA_DOMAIN_MANIFEST=hr.company python main.py          # 文件名 (在 examples/domain_configs/ 下)
PHA_DOMAIN_MANIFEST=/path/to/my.yaml python main.py     # 完整路径
PHA_MANIFEST_DIR=/path/to/dir python main.py           # 改搜索目录
# 不设环境变量: 默认 pha.health.yaml
```

## 5. PHA 已提供的 4 个示例 yaml

| yaml                     | 场景                | agent 配置                                            |
| ------------------------ | ------------------- | ----------------------------------------------------- |
| `pha.health.yaml`        | 个人健康助手 (默认) | health_advisor + records + medication + visit_summary |
| `hr.company.yaml`        | 企业 HR / IT / 财务 | concierge + hr_advisor + it_support + finance_advisor |
| `ecommerce.support.yaml` | 电商客服            | triage + pre_sales + logistics + after_sales          |
| `edu.tutor.yaml`         | 教育教学            | guide + lecturer + ta + recommender                   |

## 6. 实际部署一个新 domain 的 5 步

```bash
# 1. 选 yaml 模板
cp examples/domain_configs/hr.company.yaml my_e-commerce.yaml

# 2. 改 agent 名 + 加 prompt + 加 tools
cd backend/EcommerceSupport
mkdir -p mcpserver
# 写 mcpserver/order_tool.py / logistics_tool.py / return_tool.py 等
# (每个 @mcp.tool() 装饰的函数会被 mcp_discover 自动扫到)

# 3. 改 yaml 里 tools_module 字段 (例如: tools_module: "ecommerce_support")

# 4. 镜像构建 + 改 docker-compose (改 service 端口 + 环境变量)

# 5. PHA_DOMAIN_MANIFEST=my_e-commerce.yaml docker-compose up
```

注意:

- `phacore_modules` 字段可让 agent re-export OCR 等共享能力
- `dangerously: true` 让该 agent 的工具自动 require HITL (改 `dangerous_tools.py` 自动)

## 7. 还没自动化的硬编码

| 位置                                                              | 改的方法                                  | 状态     |
| ----------------------------------------------------------------- | ----------------------------------------- | -------- |
| `bridge.py` fallback agent                                        | ✅ 已读 manifest                          | 完成     |
| `did_wba.py` svc_port                                             | ✅ 已读 manifest                          | 完成     |
| `did_wba.py` DID list                                             | ✅ 已读 manifest                          | 完成     |
| `frontend/multiagent_front/src/pages/NewChat.jsx` agent name 显示 | 需改前端, 用 manifest                     | **TODO** |
| `host_graph.py` keywords routing                                  | 已在 agent 层用 keyword 字段              | 部分完成 |
| `dangerous_tools.py` HITL 配置                                    | 需改成从 `manifest.dangerous_agents()` 读 | **TODO** |
| K8s manifest (k8s/04-mcps.yaml)                                   | 需改 port + service name                  | **TODO** |

## 8. 后续 (待 Stage 48-21+)

- [ ] 前端 `NewChat.jsx` 拉 `GET /v2/manifest` 显示当前 domain + agent 列表
- [ ] `dangerous_tools.py` 从 manifest `dangerously: true` 自动收集
- [ ] K8s Helm chart 根据 manifest 动态生成
- [ ] 加 manifest validator (schema check)
- [ ] LangGraph routing 根据 manifest 动态 build

---

# 验证

```bash
python scripts/test_domain_manifest.py   # 4 个 yaml 都能加载
```

输出:

```
=== Test 1: 默认 (PHA) ===
  domain: personal_health_assistant
  host_agent: health_advisor

=== Test 2: HR 企业助手 ===
  domain: enterprise_assistant
  host_agent: concierge
  agents: concierge + hr_advisor + it_support + finance_advisor

=== Test 3: 电商 ===
  domain: ecommerce_support
  host_agent: triage_agent
  ...
```

---

## 9. 阶段 48-21: API 端点 + 前端切换

### 后端端点 (FastAPI)

| 端点                                                   | 用途                                                 |
| ------------------------------------------------------ | ---------------------------------------------------- |
| `GET /v2/manifest`                                     | 当前 domain 全字段                                   |
| `GET /v2/manifest/list`                                | 4 个 yaml 预览 (name / display / agent_count / host) |
| `GET /v2/manifest/dangerous`                           | 当前 domain 的 HITL 候选                             |
| `POST /v2/manifest/switch` body=`{name: "hr.company"}` | 切换 (env var level, 不持久化)                       |

### 试一下

```bash
# 当前默认
curl http://localhost:13002/v2/manifest

# 列 yaml
curl http://localhost:13002/v2/manifest/list

# 切换到 HR
curl -X POST http://localhost:13002/v2/manifest/switch \
  -H 'Content-Type: application/json' \
  -d '{"name": "hr.company"}'
```

### 前端 DomainSwitcher

NewChat 顶部 chip:

- `[PHA]个人健康助手` — 点击 → 下拉 4 个 yaml (PHA/HR/电商/教育)
- 当前 yaml 有 "当前" chip + checkmark
- 切换后 ManifestBadge 自动 reload, agent chips 同步更新
- 🔒 = dangerously agent (HITL 自动加)

### dangerous_tools 自动收集

旧:

```python
if agent_name == "medication_reminder":
    return {"add_medication_reminder": True, "log_medication_taken": True, ...}
elif agent_name == "health_records":
    return {"delete_reminder": True, "save_health_record": True, ...}
```

新:

```python
# 1. 读 manifest.get_agent(name).dangerously
# 2. 如果 True → 该 agent 的所有写类 tool 自动 (delete/add/save/send/log_taken/...)
# 3. 否则 → 读旧硬编码 fallback
```

效果: HR `finance_advisor` 加了 `dangerously: true` 后, 该 agent 的所有报销/付款/审批 tool 自动 require HITL, **不用改代码**.

### 注意事项

- `/v2/manifest/switch` 是 process-level (写到 env var), 不是持久化. 进程重启就回默认 yaml.
- 想持久化就要在 K8s deployment 加 env var, 或 hostapi 启动时读文件 + 写到 env var.
- 已经 cache 的 agent (v2_agent 单例) 不会立即重载, 下一请求会刷新.
