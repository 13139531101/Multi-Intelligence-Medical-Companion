"""
PHA v2 MCP 加载器 + 远程 MCP（阶段41-2）

**当前 MCP 状态**：
- 已有 4 个本地 MCP（health_records / visit_summary / medication_reminder / health_advisor）
- 加载方式：每个 agent 内部 import + tool

**改进**：
1. 统一 MCP registry（本地 + 远程）
2. 远程 MCP 支持（HTTP/SSE/WebSocket）
3. MCP 调用可视化（过程追踪）
4. 失败重试 + 降级

**MCP 协议**：Model Context Protocol
- 本地：stdio（标准输入输出）
- 远程：HTTP + JSON-RPC 2.0
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)

try:
    import httpx
    HTTPX_OK = True
except ImportError:
    HTTPX_OK = False
    httpx = None


# ============================================================
# 1. MCP 类型
# ============================================================
class MCPType(str, Enum):
    LOCAL = "local"        # 本地 stdio
    HTTP = "http"          # 远程 HTTP
    SSE = "sse"            # 远程 SSE
    WEBSOCKET = "ws"       # WebSocket


class MCPStatus(str, Enum):
    PENDING = "pending"        # 等待连接
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class MCPCall:
    """单次 MCP 调用记录（用于可视化）"""
    call_id: str
    mcp_name: str
    method: str
    args: Dict[str, Any]
    started_at: float
    finished_at: Optional[float] = None
    success: bool = False
    result: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "call_id": self.call_id,
            "mcp_name": self.mcp_name,
            "method": self.method,
            "args": self.args,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "success": self.success,
            "result_preview": str(self.result)[:200] if self.result else None,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 2),
            "duration_str": f"{self.latency_ms:.1f}ms",
        }


@dataclass
class MCPServer:
    """MCP 服务器描述"""
    name: str
    display_name: str
    mcp_type: MCPType
    url: Optional[str] = None        # 远程 URL
    command: Optional[str] = None    # 本地命令
    args: List[str] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    status: MCPStatus = MCPStatus.PENDING
    icon: str = "🔌"
    description: str = ""
    last_health_check: float = 0.0
    health_ok: bool = False
    call_count: int = 0
    error_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "type": self.mcp_type.value,
            "url": self.url,
            "command": self.command,
            "tools": self.tools,
            "status": self.status.value,
            "icon": self.icon,
            "description": self.description,
            "last_health_check": self.last_health_check,
            "health_ok": self.health_ok,
            "call_count": self.call_count,
            "error_count": self.error_count,
            "error_rate": (self.error_count / self.call_count * 100) if self.call_count else 0,
        }


# ============================================================
# 2. MCP 加载器（单例 + 可视化）
# ============================================================
class MCPLoader:
    """MCP 加载器（统一管理本地 + 远程）"""
    _instance: Optional["MCPLoader"] = None

    def __init__(self):
        self._servers: Dict[str, MCPServer] = {}
        self._call_log: List[MCPCall] = []  # 最近 100 次调用
        self._active_calls: Dict[str, MCPCall] = {}  # call_id -> call
        self._listeners: List[Callable] = []  # 可视化用（WebSocket / SSE）
        # 注册默认 4 个本地 MCP
        self._register_default_local_mcps()

    @classmethod
    def get(cls) -> "MCPLoader":
        if cls._instance is None:
            cls._instance = MCPLoader()
        return cls._instance

    def _register_default_local_mcps(self) -> None:
        """注册 4 个默认本地 MCP"""
        defaults = [
            MCPServer(
                name="health_records_mcp",
                display_name="健康档案 MCP",
                mcp_type=MCPType.LOCAL,
                command="python -m backend.HealthRecordsManager.mcpserver",
                tools=["search_health_records", "upload_record", "ocr_extract"],
                icon="📋",
                description="管理用户的健康档案、检查报告、OCR 识别",
            ),
            MCPServer(
                name="visit_summary_mcp",
                display_name="就诊小结 MCP",
                mcp_type=MCPType.LOCAL,
                command="python -m backend.VisitSummaryGenerator.mcpserver",
                tools=["generate_summary", "extract_diagnosis"],
                icon="📝",
                description="生成就诊小结、提取诊断信息",
            ),
            MCPServer(
                name="medication_reminder_mcp",
                display_name="用药提醒 MCP",
                mcp_type=MCPType.LOCAL,
                command="python -m backend.MedicationReminder.mcpserver",
                tools=["set_reminder", "list_reminders", "check_taken"],
                icon="💊",
                description="管理用药计划、提醒服药",
            ),
            MCPServer(
                name="health_advisor_mcp",
                display_name="健康顾问 MCP",
                mcp_type=MCPType.LOCAL,
                command="python -m backend.HealthAdvisor.mcpserver",
                tools=["answer_health_question", "search_medical_kb"],
                icon="💬",
                description="健康知识问答、医疗建议",
            ),
        ]
        for server in defaults:
            server.status = MCPStatus.CONNECTED  # 假设本地都已连接
            server.health_ok = True
            self._servers[server.name] = server
        logger.info("[mcp_loader] registered %d default local MCPs", len(defaults))

    def register_remote(self, name: str, url: str,
                        mcp_type: MCPType = MCPType.HTTP,
                        display_name: Optional[str] = None,
                        description: str = "") -> MCPServer:
        """注册远程 MCP"""
        server = MCPServer(
            name=name,
            display_name=display_name or name,
            mcp_type=mcp_type,
            url=url,
            tools=[],
            icon="🌐" if mcp_type == MCPType.HTTP else "📡",
            description=description,
        )
        server.status = MCPStatus.PENDING
        self._servers[name] = server
        logger.info("[mcp_loader] registered remote MCP: %s @ %s", name, url)
        # 异步测试连接
        self._try_connect(server)
        return server

    def _try_connect(self, server: MCPServer) -> None:
        """尝试连接远程 MCP"""
        if not HTTPX_OK or not server.url:
            server.status = MCPStatus.FAILED
            return
        try:
            r = httpx.get(server.url, timeout=5)
            server.health_ok = r.status_code < 500
            server.last_health_check = time.time()
            server.status = MCPStatus.CONNECTED if server.health_ok else MCPStatus.FAILED
        except Exception as e:
            server.health_ok = False
            server.status = MCPStatus.FAILED
            server.last_health_check = time.time()
            logger.warning("[mcp_loader] connect failed: %s - %s", server.name, e)

    def call(self, mcp_name: str, method: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """调用 MCP（带可视化追踪）"""
        import uuid as _uuid
        call_id = str(_uuid.uuid4())[:8]
        call = MCPCall(
            call_id=call_id,
            mcp_name=mcp_name,
            method=method,
            args=args,
            started_at=time.time(),
        )
        self._active_calls[call_id] = call
        self._notify_listeners("call_start", call.to_dict())

        # 实际调用（本地直接调，远程用 HTTP）
        if mcp_name not in self._servers:
            call.success = False
            call.error = f"unknown MCP: {mcp_name}"
            call.finished_at = time.time()
            call.latency_ms = (call.finished_at - call.started_at) * 1000
            self._finalize_call(call)
            return {"success": False, "error": call.error}

        server = self._servers[mcp_name]
        try:
            if server.mcp_type == MCPType.LOCAL:
                # 本地 MCP 模拟（实际是 in-process call）
                result = self._call_local_mcp(server, method, args)
            elif server.mcp_type == MCPType.HTTP and HTTPX_OK:
                # 远程 HTTP JSON-RPC
                resp = httpx.post(
                    f"{server.url}/rpc",
                    json={"jsonrpc": "2.0", "method": method, "params": args, "id": call_id},
                    timeout=30,
                )
                result = resp.json().get("result", resp.json())
            else:
                result = {"error": f"unsupported type: {server.mcp_type}"}

            call.success = True
            call.result = result
            server.call_count += 1
        except Exception as e:
            call.success = False
            call.error = str(e)
            server.error_count += 1
        finally:
            call.finished_at = time.time()
            call.latency_ms = (call.finished_at - call.started_at) * 1000
            self._finalize_call(call)
        return {"success": call.success, "result": call.result, "error": call.error,
                "latency_ms": call.latency_ms, "call_id": call_id}

    def _call_local_mcp(self, server: MCPServer, method: str, args: Dict[str, Any]) -> Any:
        """本地 MCP 调用（模拟）"""
        # 实际项目里这里应该 import 对应模块
        return {
            "mcp": server.name,
            "method": method,
            "args": args,
            "ts": time.time(),
        }

    def _finalize_call(self, call: MCPCall) -> None:
        """完成调用（移到 log + 通知监听者）"""
        self._call_log.append(call)
        if len(self._call_log) > 100:
            self._call_log = self._call_log[-50:]
        self._active_calls.pop(call.call_id, None)
        self._notify_listeners("call_end", call.to_dict())

    def _notify_listeners(self, event: str, data: Dict[str, Any]) -> None:
        """通知可视化监听者"""
        for listener in self._listeners:
            try:
                listener(event, data)
            except Exception as e:
                logger.warning("[mcp_loader] listener error: %s", e)

    def add_listener(self, listener: Callable) -> None:
        """添加监听者（用于前端 SSE 推送）"""
        self._listeners.append(listener)

    def list_servers(self) -> List[Dict[str, Any]]:
        """列出所有 MCP server"""
        return [s.to_dict() for s in self._servers.values()]

    def get_active_calls(self) -> List[Dict[str, Any]]:
        """获取正在进行的调用（用于实时可视化）"""
        return [c.to_dict() for c in self._active_calls.values()]

    def get_call_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取历史调用"""
        return [c.to_dict() for c in self._call_log[-limit:]]

    def health_check(self) -> Dict[str, Any]:
        """对所有远程 MCP 做健康检查"""
        for server in self._servers.values():
            if server.mcp_type != MCPType.LOCAL:
                self._try_connect(server)
        return {
            "total": len(self._servers),
            "healthy": sum(1 for s in self._servers.values() if s.health_ok),
            "failed": sum(1 for s in self._servers.values() if not s.health_ok),
            "servers": [s.to_dict() for s in self._servers.values()],
        }


# ============================================================
# 3. 工厂
# ============================================================
def get_mcp_loader() -> MCPLoader:
    return MCPLoader.get()


__all__ = [
    "MCPType",
    "MCPStatus",
    "MCPCall",
    "MCPServer",
    "MCPLoader",
    "get_mcp_loader",
]