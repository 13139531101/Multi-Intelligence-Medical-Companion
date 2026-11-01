# -*- coding: utf-8 -*-
"""
越权（IDOR）回归门禁 —— **身份必须只来自已验证的 token**。

对应漏洞
--------
F-001  body.user_id 覆盖 token           → 越权读他人健康档案
F-002  body.metadata.user_id 覆盖        → 绕过 F-001 的修复
F-003  body.metadata 任意字段透传        → 攻击面不受控
F-012  白名单过滤点覆盖不全              → body.selected_agent 绕过过滤

证据链（同一份测试文件，两个 tag）
----------------------------------
    git checkout vuln-001  && python tests/security/test_authz_idor.py   # FAIL
    git checkout fixed-001 && python tests/security/test_authz_idor.py   # PASS

被测对象
--------
A2AServer.v2.request_identity.resolve_request_identity
真实入口：frontend/hostAgentAPI/api.py 的 /v2/chat/stream 与 /v2/chat/resume
最后一组断言会静态检查这两个入口**确实走了收口模块** ——
防止有人哪天嫌麻烦，在 api.py 里自己再写一遍 `body.get("user_id")`。

四条安全不变式
--------------
1. 身份不可被请求体覆盖    body.user_id / metadata.user_id 都无效
2. 别名同样无效            uid / userId / sub 都不能覆盖
3. 客户端不能塞任意元数据  只有白名单 key 能进最终 metadata
4. 没有身份就拒绝          fail-closed，不许退到 "default_user"

为什么写成纯标准库
------------------
门禁要在 CI 里毫秒级跑完，不能依赖 DB / 网络 / LLM / pytest。
所以这里不 import pytest，也不 import 任何业务模块 ——
被测的收口模块本身就是零重依赖的。
"""
import os
import sys

# 让 import 找 backend/A2AServer/src
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))  # tests/security -> tests -> repo root
sys.path.insert(0, os.path.join(_ROOT, "backend", "A2AServer", "src"))

from A2AServer.v2.request_identity import (  # noqa: E402
    CLIENT_META_ALLOWED,
    MissingIdentity,
    resolve_request_identity,
)

ATTACKER = {"id": "attacker_001", "user_id": "attacker_001"}
VICTIM = "victim_001"


# --------------------------------------------------------------------------
# 1. 身份不可被请求体覆盖
# --------------------------------------------------------------------------
def check_body_cannot_override_identity():
    """顶层 body.user_id 不得压过 token。"""
    ident = resolve_request_identity(
        ATTACKER, {"message": "我最近身体怎么样", "user_id": VICTIM}, "conv_1"
    )
    ok = ident.user_id == ATTACKER["id"]
    detail = f"最终身份 = {ident.user_id!r}（期望 {ATTACKER['id']!r}）"
    return ok, detail


# --------------------------------------------------------------------------
# 2. 别名同样无效
# --------------------------------------------------------------------------
def check_metadata_aliases_cannot_override_identity():
    """metadata 里的 user_id / uid / userId / sub 都不能覆盖身份。"""
    body = {
        "message": "我最近身体怎么样",
        "metadata": {
            "user_id": VICTIM,
            "uid": VICTIM,
            "userId": VICTIM,
            "sub": VICTIM,
        },
    }
    ident = resolve_request_identity(ATTACKER, body, "conv_1")
    ok = ident.user_id == ATTACKER["id"] and ident.metadata.get("user_id") == ATTACKER["id"]
    detail = f"最终 metadata.user_id = {ident.metadata.get('user_id')!r}"
    return ok, detail


