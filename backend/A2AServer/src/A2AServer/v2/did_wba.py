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
import json
import logging
import os
import pathlib
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

# 密钥持久化目录
_KEY_DIR = pathlib.Path(os.environ.get("PHA_KEYS_DIR", "/app/.pha/keys"))
_KEY_DIR.mkdir(parents=True, exist_ok=True)


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
        """生成真正的 Ed25519 密钥对，存原始 32 字节（阶段48-A2A）"""
        key_file = _KEY_DIR / f"{did.replace(':', '_')}.raw"
        if key_file.exists():
            priv_bytes = key_file.read_bytes()
        else:
            private_key = Ed25519PrivateKey.generate()
            priv_bytes = private_key.private_bytes(
                Encoding.Raw, PrivateFormat.Raw, NoEncryption()
            )
            key_file.write_bytes(priv_bytes)
        # 从原始字节重建公钥
        private_key = Ed25519PrivateKey.from_private_bytes(priv_bytes)
        public_key = private_key.public_key()
        pub_bytes = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return priv_bytes, pub_bytes

    def register(self, did: str, public_key: Optional[bytes] = None) -> DIDDocument:
        """注册一个 DID（自动生成 Ed25519 密钥对如果没传）"""
        if public_key is None:
            private, public = self.generate_keypair(did)
            self._private_keys[did] = private
            public_key = public

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
    private_key_bytes: bytes,
    method: str,
    path: str,
    body: str = "",
    timestamp: Optional[float] = None,
) -> str:
    """
    用 Ed25519 私钥签名请求（阶段48-A2A）

    Args:
        private_key_bytes: 原始 32 字节 Ed25519 私钥
        method: HTTP method (GET/POST/...)
        path: URL path
        body: 请求体（已序列化）
        timestamp: Unix 时间戳（默认现在）

    Returns:
        base64 编码的 Ed25519 签名
    """
    if timestamp is None:
        timestamp = time.time()

    private_key = Ed25519PrivateKey.from_private_bytes(private_key_bytes)

    # 构造签名 payload
    body_bytes = body.encode() if body else b""
    payload = f"{method}\n{path}\n{timestamp:.0f}\n".encode()
    payload += hashlib.sha256(body_bytes).digest()

    # Ed25519 签名
    signature = private_key.sign(payload)
    return base64.b64encode(signature).decode()




def verify_request(
    public_key_bytes: bytes,
    signature_b64: str,
    method: str,
    path: str,
    body: str = "",
    timestamp: Optional[float] = None,
    max_age_sec: int = 300,
) -> tuple:
    """
    验证 Ed25519 请求签名（阶段48-A2A）

    Returns:
        (valid, error_message)
    """
    if timestamp is None:
        return False, "missing timestamp"

    # 1. 检查时间戳（防重放）
    now = time.time()
    if abs(now - timestamp) > max_age_sec:
        return False, f"timestamp expired (delta={now - timestamp:.0f}s, max={max_age_sec}s)"

    # 2. 解析 Ed25519 公钥
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        pub_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)
    except Exception as e:
        return False, f"failed to load public key: {e}"

    # 3. 重新构造 payload 并验签
    body_bytes = body.encode() if body else b""
    payload = f"{method}\n{path}\n{timestamp:.0f}\n".encode()
    payload += hashlib.sha256(body_bytes).digest()

    signature = base64.b64decode(signature_b64.encode())
    try:
        pub_key.verify(signature, payload)
    except Exception:
        return False, "signature mismatch"

    return True, ""


# ============================================================
# 4. 单例 + 默认 PHA DIDs
# ============================================================

_keystore: Optional[DIDKeyStore] = None


def get_keystore() -> DIDKeyStore:
    global _keystore
    if _keystore is None:
        _keystore = DIDKeyStore()
        # 阶段48-20: 从 DomainManifest 读 DID 列表 (不再硬编码 PHA 默认)
        did_names: list[str]
        did_prefix = "did:wba"
        did_domain = "pha.local"
        try:
            from .domain_manifest import load_default
            manifest = load_default()
            did_names = ["hostapi"] + [a.name for a in manifest.agents]
            did_prefix = manifest.did_prefix
            did_domain = manifest.did_domain
        except Exception:
            # legacy fallback (PHA)
            did_names = [
                "hostapi",
                "health_advisor",
                "health_records",
                "medication_reminder",
                "visit_summary",
            ]
        for name in did_names:
            did = f"{did_prefix}:{did_domain}:{name}"
            _keystore.register(did)
    return _keystore


def get_default_port(name: str) -> int:
    """阶段48-20: 从 DomainManifest 读 port, 不再硬编码 PHA 默认.

    Fallback: 13002 (hostapi) / port_map[agent_name] / 10000.
    """
    if name == "hostapi":
        return 13002
    try:
        from .domain_manifest import load_default
        manifest = load_default()
        if name in [a.name for a in manifest.agents]:
            return manifest.service_discovery.get_port(name)
    except Exception:
        pass
    # legacy fallback
    legacy = {
        "health_advisor": 10011,
        "health_records": 10010,
        "medication_reminder": 10012,
        "visit_summary": 10013,
    }
    return legacy.get(name, 10000)


__all__ = [
    "DIDDocument",
    "DIDKeyStore",
    "get_keystore",
    "sign_request",
    "verify_request",
    "get_default_port",
]