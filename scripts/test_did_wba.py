"""阶段39-2: DID WBA 签名验证测试"""
import json
import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))

from A2AServer.v2.did_wba import (
    DIDDocument, DIDKeyStore, get_keystore,
    sign_request, verify_request,
)


# Test 1: 密钥对生成
print("=" * 60)
print("Test 1: DIDKeyStore.generate_keypair")
print("=" * 60)
ks = DIDKeyStore()
priv, pub = ks.generate_keypair("did:wba:pha.local:test1")
assert len(priv) == 32
assert len(pub) == 32
# 简化版：pub = priv（HMAC 对称）
print(f"  priv len: {len(priv)}")
print(f"  pub len: {len(pub)}")
print(f"  priv == pub (simplified symmetric): {priv == pub}")
print("[PASS] Test 1")


# Test 2: 注册 DID + 生成 DID Document
print()
print("=" * 60)
print("Test 2: DIDKeyStore.register + DIDDocument")
print("=" * 60)
doc = ks.register("did:wba:pha.local:health_advisor")
assert doc.id == "did:wba:pha.local:health_advisor"
assert doc.public_key  # base64
d = doc.to_dict()
assert d["@context"] == "https://www.w3.org/ns/did/v1"
assert d["id"] == "did:wba:pha.local:health_advisor"
assert len(d["verificationMethod"]) == 1
print(f"  did: {doc.id}")
print(f"  public_key (base64): {doc.public_key[:40]}...")
print(f"  verificationMethod: {len(d['verificationMethod'])}")
print(f"  authentication: {doc.authentication}")
print("[PASS] Test 2")


# Test 3: 签名 + 验证 (正常)
print()
print("=" * 60)
print("Test 3: sign_request + verify_request (正常)")
print("=" * 60)
ks = DIDKeyStore()
priv, pub = ks.generate_keypair("did:wba:pha.local:test3")
ts = time.time()
sig = sign_request(priv, "POST", "/rpc", '{"a":1}', ts)
print(f"  signature: {sig[:40]}...")
valid, err = verify_request(pub, sig, "POST", "/rpc", '{"a":1}', ts)
print(f"  valid: {valid}, err: {err}")
assert valid
print("[PASS] Test 3")


# Test 4: 验证失败 (错误 body)
print()
print("=" * 60)
print("Test 4: verify_request (错误 body → fail)")
print("=" * 60)
ts = time.time()
sig = sign_request(priv, "POST", "/rpc", '{"a":1}', ts)
valid, err = verify_request(pub, sig, "POST", "/rpc", '{"a":2}', ts)  # body 变了
print(f"  valid: {valid}, err: {err}")
assert not valid
assert err == "signature mismatch"
print("[PASS] Test 4")


# Test 5: 验证失败 (过期 timestamp)
print()
print("=" * 60)
print("Test 5: verify_request (过期 timestamp → fail)")
print("=" * 60)
old_ts = time.time() - 600  # 10 分钟前
sig = sign_request(priv, "POST", "/rpc", '{"a":1}', old_ts)
valid, err = verify_request(pub, sig, "POST", "/rpc", '{"a":1}', old_ts)
print(f"  valid: {valid}, err: {err}")
assert not valid
assert "expired" in err
print("[PASS] Test 5")


# Test 6: get_keystore 单例 + 默认 5 个 DID
print()
print("=" * 60)
print("Test 6: get_keystore 单例（默认 5 个 PHA DID）")
print("=" * 60)
ks1 = get_keystore()
ks2 = get_keystore()
assert ks1 is ks2  # 单例
dids = ks1.list_dids()
print(f"  registered DIDs: {dids}")
assert "did:wba:pha.local:hostapi" in dids
assert "did:wba:pha.local:health_advisor" in dids
assert "did:wba:pha.local:health_records" in dids
assert "did:wba:pha.local:medication_reminder" in dids
assert "did:wba:pha.local:visit_summary" in dids
print(f"  total: {len(dids)}")
print("[PASS] Test 6")


# Test 7: get_document
print()
print("=" * 60)
print("Test 7: get_document")
print("=" * 60)
doc = ks1.get_document("did:wba:pha.local:hostapi")
assert doc is not None
assert doc.id == "did:wba:pha.local:hostapi"
assert doc.public_key
print(f"  found: {doc.id}")
print(f"  pub key: {doc.public_key[:40]}...")

doc2 = ks1.get_document("did:wba:unknown")
assert doc2 is None
print(f"  unknown did: None (correct)")
print("[PASS] Test 7")


# Test 8: 完整签名 + 验证流程 (end-to-end)
print()
print("=" * 60)
print("Test 8: End-to-end 签名流程")
print("=" * 60)
ks = DIDKeyStore()
did = "did:wba:pha.local:health_advisor"
ks.register(did)
priv_key = ks.get_private_key(did)
doc = ks.get_document(did)

# 模拟 agent 发送请求
import base64 as b64mod
ts = time.time()
body = json.dumps({"method": "echo", "params": ["hello"]})
sig = sign_request(priv_key, "POST", "/agent/rpc", body, ts)
print(f"  client signed: {sig[:30]}...")

# 模拟 server 验证
pub_key = b64mod.b64decode(doc.public_key)
valid, err = verify_request(pub_key, sig, "POST", "/agent/rpc", body, ts)
print(f"  server verified: valid={valid}, err={err}")
assert valid
print("[PASS] Test 8")


print()
print("=" * 60)
print("[ALL PASS] 8/8 tests")
print("=" * 60)