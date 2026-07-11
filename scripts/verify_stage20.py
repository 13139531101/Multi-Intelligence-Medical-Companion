"""阶段20 验收 - OAuth2 鉴权 (GitHub + JWT + 刷新 + 撤销)"""
import os
import sys
import time
import asyncio

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PHA_OAUTH_TEST_MODE'] = 'true'  # 测试模式：免 GitHub 直接发 token
os.environ['PHA_OAUTH_ISSUE_RATE_LIMIT'] = '10'

import locale
try:
    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
except Exception:
    pass

# 强制加入 v2 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))

import jwt
import httpx

print('=' * 70)
print('PHA v2 阶段20 验收 - OAuth2 鉴权')
print('=' * 70)

total = 0
passed = 0


def check(name, ok, detail=''):
    global total, passed
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:55s} {detail}')
    total += 1
    if ok:
        passed += 1


# ---- 1. JWT 颁发 ----
print('\n[1] JWT 颁发 (access + refresh)')
from A2AServer.v2 import oauth2

access = oauth2.create_access_token("user_001")
check('create_access_token 返 access_token 字段', "access_token" in access)
check('access_token 是非空字符串', isinstance(access["access_token"], str) and len(access["access_token"]) > 20)
check('token_type = Bearer', access["token_type"] == "Bearer")
check('expires_in = 900 (15min)', access["expires_in"] == 900)

refresh = oauth2.create_refresh_token("user_001")
check('create_refresh_token 返 refresh_token 字段', "refresh_token" in refresh)
check('refresh expires_in = 604800 (7day)', refresh["expires_in"] == 604800)

# ---- 2. JWT 解码与校验 ----
print('\n[2] JWT 解码校验')
payload = oauth2.decode_token(access["access_token"], expected_type="access")
check('access token 解码成功', payload["sub"] == "user_001")
check('access token type=access', payload["type"] == "access")
check('access token 含 jti', "jti" in payload and len(payload["jti"]) > 0)

try:
    oauth2.decode_token(refresh["refresh_token"], expected_type="access")
    check('refresh token 拒绝作为 access', False, 'should have raised')
except ValueError as e:
    check('refresh token 拒绝作为 access', "type" in str(e) or "mismatch" in str(e), str(e)[:60])

try:
    oauth2.decode_token("invalid.token.here", expected_type="access")
    check('无效 token 被拒', False)
except ValueError as e:
    check('无效 token 被拒', "invalid" in str(e), str(e)[:60])

# ---- 3. Refresh 轮转 ----
print('\n[3] Refresh token 轮转')
new_tokens = asyncio.run(oauth2.refresh_tokens(refresh["refresh_token"]))
check('refresh 后获新 access', "access_token" in new_tokens and new_tokens["access_token"] != access["access_token"])
check('refresh 后获新 refresh (轮转)', "refresh_token" in new_tokens and new_tokens["refresh_token"] != refresh["refresh_token"])

# 旧 refresh 应该被撤销
try:
    oauth2.decode_token(refresh["refresh_token"], expected_type="refresh")
    check('旧 refresh 被撤销', False, 'should have raised')
except ValueError as e:
    check('旧 refresh 被撤销', "revoked" in str(e), str(e)[:60])

# ---- 4. Token 撤销 ----
print('\n[4] Token 主动撤销')
access2 = oauth2.create_access_token("user_002")
payload2 = oauth2.decode_token(access2["access_token"], expected_type="access")
asyncio.run(oauth2.revoke_token(payload2["jti"], payload2["exp"]))
try:
    oauth2.decode_token(access2["access_token"], expected_type="access")
    check('撤销后 access 被拒', False)
except ValueError as e:
    check('撤销后 access 被拒', "revoked" in str(e), str(e)[:60])

# 撤销过期清理
time.sleep(0.1)  # 太短，token 还未过期
# 强制 revoke 一个已经过期的 token
import time
old_exp = int(time.time()) - 1
asyncio.run(oauth2.revoke_token("test_old_jti", old_exp))
cleaned = oauth2._revoked.cleanup_expired()
check('cleanup_expired 清理过期', cleaned >= 1, f'cleaned={cleaned}')

# ---- 5. Bearer 解析 ----
print('\n[5] Bearer token 解析')
check('extract_bearer("Bearer xyz") = xyz', oauth2.extract_bearer("Bearer xyz") == "xyz")
check('extract_bearer("bearer xyz") = xyz (大小写)', oauth2.extract_bearer("bearer xyz") == "xyz")
check('extract_bearer("Basic xyz") = None', oauth2.extract_bearer("Basic xyz") is None)
check('extract_bearer("") = None', oauth2.extract_bearer("") is None)
check('extract_bearer("Bearer") = None (无 token)', oauth2.extract_bearer("Bearer") is None)

