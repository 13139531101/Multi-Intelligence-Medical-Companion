# PHA v2 A2A 分布式架构文档

## 实现状态（阶段48-A2A）

以下功能已在阶段48-A2A 中实施：

| 功能 | 文件 | 状态 |
|------|------|------|
| 真正的 Ed25519 DID 签名 | `backend/A2AServer/src/A2AServer/v2/did_wba.py` | ✅ 已实现 |
| 密钥持久化（`~/.pha/keys/*.raw`） | `did_wba.py` | ✅ 已实现 |
| Sub-agent ANP 端点 mount | `backend/HealthAdvisor/main.py` 等 4 个 main.py | ✅ 已实现 |
| `a2a_integration_tool.py` 改用 `call_anp_rpc` | `backend/HealthAdvisor/mcpserver/a2a_integration_tool.py` | ✅ 已实现 |
| DID 解析从 DomainManifest 读取 | `backend/A2AServer/src/A2AServer/v2/anp_crawler.py` | ✅ 已实现 |
| DomainManifest Peer 拓扑 | `backend/A2AServer/src/A2AServer/v2/domain_manifest.py` | ✅ 已实现 |

---

## 架构概览

```
                    ┌─────────────────────────┐
                    │  用户请求                 │
                    │  (前端 → hostapi:13002) │
                    └───────────┬─────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │health_advisor│◄───│medication_   │───►│health_records│
  │ :10011 /anp  │    │reminder:10012│    │ :10010 /anp  │
  │ AgentCard ✅ │    │ /anp ✅     │    │ AgentCard ✅ │
  └──────────────┘    └──────────────┘    └──────────────┘
         ▲                   ▲
         │    ANP RPC         │
         └────────────────────┘
              点对点 A2A 网络
```

---

## 关键改动说明

### 1. Ed25519 DID 身份（did_wba.py）

- `generate_keypair()` 用 `cryptography` 库生成真正的 Ed25519 密钥对
- 密钥存为原始 32 字节文件（`~/.pha/keys/did_wba_pha_local_<name>.raw`）
- 重启后自动加载已有密钥
- `sign_request()` / `verify_request()` 使用 Ed25519 签名，不再是 HMAC

### 2. Sub-agent ANP 端点

每个 sub-agent 启动时在 Starlette app 上 mount `/anp` 路径：

```python
# backend/HealthAdvisor/main.py 等
anp_app = create_anp_app(
    agent_name="HealthAdvisor",
    description="...",
    forward_to_a2a=lambda **kw: {"status": "ok"},
    did_domain="pha.local",
    prefix="/agent",
)
server.app.mount("/anp", anp_app)
```

结果：
- `GET http://health_advisor:10011/anp/agent/ad.json` → AgentCard
- `POST http://health_advisor:10011/anp/agent/rpc` → JSON-RPC 2.0

### 3. A2A Client 替换（a2a_integration_tool.py）

`_send_task()` 从：
```python
# 旧：A2A v1 raw requests.post
requests.post(f"http://{agent_address}/rpc", json=body, ...)
```

改为：
```python
# 新：ANP JSON-RPC 2.0 via call_anp_rpc
asyncio.run(call_anp_rpc(
    base_url=f"{base_url}/anp",
    method="task/send",
    params={...},
    did=did,
))
```

### 4. DID 解析（anp_crawler.py）

`resolve_did_to_url(did)` 优先从 `DomainManifest.service_discovery` 读取端口，不再硬编码 fallback 映射。

### 5. Peer 拓扑（domain_manifest.py）

```yaml
agents:
  - name: health_advisor
    peers:
      - health_records
      - medication_reminder
      - visit_summary
```

`manifest.can_call(caller, callee)` 检查信任边界。

---

## 待验证

部署后用以下命令验证各阶段改动：

```bash
# Phase 1: Ed25519 签名
curl -X POST http://localhost:13002/anp/did/sign \
  -H "Content-Type: application/json" \
  -d '{"did":"did:wba:pha.local:health_advisor","method":"POST","path":"/task","body":"{}"}'

# Phase 2: Sub-agent ANP 端点
curl http://localhost:10011/anp/agent/ad.json   # health_advisor
curl http://localhost:10012/anp/agent/ad.json   # medication_reminder

# Phase 3: ANP RPC 跨 Agent 调用
curl -X POST http://localhost:10011/anp/agent/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"handle_request","params":{"user_id":"test","query":"hello"},"id":"test1"}'

# Phase 4: DID 解析
curl http://localhost:13002/anp/did/resolve/did:wba:pha.local:medication_reminder
```
