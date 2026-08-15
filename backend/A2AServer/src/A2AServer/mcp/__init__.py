"""
PHA MCP (Model Context Protocol) 系统

从 agent 目录发现 MCP tools，统一加载和管理。

目录结构：
    mcp/
        __init__.py          # 本模块入口，导出公开 API
        mcp_discover.py      # 从 agent 目录发现 MCP tools
        loader.py            # MCP server 加载
        tool_adapter.py      # MCP tool 适配
        endpoints.py         # MCP HTTP 端点
"""
# Import submodules (lazy loading to avoid circular imports)
# Individual modules can be imported directly:
#   from A2AServer.mcp.mcp_discover import discover_mcp_tools_static
#   from A2AServer.mcp.mcp_loader import get_mcp_loader
#   from A2AServer.mcp.mcp_tool_adapter import adapt_mcp_tool

__all__ = [
    "mcp_discover",
    "mcp_loader",
    "mcp_tool_adapter",
    "mcp_endpoints",
]