access3 = oauth2.create_access_token("user_003")
hdr = f"Bearer {access3['access_token']}"
uid = oauth2.get_current_user_id(hdr)
check('get_current_user_id 提取 user_id', uid == "user_003", f"got {uid!r}")
check('无 header 时 get_current_user_id = None', oauth2.get_current_user_id("") is None)

# ---- 6. 签发速率限制 ----
print('\n[6] 签发速率限制 (10/min)')
allowed_count = 0
for i in range(15):
    if oauth2._issue_limiter.is_allowed("192.168.1.1"):
        allowed_count += 1
check('前 10 次允许', allowed_count == 10, f'allowed={allowed_count}')
# 换 IP 重新允许
check('其他 IP 不受影响', oauth2._issue_limiter.is_allowed("192.168.1.2"))

# ---- 7. GitHub OAuth URL 构造 ----
print('\n[7] GitHub OAuth URL 构造')
# 测试环境没有真实 client_id，但我们能测参数正确
os.environ['GITHUB_OAUTH_CLIENT_ID'] = 'test_client_123'
os.environ['GITHUB_OAUTH_CLIENT_SECRET'] = 'test_secret_456'
# 重新 load 模块
import importlib
importlib.reload(oauth2)
url = oauth2.build_authorize_url(state="test_state_abc")
check('URL 含 client_id=test_client_123', "client_id=test_client_123" in url)
check('URL 含 redirect_uri', "redirect_uri=" in url)
check('URL 含 state=test_state_abc', "state=test_state_abc" in url)
check('URL 含 scope', "scope=" in url)
check('URL 含 response_type=code', "response_type=code" in url)
check('URL 是 github.com', url.startswith("https://github.com/login/oauth/authorize"))

# generate_state 长度
state = oauth2.generate_state()
check('generate_state 长度 > 30', len(state) > 30, f'len={len(state)}')

# ---- 8. issue_test_token ----
print('\n[8] test_issue（仅测试模式）')
result = oauth2.issue_test_token("test_alice", "user")
check('test_issue 返 access_token', "access_token" in result)
check('test_issue 返 refresh_token', "refresh_token" in result)
check('test_issue 返 user_id', result.get("user_id") == "test_alice")
# 关掉 test mode 应拒绝
os.environ['PHA_OAUTH_TEST_MODE'] = 'false'
try:
    oauth2.issue_test_token("test_x")
    check('test mode off 后拒绝', False)
except PermissionError as e:
    check('test mode off 后拒绝', "disabled" in str(e), str(e)[:60])

# ---- 9. Stats ----
print('\n[9] Stats')
stats = oauth2._stats.to_dict()
check('stats 含 issued', "issued" in stats)
check('stats 含 refreshes', "refreshes" in stats)
check('stats 含 revokes', "revokes" in stats)
check('stats 含 config.access_ttl', stats["config"]["access_ttl"] == 900)
check('stats 含 config.refresh_ttl', stats["config"]["refresh_ttl"] == 604800)
check('stats config.github_configured', stats["config"]["github_configured"] is True)
check('stats config.test_mode (off)', stats["config"]["test_mode"] is False)

# ---- 10. HTTP 端点（hostapi /v2/oauth/*）----
print('\n[10] HTTP 端点集成 (hostapi)')
try:
    # 等待 hostapi 启动
    r = httpx.get('http://localhost:13002/v2/oauth/stats', timeout=5)
    check('GET /v2/oauth/stats 200', r.status_code == 200, f'code={r.status_code}')
    data = r.json()
    check('/v2/oauth/stats 含 config', "config" in data)
except Exception as e:
    check('hostapi /v2/oauth/* 集成', False, str(e)[:80])

# /v2/oauth/test-issue (hostapi 启动时 PHA_OAUTH_TEST_MODE=true?)
try:
    r = httpx.post('http://localhost:13002/v2/oauth/test-issue?user_id=verify_user&scope=user', timeout=5)
    if r.status_code == 200:
        check('POST /v2/oauth/test-issue 200 (test mode)', True)
        data = r.json()
        check('test-issue 返 access_token', "access_token" in data)
    elif r.status_code == 403:
        check('POST /v2/oauth/test-issue 403 (test mode off)', True, 'PHAS 未启 test mode')
    else:
        check('POST /v2/oauth/test-issue 异常', False, f'code={r.status_code}')
except Exception as e:
    check('test-issue 调用', False, str(e)[:80])

# ---- 总结 ----
print('\n' + '=' * 70)
print(f'阶段20 验收：{passed}/{total} 通过')
if passed == total:
    print('[OK] 全部通过！阶段20 完成，OAuth2 鉴权全栈就绪。')
else:
    print(f'[WARN] 有 {total - passed} 项失败')
print('=' * 70)
