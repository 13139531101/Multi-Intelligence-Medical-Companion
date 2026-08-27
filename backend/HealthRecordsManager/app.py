"""
阶段48-ops: uvicorn --workers 入口
app = build_app(...) 在模块级别构建，供 uvicorn 直接引用
"""
from main import build_app
import os

_host = os.getenv("HOST", "0.0.0.0")
_port = int(os.getenv("PORT") or os.getenv("HEALTH_RECORDS_PORT", "10010"))
_model = os.getenv("LLM_MODEL", "deepseek-chat")
_provider = os.getenv("PROVIDER", "deepseek")
_prompt = os.getenv("PROMPT_FILE", "memory_enhanced_agent_prompt.md")
_mcp = os.getenv("MCP_CONFIG", "mcp_config.json")
_url = os.getenv("AGENT_URL", "")

app = build_app(
    host=_host,
    port=_port,
    agent_prompt_file=_prompt,
    model_name=_model,
    provider=_provider,
    mcp_config_path=_mcp,
    agent_url=_url,
)
