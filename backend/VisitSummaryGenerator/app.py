"""
阶段48-ops: uvicorn --workers 入口
app = build_app(...) 在模块级别构建，供 uvicorn 直接引用

支持热重载：收到 SIGHUP 时重新读取环境变量并重建 app
"""
import os
import signal
import importlib

import uvicorn

from main import build_app


def _read_config():
    return {
        "host": os.getenv("HOST", "0.0.0.0"),
        "port": int(os.getenv("PORT") or os.getenv("VISIT_SUMMARY_PORT", "10013")),
        "model_name": os.getenv("LLM_MODEL", "deepseek-chat"),
        "provider": os.getenv("PROVIDER", "deepseek"),
        "agent_prompt_file": os.getenv("PROMPT_FILE", "memory_enhanced_agent_prompt.md"),
        "mcp_config_path": os.getenv("MCP_CONFIG", "mcp_config.json"),
        "agent_url": os.getenv("AGENT_URL", ""),
    }


def _reload_config(signum, _frame):
    """SIGHUP handler: re-read env vars and rebuild app."""
    print(f"[hot-reload] Received signal {signum}, reloading config...", flush=True)
    import main
    importlib.reload(main)
    global app, _server
    app = build_app(**_read_config())
    print("[hot-reload] App rebuilt", flush=True)
    if _server is not None:
        _server.should_exit = True


app = build_app(**_read_config())
_server = None


def run_with_reload():
    global _server
    config = uvicorn.Config(
        app=app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT") or os.getenv("VISIT_SUMMARY_PORT", "10013")),
        reload=True,
        reload_dirs=["/app"],
        sighup_term=True,
        sigint_term=True,
    )
    _server = uvicorn.Server(config)
    signal.signal(signal.SIGHUP, _reload_config)
    _server.run()


if __name__ == "__main__":
    run_with_reload()