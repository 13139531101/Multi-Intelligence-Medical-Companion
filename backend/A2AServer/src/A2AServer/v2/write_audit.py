"""
PHA v2 写操作安全审计（阶段19）

5 层写保护：
  L1 鉴权：检查 user_id（PHA_AUTH_REQUIRED=true 强制）
  L2 白名单：仅 allowlist 工具可写
  L3 审计：写前/写后记录到 .pha_audit_log /v2/audit
  L4 限额：每用户/小时最多 N 次写（默认 50）
  L5 确认：危险写（delete_/drop_/truncate_/update_*_password）需 confirm token

设计：
  - WriteGuard 装饰器/上下文管理器
  - AsyncWriteAudit 异步审计日志
  - WriteConfirmation：confirm_token 机制
  - 限额基于 Redis（或 in-memory fallback）
"""
import os
import time
import json
import logging
import hashlib
import asyncio
from typing import Optional, Dict, List, Any
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta

from .tool_cache import is_write_tool as _is_write_tool_by_name

logger = logging.getLogger(__name__)


# ============================================================
# 配置（环境变量可覆盖）
# ============================================================
PHA_AUTH_REQUIRED = os.getenv("PHA_AUTH_REQUIRED", "true").lower() == "true"
PHA_WRITE_QUOTA_PER_HOUR = int(os.getenv("PHA_WRITE_QUOTA_PER_HOUR", "50"))
PHA_DANGEROUS_TOOLS_REQUIRE_CONFIRM = os.getenv(
    "PHA_DANGEROUS_TOOLS_REQUIRE_CONFIRM", "true"
).lower() == "true"
PHA_AUDIT_BUFFER_SIZE = int(os.getenv("PHA_AUDIT_BUFFER_SIZE", "10000"))


# 危险写操作（必须 confirm）
_DANGEROUS_PATTERNS = (
    "delete_", "drop_", "truncate_", "remove_",
    "reset_", "purge_", "wipe_", "destroy_",
    "update_password", "change_password", "revoke_",
)


# 写操作白名单（allowlist；空表示全部允许）
_WRITE_ALLOWLIST: List[str] = []  # 由 set_write_allowlist() 设置


def set_write_allowlist(tools: List[str]) -> None:
    """设置写操作白名单（空 = 不限制）"""
    global _WRITE_ALLOWLIST
    _WRITE_ALLOWLIST = list(tools)
    logger.info(f"[write_audit] allowlist set: {len(_WRITE_ALLOWLIST)} tools")


def get_write_allowlist() -> List[str]:
    return list(_WRITE_ALLOWLIST)


# ============================================================
# 数据结构
# ============================================================
@dataclass
class WriteAuditEntry:
    """一条写操作审计记录"""
    ts: float  # unix timestamp
    user_id: str
    agent_name: str  # 哪个 agent 发起的
    tool_name: str
    args: Dict[str, Any]
    result: str  # "success" / "denied" / "error"
    reason: str = ""  # 拒绝原因 / 错误信息
    duration_ms: float = 0.0
    confirm_token: str = ""  # 用了哪个 confirm token
    request_id: str = ""  # 关联请求 ID

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ts_iso"] = datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat()
        return d


@dataclass
class WriteQuotaState:
    """每用户的写限额状态（滑动窗口 1 小时）"""
    timestamps: deque = field(default_factory=deque)

    def add(self, ts: float) -> None:
        self.timestamps.append(ts)

    def count_in_window(self, now: float, window_sec: float = 3600.0) -> int:
        cutoff = now - window_sec
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()
        return len(self.timestamps)


