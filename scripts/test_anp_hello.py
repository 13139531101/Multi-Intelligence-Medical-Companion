"""ANP SDK Hello World 测试"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

print("=" * 70)
print("ANP SDK Hello World 测试")
print("=" * 70)

# Test 1: 验证 SDK 安装
print("\n=== Test 1: 验证 anp SDK 安装 ===")
try:
    from anp.openanp import AgentConfig, anp_agent, interface
    print(f"  [OK] anp.openanp imported: AgentConfig, anp_agent, interface")
except ImportError as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

# Test 2: 验证 SDK 版本
print("\n=== Test 2: 验证 anp 版本 ===")
try:
    import anp
    print(f"  [OK] anp package imported")
    print(f"        version: {getattr(anp, '__version__', 'unknown')}")
except ImportError as e:
    print(f"  [FAIL] {e}")

# Test 3: 验证 DID:WBA 模块
print("\n=== Test 3: DID:WBA 模块 ===")
try:
    from anp.did_wba import generate_did, generate_keypair
    print(f"  [OK] anp.did_wba imported")
    # 试着生成 DID
    try:
        did = generate_did(domain="pha.example.com", path="test_agent")
        print(f"  [OK] generated DID: {did}")
    except Exception as e:
        print(f"  [WARN] generate_did failed: {e}")
except ImportError as e:
    print(f"  [FAIL] {e}")

# Test 4: 验证 FastAPI 集成
print("\n=== Test 4: 验证 OpenANP 创建 Agent ===")
from fastapi import FastAPI

@anp_agent(AgentConfig(
    name="TestCalculator",
    did="did:wba:pha.example.com:test_calculator",
    prefix="/agent",
    description="Test ANP agent - simple calculator",
))
class TestCalculator:
    @interface
    async def add(self, a: int, b: int) -> int:
        return a + b

    @interface
    async def multiply(self, a: int, b: int) -> int:
        return a * b

app = FastAPI(title="Test ANP Agent")
app.include_router(TestCalculator.router())

print(f"  [OK] Created ANP agent: TestCalculator")
print(f"        routes:")
for route in app.routes:
    if hasattr(route, "path"):
        print(f"          {route.methods} {route.path}")

# Test 5: 看 OpenANP 默认暴露的端点
print("\n=== Test 5: OpenANP 默认暴露 ===")
expected_endpoints = [
    "/agent/ad.json",            # Agent Description 文档
    "/agent/interface.json",     # OpenRPC 接口定义
    "/agent/rpc",                # JSON-RPC 2.0 调用端点
]
for ep in expected_endpoints:
    print(f"  Expected: {ep}")

# Test 6: 模拟启动 + 调用（用 TestClient）
print("\n=== Test 6: 模拟 RPC 调用 ===")
try:
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    # 调 GET /agent/ad.json
    r = client.get("/agent/ad.json")
    print(f"  GET /agent/ad.json: HTTP {r.status_code}")
    if r.status_code == 200:
        ad = r.json()
        print(f"    name: {ad.get('name')}")
        print(f"    did: {ad.get('did')}")
        print(f"    description: {ad.get('description')}")
    
    # 调 GET /agent/interface.json
    r = client.get("/agent/interface.json")
    print(f"  GET /agent/interface.json: HTTP {r.status_code}")
    if r.status_code == 200:
        ifc = r.json()
        if isinstance(ifc, dict):
            methods = ifc.get("methods", [])
            print(f"    methods: {[m.get('name') for m in methods]}")
    
    # 调 POST /agent/rpc (JSON-RPC 2.0)
    rpc_body = {
        "jsonrpc": "2.0",
        "method": "add",
        "params": {"a": 3, "b": 5},
        "id": 1
    }
    r = client.post("/agent/rpc", json=rpc_body)
    print(f"  POST /agent/rpc add(3,5): HTTP {r.status_code}")
    if r.status_code == 200:
        result = r.json()
        print(f"    result: {result}")
    
    # 调 multiply
    rpc_body = {
        "jsonrpc": "2.0",
        "method": "multiply",
        "params": {"a": 4, "b": 7},
        "id": 2
    }
    r = client.post("/agent/rpc", json=rpc_body)
    print(f"  POST /agent/rpc multiply(4,7): HTTP {r.status_code}")
    if r.status_code == 200:
        result = r.json()
        print(f"    result: {result}")
except ImportError:
    print(f"  [SKIP] fastapi.testclient not available, skipping RPC test")

print("\n" + "=" * 70)
print("ANP SDK 测试完成")
print("=" * 70)