"""
i:\A2A\3\A2AServer\frontend\hostAgentAPI\app.py

uvicorn --workers 入口点
========================

为了让多个 uvicorn worker 并发处理请求，每个 worker 都必须拥有自己的：
  - FastAPI app 实例
  - ADKHostManager (LLM client)
  - ConversationServer (agent registry + 后台线程)
  - prometheus metrics 寄存器
  - httpx proxy client / semaphore

因此 init 逻辑都放在 api.py 顶部的 `lifespan()` async context manager 里。
当 uvicorn fork 出 N 个 worker 时，每个 worker 都会执行一次 lifespan()，
从而拿到独立的运行时状态（不会因为 fork() 共享父进程的 ADKHostManager）。

启动命令 (容器内 / 生产):
    python -m uvicorn app:app --host 0.0.0.0 --port 13002 --workers 4

启动命令 (开发 / 单进程):
    python -m uvicorn app:app --host 0.0.0.0 --port 13002 --reload

本模块本身只 import `app` 对象（来自 api.py 的 module-level `app = FastAPI(lifespan=lifespan)`），
方便 `uvicorn app:app` 直接定位。
"""
import os

# 直接 re-export api.py 里创建的 app 对象（lifespan 已经绑定）
from api import app  # noqa: F401  (uvicorn 通过 `app:app` 引用)


def _worker_count_from_env(default: int = 1) -> int:
    """读 HOST_API_WORKERS 环境变量，默认 1（兼容旧部署）。"""
    raw = os.getenv("HOST_API_WORKERS", "").strip()
    if not raw:
        return default
    try:
        n = int(raw)
        return n if n > 0 else default
    except Exception:
        return default


if __name__ == "__main__":
    # 直接 `python app.py` 时使用 uvicorn 启动，支持 --workers
    import uvicorn
    import socket

    env_port = os.getenv("HOST_API_PORT", "13002")
    host = os.getenv("HOST_API_BIND", "0.0.0.0")
    workers = _worker_count_from_env(default=1)

    def _resolve_port(port_str, bind_host):
        try:
            p = int(port_str)
            if p > 0:
                return p
        except Exception:
            pass
        if str(port_str).lower() in ("auto", "0"):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((bind_host if bind_host else "127.0.0.1", 0))
            p = s.getsockname()[1]
            s.close()
            return p
        return 13002

    port = _resolve_port(env_port, host)
    print(f"[HostAPI] launching uvicorn: {host}:{port} workers={workers}")

    if workers > 1:
        # 多 worker：uvicorn 会 fork 出 N 个子进程，每个子进程都会执行 lifespan() 拿到自己的状态
        uvicorn.run(
            "app:app",
            host=host,
            port=port,
            workers=workers,
            log_level=os.getenv("HOST_API_LOG_LEVEL", "info"),
            access_log=os.getenv("HOST_API_ACCESS_LOG", "1") == "1",
        )
    else:
        # 单进程：直接传 app 对象（避免 subprocess 多绕一层）
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=os.getenv("HOST_API_LOG_LEVEL", "info"),
            access_log=os.getenv("HOST_API_ACCESS_LOG", "1") == "1",
        )