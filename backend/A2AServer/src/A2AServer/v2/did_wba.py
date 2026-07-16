"""
PHA v2 DID WBA 签名验证（阶段39-2）

DID WBA = DID + Web-Based Authentication
类似 mTLS，但基于 DID 标识而不是证书 CN

**核心思想**：
- 每个 agent 有一对密钥（公钥/私钥）
- 公钥存在 DID Document 里
- 调用时用私钥签名请求
- 服务端用公钥验证签名

**简化版实现**（不依赖外部 CA）：
- 密钥对：Ed25519 (推荐) 或 RSA
- DID 文档：JSON，存公钥 + 服务端点
- 签名算法：Ed25519
- 签名内容：timestamp + method + path + body 的 hash

**生产环境应该**：
- 私钥存 HSM / Vault
- 公钥通过 DNS 记录发布（类似 TLSA）
- 用 mTLS / JWT 替代简化签名
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 1. DID 文档
# ============================================================

@dataclass
class DIDDocument:
    """DID Document（W3C 标准简化版）"""
    id: str                                       # did:wba:pha.local:health_advisor
    public_key: str = ""                          # base64 编码的公钥
    authentication: list = field(default_factory=list)  # ["#key-1"]
    service: list = field(default_factory=list)   # [{"id":"agent", "type":"ANP", "serviceEndpoint":"http://..."}]
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["@context"] = "https://www.w3.org/ns/did/v1"
        d["verificationMethod"] = [
            {
                "id": f"{self.id}#key-1",
                "type": "Ed25519VerificationKey2020",
                "controller": self.id,
                "publicKeyBase64": self.public_key,
            }
        ] if self.public_key else []
        return d


# ============================================================
# 2. DID 密钥存储
# ============================================================

class DIDKeyStore:
    """简化的 DID 密钥存储（生产应换 HSM）"""

    def __init__(self):
        self._private_keys: Dict[str, bytes] = {}  # did -> private_key_bytes
        self._documents: Dict[str, DIDDocument] = {}

    def generate_keypair(self, did: str) -> tuple:
        """生成 Ed25519 密钥对（用 hashlib + hmac 模拟，避免外部依赖）"""
        # 模拟：实际应用用 cryptography 库的 ed25519
        # 简化：pub_key = priv_key（用于对称 HMAC；生产应用 ed25519 真密钥对）
        seed = os.urandom(32)
        private_key = hashlib.sha256(seed + did.encode()).digest()
        public_key = private_key
        return private_key, public_key

    def register(self, did: str, public_key: Optional[bytes] = None) -> DIDDocument:
        """注册一个 DID（自动生成密钥对如果没传）"""
        if public_key is None:
            private, public = self.generate_keypair(did)
            self._private_keys[did] = private
            # 简化：公开 key = private key（实际应用 ed25519 公私钥对）
            public_key = private

        pub_b64 = base64.b64encode(public_key).decode()
        doc = DIDDocument(
            id=did,
            public_key=pub_b64,
            authentication=[f"{did}#key-1"],
        )
        self._documents[did] = doc
        logger.info("[did_wba] registered %s", did)
        return doc

    def get_document(self, did: str) -> Optional[DIDDocument]:
        return self._documents.get(did)

    def list_dids(self) -> list:
        return list(self._documents.keys())

    def get_private_key(self, did: str) -> Optional[bytes]:
        return self._private_keys.get(did)


# ============================================================
# 3. 签名 / 验证
# ============================================================

def sign_request(
    private_key: bytes,
    method: str,
    path: str,
    body: str = "",
    timestamp: Optional[float] = None,
) -> str:
    """
    用私钥签名请求

    Args:
        private_key: 32 字节私钥
        method: HTTP method (GET/POST/...)
        path: URL path
        body: 请求体（已序列化）
        timestamp: Unix 时间戳（默认现在）

    Returns:
        base64 编码的签名
    """
    if timestamp is None:
        timestamp = time.time()

    # 构造签名 payload
    body_hash = hashlib.sha256(body.encode() if body else b"").hexdigest()
    payload = f"{method}\n{path}\n{timestamp:.0f}\n{body_hash}"

    # 用 HMAC-SHA256 模拟 Ed25519（实际生产用 nacl 或 cryptography）
    signature = hmac.new(private_key, payload.encode(), hashlib.sha256).digest()
    return base64.b64encode(signature).decode()


def verify_request(
    public_key: bytes,
    signature_b64: str,
    method: str,
    path: str,
    body: str = "",
    timestamp: Optional[float] = None,
    max_age_sec: int = 300,
) -> tuple:
    """
    验证请求签名

    Returns:
        (valid, error_message)
    """
    if timestamp is None:
        return False, "missing timestamp"

    # 1. 检查时间戳（防重放）
    now = time.time()
    if abs(now - timestamp) > max_age_sec:
        return False, f"timestamp expired (delta={now - timestamp:.0f}s, max={max_age_sec}s)"

    # 2. 重新签名
    body_hash = hashlib.sha256(body.encode() if body else b"").hexdigest()
    payload = f"{method}\n{path}\n{timestamp:.0f}\n{body_hash}"
    expected = hmac.new(public_key, payload.encode(), hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode()

    # 3. 恒定时间比较
    if hmac.compare_digest(signature_b64, expected_b64):
        return True, ""
    return False, "signature mismatch"


# ============================================================
# 4. 单例 + 默认 PHA DIDs
# ============================================================

_keystore: Optional[DIDKeyStore] = None


def get_keystore() -> DIDKeyStore:
    global _keystore
    if _keystore is None:
        _keystore = DIDKeyStore()
        # 默认注册 5 个 PHA DID
        for name in [
            "hostapi",
            "health_advisor",
            "health_records",
            "medication_reminder",
            "visit_summary",
        ]:
            did = f"did:wba:pha.local:{name}"
            _keystore.register(did)
    return _keystore


def get_default_port(name: str) -> int:
    port_map = {
        "hostapi": 13002,
        "health_advisor": 10011,
        "health_records": 10010,
        "medication_reminder": 10012,
        "visit_summary": 10013,
    }
    return port_map.get(name, 10000)


__all__ = [
    "DIDDocument",
    "DIDKeyStore",
    "get_keystore",
    "sign_request",
    "verify_request",
    "get_default_port",
]