# --------------------------------------------------------------------------
# 3. 客户端不能塞任意元数据
# --------------------------------------------------------------------------
def check_client_metadata_is_allowlisted():
    """只有白名单 key 能进最终 metadata。"""
    body = {
        "message": "我最近身体怎么样",
        "metadata": {
            "selected_agent": "health_records",  # 合法路由字段，应保留
            "v2_mode": "multi",                 # 合法路由字段，应保留
            "evil_key": "payload",              # 不在白名单，应被丢弃
            "role": "admin",                    # 不在白名单，应被丢弃
        },
    }
    ident = resolve_request_identity(ATTACKER, body, "conv_1")
    leaked = sorted(set(ident.metadata) - set(CLIENT_META_ALLOWED) - {"conversation_id", "user_id"})
    kept_legal = all(k in ident.metadata for k in ("selected_agent", "v2_mode"))
    ok = not leaked and kept_legal
    detail = f"泄漏字段 = {leaked or '无'}；合法路由字段保留 = {kept_legal}"
    return ok, detail


# --------------------------------------------------------------------------
# 4. 没有身份就拒绝（fail-closed）
# --------------------------------------------------------------------------
def check_missing_identity_is_rejected():
    """无已认证身份时必须拒绝，不许退到 'default_user' 或任何全局兜底。"""
    try:
        ident = resolve_request_identity({}, {"message": "hi"}, "conv_1")
    except MissingIdentity:
        return True, "已拒绝（MissingIdentity → 401）"
    except Exception as e:  # noqa: BLE001
        return False, f"抛了非预期异常 {type(e).__name__}，接口契约应当是 MissingIdentity"
    return False, f"未拒绝，落到 user_id = {ident.user_id!r}"


# --------------------------------------------------------------------------
# 5. 入口必须走收口模块（结构守卫）
# --------------------------------------------------------------------------
def check_endpoints_use_single_ingress():
    """api.py 的两处身份取用必须走收口模块，不能再有就地解析。"""
    api_path = os.path.join(_ROOT, "frontend", "hostAgentAPI", "api.py")
    try:
        with open(api_path, encoding="utf-8") as f:
            src = f.read()
    except OSError as e:
        return False, f"读不到 {api_path}: {e}"

    problems = []
    if 'body.get("user_id")' in src:
        problems.append('api.py 仍有 body.get("user_id") —— 绕过收口模块就地解析身份')
    uses = src.count("resolve_request_identity(")
    if uses < 2:
        problems.append(f"api.py 里 resolve_request_identity 出现 {uses} 次，应覆盖 2 处入口")
    detail = "; ".join(problems) if problems else f"api.py 两处入口均走收口模块（{uses} 处引用）"
    return not problems, detail


CHECKS = [
    ("身份不可被请求体覆盖", check_body_cannot_override_identity),
    ("身份别名不可覆盖", check_metadata_aliases_cannot_override_identity),
    ("客户端元数据白名单", check_client_metadata_is_allowlisted),
    ("无身份即拒绝", check_missing_identity_is_rejected),
    ("入口走单一收口", check_endpoints_use_single_ingress),
]


# --------------------------------------------------------------------------
# pytest 入口
# --------------------------------------------------------------------------
def test_identity_is_never_taken_from_request_body():
    """pytest 入口：五条不变式全过才算绿。"""
    failures = []
    for name, fn in CHECKS:
        ok, detail = fn()
        if not ok:
            failures.append(f"[{name}] {detail}")
    assert not failures, "安全不变式被破坏:\n" + "\n".join("  - " + f for f in failures)


# --------------------------------------------------------------------------
# 独立运行入口（CI 门禁用这个）
# --------------------------------------------------------------------------
def main() -> int:
    print("== PHA 越权(IDOR)回归门禁 — 身份必须只来自已验证的 token ==\n")
    print(f"  被测: A2AServer.v2.request_identity.resolve_request_identity")
    print(f"  入口: /v2/chat/stream, /v2/chat/resume\n")

    failed = 0
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"检查本身抛异常 {type(e).__name__}: {e}"
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{mark}] {name:<22} {detail}")

    print()
    if failed:
        print(f"[FAIL] {failed}/{len(CHECKS)} 条不变式被破坏 —— 身份可被请求体影响")
        return 1
    print(f"[OK] {len(CHECKS)}/{len(CHECKS)} 条不变式成立 —— 身份只来自已验证的 token")
    return 0


if __name__ == "__main__":
    sys.exit(main())
