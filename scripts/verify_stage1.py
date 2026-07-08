"""
阶段1 验收脚本
- 验证 v2 依赖可正常导入
- 验证现有代码未被破坏
- 验证可观测性模块工作正常
"""
from __future__ import annotations
import sys


def check(name: str, fn):
    try:
        fn()
        print(f"  [OK]    {name}")
        return True
    except Exception as e:
        print(f"  [FAIL]  {name}: {e}")
        return False


def main():
    print("=" * 70)
    print("PHA v2 阶段1 验收")
    print("=" * 70)

    passed = 0
    total = 0

    # ---- 1. Python 版本 ----
    print("\n[1] Python 版本检查")
    v = sys.version_info
    if (v.major, v.minor) >= (3, 12):
        print(f"  [OK]    Python {v.major}.{v.minor}.{v.micro}")
        passed += 1
    else:
        print(f"  [FAIL]  Python {v.major}.{v.minor}.{v.micro} < 3.12")
    total += 1

    # ---- 2. AI 框架 ----
    print("\n[2] AI 框架依赖")
    total += 1
    if check("langchain", lambda: __import__("langchain").__version__):
        passed += 1
    total += 1
    if check("langgraph", lambda: __import__("langgraph").__version__):
        passed += 1
    total += 1
    if check("langchain_openai", lambda: __import__("langchain_openai").__version__):
        passed += 1
    total += 1
    if check("langgraph.checkpoint.postgres", lambda: __import__(
        "langgraph.checkpoint.postgres"
    )):
        passed += 1
    total += 1
    if check("langchain_postgres", lambda: __import__("langchain_postgres")):
        passed += 1
    total += 1
    if check("a2a_sdk", lambda: __import__("a2a")):
        passed += 1

    # ---- 3. Web / 数据 ----
    print("\n[3] Web / 数据依赖")
    total += 1
    if check("fastapi", lambda: __import__("fastapi").__version__):
        passed += 1
    total += 1
    if check("uvicorn", lambda: __import__("uvicorn").__version__):
        passed += 1
    total += 1
    if check("pydantic", lambda: __import__("pydantic").VERSION):
        passed += 1
    total += 1
    if check("psycopg", lambda: __import__("psycopg").__version__):
        passed += 1
    total += 1
    if check("sqlalchemy", lambda: __import__("sqlalchemy").__version__):
        passed += 1
    total += 1
    if check("redis", lambda: __import__("redis").__version__):
        passed += 1

    # ---- 4. 可观测性 ----
    print("\n[4] 可观测性依赖")
    total += 1
    if check("opentelemetry-api", lambda: __import__("opentelemetry")):
        passed += 1
    total += 1
    if check("opentelemetry-instrumentation-fastapi", lambda: __import__(
        "opentelemetry.instrumentation.fastapi"
    )):
        passed += 1
    total += 1
    if check("langsmith", lambda: __import__("langsmith")):
        passed += 1
    total += 1
    if check("langfuse", lambda: __import__("langfuse")):
        passed += 1

    # ---- 5. 可观测性模块自测 ----
    print("\n[5] 可观测性模块自测")
    sys.path.insert(0, "backend")
    total += 1
    if check("observability.setup_observability()", lambda: __import__(
        "observability"
    ).setup_observability("pha-verify")):
        passed += 1

    # ---- 6. 现有业务模块不破坏 ----
    print("\n[6] 现有业务模块导入测试（向后兼容）")
    sys.path.insert(0, "backend/A2AServer/src")
    sys.path.insert(0, "backend/HealthAdvisor")
    sys.path.insert(0, "frontend/hostAgentAPI")
    total += 1
    if check("common.A2Atypes (现有协议模型)", lambda: __import__(
        "A2AServer.common.A2Atypes"
    )):
        passed += 1

    # ---- 总结 ----
    print("\n" + "=" * 70)
    print(f"阶段1 验收：{passed}/{total} 通过")
    if passed == total:
        print("[OK] 全部通过！可以进入阶段2。")
    else:
        print(f"[WARN] 有 {total - passed} 项失败，请先 pip install -r requirements-v2.txt")
    print("=" * 70)


if __name__ == "__main__":
    main()