# ============================================================
# 写保护主类
# ============================================================
class WriteGuard:
    """
    写操作安全网关（单例）

    用法：
        from A2AServer.v2.write_audit import get_write_guard
        guard = get_write_guard()

        # 方式1：上下文管理器
        with guard.protect(user_id, agent_name, tool_name, args) as ctx:
            result = await tool.ainvoke(args)
            ctx.set_result(result)

        # 方式2：手动
        decision = guard.check(user_id, agent_name, tool_name, args)
        if decision.allowed:
            result = await tool.ainvoke(args)
            guard.record_success(user_id, agent_name, tool_name, args, result)
        else:
            raise PermissionError(decision.reason)
    """

    def __init__(self):
        self._audit_log: deque = deque(maxlen=PHA_AUDIT_BUFFER_SIZE)
        self._quota: Dict[str, WriteQuotaState] = {}
        self._lock = asyncio.Lock()
        self._confirm_tokens: Dict[str, dict] = {}  # token -> {tool, args, user_id, expires_at}

    # ---------- L1 鉴权 ----------
    def _check_auth(self, user_id: str) -> Optional[str]:
        """L1 鉴权检查。返回 None 表示通过，返回 reason 表示拒绝。"""
        if not PHA_AUTH_REQUIRED:
            return None
        if not user_id or not isinstance(user_id, str):
            return "missing user_id (auth required)"
        # 用户 ID 至少 3 字符（避免垃圾数据）
        if len(user_id.strip()) < 3:
            return f"invalid user_id: {user_id!r}"
        return None

    # ---------- L2 白名单 ----------
    def _check_allowlist(self, tool_name: str) -> Optional[str]:
        """L2 白名单检查。空 allowlist 表示全部允许。"""
        if not _WRITE_ALLOWLIST:
            return None
        if tool_name in _WRITE_ALLOWLIST:
            return None
        return f"tool {tool_name!r} not in write allowlist ({len(_WRITE_ALLOWLIST)} allowed)"

    # ---------- L3 审计 ----------
    def _log_audit(self, entry: WriteAuditEntry) -> None:
        """L3 写审计日志"""
        self._audit_log.append(entry)
        # INFO 级别记录（生产可改为 JSON formatter）
        logger.info(
            f"[write_audit] {entry.result:8s} user={entry.user_id} "
            f"agent={entry.agent_name} tool={entry.tool_name} "
            f"dur={entry.duration_ms:.1f}ms {('reason='+entry.reason) if entry.reason else ''}"
        )

    # ---------- L4 限额 ----------
    async def _check_quota(self, user_id: str) -> Optional[str]:
        """L4 限额检查。返回 reason 表示超限。"""
        now = time.time()
        async with self._lock:
            state = self._quota.setdefault(user_id, WriteQuotaState())
            count = state.count_in_window(now)
            if count >= PHA_WRITE_QUOTA_PER_HOUR:
                return f"write quota exceeded: {count}/{PHA_WRITE_QUOTA_PER_HOUR} per hour"
            # 预占位（写成功后 record_xxx 确认，写失败回滚）
            state.add(now)
            return None

    async def _refund_quota(self, user_id: str) -> None:
        """写失败时退还配额"""
        async with self._lock:
            state = self._quota.get(user_id)
            if state and state.timestamps:
                state.timestamps.pop()

    # ---------- L5 确认 ----------
    def is_dangerous(self, tool_name: str) -> bool:
        """判断是否危险写操作"""
        if not PHA_DANGEROUS_TOOLS_REQUIRE_CONFIRM:
            return False
        name = tool_name.lower()
        return any(p in name for p in _DANGEROUS_PATTERNS)

    def issue_confirm_token(
        self, user_id: str, agent_name: str, tool_name: str, args: dict, ttl_sec: int = 60
    ) -> str:
        """L5 发放一次性 confirm token（TTL 60s 默认）"""
        token = hashlib.sha256(
            f"{user_id}:{tool_name}:{time.time()}:{os.urandom(8).hex()}".encode()
        ).hexdigest()[:32]
        self._confirm_tokens[token] = {
            "user_id": user_id,
            "agent_name": agent_name,
            "tool_name": tool_name,
            "args": args,
            "expires_at": time.time() + ttl_sec,
        }
        return token

    def verify_confirm_token(self, token: str, user_id: str, tool_name: str) -> Optional[str]:
        """验证 confirm token。返回 reason 表示无效。"""
        info = self._confirm_tokens.pop(token, None)
        if not info:
            return "invalid or used confirm token"
        if info["expires_at"] < time.time():
            return "confirm token expired"
        if info["user_id"] != user_id:
            return f"confirm token user mismatch ({info['user_id']!r} != {user_id!r})"
        if info["tool_name"] != tool_name:
            return f"confirm token tool mismatch ({info['tool_name']!r} != {tool_name!r})"
        return None

    # ---------- 公开 API ----------
    async def check(
        self,
        user_id: str,
        agent_name: str,
        tool_name: str,
        args: dict,
        confirm_token: str = "",
    ) -> "WriteDecision":
        """
        检查写操作是否允许。返回 WriteDecision。
        不修改任何状态（除了 confirm token 验证会消费 token）。
        """
        # L1
        reason = self._check_auth(user_id)
        if reason:
            return WriteDecision(allowed=False, layer="L1_auth", reason=reason)

        # L2
        reason = self._check_allowlist(tool_name)
        if reason:
            return WriteDecision(allowed=False, layer="L2_allowlist", reason=reason)

        # L5（危险工具）
        if self.is_dangerous(tool_name):
            if not confirm_token:
                # 生成新 token 让用户确认
                new_token = self.issue_confirm_token(user_id, agent_name, tool_name, args)
                return WriteDecision(
                    allowed=False,
                    layer="L5_confirm_required",
                    reason=f"dangerous tool {tool_name!r} requires confirm",
                    confirm_token=new_token,
                )
            reason = self.verify_confirm_token(confirm_token, user_id, tool_name)
            if reason:
                return WriteDecision(allowed=False, layer="L5_confirm_invalid", reason=reason)

        return WriteDecision(allowed=True, layer="OK")

    async def check_and_consume_quota(self, user_id: str, agent_name: str, tool_name: str) -> "WriteDecision":
        """check + 预占限额（在写操作开始前调用）"""
        reason = await self._check_quota(user_id)
        if reason:
            entry = WriteAuditEntry(
                ts=time.time(), user_id=user_id, agent_name=agent_name,
                tool_name=tool_name, args={}, result="denied",
                reason=f"L4_quota: {reason}",
            )
            self._log_audit(entry)
            return WriteDecision(allowed=False, layer="L4_quota", reason=reason)
        return WriteDecision(allowed=True, layer="OK")

    def record_success(
        self, user_id: str, agent_name: str, tool_name: str, args: dict,
        result: Any = None, duration_ms: float = 0.0, request_id: str = "",
    ) -> None:
        """记录成功的写操作"""
        entry = WriteAuditEntry(
            ts=time.time(), user_id=user_id, agent_name=agent_name,
            tool_name=tool_name, args=args if isinstance(args, dict) else {"_args": str(args)},
            result="success", duration_ms=duration_ms, request_id=request_id,
        )
        self._log_audit(entry)

    def record_denied(
        self, user_id: str, agent_name: str, tool_name: str, args: dict,
        layer: str, reason: str, request_id: str = "",
    ) -> None:
        """记录被拒绝的写操作（限额检查会立即 record）"""
        entry = WriteAuditEntry(
            ts=time.time(), user_id=user_id, agent_name=agent_name,
            tool_name=tool_name, args=args if isinstance(args, dict) else {"_args": str(args)},
            result="denied", reason=f"{layer}: {reason}", request_id=request_id,
        )
        self._log_audit(entry)

    def record_error(
        self, user_id: str, agent_name: str, tool_name: str, args: dict,
        error: str, duration_ms: float = 0.0, request_id: str = "",
    ) -> None:
        """记录写操作失败（含 L4 退还）"""
        # 失败时同步退还配额（避免异步 task 时序问题）
        try:
            state = self._quota.get(user_id)
            if state and state.timestamps:
                state.timestamps.pop()
        except Exception:
            pass
        entry = WriteAuditEntry(
            ts=time.time(), user_id=user_id, agent_name=agent_name,
            tool_name=tool_name, args=args if isinstance(args, dict) else {"_args": str(args)},
            result="error", reason=error, duration_ms=duration_ms, request_id=request_id,
        )
        self._log_audit(entry)

    # ---------- 审计查询 ----------
    def get_recent(self, limit: int = 100, user_id: str = None, tool_name: str = None) -> List[dict]:
        """查询最近审计记录"""
        out: List[dict] = []
        for entry in reversed(self._audit_log):
            if user_id and entry.user_id != user_id:
                continue
            if tool_name and entry.tool_name != tool_name:
                continue
            out.append(entry.to_dict())
            if len(out) >= limit:
                break
        return out

    def stats(self) -> dict:
        """审计统计"""
        now = time.time()
        success = sum(1 for e in self._audit_log if e.result == "success")
        denied = sum(1 for e in self._audit_log if e.result == "denied")
        error = sum(1 for e in self._audit_log if e.result == "error")
        per_user = {}
        for e in self._audit_log:
            per_user.setdefault(e.user_id, 0)
            per_user[e.user_id] += 1
        per_tool = {}
        for e in self._audit_log:
            per_tool.setdefault(e.tool_name, 0)
            per_tool[e.tool_name] += 1
        return {
            "total": len(self._audit_log),
            "success": success,
            "denied": denied,
            "error": error,
            "buffer_size": PHA_AUDIT_BUFFER_SIZE,
            "quota_per_hour": PHA_WRITE_QUOTA_PER_HOUR,
            "auth_required": PHA_AUTH_REQUIRED,
            "dangerous_require_confirm": PHA_DANGEROUS_TOOLS_REQUIRE_CONFIRM,
            "active_users": len(per_user),
            "unique_tools": len(per_tool),
            "top_users": sorted(per_user.items(), key=lambda x: -x[1])[:5],
            "top_tools": sorted(per_tool.items(), key=lambda x: -x[1])[:10],
        }

    # ---------- 上下文管理器 ----------
    def protect(
        self, user_id: str, agent_name: str, tool_name: str, args: dict,
        confirm_token: str = "", request_id: str = "",
    ):
        return _WriteContext(self, user_id, agent_name, tool_name, args, confirm_token, request_id)


