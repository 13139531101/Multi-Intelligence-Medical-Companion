"""
PHA MCP (Model Context Protocol) 系统

从 agent 目录发现 MCP tools，统一加载和管理。

目录结构：
    mcp/
        __init__.py          # 本模块入口，导出公开 API
        discover.py          # 从 agent 目录发现 MCP tools
        loader.py            # MCP server 加载
        tool_adapter.py      # MCP tool 适配
        endpoints.py         # MCP HTTP 端点
"""
from .discover import discover_mcp_tools, get_all_mcp_tools
from .tool_adapter import adapt_mcp_tool

__all__ = [
    "discover_mcp_tools",
    "get_all_mcp_tools",
    "adapt_mcp_tool",
]
