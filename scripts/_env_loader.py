"""scripts/ 下脚本共用的 .env 加载器。

背景
----
scripts/ 下曾有 4 个脚本把 **API key / 数据库密码 / JWT 签名密钥**硬编码在源码里，
并随仓库推到了公开远端。其中 JWT_SECRET_KEY 与 DB_PASSWORD 当时与生产 .env
**完全一致** —— 等于把整个应用的登录签发能力和数据库口令公开了。

因此统一改为从 .env（或调用方已注入的环境变量）读取：
- 不覆盖已存在的环境变量，便于 CI / 容器里注入
- 缺失时**立刻报错退出**，而不是静默拿到空值去连服务（那样报错信息会很难懂）

用法
----
    import _env_loader
    _env_loader.load_env()
    key = _env_loader.require("DASHSCOPE_API_KEY")
"""
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def load_env(path=None) -> dict:
    """把仓库根目录的 .env 读进 os.environ；已存在的变量不覆盖。"""
    env_path = Path(path) if path else _ROOT / ".env"
    if not env_path.exists():
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError:
        # 没装 python-dotenv 时退化为什么都不做，由 require() 给出清晰报错
        return {}
    values = dotenv_values(env_path)
    for k, v in values.items():
        if v is not None and not os.environ.get(k):
            os.environ[k] = v
    return values


def require(name: str) -> str:
    """取必填环境变量；没有就明确报错，避免拿空凭证去连服务。"""
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise SystemExit(
            f"缺少环境变量 {name}。\n"
            f"  请在本仓库根目录的 .env 中配置，或先 `export {name}=...` 再运行。\n"
            f"  （这些值此前被硬编码在脚本里并已泄露到公开仓库，故改为强制外部注入。）"
        )
    return v


def optional(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()