@dataclass
class WriteDecision:
    """写操作决策结果"""
    allowed: bool
    layer: str  # "L1_auth" / "L2_allowlist" / "L4_quota" / "L5_confirm_required" / "L5_confirm_invalid" / "OK"
    reason: str = ""
    confirm_token: str = ""  # 当 layer == L5_confirm_required 时返回


class _WriteContext:
    """WriteGuard 上下文管理器"""

    def __init__(
        self, guard: WriteGuard, user_id: str, agent_name: str,
        tool_name: str, args: dict, confirm_token: str, request_id: str,
    ):
        self.guard = guard
        self.user_id = user_id
        self.agent_name = agent_name
        self.tool_name = tool_name
        self.args = args
        self.confirm_token = confirm_token
        self.request_id = request_id
        self.start_ts = 0.0
        self.result: Any = None
        self.decision: Optional[WriteDecision] = None

    async def __aenter__(self):
        # 1. check (L1/L2/L5)
        self.decision = await self.guard.check(
            self.user_id, self.agent_name, self.tool_name, self.args, self.confirm_token
        )
        if not self.decision.allowed:
            self.guard.record_denied(
                self.user_id, self.agent_name, self.tool_name, self.args,
                self.decision.layer, self.decision.reason, self.request_id,
            )
            raise PermissionError(
                f"[{self.decision.layer}] {self.decision.reason} "
                f"(confirm_token={self.decision.confirm_token or 'N/A'})"
            )
        # 2. quota (L4)
        quota_decision = await self.guard.check_and_consume_quota(
            self.user_id, self.agent_name, self.tool_name
        )
        if not quota_decision.allowed:
            raise PermissionError(f"[{quota_decision.layer}] {quota_decision.reason}")
        self.start_ts = time.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        dur_ms = (time.time() - self.start_ts) * 1000.0 if self.start_ts else 0.0
        if exc_type is None:
            # 成功
            self.guard.record_success(
                self.user_id, self.agent_name, self.tool_name, self.args,
                self.result, dur_ms, self.request_id,
            )
        else:
            # 失败（含 L4 退还）
            err = f"{exc_type.__name__}: {exc_val}" if exc_val else exc_type.__name__
            self.guard.record_error(
                self.user_id, self.agent_name, self.tool_name, self.args,
                err, dur_ms, self.request_id,
            )
        return False  # 不吞异常

    def set_result(self, result: Any) -> None:
        self.result = result


# ============================================================
# 单例
# ============================================================
_instance: Optional[WriteGuard] = None


def get_write_guard() -> WriteGuard:
    """获取 WriteGuard 单例"""
    global _instance
    if _instance is None:
        _instance = WriteGuard()
    return _instance


# ============================================================
# 工具函数
# ============================================================
def is_dangerous_write(tool_name: str) -> bool:
    """公开 API：判断工具名是否是危险写操作"""
    return get_write_guard().is_dangerous(tool_name)
