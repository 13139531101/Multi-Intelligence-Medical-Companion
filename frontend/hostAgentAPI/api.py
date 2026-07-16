import logging
import uuid
import asyncio
import anyio
import os
import sys
import psycopg
from psycopg.rows import dict_row
from fastapi import FastAPI, APIRouter, Response, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional, Dict, Any
from fastapi.middleware.cors import CORSMiddleware
from server import ConversationServer
from auth import router as auth_router, get_current_user, DB_CONFIG, auth_service
from auth_middleware import get_current_user_optional
from dotenv import load_dotenv
import json
import base64
import time
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import unquote, urlparse
import httpx

load_dotenv(override=False)

backend_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env"))
try:
    if os.path.exists(backend_env_path):
        load_dotenv(backend_env_path, override=False)
except Exception:
    pass

# 尝试全局导入健康档案API模块，以便各端点使用（带文件路径兜底）
health_api = None
try:
    backend_path = os.environ.get("BACKEND_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    import importlib
    try:
        health_api = importlib.import_module("health_records_api")
    except Exception:
        # 兜底：按文件路径加载模块，避免包路径问题
        import importlib.util
        module_path = os.path.join(backend_path, "health_records_api.py")
        spec = importlib.util.spec_from_file_location("health_records_api", module_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            health_api = mod
except Exception as e:
    print(f"Warning: Failed to import health_records_api globally: {e}")

logfile = "api.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(module)s - %(funcName)s - %(message)s",
    handlers=[
        logging.FileHandler(logfile, mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
app = FastAPI()

# 阶段14：集成 v2 监控端点（/health /health/deep /metrics /v2/status 等）
try:
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", "A2AServer", "src")))
    from A2AServer.v2.monitoring_endpoints import router as v2_monitor_router, health_router
    app.include_router(health_router)
    app.include_router(v2_monitor_router)
    print("[hostapi] v2 monitoring endpoints mounted: /health, /health/deep, /metrics, /v2/*")
except Exception as _e:
    import traceback
    print(f"[hostapi] v2 monitoring endpoints mount failed: {_e}")

# 阶段33：集成 ANP 协议（Agent Network Protocol）
try:
    from A2AServer.v2.anp_bridge import create_hostapi_anp_app
    anp_app = create_hostapi_anp_app()
    app.mount("/anp", anp_app)
    print("[hostapi] ANP bridge mounted: /anp/agent/{ad.json,interface.json,rpc}, /anp/agents/*")
except Exception as _e:
    import traceback
    print(f"[hostapi] ANP bridge mount failed: {_e}")
    traceback.print_exc()

# 阶段20：集成 OAuth2 端点
try:
    from A2AServer.v2.oauth2_endpoints import oauth_router
    app.include_router(oauth_router)
    print("[hostapi] v2 oauth2 endpoints mounted: /v2/oauth/*")
except Exception as _e:
    import traceback
    print(f"[hostapi] v2 oauth2 endpoints mount failed: {_e}")
    traceback.print_exc()

# 阶段39-6: 提供前端测试页（避免跨域）
try:
    from fastapi.staticfiles import StaticFiles
    import os as _os
    # 容器里 /app 是工作目录，html 文件已经 COPY 过来
    _test_dir = _os.path.dirname(_os.path.abspath(__file__))
    _test_files = ["test_simple.html", "test_page.html"]
    if all(_os.path.isfile(_os.path.join(_test_dir, f)) for f in _test_files):
        app.mount("/test", StaticFiles(directory=_test_dir, html=True), name="test_static")
        print(f"[hostapi] test static mounted: /test/test_simple.html from {_test_dir}")
    else:
        print(f"[hostapi] test static skipped: files not in {_test_dir}")
except Exception as _e:
    import traceback
    print(f"[hostapi] test static mount failed: {_e}")
    traceback.print_exc()

# 阶段21：集成 RAG 端点
try:
    from A2AServer.v2.rag_endpoints import rag_router
    app.include_router(rag_router)
    print("[hostapi] v2 RAG endpoints mounted: /v2/rag/*")
except Exception as _e:
    import traceback
    print(f"[hostapi] v2 RAG endpoints mount failed: {_e}")
    traceback.print_exc()

# 阶段24：集成多模型协同端点
try:
    from A2AServer.v2.multi_model_endpoints import mm_router
    app.include_router(mm_router)
    print("[hostapi] v2 multi-model endpoints mounted: /v2/models/*")
except Exception as _e:
    import traceback
    print(f"[hostapi] v2 multi-model endpoints mount failed: {_e}")
    traceback.print_exc()

@app.on_event("startup")
async def startup_event():
    """应用启动时尝试初始化记忆系统"""
    try:
        # 尝试调用后端模块的预热逻辑（如果已导入）
        if health_api and hasattr(health_api, "_warmup_optional_tools"):
            logger.info("Triggering backend warmup/memory initialization...")
            await health_api._warmup_optional_tools()
        else:
            logger.warning("Backend health_api module not loaded or missing warmup function.")
    except Exception as e:
        logger.warning(f"Startup warmup failed: {e}")

def _env_int(name: str, default: int) -> int:
    try:
        v = int(str(os.getenv(name, "")).strip())
        return v if v > 0 else default
    except Exception:
        return default

_A2A_PROXY_MAX_CONCURRENCY = _env_int("A2A_PROXY_MAX_CONCURRENCY", 64)
_A2A_PROXY_MAX_CONNECTIONS = _env_int("A2A_PROXY_MAX_CONNECTIONS", 200)
_A2A_PROXY_MAX_KEEPALIVE = _env_int("A2A_PROXY_MAX_KEEPALIVE", 50)

_a2a_proxy_timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
_a2a_proxy_client: httpx.AsyncClient | None = None
_a2a_proxy_semaphore: asyncio.Semaphore | None = None


def _mask_db_dsn(dsn: str) -> str:
    try:
        p = urlparse(str(dsn or ""))
        user = p.username or ""
        host = p.hostname or ""
        port = p.port or ""
        db = (p.path or "").lstrip("/")
        query = p.query or ""
        auth = user or ""
        netloc = f"{auth}@{host}" if auth else host
        if port:
            netloc = f"{netloc}:{port}"
        q = f"?{query}" if query else ""
        return f"{p.scheme}://{netloc}/{db}{q}" if p.scheme else str(dsn or "")
    except Exception:
        return str(dsn or "")

def _get_a2a_proxy_client() -> httpx.AsyncClient:
    global _a2a_proxy_client
    if _a2a_proxy_client is not None:
        return _a2a_proxy_client
    limits = httpx.Limits(
        max_connections=_A2A_PROXY_MAX_CONNECTIONS,
        max_keepalive_connections=min(_A2A_PROXY_MAX_KEEPALIVE, _A2A_PROXY_MAX_CONNECTIONS),
        keepalive_expiry=30.0,
    )
    _a2a_proxy_client = httpx.AsyncClient(timeout=_a2a_proxy_timeout, limits=limits)
    return _a2a_proxy_client

def _get_a2a_proxy_semaphore() -> asyncio.Semaphore:
    global _a2a_proxy_semaphore
    if _a2a_proxy_semaphore is None:
        _a2a_proxy_semaphore = asyncio.Semaphore(_A2A_PROXY_MAX_CONCURRENCY)
    return _a2a_proxy_semaphore

def _get_user_id(user: dict) -> str:
    return str(user.get("id") or user.get("user_id") or user.get("uid") or "")

# 更严格且兼容本地开发的 CORS 设置：明确允许本地前端来源
frontend_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
extra_origin = os.getenv("FRONTEND_ORIGIN")
if extra_origin:
    try:
        frontend_origins.append(extra_origin)
    except Exception:
        pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=frontend_origins,
    allow_origin_regex=r"https?://(localhost|127\\.0\\.0\\.1)(:\\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _host_api_startup_warmup():
    logger = logging.getLogger(__name__)
    try:
        # 如果设置了禁用标志，则跳过预热以避免阻塞启动
        if os.getenv("DISABLE_MEMORY_WARMUP", "1") == "1":
            logging.info("[HostAPI] 跳过记忆系统预热 (DISABLE_MEMORY_WARMUP=1)")
            return
        # 尝试导入后端的健康档案API模块以访问其工具与服务
        try:
            sys.path.insert(0, os.environ.get("BACKEND_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
        except Exception:
            pass
        try:
            import importlib
            try:
                health_api = importlib.import_module("health_records_api")
            except Exception:
                import importlib.util
                module_path = os.path.join(os.environ.get("BACKEND_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")), "health_records_api.py")
                spec = importlib.util.spec_from_file_location("health_records_api", module_path)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    health_api = mod
        except Exception as e:
            logging.warning(f"导入后端健康档案模块失败，跳过预热: {e}")
            return

        # 预热记忆系统嵌入模型（后台异步，不阻塞应用启动）
        try:
            service = getattr(health_api, "health_records_memory_service", None)
            if service:
                async def _do_warmup():
                    try:
                        await service.initialize()
                        ms = getattr(service, "memory_system", None)
                        if ms and getattr(ms, "embedding_service", None):
                            try:
                                ms.embedding_service.generate_embedding("host_api_warmup_embeddings")
                                logging.info("[HostAPI] 记忆嵌入模型预热完成")
                            except Exception as e:
                                logging.warning(f"[HostAPI] 嵌入模型预热异常: {e}")
                    except Exception as e:
                        logging.warning(f"[HostAPI] 记忆系统初始化失败: {e}")
                # 不等待，直接后台运行
                try:
                    asyncio.create_task(_do_warmup())
                except Exception as e:
                    # 如果事件循环不可用则直接跳过，不影响服务启动
                    logging.warning(f"[HostAPI] 启动后台预热任务失败: {e}")
        except Exception as e:
            logging.warning(f"[HostAPI] 预热逻辑异常: {e}")
    except Exception:
        # 避免因预热异常影响服务启动
        pass

        # 预热 OCR 工具
        try:
            tiny_png_b64 = (
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
            )
            extract_text_from_image = getattr(health_api, "extract_text_from_image", None)
            validate_medical_document = getattr(health_api, "validate_medical_document", None)
            if extract_text_from_image:
                try:
                    _ = extract_text_from_image.fn(tiny_png_b64) if hasattr(extract_text_from_image, "fn") else extract_text_from_image(tiny_png_b64)
                    logging.info("[HostAPI] OCR工具预热完成")
                except Exception as e:
                    logging.warning(f"[HostAPI] OCR工具预热异常: {e}")
            if validate_medical_document:
                try:
                    _ = validate_medical_document.fn("host_api warmup text") if hasattr(validate_medical_document, "fn") else validate_medical_document("host_api warmup text")
                    logging.info("[HostAPI] 医疗文档验证器预热完成")
                except Exception as e:
                    logging.warning(f"[HostAPI] 医疗文档验证器预热异常: {e}")
        except Exception as e:
            logging.warning(f"[HostAPI] 预热OCR时出现异常: {e}")
    except Exception as e:
        logging.warning(f"[HostAPI] 启动预热过程出现异常（忽略继续启动）: {e}")

@app.on_event("startup")
async def _init_a2a_proxy_http_client():
    _get_a2a_proxy_client()
    _get_a2a_proxy_semaphore()


@app.on_event("startup")
async def _startup_db_connectivity_self_check():
    timeout_raw = (
        os.getenv("HOSTAPI_DB_SELF_CHECK_TIMEOUT")
        or os.getenv("DB_CONNECT_TIMEOUT")
        or "3"
    )
    try:
        timeout_sec = max(int(str(timeout_raw).strip()), 1)
    except Exception:
        timeout_sec = 3

    checks: list[tuple[str, str]] = []
    try:
        auth_dsn = auth_service._build_dsn()
        if auth_dsn:
            checks.append(("auth_db", auth_dsn))
    except Exception as e:
        logging.warning(f"[HostAPI] auth_db 自检准备失败: {e}")
    try:
        if health_api and hasattr(health_api, "_build_db_dsn"):
            health_dsn = health_api._build_db_dsn()
            if health_dsn:
                checks.append(("health_records_db", health_dsn))
    except Exception as e:
        logging.warning(f"[HostAPI] health_records_db 自检准备失败: {e}")

    if not checks:
        logging.warning("[HostAPI] 数据库自检跳过：未发现可用DSN")
        return

    for label, dsn in checks:
        begin = time.perf_counter()
        masked = _mask_db_dsn(dsn)
        try:
            with psycopg.connect(dsn, connect_timeout=timeout_sec) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    _ = cursor.fetchone()
            elapsed_ms = int((time.perf_counter() - begin) * 1000)
            logging.info(
                f"[HostAPI] DB自检通过 label={label} elapsed_ms={elapsed_ms} dsn={masked}"
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - begin) * 1000)
            logging.error(
                f"[HostAPI] DB自检失败 label={label} elapsed_ms={elapsed_ms} timeout={timeout_sec}s dsn={masked} err={e}"
            )

@app.on_event("shutdown")
async def _close_a2a_proxy_http_client():
    global _a2a_proxy_client
    if _a2a_proxy_client is None:
        return
    try:
        await _a2a_proxy_client.aclose()
    finally:
        _a2a_proxy_client = None

@app.middleware("http")
async def log_request_body(request: Request, call_next):
    start = time.perf_counter()
    status_code = 500
    try:
        content_type = request.headers.get("content-type", "")
        # 为避免影响 multipart/form-data 的流式解析，跳过读取其原始请求体
        if request.method == "POST" and "multipart/form-data" not in content_type:
            body = await request.body()
            try:
                decoded = body.decode("utf-8")
            except UnicodeDecodeError:
                decoded = body.decode("utf-8", errors="replace")
            logging.info(f"Request to {request.url.path} with body: {decoded}")
        else:
            logging.info(f"Request to {request.url.path} (content-type: {content_type})")
    except Exception as e:
        logging.warning(f"Failed to log request body: {e}")
    try:
        response = await call_next(request)
        status_code = int(getattr(response, "status_code", 500) or 500)
        return response
    finally:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logging.info(
            f"Response {request.method} {request.url.path} status={status_code} elapsed_ms={elapsed_ms}"
        )
router = APIRouter()
agent_server = ConversationServer(router)

def _normalize_agent_name(name: str) -> str:
    n = (name or "").strip()
    alias = {
        "就诊摘要生成器": "就诊摘要生成",
        "就诊摘要": "就诊摘要生成",
        "就诊摘要助手": "就诊摘要生成",
        "健康档案": "健康档案管理员",
        "健康档案管理": "健康档案管理员",
        "档案管理员": "健康档案管理员",
        # 阶段18：英文 alias 方便测试（避免中文编码问题）
        "health_advisor": "健康顾问",
        "health_adviser": "健康顾问",
        "advisor": "健康顾问",
        "health_records": "健康档案管理员",
        "records": "健康档案管理员",
        "hrm": "健康档案管理员",
        "medication_reminder": "用药提醒助手",
        "medication": "用药提醒助手",
        "reminder": "用药提醒助手",
        "visit_summary": "就诊摘要生成",
        "visit": "就诊摘要生成",
        "summary": "就诊摘要生成",
    }
    return alias.get(n, n)


def _resolve_agent_url_by_name(agent_name: str) -> str | None:
    name = _normalize_agent_name(agent_name)
    agents = getattr(agent_server, "manager", None)
    # ADKHostManager 内部存的是 _agents（带下划线），不是 agents
    cards = getattr(agents, "_agents", None) or getattr(agents, "agents", None) if agents else None
    if not cards:
        return None

    for c in cards:
        try:
            if c.name == name:
                return c.url
        except Exception:
            continue
    name_l = name.lower()
    for c in cards:
        try:
            if c.name.lower() == name_l:
                return c.url
        except Exception:
            continue
    for c in cards:
        try:
            if name_l and name_l in c.name.lower():
                return c.url
        except Exception:
            continue
    return None


def _safe_int_env(name: str, default: int) -> int:
    try:
        v = int(str(os.getenv(name, "")).strip())
        return v if v > 0 else default
    except Exception:
        return default


async def _read_image_bytes_from_uri(uri: str) -> bytes:
    file_uri = str(uri or "").strip()
    if not file_uri:
        return b""

    parsed = urlparse(file_uri)
    path = parsed.path if parsed.scheme else file_uri
    upload_dir = getattr(agent_server, "_upload_dir", "")
    max_bytes = _safe_int_env("HOSTAPI_CHAT_OCR_MAX_IMAGE_BYTES", 10 * 1024 * 1024)

    try:
        if "/files/" in path and upload_dir:
            file_id = path.split("/files/", 1)[1].split("?", 1)[0].strip("/")
            file_id = os.path.basename(unquote(file_id))
            local_path = os.path.join(upload_dir, file_id)
            if os.path.isfile(local_path):
                def _read_local_file() -> bytes:
                    with open(local_path, "rb") as f:
                        return f.read()
                data = await anyio.to_thread.run_sync(_read_local_file)
                return data[:max_bytes]
    except Exception:
        pass

    if file_uri.startswith("http://") or file_uri.startswith("https://"):
        try:
            timeout = httpx.Timeout(connect=8.0, read=20.0, write=20.0, pool=8.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(file_uri)
                if 200 <= resp.status_code < 300:
                    return (resp.content or b"")[:max_bytes]
        except Exception:
            return b""

    return b""


def _parse_bool_like(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "on", "yes"}:
        return True
    if text in {"0", "false", "off", "no"}:
        return False
    return None


def _resolve_request_ocr_options(params: dict | None, message: dict | None) -> tuple[str | None, bool | None]:
    candidates: list[dict] = []
    if isinstance(params, dict):
        pmeta = params.get("metadata")
        if isinstance(pmeta, dict):
            candidates.append(pmeta)
    if isinstance(message, dict):
        mmeta = message.get("metadata")
        if isinstance(mmeta, dict):
            candidates.append(mmeta)
    engine: str | None = None
    strict: bool | None = None
    for meta in candidates:
        if not engine:
            for k in ("ocr_engine", "chat_ocr_engine", "ocrEngine", "chatOcrEngine"):
                v = meta.get(k)
                if v is not None and str(v).strip():
                    engine = str(v).strip().lower()
                    break
        if strict is None:
            for k in ("ocr_strict", "chat_ocr_strict", "ocrStrict", "chatOcrStrict"):
                b = _parse_bool_like(meta.get(k))
                if b is not None:
                    strict = b
                    break
    return engine, strict


async def _extract_ocr_text_from_image_bytes(
    image_bytes: bytes,
    ocr_engine_override: str | None = None,
    strict_override: bool | None = None,
) -> str:
    if not image_bytes:
        return ""
    ocr_engine = (
        str(ocr_engine_override).strip().lower()
        if ocr_engine_override is not None and str(ocr_engine_override).strip()
        else str(os.getenv("HOSTAPI_CHAT_OCR_ENGINE", "legacy")).strip().lower()
    )
    strict_mode = (
        bool(strict_override)
        if strict_override is not None
        else str(os.getenv("HOSTAPI_CHAT_OCR_STRICT", "0")).strip().lower() in {"1", "true", "on"}
    )
    prefer_qwen_vl = ocr_engine in {"qwen", "qwen_vl", "qwen35", "qwen3.5", "qwen3.5-vl", "qwen_vl_ocr"}
    if prefer_qwen_vl:
        qwen_text = await _extract_ocr_text_with_qwen_vl(image_bytes)
        if qwen_text:
            return qwen_text
        if strict_mode:
            return ""
    extract_text = getattr(health_api, "extract_text_from_image", None) if "health_api" in globals() else None
    if not extract_text:
        return ""

    b64_content = base64.b64encode(image_bytes).decode("utf-8")
    try:
        if hasattr(extract_text, "fn"):
            text = await anyio.to_thread.run_sync(lambda: extract_text.fn(b64_content))
        else:
            text = await anyio.to_thread.run_sync(lambda: extract_text(b64_content))
    except Exception:
        return ""

    raw = str(text or "").strip()
    if not raw:
        return ""
    normalizer = getattr(health_api, "_normalize_ocr_text", None) if "health_api" in globals() else None
    if callable(normalizer):
        try:
            raw = str(normalizer(raw) or "").strip()
        except Exception:
            pass
    placeholder_checker = getattr(health_api, "_is_ocr_placeholder_text", None) if "health_api" in globals() else None
    if callable(placeholder_checker):
        try:
            if placeholder_checker(raw):
                return ""
        except Exception:
            pass
    return raw


def _parse_qwen_vl_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, str):
                t = item.strip()
                if t:
                    texts.append(t)
                continue
            if not isinstance(item, dict):
                continue
            t = str(item.get("text") or "").strip()
            if t:
                texts.append(t)
        return "\n".join(texts).strip()
    return ""


async def _extract_ocr_text_with_qwen_vl(image_bytes: bytes) -> str:
    api_key = (
        os.getenv("QWEN_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("ALIYUN_DASHSCOPE_API_KEY")
        or ""
    ).strip()
    if not api_key:
        return ""
    api_base = (
        os.getenv("QWEN_VL_API_BASE")
        or os.getenv("QWEN_ASR_API_BASE")
        or "https://dashscope.aliyuncs.com/compatible/v1"
    ).rstrip("/")
    model_name = (os.getenv("QWEN_VL_MODEL") or "qwen3.5-vl-plus").strip()
    prompt_text = (
        os.getenv("HOSTAPI_CHAT_OCR_QWEN_PROMPT")
        or "请识别这张图片中的所有文字，按原始结构输出纯文本，不要解释。"
    ).strip()
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)
    max_tokens = _safe_int_env("HOSTAPI_CHAT_OCR_QWEN_MAX_TOKENS", 1200)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{image_b64}"
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{api_base}/chat/completions",
                headers=headers,
                json=payload,
            )
    except Exception:
        return ""
    try:
        data = resp.json()
    except Exception:
        return ""
    if resp.status_code < 200 or resp.status_code >= 300:
        return ""
    text = ""
    if isinstance(data, dict):
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            msg = first.get("message") if isinstance(first, dict) else {}
            if isinstance(msg, dict):
                text = _parse_qwen_vl_content_to_text(msg.get("content"))
        if not text:
            output = data.get("output")
            if isinstance(output, dict):
                out_choices = output.get("choices")
                if isinstance(out_choices, list) and out_choices:
                    first = out_choices[0] if isinstance(out_choices[0], dict) else {}
                    msg = first.get("message") if isinstance(first, dict) else {}
                    if isinstance(msg, dict):
                        text = _parse_qwen_vl_content_to_text(msg.get("content"))
    raw = str(text or "").strip()
    if not raw:
        return ""
    normalizer = getattr(health_api, "_normalize_ocr_text", None) if "health_api" in globals() else None
    if callable(normalizer):
        try:
            raw = str(normalizer(raw) or "").strip()
        except Exception:
            pass
    placeholder_checker = getattr(health_api, "_is_ocr_placeholder_text", None) if "health_api" in globals() else None
    if callable(placeholder_checker):
        try:
            if placeholder_checker(raw):
                return ""
        except Exception:
            pass
    return raw


async def _inject_auto_ocr_parts(body: dict) -> int:
    if str(os.getenv("HOSTAPI_CHAT_AUTO_OCR", "1")).strip().lower() in {"0", "false", "off"}:
        return 0
    params = body.get("params") if isinstance(body, dict) else None
    message = params.get("message") if isinstance(params, dict) else None
    parts = message.get("parts") if isinstance(message, dict) else None
    if not isinstance(parts, list) or not parts:
        return 0
    req_engine, req_strict = _resolve_request_ocr_options(params, message)

    max_images = _safe_int_env("HOSTAPI_CHAT_OCR_MAX_IMAGES", 3)
    max_text_len = _safe_int_env("HOSTAPI_CHAT_OCR_TEXT_LIMIT", 1200)
    extracted_blocks: list[str] = []
    scanned = 0

    for p in parts:
        if scanned >= max_images:
            break
        if not isinstance(p, dict) or p.get("type") != "file":
            continue
        f = p.get("file") or {}
        if not isinstance(f, dict):
            continue
        mime = str(f.get("mimeType") or "").lower().strip()
        uri = str(f.get("uri") or "").strip()
        name = str(f.get("name") or f"图片{scanned + 1}").strip()
        is_image = mime.startswith("image/") or any(
            uri.lower().split("?", 1)[0].endswith(ext)
            for ext in [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".heic"]
        )
        if not is_image:
            continue
        scanned += 1
        image_bytes = await _read_image_bytes_from_uri(uri)
        text = await _extract_ocr_text_from_image_bytes(
            image_bytes,
            ocr_engine_override=req_engine,
            strict_override=req_strict,
        )
        if not text:
            continue
        clipped = text[:max_text_len]
        extracted_blocks.append(f"【{name}】\n{clipped}")

    if not extracted_blocks:
        return 0

    injected_text = "用户本轮上传图片的OCR结果如下，请结合这些文本与上下文回答：\n\n" + "\n\n".join(extracted_blocks)
    parts.append({"type": "text", "text": injected_text})
    return len(extracted_blocks)


@app.post("/a2a")
async def a2a_streaming_proxy(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体必须是JSON")

    method = body.get("method")
    if method not in ("tasks/sendSubscribe", "tasks/send"):
        raise HTTPException(status_code=400, detail="不支持的method")

    hdr = request.headers.get("X-Target-Agent") or request.headers.get("x-target-agent") or ""
    agent_name = unquote(hdr).strip() if isinstance(hdr, str) else ""
    if not agent_name:
        try:
            agent_name = (
                (body.get("params") or {})
                .get("message", {})
                .get("metadata", {})
                .get("selected_agent", "")
            )
        except Exception:
            agent_name = ""
    if not agent_name:
        raise HTTPException(status_code=400, detail="缺少目标智能体名称")

    agent_url = _resolve_agent_url_by_name(agent_name)
    if not agent_url:
        raise HTTPException(status_code=404, detail="未找到目标智能体")

    try:
        await _inject_auto_ocr_parts(body)
    except Exception as e:
        logger.warning(f"自动OCR注入失败: {e}")

    auth = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if isinstance(auth, str) and auth.strip():
        headers["Authorization"] = auth.strip()

    async def _iter():
        sem = _get_a2a_proxy_semaphore()
        async with sem:
            client = _get_a2a_proxy_client()
            async with client.stream(
                "POST",
                agent_url.rstrip("/"),
                headers=headers,
                json=body,
            ) as resp:
                if resp.status_code < 200 or resp.status_code >= 300:
                    data = await resp.aread()
                    raise HTTPException(
                        status_code=resp.status_code,
                        detail=(data.decode("utf-8", errors="replace") if data else ""),
                    )
                async for chunk in resp.aiter_bytes():
                    if chunk:
                        yield chunk

    return StreamingResponse(
        _iter(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )

# === 集成健康档案 API（方案B：将后端 API 挂载到 hostAgentAPI）===
# 为了在同一进程内复用后端实现，这里将请求转发到 backend/health_records_api.py 中已实现的处理函数
try:
    backend_dir = os.environ.get("BACKEND_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
    if backend_dir not in sys.path:
        sys.path.append(backend_dir)
    try:
        import health_records_api as health_api  # noqa: E402
    except Exception:
        import importlib.util
        module_path = os.path.join(backend_dir, "health_records_api.py")
        spec = importlib.util.spec_from_file_location("health_records_api", module_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            health_api = mod

    try:
        if hasattr(health_api, "init_database"):
            health_api.init_database()
    except Exception as e:
        logging.warning(f"健康档案API数据库初始化失败: {e}")

    health_router = APIRouter()

    @health_router.get("/api/health-records/status")
    async def health_status_proxy():
        return await health_api.get_api_status()

    # ====== 辅助：前端->后端字段映射与类型转换 ======
    def _map_record_type(front_type: str | None) -> health_api.RecordType | None:
        if not front_type:
            return None
        mapping = {
            "examination": "medical_report",
            "diagnosis": "symptom",
            "prescription": "prescription",
            "surgery": "surgery",
            "other": "other",
        }
        v = mapping.get(front_type, front_type)
        try:
            return health_api.RecordType(v)
        except Exception:
            return None

    def _map_importance(val: str | None) -> health_api.ImportanceLevel | None:
        if not val:
            return None
        try:
            return health_api.ImportanceLevel(val)
        except Exception:
            # 兼容可能的数值或中文等级
            normalize = {
                "低": "low",
                "中": "medium",
                "高": "high",
                "紧急": "critical",
                "1": "low",
                "2": "medium",
                "3": "high",
                "4": "critical",
            }.get(str(val).lower(), None)
            if normalize:
                try:
                    return health_api.ImportanceLevel(normalize)
                except Exception:
                    return None
            return None

    def _parse_date(val) -> date | None:
        if not val:
            return None
        try:
            # 允许完整ISO日期时间字符串
            s = str(val)
            return date.fromisoformat(s[:10])
        except Exception:
            return None

    def transform_record_payload(payload: dict) -> dict:
        # 映射前端字段到后端模型
        record_type = _map_record_type(payload.get("type") or payload.get("record_type"))
        importance = _map_importance(payload.get("importance"))
        record_date = _parse_date(payload.get("date") or payload.get("record_date"))
        summary = payload.get("summary") or payload.get("description")
        content = payload.get("content") or payload.get("description")
        # 将额外字段放入metadata
        metadata = payload.get("metadata") or {}
        for k in ("doctor", "hospital"):
            if payload.get(k) is not None:
                metadata[k] = payload.get(k)
        if payload.get("type") is not None:
            metadata["original_type"] = payload.get("type")
        # 仅保留可序列化的文件名
        files = payload.get("files") or []
        safe_files = [f for f in files if isinstance(f, str)]
        if safe_files:
            metadata["uploaded_files"] = safe_files
        return {
            "title": payload.get("title", ""),
            "record_type": record_type or health_api.RecordType.OTHER,
            "summary": summary,
            "content": content,
            "importance": importance or health_api.ImportanceLevel.MEDIUM,
            "tags": payload.get("tags") or [],
            "metadata": metadata,
            "record_date": record_date,
        }

    def transform_update_payload(payload: dict) -> dict:
        data: dict = {}
        if "title" in payload:
            data["title"] = payload.get("title")
        if "type" in payload or "record_type" in payload:
            rt = _map_record_type(payload.get("type") or payload.get("record_type"))
            data["record_type"] = rt
        if "description" in payload or "summary" in payload:
            data["summary"] = payload.get("summary") or payload.get("description")
        if "content" in payload or "description" in payload:
            data["content"] = payload.get("content") or payload.get("description")
        if "importance" in payload:
            data["importance"] = _map_importance(payload.get("importance"))
        if "tags" in payload:
            data["tags"] = payload.get("tags")
        if "record_date" in payload or "date" in payload:
            data["record_date"] = _parse_date(payload.get("record_date") or payload.get("date"))
        # 合并扩展元数据
        md = payload.get("metadata") or {}
        for k in ("doctor", "hospital"):
            if payload.get(k) is not None:
                md[k] = payload.get(k)
        if payload.get("type") is not None:
            md["original_type"] = payload.get("type")
        # 新增：若顶层 files 提供字符串数组，则写入 uploaded_files 以便后端返回
        if isinstance(payload.get("files"), list):
            safe_files = [f for f in payload.get("files") if isinstance(f, str)]
            if safe_files:
                md["uploaded_files"] = safe_files
                md.setdefault("files", safe_files)
        if md:
            data["metadata"] = md
        return data

    # === 后端->前端 结果映射 ===
    def _map_type_backend_to_front(back_type: str | None) -> str:
        if not back_type:
            return "other"
        mapping = {
            "medical_report": "examination",
            "lab_result": "examination",
            "inspection_report": "examination",
            "test_report": "examination",
            "medical_record": "diagnosis",
            "prescription": "prescription",
            "surgery": "surgery",
            "symptom": "diagnosis",
            "vaccination": "other",
            "allergy": "other",
            "vital_signs": "other",
            "other": "other",
        }
        return mapping.get(back_type, "other")

    def to_front_record(obj) -> dict:
        # 支持 pydantic BaseModel 或 dict
        get = (lambda k: getattr(obj, k, None)) if hasattr(obj, "dict") else (lambda k: obj.get(k))
        metadata = get("metadata") or {}
        # 合并并去重附件ID，避免前端重复显示预览按钮
        raw_files = (get("file_attachments") or []) + (metadata.get("uploaded_files") or [])
        dedup_files = []
        for f in raw_files:
            if isinstance(f, str) and f not in dedup_files:
                dedup_files.append(f)
        # 优化摘要：优先使用 summary，限制长度以控制噪声，但对检验报告放宽
        def _shorten(text: str | None, max_len: int = 200) -> str:
            if not text:
                return ""
            s = str(text).replace("\n", " ").strip()
            return s[:max_len]
        # 提取 JSON 字符串中的文本内容
        def _extract_text_from_jsonish(s: str | None) -> str:
            try:
                txt = (s or "")
                if not isinstance(txt, str):
                    txt = str(txt)
                st = txt.strip()
                if st.startswith("{") or st.startswith("["):
                    import json as _json
                    try:
                        obj = _json.loads(st)
                    except Exception:
                        return st
                    if isinstance(obj, dict):
                        for k in ("content", "Content"):
                            v = obj.get(k)
                            if isinstance(v, str) and v.strip():
                                return v.strip()
                        data = obj.get("data") or obj.get("Data")
                        if isinstance(data, dict):
                            v = data.get("content") or data.get("Content")
                            if isinstance(v, str) and v.strip():
                                return v.strip()
                            lines = data.get("lines") or data.get("prism_wordsInfo")
                            if isinstance(lines, list) and lines:
                                parts = []
                                for it in lines:
                                    if isinstance(it, dict):
                                        parts.append(str(it.get("text") or it.get("word") or "").strip())
                                    elif isinstance(it, str):
                                        parts.append(it.strip())
                                text = "\n".join([p for p in parts if p])
                                if text.strip():
                                    return text.strip()
                        elif isinstance(data, str) and data.strip():
                            return data.strip()
                    elif isinstance(obj, list) and obj:
                        parts = []
                        for it in obj:
                            if isinstance(it, dict):
                                parts.append(str(it.get("text") or it.get("word") or "").strip())
                            elif isinstance(it, str):
                                parts.append(it.strip())
                        text = "\n".join([p for p in parts if p])
                        if text.strip():
                            return text.strip()
                return st
            except Exception:
                return (s or "").strip()

        # 先取类型以便动态调整摘要长度
        back_type = get("record_type")
        summary_src_raw = get("summary") or get("content") or ""
        summary_src = _extract_text_from_jsonish(summary_src_raw)
        # 新增：中文占比估算，用于噪声检测
        def _ch_ratio(s: str | None) -> float:
            try:
                if not s:
                    return 0.0
                s2 = ''.join(c for c in str(s) if not c.isspace())
                if not s2:
                    return 0.0
                zh = sum(1 for c in s2 if '\u4e00' <= c <= '\u9fff')
                return zh / len(s2)
            except Exception:
                return 0.0
        ocr_info = metadata.get("ocr_info") or {}
        conf_raw = ocr_info.get("confidence")
        try:
            conf_val = float(conf_raw) if conf_raw is not None else 0.8
        except Exception:
            conf_val = 0.8
        cn_ratio = _ch_ratio(summary_src)
        # 默认长度 400；检验报告/处方放宽到 1200
        tval = back_type.value if hasattr(back_type, "value") else back_type
        if tval in ("medical_report", "lab_result", "examination", "prescription"):
            max_len = 3000
        else:
            max_len = 400
        try:
            if (conf_val < 0.3) and (cn_ratio < 0.2) and (len(summary_src) < 100):
                max_len = 200
        except Exception:
            pass
        summary = _shorten(summary_src, max_len=max_len)
        if not summary and isinstance(summary_src_raw, str) and summary_src_raw.strip():
            summary = summary_src_raw.strip()
        record_date = get("record_date")
        # pydantic datetime/date 直接序列化
        tags = get("tags") or []
        if isinstance(tags, list):
            tags = [t for t in tags if not (isinstance(t, str) and t.startswith("file:"))]
        return {
            "id": get("id"),
            "title": get("title") or "",
            "type": _map_type_backend_to_front(back_type.value if hasattr(back_type, "value") else back_type),
            "date": record_date,
            "description": summary,
            "content": summary_src,
            "doctor": metadata.get("doctor", ""),
            "hospital": metadata.get("hospital", ""),
            "files": dedup_files,
            "importance": (get("importance").value if hasattr(get("importance"), "value") else get("importance")) or "medium",
            "tags": tags,
            "metadata": metadata,
            "created_at": get("created_at"),
            "updated_at": get("updated_at"),
        }

    @health_router.get("/api/health-records")
    async def get_records_proxy(
        skip: int = 0,
        limit: int = 100,
        record_type: str | None = None,
        importance: str | None = None,
        search: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        user: dict = Depends(get_current_user),
    ):
        # 将字符串参数转换为后端所需的枚举与日期类型
        rt = None
        if record_type:
            try:
                rt = health_api.RecordType(record_type)
            except Exception:
                rt = None
        imp = None
        if importance:
            try:
                imp = health_api.ImportanceLevel(importance)
            except Exception:
                imp = None
        sd = None
        if start_date:
            try:
                sd = date.fromisoformat(start_date)
            except Exception:
                sd = None
        ed = None
        if end_date:
            try:
                ed = date.fromisoformat(end_date)
            except Exception:
                ed = None
        user_id = _get_user_id(user)
        result = await health_api.get_health_records(
            skip=skip,
            limit=limit,
            record_type=rt,
            importance=imp,
            search=search,
            start_date=sd,
            end_date=ed,
            user_id=user_id,
        )
        # 统一映射为前端需要的字段
        return [to_front_record(r) for r in result]

    @health_router.get("/api/health-records/{record_id}")
    async def get_record_proxy(record_id: str, user: dict = Depends(get_current_user)):
        user_id = _get_user_id(user)
        r = await health_api.get_health_record(record_id, user_id=user_id)
        return to_front_record(r)

    @health_router.post("/api/health-records")
    async def create_record_proxy(request: Request, user: dict = Depends(get_current_user)):
        payload = await request.json()
        converted = transform_record_payload(payload or {})
        record = health_api.HealthRecordCreate(**converted)
        user_id = _get_user_id(user)
        r = await health_api.create_health_record(record, user_id=user_id, request=request)
        return to_front_record(r)

    @health_router.put("/api/health-records/{record_id}")
    async def update_record_proxy(record_id: str, request: Request, user: dict = Depends(get_current_user)):
        payload = await request.json()
        converted = transform_update_payload(payload or {})
        record = health_api.HealthRecordUpdate(**converted)
        user_id = _get_user_id(user)
        r = await health_api.update_health_record(record_id, record, user_id=user_id, request=request)
        return to_front_record(r)

    @health_router.delete("/api/health-records/{record_id}")
    async def delete_record_proxy(record_id: str, request: Request, user: dict = Depends(get_current_user)):
        user_id = _get_user_id(user)
        return await health_api.delete_health_record(record_id, user_id=user_id, request=request)

    @health_router.post("/api/health-records/upload")
    async def upload_file_proxy(
        request: Request,
        file: UploadFile = File(...),
        skip_ocr: str | None = Form(None),
        user: dict = Depends(get_current_user),
    ):
        user_id = _get_user_id(user)
        return await health_api.upload_file(
            file=file,
            user_id=user_id,
            skip_ocr=skip_ocr,
            request=request,
        )

    # 新增：批量上传代理，转发到后端批量上传端点
    @health_router.post("/api/health-records/upload/multiple")
    async def upload_files_proxy(files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
        user_id = _get_user_id(user)
        return await health_api.upload_multiple_files(files, user_id=user_id)

    # 新增：文件直链转发（按file_id读取并以内联方式返回）
    @health_router.get("/api/health-records/files/{file_id}")
    async def get_file_proxy(file_id: str):
        return await health_api.get_file_attachment(file_id)

    @health_router.get("/api/health-records/ocr/status")
    async def ocr_status_proxy():
        return {"status": "ok"}

    # === 新增：就诊摘要与咨询历史代理 ===
    @health_router.get("/api/visit-summaries/count")
    async def get_visit_summary_count_proxy(
        user: dict = Depends(get_current_user),
        request: Request = None
    ):
        user_id = _get_user_id(user)
        return await health_api.get_visit_summary_count(user_id=user_id, request=request)

    @health_router.get("/api/visit-summaries/history")
    async def get_visit_summaries_proxy(
        skip: int = 0,
        limit: int = 20,
        user: dict = Depends(get_current_user),
        request: Request = None
    ):
        user_id = _get_user_id(user)
        return await health_api.get_visit_summaries(skip=skip, limit=limit, user_id=user_id, request=request)

    @health_router.get("/api/visit-summaries/{summary_id}")
    async def get_visit_summary_detail_proxy(
        summary_id: str,
        user: dict = Depends(get_current_user),
        request: Request = None,
    ):
        user_id = _get_user_id(user)
        return await health_api.get_visit_summary_detail(
            summary_id=summary_id,
            user_id=user_id,
            request=request,
        )

    @health_router.post("/api/visit-summaries/create")
    async def create_visit_summary_proxy(
        request: Request,
        user: dict = Depends(get_current_user)
    ):
        payload = await request.json()
        # 转换 payload 为后端模型
        summary_data = health_api.VisitSummaryCreate(**payload)
        user_id = _get_user_id(user)
        return await health_api.create_visit_summary(summary=summary_data, user_id=user_id, request=request)

    @health_router.delete("/api/visit-summaries/delete/{summary_id}")
    async def delete_visit_summary_proxy(
        summary_id: str,
        request: Request,
        user: dict = Depends(get_current_user),
    ):
        user_id = _get_user_id(user)
        return await health_api.delete_visit_summary(summary_id, user_id=user_id, request=request)

    @health_router.get("/api/consultations/history")
    async def get_consultation_history_proxy(
        skip: int = 0,
        limit: int = 20,
        user: dict = Depends(get_current_user),
        request: Request = None
    ):
        user_id = _get_user_id(user)
        return await health_api.get_consultation_history(skip=skip, limit=limit, user_id=user_id, request=request)

    @health_router.get("/api/dashboard/recent-activities")
    async def get_dashboard_recent_activities_proxy(
        limit: int = 10,
        user: dict = Depends(get_current_user),
        request: Request = None,
    ):
        user_id = _get_user_id(user)
        return await health_api.get_dashboard_recent_activities(
            limit=limit,
            user_id=user_id,
            request=request,
        )

    @health_router.get("/api/dashboard/stats")
    async def get_dashboard_stats_proxy(
        user: dict = Depends(get_current_user),
        request: Request = None,
    ):
        user_id = _get_user_id(user)
        return await health_api.get_dashboard_stats(
            user_id=user_id,
            request=request,
        )

    @health_router.get("/api/health-trends/indicators")
    async def get_health_trend_indicators_proxy(
        days: int = 180,
        include_points: bool = True,
        user: dict = Depends(get_current_user),
        request: Request = None,
    ):
        user_id = _get_user_id(user)
        return await health_api.get_health_trend_indicators(
            days=days,
            include_points=include_points,
            user_id=user_id,
            request=request,
        )

    @health_router.get("/api/health-trends/indicator")
    async def get_health_trend_indicator_proxy(
        name: str,
        days: int = 180,
        user: dict = Depends(get_current_user),
        request: Request = None,
    ):
        user_id = _get_user_id(user)
        return await health_api.get_health_trend_indicator(
            name=name,
            days=days,
            user_id=user_id,
            request=request,
        )

    @health_router.post("/api/health-trends/backfill")
    async def backfill_health_trends_proxy(
        days: int = 365,
        limit: int = 200,
        dry_run: bool = True,
        user: dict = Depends(get_current_user),
        request: Request = None,
    ):
        user_id = _get_user_id(user)
        return await health_api.backfill_health_trends(
            days=days,
            limit=limit,
            dry_run=dry_run,
            user_id=user_id,
            request=request,
        )

    @health_router.post("/api/visit-summaries/analyze-image")
    async def analyze_visit_summary_image(
        file: UploadFile = File(...),
        user: dict = Depends(get_current_user)
    ):
        user_id = _get_user_id(user)
        return await health_api.analyze_visit_summary_image(
            file=file,
            user_id=user_id,
            visit_date=None,
            request=None,
        )

    @health_router.post("/api/visit-summaries/batch/collect-image")
    async def collect_visit_summary_image(
        file: UploadFile = File(...),
        batch_id: str = Form(...),
        user: dict = Depends(get_current_user),
    ):
        user_id = _get_user_id(user)
        return await health_api.collect_visit_summary_image(
            file=file,
            batch_id=batch_id,
            user_id=user_id,
            request=None,
        )

    @health_router.post("/api/visit-summaries/batch/complete")
    async def complete_visit_summary_batch(
        payload: dict,
        user: dict = Depends(get_current_user),
    ):
        user_id = _get_user_id(user)
        req = (
            health_api.VisitSummaryBatchCompleteRequest(**payload)
            if isinstance(payload, dict)
            else payload
        )
        return await health_api.complete_visit_summary_batch(
            payload=req,
            user_id=user_id,
            request=None,
        )

    app.include_router(health_router)
except Exception as e:
    # 集成失败不阻塞 HostAPI，降级为警告以避免噪音
    logging.warning(f"集成健康档案API失败（未挂载 backend 或模块缺失）: {e}")

# === 用药管理与提醒 API ===
try:
    # 优先将 backend 下的具体 Agent 目录按文件路径动态加载，避免 "mcpserver" 包名冲突
    import importlib.util
    # 使用与健康档案API一致的后端路径解析逻辑
    backend_dir = os.environ.get("BACKEND_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
    hrm_dir = os.path.join(backend_dir, "HealthRecordsManager")
    mr_dir = os.path.join(backend_dir, "MedicationReminder")

    def _load_module(module_name: str, file_path: str):
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法加载模块 {module_name}，路径: {file_path}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # 加载 HealthRecordsManager 的存储工具（提供 save_medication / get_medications）
    storage_mod = _load_module(
        "hrm_storage_tool",
        os.path.join(hrm_dir, "mcpserver", "storage_tool.py")
    )
    save_medication = storage_mod.save_medication
    storage_get_medications = storage_mod.get_medications

    # 优先加载 HealthRecordsManager 的提醒工具，避免 MedicationReminder 导入时立即连接数据库
    try:
        hrm_reminder_mod = _load_module(
            "hrm_reminder_tool",
            os.path.join(hrm_dir, "mcpserver", "reminder_tool.py")
        )
        add_medication_reminder = hrm_reminder_mod.add_medication_reminder
        storage_get_reminders = hrm_reminder_mod.get_medication_reminders
        storage_mark_taken = hrm_reminder_mod.mark_reminder_taken
    except Exception:
        # 回退加载 MedicationReminder 的提醒工具（提供 add/get/log 等函数）
        reminder_mod = _load_module(
            "mr_reminder_tool",
            os.path.join(mr_dir, "mcpserver", "reminder_tool.py")
        )
        add_medication_reminder = reminder_mod.add_medication_reminder
        storage_get_reminders = reminder_mod.get_medication_reminders
        # 对应“标记已服用”的接口为 log_medication_taken
        storage_mark_taken = reminder_mod.log_medication_taken

    # 统一封装：兼容两种提醒函数签名与装饰器包装
    def _call_add_reminder(user_id: str, drug_name: str, dosage: str, frequency: str,
                           start_date: str, times_list: list, end_date: str, notes: str):
        fn = add_medication_reminder
        impl = getattr(fn, "fn", fn)
        import inspect
        try:
            sig = inspect.signature(impl)
            params = sig.parameters
            # 构造关键字参数，兼容不同参数名
            kwargs = {}
            # user_id
            kwargs["user_id"] = user_id
            # medication/drug name
            if "medication_name" in params:
                kwargs["medication_name"] = drug_name
            elif "drug_name" in params:
                kwargs["drug_name"] = drug_name
            else:
                # 若函数使用通用名称 name
                kwargs["name"] = drug_name
            # dosage
            if "dosage" in params:
                kwargs["dosage"] = dosage
            # frequency
            if "frequency" in params:
                kwargs["frequency"] = frequency
            # start/end date
            if "start_date" in params:
                kwargs["start_date"] = start_date
            if "end_date" in params:
                kwargs["end_date"] = end_date
            # notes
            if "notes" in params:
                kwargs["notes"] = notes

            # reminder_times：根据注解类型选择 list 或 JSON 字符串
            if "reminder_times" in params:
                ann = params["reminder_times"].annotation
                try:
                    # 注解为 str 或未标注时默认字符串（HRM 风格）
                    if ann is str:
                        kwargs["reminder_times"] = json.dumps(times_list)
                    else:
                        kwargs["reminder_times"] = times_list
                except Exception:
                    kwargs["reminder_times"] = times_list

            # 以关键字参数调用以避免位置参数不匹配
            return impl(**kwargs)
        except Exception:
            # 失败时仅传递被实现函数签名支持的关键字参数，避免位置参数/多余参数
            try:
                sig2 = inspect.signature(impl)
                params2 = sig2.parameters
                kwargs2 = {}
                if "user_id" in params2:
                    kwargs2["user_id"] = user_id
                if "medication_name" in params2:
                    kwargs2["medication_name"] = drug_name
                elif "drug_name" in params2:
                    kwargs2["drug_name"] = drug_name
                elif "name" in params2:
                    kwargs2["name"] = drug_name
                if "dosage" in params2:
                    kwargs2["dosage"] = dosage
                if "frequency" in params2:
                    kwargs2["frequency"] = frequency
                if "start_date" in params2:
                    kwargs2["start_date"] = start_date
                if "end_date" in params2:
                    kwargs2["end_date"] = end_date
                if "notes" in params2:
                    kwargs2["notes"] = notes
                if "reminder_times" in params2:
                    ann2 = params2["reminder_times"].annotation
                    try:
                        kwargs2["reminder_times"] = (json.dumps(times_list) if ann2 is str else times_list)
                    except Exception:
                        kwargs2["reminder_times"] = times_list
                return impl(**kwargs2)
            except Exception:
                raise

    def _call_get_medication_reminders(user_id: str, date: str, active_only: bool):
        fn = storage_get_reminders
        impl = getattr(fn, "fn", fn)
        import inspect
        sig = inspect.signature(impl)
        params = sig.parameters
        kwargs = {}
        if "user_id" in params:
            kwargs["user_id"] = user_id
        if "date" in params:
            kwargs["date"] = date or ""
        if "active_only" in params:
            kwargs["active_only"] = active_only
        elif "is_active" in params:
            kwargs["is_active"] = active_only

        if kwargs:
            return impl(**kwargs)

        try:
            if len(params) >= 3:
                return impl(user_id, date or "", active_only)
            if len(params) == 2:
                return impl(user_id, active_only)
            return impl(user_id)
        except Exception:
            return impl(user_id)

    # 统一封装：兼容两种“标记服药”函数签名（HRM: 需要 user_id；MR: 不需要）
    def _call_mark_taken(reminder_id: int, taken_time: str, user_id: str, scheduled_time: str = ""):
        fn = storage_mark_taken
        impl = getattr(fn, "fn", fn)
        import inspect
        try:
            sig = inspect.signature(impl)
            params = sig.parameters
            kwargs = {}
            # 参数名兼容
            if "reminder_id" in params:
                kwargs["reminder_id"] = reminder_id
            elif "id" in params:
                kwargs["id"] = reminder_id
            if "taken_time" in params:
                kwargs["taken_time"] = taken_time
            elif "actual_time" in params:
                kwargs["actual_time"] = taken_time
            if "scheduled_time" in params:
                kwargs["scheduled_time"] = scheduled_time
            # HRM 需要 user_id
            if "user_id" in params:
                kwargs["user_id"] = user_id
            return impl(**kwargs)
        except Exception:
            # 二次尝试：仅传递存在的关键字参数
            try:
                sig2 = inspect.signature(impl)
                params2 = sig2.parameters
                kwargs2 = {}
                if "reminder_id" in params2:
                    kwargs2["reminder_id"] = reminder_id
                elif "id" in params2:
                    kwargs2["id"] = reminder_id
                if "taken_time" in params2:
                    kwargs2["taken_time"] = taken_time
                elif "actual_time" in params2:
                    kwargs2["actual_time"] = taken_time
                if "scheduled_time" in params2:
                    kwargs2["scheduled_time"] = scheduled_time
                if "user_id" in params2:
                    kwargs2["user_id"] = user_id
                return impl(**kwargs2)
            except Exception:
                raise

    # 加载 HRM 的数据库管理器（用于直接更新 user_medications）
    db_config_mod = _load_module(
        "hrm_database_config",
        os.path.join(hrm_dir, "database_config.py")
    )
    get_db_manager = db_config_mod.get_db_manager
except Exception as e:
        logging.error(f"加载用药工具失败: {e}")
        # 回退：提供安全的占位实现，避免前端白屏
        def storage_get_medications(user_id: str, is_active: bool = True):
            return json.dumps({"medications": []})
        # 与远程提醒工具保持一致的函数签名（包含 frequency）
        def add_medication_reminder(user_id: str, drug_name: str, dosage: str, frequency: str, reminder_times: list, start_date: str, end_date: str, notes: str):
            # 仅作为占位实现：返回成功但不实际持久化提醒
            return json.dumps({
                "success": True,
                "message": "提醒模块加载失败，已使用占位实现",
                "reminders": [],
                "frequency": frequency,
                "times": reminder_times or []
            }, ensure_ascii=False)
        def storage_get_reminders(user_id: str, date: str = "", active_only: bool = True):
            return json.dumps({"reminders": []})
        def storage_mark_taken(user_id: str, reminder_id: int, taken_time: str = ""):
            return json.dumps({"success": True})
        def get_db_manager():
            return None
        # 新增：用药更新的安全回退（导入失败时不实际持久化）
        def storage_update_medication(user_id: str, medication_id: int, drug_name: str, dosage: str, frequency: str, start_date: str, end_date: str, notes: str):
            return json.dumps({"success": True, "medication_id": medication_id})

meds_router = APIRouter()

_med_ocr_limiter: anyio.CapacityLimiter | None = None


def _get_med_ocr_limiter() -> anyio.CapacityLimiter:
    global _med_ocr_limiter
    if _med_ocr_limiter is None:
        try:
            n = int(os.getenv("HOSTAPI_MED_OCR_MAX_CONCURRENCY", "8"))
        except Exception:
            n = 8
        _med_ocr_limiter = anyio.CapacityLimiter(max(n, 1))
    return _med_ocr_limiter

# 调试：查看当前绑定的 add_medication_reminder 函数签名与来源
@meds_router.get("/debug/reminder-signature")
async def debug_reminder_signature():
    try:
        fn = add_medication_reminder
        import inspect
        sig = str(inspect.signature(getattr(fn, 'fn', fn)))
        src = inspect.getsource(getattr(fn, 'fn', fn))
        return {
            "signature": sig,
            "module": getattr(fn, "__module__", ""),
            "name": getattr(fn, "__name__", ""),
            "source_preview": src.splitlines()[:3]
        }
    except Exception as e:
        return {"error": str(e)}

@meds_router.get("/api/debug/reminder-signature")
async def debug_reminder_signature_api_prefix():
    return await debug_reminder_signature()

@meds_router.get("/api/debug/reminder-params")
async def debug_reminder_params():
    try:
        fn = add_medication_reminder
        import inspect
        impl = getattr(fn, 'fn', fn)
        sig = inspect.signature(impl)
        params = [
            {
                "name": p.name,
                "kind": str(p.kind),
                "has_default": p.default is not inspect._empty,
                "annotation": str(p.annotation) if p.annotation is not inspect._empty else ""
            } for p in sig.parameters.values()
        ]
        return {"params": params}
    except Exception as e:
        return {"error": str(e)}

@meds_router.get("/medications")
@meds_router.get("/api/medications")
async def list_medications(is_active: bool = True, user: dict = Depends(get_current_user)):
        try:
            user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
            raw = storage_get_medications(user_id, is_active)
            data = json.loads(raw) if isinstance(raw, str) else raw
            meds = data.get("medications") if isinstance(data, dict) else data
            result = []
            import re
            for m in meds or []:
                freq_text = m.get("frequency") or ""
                times = [t for t in re.findall(r"(\d{1,2}:\d{2})", freq_text)]
                item = {
                    "id": m.get("id"),
                    "name": m.get("drug_name") or m.get("medication_name") or "",
                    "dosage": m.get("dosage") or "",
                    "frequency": m.get("frequency") or "",
                    "times": times,
                    "startDate": (str(m.get("start_date"))[:10] if m.get("start_date") else ""),
                    "endDate": (str(m.get("end_date"))[:10] if m.get("end_date") else None),
                    "instructions": m.get("notes") or "",
                    "reminderEnabled": len(times) > 0,
                    "beforeMeal": False,
                    "withFood": False,
                    "notes": m.get("notes") or "",
                }
                result.append(item)
            return result
        except Exception as e:
            logging.error(f"获取用药失败: {e}")
            return {"success": False, "message": f"获取用药失败: {str(e)}"}

@meds_router.post("/medications")
@meds_router.post("/api/medications")
async def create_medication(request: Request, user: dict = Depends(get_current_user)):
        try:
            payload = await request.json()
            user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
            drug_name = payload.get("drug_name") or payload.get("name") or payload.get("medication_name") or ""
            dosage = payload.get("dosage") or ""
            frequency = payload.get("frequency") or ""
            start_date = payload.get("start_date") or payload.get("startDate") or ""
            end_date = payload.get("end_date") or payload.get("endDate") or ""
            notes = payload.get("notes") or payload.get("description") or ""
            enable_reminder = bool(payload.get("reminderEnabled") or payload.get("enableReminder") or payload.get("reminder_enabled") or False)
            times = payload.get("times") or payload.get("reminder_times") or []

            # 规范化提醒时间到 HH:MM
            import re
            norm_times = []
            for t in times if isinstance(times, list) else []:
                s = str(t)
                m = re.search(r"(\d{1,2}):(\d{2})", s)
                if m:
                    hh = int(m.group(1)); mm = int(m.group(2))
                    if 0 <= hh <= 23 and 0 <= mm <= 59:
                        norm_times.append(f"{hh:02d}:{mm:02d}")

            # 规范化日期到 YYYY-MM-DD
            start_date = (str(start_date)[:10] if start_date else "")
            end_date = (str(end_date)[:10] if end_date else "")

            if enable_reminder and norm_times:
                try:
                    # 统一通过封装调用，兼容不同签名与装饰器
                    raw = _call_add_reminder(user_id, drug_name, dosage, frequency, start_date, norm_times, end_date, notes)
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    return data
                except Exception as e:
                    # 远端提醒创建失败，回退到本地文件存储
                    try:
                        local = _create_local_reminder(user_id, drug_name, dosage, frequency, start_date, norm_times, end_date, notes)
                        return {"success": True, "message": "已回退到本地提醒", "reminder": local}
                    except Exception as ie:
                        logging.error(f"本地提醒持久化失败: {ie}")
                        raise e
            else:
                raw = save_medication(user_id, drug_name, dosage, frequency, start_date, end_date, notes)
                data = json.loads(raw) if isinstance(raw, str) else raw
                return data
        except Exception as e:
            logging.error(f"创建用药失败: {e}")
            return {"success": False, "message": f"创建用药失败: {str(e)}"}

@meds_router.put("/medications/{medication_id}")
@meds_router.put("/api/medications/{medication_id}")
async def update_medication(medication_id: int, request: Request, user: dict = Depends(get_current_user)):
        try:
            payload = await request.json()
            user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))

            drug_name = payload.get("drug_name") or payload.get("name") or payload.get("medication_name") or ""
            dosage = payload.get("dosage") or ""
            frequency = payload.get("frequency") or ""
            times = payload.get("times") or payload.get("reminder_times") or []
            start_date = payload.get("start_date") or payload.get("startDate") or ""
            end_date = payload.get("end_date") or payload.get("endDate") or ""
            notes = payload.get("notes") or payload.get("description") or ""

            # 规范化日期与时间
            import re
            norm_times = []
            for t in times if isinstance(times, list) else []:
                s = str(t)
                m = re.search(r"(\d{1,2}):(\d{2})", s)
                if m:
                    hh = int(m.group(1)); mm = int(m.group(2))
                    if 0 <= hh <= 23 and 0 <= mm <= 59:
                        norm_times.append(f"{hh:02d}:{mm:02d}")
            start_date = (str(start_date)[:10] if start_date else "")
            end_date = (str(end_date)[:10] if end_date else "")

            # 如果前端传了具体时间，则重构 frequency 文本以兼容列表解析
            if norm_times:
                frequency_text = f"每日{len(norm_times)}次，时间：{', '.join(norm_times)}"
            else:
                frequency_text = frequency or ""

            dbm = None
            try:
                dbm = get_db_manager()
            except Exception:
                dbm = None

            if dbm:
                # 持久化更新到 user_medications
                update_sql = (
                    "UPDATE user_medications SET drug_name = %s, dosage = %s, frequency = %s, "
                    "start_date = %s, end_date = %s, notes = %s, updated_at = NOW() "
                    "WHERE id = %s AND user_id = %s AND CAST(is_deleted AS TEXT) IN ('0','f','false')"
                )
                params = (
                    drug_name, dosage, frequency_text,
                    (start_date or None), (end_date or None), notes,
                    medication_id, user_id
                )
                try:
                    affected = dbm.execute_update(update_sql, params)
                    return {"success": affected > 0, "medication_id": medication_id}
                except Exception as e:
                    logging.error(f"更新用药失败: {e}")
                    return {"success": False, "message": f"更新用药失败: {str(e)}"}
            else:
                # 无数据库管理器时，使用回退以避免前端报错
                raw = storage_update_medication(user_id, medication_id, drug_name, dosage, frequency_text, start_date, end_date, notes)
                data = json.loads(raw) if isinstance(raw, str) else raw
                return data
        except Exception as e:
            logging.error(f"更新用药失败: {e}")
            return {"success": False, "message": f"更新用药失败: {str(e)}"}

@meds_router.get("/medication-reminders")
@meds_router.get("/api/medication-reminders")
async def list_medication_reminders(date: str = "", active_only: bool = True, user: dict = Depends(get_current_user)):
        try:
            user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
            raw = _call_get_medication_reminders(user_id, date, active_only)
            data = json.loads(raw) if isinstance(raw, str) else raw
            rows = (data.get("reminders") if isinstance(data, dict) else data) or []
            from datetime import datetime
            target_date = (date or (datetime.utcnow().date().isoformat()))
            result = []
            dbm = None
            try:
                dbm = get_db_manager()
            except Exception:
                dbm = None

            def _parse_times(row: dict) -> list:
                times = []
                if row.get("reminder_time"):
                    times = [str(row.get("reminder_time"))]
                else:
                    raw_times = row.get("reminder_times")
                    try:
                        if isinstance(raw_times, str):
                            times = json.loads(raw_times)
                        elif isinstance(raw_times, (list, tuple)):
                            times = list(raw_times)
                    except Exception:
                        times = []
                cleaned = []
                import re
                for t in times or []:
                    m = re.search(r"(\d{1,2}):(\d{2})", str(t))
                    if m:
                        hh = int(m.group(1)); mm = int(m.group(2))
                        if 0 <= hh <= 23 and 0 <= mm <= 59:
                            cleaned.append(f"{hh:02d}:{mm:02d}")
                return cleaned

            def _status_for(reminder_row_id: int, scheduled_dt):
                if not dbm:
                    return "pending"
                try:
                    log_rows = dbm.execute_query(
                        "SELECT status FROM reminder_logs WHERE reminder_id = %s AND user_id = %s AND scheduled_time = %s ORDER BY completion_time DESC NULLS LAST LIMIT 1",
                        (reminder_row_id, user_id, scheduled_dt),
                    )
                    if log_rows:
                        s = str(log_rows[0].get("status") or "").lower()
                        if s in ("completed", "taken"):
                            return "taken"
                        if s in ("missed", "skipped"):
                            return "missed"
                except Exception:
                    pass
                return "pending"

            for r in rows or []:
                reminder_row_id = r.get("id")
                med_id = r.get("medication_id") or r.get("medicationId")
                if not med_id and dbm and reminder_row_id:
                    try:
                        res = dbm.execute_query(
                            "SELECT medication_id FROM medication_reminders WHERE id = %s",
                            (reminder_row_id,),
                        )
                        if res:
                            med_id = res[0].get("medication_id")
                    except Exception:
                        pass

                for t in _parse_times(r):
                    try:
                        scheduled_dt = datetime.strptime(f"{target_date} {t}:00", "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        continue
                    status = _status_for(int(reminder_row_id), scheduled_dt) if reminder_row_id else "pending"
                    result.append({
                        "id": reminder_row_id,
                        "medicationId": med_id,
                        "medicationName": r.get("medication_name") or r.get("medicationName") or r.get("title") or "",
                        "dosage": r.get("dosage") or "",
                        "scheduledTime": scheduled_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "time": t,
                        "status": status,
                        "taken": status in ("taken", "completed"),
                    })

            try:
                result.sort(key=lambda x: (x.get("scheduledTime") or ""))
            except Exception:
                pass
            return result
        except Exception as e:
            logging.error(f"获取用药提醒失败: {e}")
            return {"success": False, "message": f"获取用药提醒失败: {str(e)}"}

@meds_router.post("/medication-reminders")
@meds_router.post("/api/medication-reminders")
async def create_medication_reminder(request: Request, user: dict = Depends(get_current_user)):
        try:
            payload = await request.json()
            user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
            name = payload.get("name") or payload.get("medication_name") or payload.get("drug_name") or ""
            dosage = payload.get("dosage") or ""
            times = payload.get("times") or payload.get("reminder_times") or []
            start_date = payload.get("startDate") or payload.get("start_date") or ""
            end_date = payload.get("endDate") or payload.get("end_date") or ""
            notes = payload.get("notes") or payload.get("description") or ""

            # 规范化提醒时间到 HH:MM
            norm_times = []
            try:
                import re
                for t in times if isinstance(times, list) else []:
                    s = str(t)
                    m = re.search(r"(\d{1,2}):(\d{2})", s)
                    if m:
                        hh = int(m.group(1)); mm = int(m.group(2))
                        if 0 <= hh <= 23 and 0 <= mm <= 59:
                            norm_times.append(f"{hh:02d}:{mm:02d}")
            except Exception:
                pass

            start_date = (str(start_date)[:10] if start_date else "")
            end_date = (str(end_date)[:10] if end_date else "")

            # 构造频率描述；提醒工具需要 frequency 和 times 列表
            frequency = f"每日{len(norm_times)}次" if norm_times else (payload.get("frequency") or "")
            raw = _call_add_reminder(user_id, name, dosage, frequency, start_date, norm_times, end_date, notes)
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data
        except Exception as e:
            logging.error(f"创建用药提醒失败: {e}")
            return {"success": False, "message": f"创建用药提醒失败: {str(e)}"}


# (Removes conflicting endpoints that are now handled by health_records_api via health_router)

@meds_router.get("/api/consultations/history")
async def get_consultation_history(
    skip: int = 0,
    limit: int = 20,
    include_summary: bool = False,
    include_health_records: bool = False,
    user: dict = Depends(get_current_user),
):
    try:
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
        db_manager = get_db_manager()
        if not db_manager:
             return []

        where_clauses = ["user_id = %s"]
        if not include_summary:
            where_clauses.append("(tags IS NULL OR NOT (tags ? 'summary'))")
        if not include_health_records:
            where_clauses.append("(tags IS NULL OR NOT (tags ? 'health_records'))")
        where_sql = " AND ".join(where_clauses)
        rows = db_manager.execute_query(
            f"SELECT * FROM consultations WHERE {where_sql} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            (user_id, limit, skip),
        )
        # Convert datetimes and ensure consistent fields
        filtered = []
        for row in rows:
             if row.get('created_at'): row['created_at'] = str(row['created_at'])
             if row.get('updated_at'): row['updated_at'] = str(row['updated_at'])
             # Ensure frontend compatible fields
             if not row.get('consultation_type') and row.get('type'):
                 row['consultation_type'] = row['type']
             tags = row.get("tags")
             if isinstance(tags, str):
                 try:
                     tags = json.loads(tags)
                 except Exception:
                     tags = []
             elif tags is None:
                 tags = []
             elif not isinstance(tags, list):
                 tags = []
             row["tags"] = tags

             filtered.append(row)
        return filtered
    except Exception as e:
        logging.error(f"Get history error: {e}")
        return []

@meds_router.post("/api/consultations/create")
async def create_consultation_db(request: Request, user: dict = Depends(get_current_user)):
    try:
        payload = await request.json()
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
        title = payload.get("title", "New Consultation")
        c_type = payload.get("type", "general")
        agent_id = payload.get("agentId", "")
        question = payload.get("question", "")
        session_id = payload.get("session_id", "")
        tags = payload.get("tags", [])

        # Use provided consultation_id or generate new one
        c_id = payload.get("consultation_id") or payload.get("id") or str(uuid.uuid4())

        db_manager = get_db_manager()
        if not db_manager:
             return {"success": False, "message": "DB not available"}
        _ensure_consultation_tables(db_manager)

        # Serialize tags if list
        import json
        tags_json = json.dumps(tags) if isinstance(tags, list) else tags

        db_manager.execute_update(
            "INSERT INTO consultations (consultation_id, user_id, title, consultation_type, agent_id, status, question, session_id, tags) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (c_id, user_id, title, c_type, agent_id, "active", question, session_id, tags_json)
        )

        return {"success": True, "consultation_id": c_id}
    except Exception as e:
        return {"success": False, "message": str(e)}

@meds_router.post("/api/consultations/message")
async def save_consultation_message(request: Request, user: dict = Depends(get_current_user)):
    try:
        payload = await request.json()
        consultation_id = payload.get("consultation_id")
        role = payload.get("role")
        content = payload.get("content")
        files = payload.get("files") # Optional files list

        if not consultation_id or not role or not content:
            return {"success": False, "message": "Missing required fields"}

        db_manager = get_db_manager()
        if not db_manager:
            return {"success": False, "message": "DB Manager not available"}
        _ensure_consultation_tables(db_manager)

        msg_id = str(uuid.uuid4())

        # Serialize files if present
        import json
        files_json = json.dumps(files or [])

        db_manager.execute_update(
            """
            INSERT INTO chat_messages (id, consultation_id, role, content, files, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, now())
            """,
            (msg_id, consultation_id, role, content, files_json),
        )
        return {"success": True}
    except Exception as e:
        logging.error(f"Save message error: {e}")
        return {"success": False, "message": str(e)}

@meds_router.get("/api/consultations/{consultation_id}/messages")
async def get_consultation_messages(consultation_id: str, user: dict = Depends(get_current_user)):
    try:
        db_manager = get_db_manager()
        if not db_manager:
            return {"success": False, "message": "DB Manager not available"}
        _ensure_consultation_tables(db_manager)

        rows = db_manager.execute_query(
            """
            SELECT id, role, content, files, created_at
            FROM chat_messages
            WHERE consultation_id = %s
            ORDER BY created_at ASC
            """,
            (consultation_id,)
        )
        messages = []
        for row in rows:
            files = row.get("files")
            if isinstance(files, str):
                try:
                    files = json.loads(files)
                except Exception:
                    files = []
            messages.append(
                {
                    "id": str(row.get("id") or ""),
                    "role": row.get("role") or "",
                    "content": row.get("content") or "",
                    "files": files or [],
                    "created_at": str(row.get("created_at") or ""),
                }
            )

        return {"success": True, "messages": messages}
    except Exception as e:
        logging.error(f"Get messages error: {e}")
        return {"success": False, "message": str(e)}

@meds_router.delete("/api/consultations/{consultation_id}")
async def delete_consultation_api(consultation_id: str, user: dict = Depends(get_current_user)):
    try:
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))

        db_manager = get_db_manager()
        if not db_manager:
             return {"success": False, "message": "DB Manager not available"}

        # Verify ownership
        check_query = "SELECT user_id FROM consultations WHERE consultation_id = %s"
        rows = db_manager.execute_query(check_query, (consultation_id,))
        if not rows:
            return {"success": False, "message": "Consultation not found"}

        if rows[0]['user_id'] != user_id:
             return {"success": False, "message": "Permission denied"}

        # Delete messages first
        db_manager.execute_update("DELETE FROM chat_messages WHERE consultation_id = %s", (consultation_id,))

        # Delete consultation
        db_manager.execute_update("DELETE FROM consultations WHERE consultation_id = %s", (consultation_id,))

        return {"success": True}
    except Exception as e:
        logging.error(f"Delete consultation error: {e}")
        return {"success": False, "message": str(e)}


# (Removes conflicting visit summary endpoints handled by health_records_api)

@meds_router.post("/medication-reminders/{reminder_id}/taken")
@meds_router.post("/api/medication-reminders/{reminder_id}/taken")
async def mark_medication_taken(reminder_id: int, request: Request, taken_time: str = "", user: dict = Depends(get_current_user)):
        try:
            # 记录服药接口签名为 log_medication_taken(reminder_id, actual_time=None, notes=None)
            try:
                user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
                payload = {}
                try:
                    payload = await request.json()
                except Exception:
                    payload = {}

                scheduled_time = payload.get("scheduledTime") or payload.get("scheduled_time") or ""
                taken_payload = payload.get("takenTime") or payload.get("taken_time") or payload.get("actual_time") or ""
                if not taken_time and taken_payload:
                    taken_time = str(taken_payload)

                raw = _call_mark_taken(reminder_id, taken_time, user_id, str(scheduled_time or ""))
                data = json.loads(raw) if isinstance(raw, str) else raw
                return data
            except Exception:
                # 回退更新本地提醒状态
                ok = _mark_local_taken(reminder_id, taken_time)
                return {"success": ok}
        except Exception as e:
            logging.error(f"标记服药失败: {e}")
            return {"success": False, "message": f"标记服药失败: {str(e)}"}

@meds_router.post("/api/medication-reminders/{reminder_id}/skipped")
async def mark_medication_skipped(reminder_id: int, request: Request, user: dict = Depends(get_current_user)):
    user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
    payload = {}
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    scheduled_raw = payload.get("scheduledTime") or payload.get("scheduled_time") or ""
    scheduled_dt = None
    from datetime import datetime
    if scheduled_raw:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                scheduled_dt = datetime.strptime(str(scheduled_raw), fmt)
                break
            except Exception:
                pass

    if scheduled_dt is None:
        scheduled_dt = datetime.now().replace(second=0, microsecond=0)

    dbm = None
    try:
        dbm = get_db_manager()
    except Exception:
        dbm = None

    now = datetime.now()
    if dbm:
        try:
            affected = dbm.execute_update(
                "UPDATE reminder_logs SET status = 'missed', completion_time = NOW(), notes = '用户标记跳过' WHERE reminder_id = %s AND user_id = %s AND scheduled_time = %s",
                (reminder_id, user_id, scheduled_dt),
            )
            if not affected:
                dbm.execute_insert(
                    "INSERT INTO reminder_logs (reminder_id, user_id, scheduled_time, actual_time, status, completion_time, notes) VALUES (%s, %s, %s, %s, 'missed', %s, '用户标记跳过')",
                    (reminder_id, user_id, scheduled_dt, None, now),
                )
            return {"success": True}
        except Exception:
            try:
                dbm.execute_insert(
                    "INSERT INTO reminder_logs (reminder_id, scheduled_time, actual_time, status, notes, created_at) VALUES (%s, %s, %s, 'missed', '用户标记跳过', %s)",
                    (reminder_id, scheduled_dt, None, now),
                )
                return {"success": True}
            except Exception as e:
                return {"success": False, "message": str(e)}

    ok = _mark_local_missed(reminder_id, str(scheduled_dt))
    return {"success": ok}

@meds_router.put("/api/medication-reminders/{reminder_id}/active")
async def set_medication_reminder_active(reminder_id: int, request: Request, user: dict = Depends(get_current_user)):
    user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
    payload = {}
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    raw_enabled = payload.get("enabled")
    if isinstance(raw_enabled, bool):
        enabled = raw_enabled
    elif isinstance(raw_enabled, (int, float)):
        enabled = bool(int(raw_enabled))
    elif isinstance(raw_enabled, str):
        enabled = raw_enabled.strip().lower() in ("1", "t", "true", "y", "yes", "on")
    else:
        enabled = False

    dbm = None
    try:
        dbm = get_db_manager()
    except Exception:
        dbm = None

    if not dbm:
        ok = _set_local_reminder_active(reminder_id, enabled)
        return {"success": ok}

    try:
        try:
            affected = dbm.execute_update(
                "UPDATE medication_reminders SET is_active = (%s)::boolean, updated_at = NOW() WHERE id = %s AND user_id = %s",
                ("true" if enabled else "false", reminder_id, user_id),
            )
        except Exception:
            affected = dbm.execute_update(
                "UPDATE medication_reminders SET is_active = %s, updated_at = NOW() WHERE id = %s AND user_id = %s",
                (1 if enabled else 0, reminder_id, user_id),
            )
        return {"success": affected > 0}
    except Exception as e:
        return {"success": False, "message": str(e)}

@meds_router.delete("/medications/{medication_id}")
@meds_router.delete("/api/medications/{medication_id}")
async def delete_medication_api(medication_id: int, user: dict = Depends(get_current_user)):
    user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
    dbm = None
    try:
        dbm = get_db_manager()
    except Exception:
        dbm = None

    if not dbm:
        return {"success": False, "message": "DB not available"}

    try:
        try:
            affected = dbm.execute_update(
                "UPDATE user_medications SET is_deleted = %s, is_active = %s, updated_at = NOW() WHERE id = %s AND user_id = %s",
                (True, False, medication_id, user_id),
            )
        except Exception:
            affected = dbm.execute_update(
                "UPDATE user_medications SET is_deleted = %s, is_active = %s, updated_at = NOW() WHERE id = %s AND user_id = %s",
                (1, 0, medication_id, user_id),
            )

        if affected <= 0:
            return {"success": False, "message": "not_found"}

        try:
            try:
                dbm.execute_update(
                    "UPDATE medication_reminders SET is_active = %s, updated_at = NOW() WHERE user_id = %s AND medication_id = %s",
                    (False, user_id, medication_id),
                )
            except Exception:
                dbm.execute_update(
                    "UPDATE medication_reminders SET is_active = %s, updated_at = NOW() WHERE user_id = %s AND medication_id = %s",
                    (0, user_id, medication_id),
                )
        except Exception:
            pass

        return {"success": True}
    except Exception as e:
        return {"success": False, "message": str(e)}

@meds_router.post("/api/medications/{medication_id}/reminders")
async def add_reminders_to_medication(medication_id: int, request: Request, user: dict = Depends(get_current_user)):
    user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
    payload = await request.json()
    times = payload.get("times") or payload.get("reminder_times") or []
    start_date = payload.get("startDate") or payload.get("start_date") or ""
    end_date = payload.get("endDate") or payload.get("end_date") or ""
    notes = payload.get("notes") or ""

    import re
    norm_times = []
    for t in times if isinstance(times, list) else []:
        m = re.search(r"(\d{1,2}):(\d{2})", str(t))
        if m:
            hh = int(m.group(1)); mm = int(m.group(2))
            if 0 <= hh <= 23 and 0 <= mm <= 59:
                norm_times.append(f"{hh:02d}:{mm:02d}")

    start_date = (str(start_date)[:10] if start_date else "")
    end_date = (str(end_date)[:10] if end_date else "")

    if not norm_times:
        return {"success": False, "message": "no_valid_times"}

    dbm = None
    try:
        dbm = get_db_manager()
    except Exception:
        dbm = None

    if not dbm:
        return {"success": False, "message": "DB not available"}

    from datetime import datetime
    meds = dbm.execute_query(
        "SELECT id, drug_name, dosage, frequency, start_date, end_date, notes FROM user_medications WHERE id = %s AND user_id = %s AND CAST(is_deleted AS TEXT) IN ('0','f','false')",
        (medication_id, user_id),
    )
    if not meds:
        return {"success": False, "message": "medication_not_found"}

    med = meds[0]
    drug_name = med.get("drug_name") or ""
    dosage = med.get("dosage") or ""
    frequency_text = med.get("frequency") or ""
    merged_notes = notes or (med.get("notes") or "")
    if not start_date:
        start_date = str(med.get("start_date"))[:10] if med.get("start_date") else ""
    if not end_date:
        end_date = str(med.get("end_date"))[:10] if med.get("end_date") else ""

    try:
        import re as _re
        existing_times = set(_re.findall(r"(\d{1,2}:\d{2})", frequency_text or ""))
        if existing_times:
            merged = sorted({*existing_times, *set(norm_times)})
            frequency_text = f"每日{len(merged)}次，时间：{', '.join(merged)}"
        else:
            frequency_text = f"每日{len(norm_times)}次，时间：{', '.join(norm_times)}"
        dbm.execute_update(
            "UPDATE user_medications SET frequency = %s, updated_at = NOW() WHERE id = %s AND user_id = %s",
            (frequency_text, medication_id, user_id),
        )
    except Exception:
        pass

    reminder_ids = []
    for t in norm_times:
        existing = []
        try:
            existing = dbm.execute_query(
                "SELECT id FROM medication_reminders WHERE user_id = %s AND medication_id = %s AND reminder_times::text LIKE %s AND CAST(is_deleted AS TEXT) IN ('0','f','false') AND CAST(is_active AS TEXT) IN ('1','t','true') LIMIT 1",
                (user_id, medication_id, f"%{t}%"),
            )
        except Exception:
            existing = []
        if existing:
            continue

        try:
            first_dt = f"{start_date or datetime.utcnow().date().isoformat()} {t}:00"
            main_id = dbm.execute_insert(
                "INSERT INTO reminders (user_id, reminder_type, title, description, reminder_time) VALUES (%s, %s, %s, %s, %s)",
                (user_id, "medication", drug_name, merged_notes, first_dt),
            )
            rid = dbm.execute_insert(
                "INSERT INTO medication_reminders (reminder_id, user_id, medication_id, medication_name, dosage, frequency, reminder_times, start_date, end_date, notes) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (main_id, user_id, medication_id, drug_name, dosage, frequency_text, json.dumps([t]), (start_date or None), (end_date or None), merged_notes),
            )
            reminder_ids.append(rid)
        except Exception:
            continue

    return {"success": True, "reminder_ids": reminder_ids}

@meds_router.get("/api/medication-stats")
async def get_medication_stats(days: int = 7, date: str = "", user: dict = Depends(get_current_user)):
    user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
    from datetime import datetime, timedelta

    try:
        end_date = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
    except Exception:
        end_date = datetime.now().date()

    days = int(days or 7)
    if days < 1:
        days = 7
    if days > 90:
        days = 90

    dbm = None
    try:
        dbm = get_db_manager()
    except Exception:
        dbm = None

    if not dbm:
        return {"success": False, "message": "DB not available"}

    per_day = []
    for i in range(days):
        d = end_date - timedelta(days=(days - 1 - i))

        scheduled_cnt = 0
        try:
            row = dbm.execute_query(
                """
                SELECT COUNT(*) AS cnt
                FROM medication_reminders mr
                LEFT JOIN user_medications um
                  ON um.user_id = mr.user_id
                 AND um.id = mr.medication_id
                 AND CAST(um.is_deleted AS TEXT) IN ('0','f','false')
                WHERE mr.user_id = %s
                  AND CAST(mr.is_deleted AS TEXT) IN ('0','f','false')
                  AND CAST(mr.is_active AS TEXT) IN ('1','t','true')
                  AND COALESCE(mr.start_date, um.start_date, DATE '1900-01-01') <= %s
                  AND (
                    COALESCE(mr.end_date, um.end_date) IS NULL
                    OR COALESCE(mr.end_date, um.end_date) >= %s
                  )
                """,
                (user_id, d, d),
            )
            scheduled_cnt = int((row[0] or {}).get("cnt") or 0) if row else 0
        except Exception:
            scheduled_cnt = 0

        taken_ids = set()
        missed_ids = set()
        on_time_ids = set()
        try:
            start_dt = datetime(d.year, d.month, d.day)
            end_dt = start_dt + timedelta(days=1)
            logs = dbm.execute_query(
                "SELECT reminder_id, scheduled_time, actual_time, status FROM reminder_logs WHERE user_id = %s AND scheduled_time >= %s AND scheduled_time < %s",
                (user_id, start_dt, end_dt),
            )
            for l in logs or []:
                rid = l.get("reminder_id")
                if rid is None:
                    continue
                status = str(l.get("status") or "").lower()
                if status in ("completed", "taken"):
                    taken_ids.add(int(rid))
                    try:
                        st = l.get("scheduled_time")
                        at = l.get("actual_time")
                        if st and at:
                            delta = abs((at - st).total_seconds())
                            if delta <= 30 * 60:
                                on_time_ids.add(int(rid))
                    except Exception:
                        pass
                elif status in ("missed", "skipped"):
                    missed_ids.add(int(rid))
        except Exception:
            pass

        per_day.append({
            "date": d.isoformat(),
            "scheduled": scheduled_cnt,
            "taken": len(taken_ids),
            "missed": len(missed_ids),
            "onTime": len(on_time_ids),
        })

    total_scheduled = sum(x["scheduled"] for x in per_day)
    total_taken = sum(x["taken"] for x in per_day)
    total_missed = sum(x["missed"] for x in per_day)
    total_on_time = sum(x["onTime"] for x in per_day)

    adherence_rate = int(round((total_taken / total_scheduled) * 100)) if total_scheduled > 0 else 0
    on_time_rate = int(round((total_on_time / total_taken) * 100)) if total_taken > 0 else 0

    streak = 0
    for x in reversed(per_day):
        if x["scheduled"] > 0 and x["taken"] >= x["scheduled"] and x["missed"] == 0:
            streak += 1
        else:
            break

    return {
        "success": True,
        "totalDays": streak,
        "adherenceRate": adherence_rate,
        "missedDoses": total_missed,
        "onTimeRate": on_time_rate,
        "windowDays": days,
        "totalScheduled": total_scheduled,
        "perDay": per_day,
    }

@meds_router.post("/api/medications/ocr")
async def recognize_medication_image(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    limiter = _get_med_ocr_limiter()
    await limiter.acquire()
    try:
        max_size = int(
            os.getenv("HOSTAPI_MED_OCR_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))
        )
        chunk_size = int(
            os.getenv("HOSTAPI_MED_OCR_UPLOAD_CHUNK_BYTES", str(1024 * 1024))
        )
        file_size = 0
        buf = bytearray()
        try:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > max_size:
                    return {"success": False, "message": "文件大小超过限制"}
                buf.extend(chunk)
        finally:
            try:
                await file.close()
            except Exception:
                pass

        content = bytes(buf)
        if not content:
            return {"success": False, "message": "文件为空"}

        # 转换为Base64
        import base64
        b64_content = base64.b64encode(content).decode("utf-8")

        # 调用OCR工具
        extract_text = getattr(health_api, "extract_text_from_image", None)
        if not extract_text:
            return {"success": False, "message": "OCR服务不可用"}

        # extract_text_from_image 是一个 MCP 工具函数，可能直接调用或者通过 fn 调用
        text = ""
        try:
            if hasattr(extract_text, "fn"):
                text = extract_text.fn(b64_content)
            else:
                text = extract_text(b64_content)
        except Exception as ocr_err:
            logging.error(f"OCR识别出错: {ocr_err}")
            return {"success": False, "message": f"识别失败: {str(ocr_err)}"}

        llm_med_names: list[str] = []
        llm_drug_name = ""
        try:
            maybe_llm_display_fields = getattr(health_api, "_maybe_llm_display_fields", None)
            if maybe_llm_display_fields and str(text or "").strip():
                seed = {"document_type": "prescription", "original_content": text}
                display_fields = await maybe_llm_display_fields(
                    str(text or ""),
                    seed,
                    doc_kind="prescription",
                )
                meds_val = None
                if isinstance(display_fields, dict):
                    meds_val = display_fields.get("medications") or display_fields.get("medication_names")
                if isinstance(meds_val, list):
                    for m in meds_val:
                        name = ""
                        if isinstance(m, str):
                            name = m.strip()
                        elif isinstance(m, dict):
                            name = str(m.get("name") or "").strip()
                        if name:
                            llm_med_names.append(name)
                if llm_med_names:
                    llm_med_names = list(dict.fromkeys(llm_med_names))[:8]
                    llm_drug_name = llm_med_names[0]
        except Exception as llm_err:
            logging.warning(f"LLM药名抽取失败，回退规则提取: {llm_err}")

        lines = [line.strip() for line in text.split('\n') if line.strip()]
        stop_words = {
            "国药准字",
            "批准文号",
            "生产企业",
            "生产厂家",
            "功能主治",
            "适应症",
            "用法用量",
            "不良反应",
            "注意事项",
            "禁忌",
            "规格",
            "有效期",
            "条形码",
            "二维码",
            "说明书",
            "请仔细阅读",
            "OTC",
            "Rx",
        }
        suffixes = (
            "片",
            "胶囊",
            "颗粒",
            "口服液",
            "糖浆",
            "混悬液",
            "注射液",
            "滴眼液",
            "滴鼻液",
            "喷雾剂",
            "软膏",
            "乳膏",
            "凝胶",
            "贴剂",
            "贴",
            "栓",
            "丸",
            "散",
            "合剂",
        )

        def _normalize_line(line: str) -> str:
            return (
                str(line or "")
                .strip()
                .replace(" ", "")
                .replace("\t", "")
                .replace("（", "(")
                .replace("）", ")")
            )

        def _score_name(line: str) -> int:
            s = _normalize_line(line)
            if not s:
                return -999
            if len(s) < 2 or len(s) > 30:
                return -999
            if any(w in s for w in stop_words):
                return -999
            if re.search(r"[^A-Za-z0-9\u4e00-\u9fa5·\-\(\)]", s):
                return -999
            score = 0
            if re.search(r"[\u4e00-\u9fa5]", s):
                score += 10
            if 3 <= len(s) <= 16:
                score += 8
            if any(s.endswith(x) or x in s for x in suffixes):
                score += 25
            if re.search(r"(每日|每次|用法|用量|毫克|mg|ml|g)", s, flags=re.I):
                score -= 12
            if re.search(r"\d{3,}", s):
                score -= 8
            return score

        candidates = []
        for raw in lines[:24]:
            s = _normalize_line(raw)
            if not s:
                continue
            s = re.sub(r"^[药品名称品名]+[:：]?", "", s)
            s = re.sub(r"^[（(]?[甲乙丙丁戊]?[0-9一二三四五六七八九十]+[）).、\-]*", "", s)
            if s:
                candidates.append(s)
        candidates = list(dict.fromkeys(candidates))
        best = ""
        best_score = -999
        for c in candidates:
            sc = _score_name(c)
            if sc > best_score:
                best_score = sc
                best = c
        rule_drug_name = best if best_score >= 0 else (candidates[0] if candidates else "")
        drug_name = llm_drug_name or rule_drug_name
        if len(drug_name) > 24:
            drug_name = drug_name[:24]

        return {
            "success": True,
            "text": text,
            "drug_name": drug_name,
            "medication_names": llm_med_names,
            "lines": lines
        }
    except Exception as e:
        logging.error(f"药物图片识别失败: {e}")
        return {"success": False, "message": f"处理失败: {str(e)}"}
    finally:
        limiter.release()

app.include_router(meds_router)

def _get_backend_notification_service():
    try:
        backend_dir = os.environ.get("BACKEND_DIR") or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "backend")
        )
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        import importlib
        mod = importlib.import_module("notification_service")
        return getattr(mod, "notification_service", None)
    except Exception:
        return None

@app.get("/api/wechat/template-ids")
async def get_wechat_template_ids():
    svc = _get_backend_notification_service()
    template_ids = getattr(svc, "template_ids", {}) if svc else {}
    return {
        "task_complete": template_ids.get("task_complete", ""),
        "health_alert": template_ids.get("health_alert", ""),
        "medication_reminder": template_ids.get("medication_reminder", ""),
    }

@app.post("/api/wechat/bind-openid")
async def bind_wechat_openid(request: Request, user: dict = Depends(get_current_user)):
    payload = {}
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    code = str(payload.get("code") or "").strip()
    if not code:
        return {"success": False, "message": "缺少code"}

    svc = _get_backend_notification_service()
    if not svc:
        return {"success": False, "message": "微信服务不可用"}

    data = None
    try:
        data = await svc.code_to_session(code)
    except Exception:
        data = None

    openid = (data or {}).get("openid") if isinstance(data, dict) else None
    if not openid:
        return {"success": False, "message": "获取openid失败"}

    user_id = str(user.get("user_id") or user.get("id") or "").strip()
    if not user_id:
        return {"success": False, "message": "用户未登录"}

    try:
        with psycopg.connect(**DB_CONFIG, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS openid VARCHAR(64) UNIQUE")
                cur.execute(
                    "UPDATE users SET openid = %s, updated_at = NOW() WHERE user_id = %s",
                    (openid, user_id),
                )
                conn.commit()
    except Exception as e:
        return {"success": False, "message": str(e)}

    return {"success": True, "openid": openid}

def _build_wechat_medication_data(medication_name: str, dosage: str, scheduled_dt: datetime, notes: str):
    raw = os.getenv("WECHAT_MEDICATION_TEMPLATE_DATA_JSON", "").strip()
    vars_map = {
        "medication_name": medication_name or "",
        "dosage": dosage or "",
        "time": scheduled_dt.strftime("%H:%M"),
        "date": scheduled_dt.strftime("%Y-%m-%d"),
        "datetime": scheduled_dt.strftime("%Y-%m-%d %H:%M"),
        "notes": notes or "",
    }

    if raw:
        try:
            mapping = json.loads(raw)
            if isinstance(mapping, dict):
                out = {}
                for k, v in mapping.items():
                    try:
                        out[str(k)] = {"value": str(v).format(**vars_map)}
                    except Exception:
                        out[str(k)] = {"value": str(v)}
                return out
        except Exception:
            pass

    return {
        "thing1": {"value": medication_name or ""},
        "thing2": {"value": dosage or ""},
        "time3": {"value": scheduled_dt.strftime("%Y-%m-%d %H:%M")},
        "time8": {"value": scheduled_dt.strftime("%Y-%m-%d %H:%M")},
    }

async def _wechat_subscribe_worker_loop():
    svc = _get_backend_notification_service()
    if not svc:
        return
    try:
        redis_client = svc._get_redis()
    except Exception:
        redis_client = None
    if redis_client is None:
        return

    queue_key = getattr(svc, "queue_key", None) or os.environ.get("WECHAT_SUBSCRIBE_QUEUE_KEY", "wechat:subscribe_queue")
    pop_timeout_sec = int(os.getenv("WECHAT_SUBSCRIBE_WORKER_POP_TIMEOUT_SEC", "5") or "5")
    max_attempts = int(os.getenv("WECHAT_SUBSCRIBE_WORKER_MAX_ATTEMPTS", "3") or "3")
    idle_sleep_sec = float(os.getenv("WECHAT_SUBSCRIBE_WORKER_IDLE_SLEEP_SEC", "0.5") or "0.5")

    while True:
        item = None
        try:
            item = await anyio.to_thread.run_sync(lambda: redis_client.blpop(queue_key, timeout=max(1, pop_timeout_sec)))
        except Exception:
            item = None

        if not item:
            await asyncio.sleep(max(0.1, idle_sleep_sec))
            continue

        payload_raw = None
        try:
            payload_raw = item[1] if isinstance(item, (list, tuple)) and len(item) >= 2 else None
        except Exception:
            payload_raw = None

        if not payload_raw:
            continue

        msg = None
        try:
            msg = json.loads(payload_raw.decode("utf-8") if isinstance(payload_raw, (bytes, bytearray)) else str(payload_raw))
        except Exception:
            msg = None

        if not isinstance(msg, dict):
            continue

        openid = str(msg.get("openid") or "").strip()
        template_id = str(msg.get("template_id") or "").strip()
        data = msg.get("data") if isinstance(msg.get("data"), dict) else {}
        page = str(msg.get("page") or "pages/index/index")
        extra = msg.get("extra") if isinstance(msg.get("extra"), dict) else {}
        attempt = int(msg.get("attempt") or 0)

        ok = False
        try:
            ok = await svc.send_subscribe_message(
                openid=openid,
                template_id=template_id,
                data=data,
                page=page,
            )
        except Exception:
            ok = False

        if not ok and attempt < max_attempts:
            msg["attempt"] = attempt + 1
            try:
                redis_client.rpush(queue_key, json.dumps(msg, ensure_ascii=False))
            except Exception:
                pass
            await asyncio.sleep(min(10.0, 2.0 ** attempt))
            continue

        try:
            message_type = str(extra.get("type") or "").strip()
            if message_type == "medication_reminder":
                reminder_id = extra.get("reminder_id")
                scheduled_time = extra.get("scheduled_time")
                user_id = str(extra.get("user_id") or "").strip()
                if reminder_id and scheduled_time:
                    with psycopg.connect(**DB_CONFIG, row_factory=dict_row) as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                UPDATE reminder_logs
                                SET status = %s, actual_time = NOW(), notes = %s
                                WHERE reminder_id = %s AND scheduled_time = %s
                                """,
                                (
                                    "notified" if ok else "notify_failed",
                                    "wechat_subscribe_queue",
                                    int(reminder_id),
                                    scheduled_time,
                                ),
                            )
                            if cur.rowcount == 0:
                                cur.execute(
                                    """
                                    INSERT INTO reminder_logs (reminder_id, scheduled_time, status, notes, user_id)
                                    VALUES (%s, %s, %s, %s, %s)
                                    """,
                                    (
                                        int(reminder_id),
                                        scheduled_time,
                                        "notified" if ok else "notify_failed",
                                        "wechat_subscribe_queue",
                                        user_id,
                                    ),
                                )
                            conn.commit()
        except Exception:
            pass

async def _wechat_medication_reminder_tick():
    svc = _get_backend_notification_service()
    template_ids = getattr(svc, "template_ids", {}) if svc else {}
    template_id = (template_ids or {}).get("medication_reminder", "")
    if not svc or not template_id:
        return 0

    interval_sec = int(os.getenv("WECHAT_MEDICATION_REMINDER_INTERVAL_SEC", "20") or "20")
    window_sec = int(os.getenv("WECHAT_MEDICATION_REMINDER_WINDOW_SEC", str(max(interval_sec, 60))) or "60")

    try:
        tz_offset_hours = int(os.getenv("APP_TZ_OFFSET_HOURS", os.getenv("TZ_OFFSET_HOURS", "8")) or "8")
    except Exception:
        tz_offset_hours = 8
    local_tz = timezone(timedelta(hours=tz_offset_hours))

    now = datetime.now(timezone.utc).astimezone(local_tz).replace(microsecond=0)
    now_floor = now.replace(second=0)
    today = now_floor.date()

    sent = 0
    scan_lock_token = None
    redis_available = False
    try:
        redis_available = svc._get_redis() is not None
    except Exception:
        redis_available = False
    if redis_available:
        try:
            scan_lock_token = svc.try_acquire_lock(
                "wechat:medication_reminder_scan_lock",
                ttl_sec=max(10, interval_sec + window_sec),
            )
        except Exception:
            scan_lock_token = None
        if scan_lock_token is None:
            return 0

    with psycopg.connect(**DB_CONFIG, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS openid VARCHAR(64) UNIQUE")
                conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    pass
            cur.execute(
                """
                SELECT mr.id AS reminder_id,
                       mr.user_id,
                       u.openid,
                       mr.medication_name,
                       mr.dosage,
                       mr.reminder_times,
                       mr.notes
                FROM medication_reminders mr
                LEFT JOIN users u ON u.user_id = mr.user_id
                WHERE mr.is_active = TRUE
                  AND mr.start_date <= %s
                  AND (mr.end_date IS NULL OR mr.end_date >= %s)
                """,
                (today, today),
            )
            rows = cur.fetchall() or []

            for r in rows:
                openid = (r.get("openid") or "").strip()
                if not openid:
                    continue

                raw_times = r.get("reminder_times")
                times_list = []
                if isinstance(raw_times, list):
                    times_list = raw_times
                elif isinstance(raw_times, str) and raw_times.strip():
                    try:
                        parsed = json.loads(raw_times)
                        if isinstance(parsed, list):
                            times_list = parsed
                        else:
                            times_list = [parsed]
                    except Exception:
                        times_list = [raw_times]

                for t in times_list or []:
                    time_str = str(t).strip()
                    try:
                        tt = datetime.strptime(time_str, "%H:%M").time()
                    except Exception:
                        continue

                    scheduled_dt = datetime.combine(today, tt).replace(tzinfo=local_tz)
                    delta = abs((scheduled_dt - now).total_seconds())
                    if scheduled_dt != now_floor and delta > window_sec:
                        continue
                    if scheduled_dt != now_floor and scheduled_dt < now_floor:
                        continue

                    reminder_id = int(r.get("reminder_id"))
                    cur.execute(
                        "SELECT 1 FROM reminder_logs WHERE reminder_id = %s AND scheduled_time = %s LIMIT 1",
                        (reminder_id, scheduled_dt),
                    )
                    if cur.fetchone():
                        continue

                    token = "local"
                    if redis_available:
                        try:
                            dedupe_key = f"wechat:medication_reminder:dedupe:{reminder_id}:{scheduled_dt.isoformat()}"
                            token = svc.try_acquire_lock(
                                dedupe_key, ttl_sec=24 * 3600
                            )
                        except Exception:
                            token = None
                        if token is None:
                            continue

                    data = _build_wechat_medication_data(
                        str(r.get("medication_name") or ""),
                        str(r.get("dosage") or ""),
                        scheduled_dt,
                        str(r.get("notes") or ""),
                    )
                    cur.execute(
                        """
                        INSERT INTO reminder_logs (reminder_id, scheduled_time, status, notes, user_id)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            reminder_id,
                            scheduled_dt,
                            "queued",
                            "wechat_subscribe_queue",
                            str(r.get("user_id") or ""),
                        ),
                    )
                    conn.commit()

                    enqueued = False
                    try:
                        enqueued = svc.enqueue_subscribe_message(
                            openid=openid,
                            template_id=template_id,
                            data=data,
                            page="pages/medication/medication",
                            dedupe_key="",
                            extra={
                                "type": "medication_reminder",
                                "reminder_id": reminder_id,
                                "scheduled_time": scheduled_dt.isoformat(),
                                "user_id": str(r.get("user_id") or ""),
                            },
                        )
                    except Exception:
                        enqueued = False

                    if not enqueued:
                        ok = False
                        try:
                            ok = await svc.send_subscribe_message(
                                openid=openid,
                                template_id=template_id,
                                data=data,
                                page="pages/medication/medication",
                            )
                        except Exception:
                            ok = False
                        cur.execute(
                            """
                            UPDATE reminder_logs
                            SET status = %s, actual_time = NOW(), notes = %s
                            WHERE reminder_id = %s AND scheduled_time = %s
                            """,
                            (
                                "notified" if ok else "notify_failed",
                                "wechat_subscribe_fallback",
                                reminder_id,
                                scheduled_dt,
                            ),
                        )
                    sent += 1

            conn.commit()

    try:
        if redis_available and scan_lock_token:
            svc.release_lock("wechat:medication_reminder_scan_lock", scan_lock_token)
    except Exception:
        pass

    return sent

async def _wechat_medication_reminder_loop():
    interval_sec = int(os.getenv("WECHAT_MEDICATION_REMINDER_INTERVAL_SEC", "20") or "20")
    while True:
        try:
            await _wechat_medication_reminder_tick()
        except Exception as e:
            logging.error(f"微信用药提醒扫描异常: {e}")
        await asyncio.sleep(max(5, interval_sec))

@app.on_event("startup")
async def _start_wechat_medication_reminder_loop():
    if os.getenv("ENABLE_WECHAT_MEDICATION_REMINDER", "1") != "1":
        return
    try:
        asyncio.create_task(_wechat_medication_reminder_loop())
    except Exception as e:
        logging.warning(f"启动微信用药提醒扫描失败: {e}")

@app.on_event("startup")
async def _start_wechat_subscribe_worker():
    if os.getenv("ENABLE_WECHAT_SUBSCRIBE_WORKER", "1") != "1":
        return
    try:
        asyncio.create_task(_wechat_subscribe_worker_loop())
    except Exception as e:
        logging.warning(f"启动微信订阅消息队列worker失败: {e}")

# 直接挂载到 app 的调试端点，便于排查提醒函数签名
@app.get("/debug/reminder-signature")
async def _debug_reminder_signature_app_level():
    try:
        fn = add_medication_reminder
        import inspect
        return {
            "signature": str(inspect.signature(getattr(fn, 'fn', fn))),
            "module": getattr(fn, "__module__", ""),
            "name": getattr(fn, "__name__", ""),
        }
    except Exception as e:
        return {"error": str(e)}

# === 挂载就诊摘要与健康趋势 API ===
try:
    import visit_summary_api
    app.include_router(visit_summary_api.router)
    logger.info("Visit Summary API router mounted.")
except ImportError as e:
    logger.warning(f"Failed to mount Visit Summary API: {e}")
except Exception as e:
    logger.error(f"Error mounting Visit Summary API: {e}")

# === 本地提醒回退存储（当远端提醒模块不可用时） ===
_REM_DB_PATH = os.path.join(os.path.dirname(__file__), "reminders.json")

def _load_local_reminders() -> dict:
    try:
        if not os.path.exists(_REM_DB_PATH):
            return {"reminders": []}
        with open(_REM_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"reminders": []}

def _save_local_reminders(data: dict) -> None:
    try:
        with open(_REM_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"保存本地提醒失败: {e}")


def _create_local_reminder(
    user_id: str,
    drug_name: str,
    dosage: str,
    frequency: str,
    start_date: str,
    times_list: list,
    end_date: str,
    notes: str,
) -> dict:
    db = _load_local_reminders()
    items = db.get("reminders", [])
    new_id = (max([r.get("id", 0) for r in items]) + 1) if items else 1
    rec = {
        "id": new_id,
        "user_id": user_id,
        "medication_name": drug_name,
        "dosage": dosage,
        "frequency": frequency,
        "reminder_times": times_list,
        "start_date": start_date,
        "end_date": end_date,
        "notes": notes,
        "status": "scheduled",
        "created_at": datetime.utcnow().isoformat()
    }
    items.append(rec)
    db["reminders"] = items
    _save_local_reminders(db)
    return rec

def _mark_local_taken(reminder_id: int, taken_time: str = "") -> bool:
    db = _load_local_reminders()
    items = db.get("reminders", [])
    ok = False
    for r in items:
        if int(r.get("id", 0)) == int(reminder_id):
            r["status"] = "taken"
            r["last_taken_at"] = taken_time or datetime.utcnow().isoformat()
            ok = True
            break
    if ok:
        _save_local_reminders({"reminders": items})
    return ok

def _mark_local_missed(reminder_id: int, scheduled_time: str = "") -> bool:
    db = _load_local_reminders()
    items = db.get("reminders", [])
    ok = False
    for r in items:
        if int(r.get("id", 0)) == int(reminder_id):
            r["status"] = "missed"
            r["last_missed_at"] = scheduled_time or datetime.utcnow().isoformat()
            ok = True
            break
    if ok:
        _save_local_reminders({"reminders": items})
    return ok

def _set_local_reminder_active(reminder_id: int, enabled: bool) -> bool:
    db = _load_local_reminders()
    items = db.get("reminders", [])
    ok = False
    for r in items:
        if int(r.get("id", 0)) == int(reminder_id):
            r["is_active"] = bool(enabled)
            r["updated_at"] = datetime.utcnow().isoformat()
            ok = True
            break
    if ok:
        _save_local_reminders({"reminders": items})
    return ok

@app.get("/api/medication-reminder-plans")
async def list_medication_reminder_plans(active_only: bool = True, user: dict = Depends(get_current_user)):
    uid = str(user.get("id") or user.get("user_id") or user.get("uid"))
    dbm = None
    try:
        dbm = get_db_manager()
    except Exception:
        dbm = None

    if dbm:
        try:
            if active_only:
                rows = dbm.execute_query(
                    """
                    SELECT mr.id, mr.medication_id, mr.medication_name, mr.dosage, mr.frequency,
                           mr.reminder_times, mr.start_date, mr.end_date, mr.notes, mr.is_active,
                           COALESCE(mr.start_date, um.start_date) AS effective_start_date,
                           COALESCE(mr.end_date, um.end_date) AS effective_end_date
                    FROM medication_reminders mr
                    LEFT JOIN user_medications um
                      ON um.user_id = mr.user_id
                     AND um.id = mr.medication_id
                     AND CAST(um.is_deleted AS TEXT) IN ('0','f','false')
                    WHERE mr.user_id = %s
                      AND CAST(mr.is_deleted AS TEXT) IN ('0','f','false')
                      AND CAST(mr.is_active AS TEXT) IN ('1','t','true')
                      AND (
                        COALESCE(mr.end_date, um.end_date) IS NULL
                        OR COALESCE(mr.end_date, um.end_date) >= CURRENT_DATE
                      )
                    ORDER BY mr.created_at DESC
                    """,
                    (uid,),
                )
            else:
                rows = dbm.execute_query(
                    """
                    SELECT mr.id, mr.medication_id, mr.medication_name, mr.dosage, mr.frequency,
                           mr.reminder_times, mr.start_date, mr.end_date, mr.notes, mr.is_active,
                           COALESCE(mr.start_date, um.start_date) AS effective_start_date,
                           COALESCE(mr.end_date, um.end_date) AS effective_end_date
                    FROM medication_reminders mr
                    LEFT JOIN user_medications um
                      ON um.user_id = mr.user_id
                     AND um.id = mr.medication_id
                     AND CAST(um.is_deleted AS TEXT) IN ('0','f','false')
                    WHERE mr.user_id = %s
                      AND CAST(mr.is_deleted AS TEXT) IN ('0','f','false')
                    ORDER BY mr.created_at DESC
                    """,
                    (uid,),
                )
            plans = []
            import re
            for r in rows or []:
                times = []
                raw_times = r.get("reminder_times")
                try:
                    if isinstance(raw_times, str):
                        times = json.loads(raw_times)
                    elif isinstance(raw_times, (list, tuple)):
                        times = list(raw_times)
                except Exception:
                    times = []
                for t in times or []:
                    m = re.search(r"(\d{1,2}):(\d{2})", str(t))
                    if not m:
                        continue
                    hh = int(m.group(1))
                    mm = int(m.group(2))
                    if not (0 <= hh <= 23 and 0 <= mm <= 59):
                        continue
                    plans.append(
                        {
                            "id": r.get("id"),
                            "medicationId": r.get("medication_id"),
                            "medicationName": r.get("medication_name") or "",
                            "dosage": r.get("dosage") or "",
                            "frequency": r.get("frequency") or "",
                            "time": f"{hh:02d}:{mm:02d}",
                            "enabled": str(r.get("is_active") or "").lower()
                            in ("1", "t", "true"),
                            "notes": r.get("notes") or "",
                            "startDate": (
                                str(r.get("effective_start_date"))[:10]
                                if r.get("effective_start_date")
                                else ""
                            ),
                            "endDate": (
                                str(r.get("effective_end_date"))[:10]
                                if r.get("effective_end_date")
                                else None
                            ),
                        }
                    )
            plans.sort(key=lambda x: (x.get("time") or ""))
            return {"success": True, "plans": plans}
        except Exception:
            pass

    try:
        raw = _call_get_medication_reminders(uid, "", active_only)
        data = json.loads(raw) if isinstance(raw, str) else raw
        rows = data.get("reminders") if isinstance(data, dict) else data
        plans = []
        for r in rows or []:
            plans.append(
                {
                    "id": r.get("id"),
                    "medicationId": r.get("medication_id") or r.get("medicationId"),
                    "medicationName": (
                        r.get("medication_name") or r.get("medicationName") or ""
                    ),
                    "dosage": r.get("dosage") or "",
                    "frequency": r.get("frequency") or "",
                    "time": str(r.get("reminder_time") or ""),
                    "enabled": True,
                    "notes": r.get("notes") or "",
                    "startDate": (
                        str(r.get("start_date"))[:10] if r.get("start_date") else ""
                    ),
                    "endDate": (
                        str(r.get("end_date"))[:10] if r.get("end_date") else None
                    ),
                }
            )
        plans.sort(key=lambda x: (x.get("time") or ""))
        return {"success": True, "plans": plans}
    except Exception:
        return {"success": True, "plans": []}


@app.get("/api/debug/db-tables")
async def _debug_db_tables():
    try:
        dbm = get_db_manager()
        _ensure_visit_summaries_table(dbm)
    except Exception:
        return {"error": "no_db_manager"}
    rows = dbm.execute_query(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema='public'
        ORDER BY 1
        """
    )
    names = []
    for r in rows:
        name = r.get("table_name") if isinstance(r, dict) else (r[0] if r else None)
        names.append(name)
    return {"tables": names}


@app.get("/api/debug/db-columns/{table}")
async def _debug_db_columns(table: str):
    try:
        dbm = get_db_manager()
        _ensure_visit_summaries_table(dbm)
    except Exception:
        return {"error": "no_db_manager"}
    rows = dbm.execute_query(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        ORDER BY ordinal_position
        """,
        (table,)
    )
    return {"columns": rows}


@app.post("/api/debug/init-med-tables")
async def _debug_init_med_tables():
    try:
        dbm = get_db_manager()
        _ensure_visit_summaries_table(dbm)
    except Exception:
        return {"error": "no_db_manager"}
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS user_medications (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            drug_name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT,
            start_date DATE,
            end_date DATE,
            notes TEXT,
            is_active SMALLINT DEFAULT 1,
            is_deleted SMALLINT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            reminder_type TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            reminder_time TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS consultations (
            consultation_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            consultation_type TEXT,
            agent_id TEXT,
            status TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            consultation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            files JSONB,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS visit_summaries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            visit_date DATE,
            doctor TEXT,
            hospital TEXT,
            department TEXT,
            chief_complaint TEXT,
            symptoms TEXT,
            examination TEXT,
            diagnosis TEXT,
            treatment TEXT,
            prescription TEXT,
            follow_up TEXT,
            notes TEXT,
            files JSONB,
            tests JSONB,
            is_deleted SMALLINT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_visit_summaries_user_date ON visit_summaries(user_id, visit_date)",
        "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS tests JSONB",
        "ALTER TABLE health_records ADD COLUMN IF NOT EXISTS file_hash TEXT",
        "ALTER TABLE medication_reminders ADD COLUMN IF NOT EXISTS reminder_id INTEGER",
        "ALTER TABLE medication_reminders ADD COLUMN IF NOT EXISTS medication_id INTEGER",
        "CREATE INDEX IF NOT EXISTS idx_medication_reminders_user ON medication_reminders(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_medication_reminders_active ON medication_reminders(is_active)",
        "CREATE INDEX IF NOT EXISTS idx_medication_reminders_created ON medication_reminders(created_at)",
        "CREATE INDEX IF NOT EXISTS idx_medication_reminders_user_created_desc ON medication_reminders(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_medication_reminders_user_medication ON medication_reminders(user_id, medication_id)",
        "ALTER TABLE reminder_logs ADD COLUMN IF NOT EXISTS user_id TEXT",
        "ALTER TABLE reminder_logs ADD COLUMN IF NOT EXISTS completion_time TIMESTAMPTZ",
        "CREATE INDEX IF NOT EXISTS idx_reminder_logs_reminder ON reminder_logs(reminder_id)",
        "CREATE INDEX IF NOT EXISTS idx_reminder_logs_reminder_scheduled ON reminder_logs(reminder_id, scheduled_time)",
        "CREATE INDEX IF NOT EXISTS idx_reminder_logs_user_scheduled ON reminder_logs(user_id, scheduled_time)",
        "CREATE INDEX IF NOT EXISTS idx_reminder_logs_status ON reminder_logs(status)",
        "CREATE INDEX IF NOT EXISTS idx_reminder_logs_created ON reminder_logs(created_at)",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS question TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS answer TEXT",
        "ALTER TABLE consultations ALTER COLUMN answer SET DEFAULT ''",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS title TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS consultation_type TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS agent_id TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS status TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS session_id TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS tags JSONB",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS files JSONB",
    ]
    for s in stmts:
        dbm.execute_update(s)
    return {"ok": True}

# === 新增：健康咨询 DB 端点 ===

def _ensure_consultation_tables(dbm):
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS consultations (
            consultation_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            consultation_type TEXT,
            agent_id TEXT,
            status TEXT,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now(),
            question TEXT,
            answer TEXT DEFAULT '',
            session_id TEXT,
            tags JSONB
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            consultation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            files JSONB,
            created_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_consultations_user ON consultations(user_id, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_cid ON chat_messages(consultation_id, created_at ASC)",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS title TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS consultation_type TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS agent_id TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS status TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS question TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS answer TEXT",
        "ALTER TABLE consultations ALTER COLUMN answer SET DEFAULT ''",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS session_id TEXT",
        "ALTER TABLE consultations ADD COLUMN IF NOT EXISTS tags JSONB",
        "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS files JSONB"
    ]
    for s in stmts:
        try:
            dbm.execute_update(s)
        except Exception as e:
            logging.warning(f"DB init warning: {e}")

@app.get("/api/consultations")
@app.get("/consultations")
async def list_consultations(user: dict = Depends(get_current_user)):
    uid = _get_user_id(user)
    try:
        dbm = get_db_manager()
        _ensure_consultation_tables(dbm)
        rows = dbm.execute_query(
            """
            SELECT consultation_id, title, consultation_type, created_at, question, session_id, tags
            FROM consultations
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (uid,)
        )
        items = []
        for r in rows:
            # 兼容前端字段 naming
            items.append({
                "id": r.get("consultation_id"),
                "title": r.get("title") or "未命名咨询",
                "type": r.get("consultation_type") or "general",
                "userId": uid,
                "createdAt": str(r.get("created_at")),
                "question": r.get("question"),
                "sessionId": r.get("session_id"),
                "tags": r.get("tags") if isinstance(r.get("tags"), list) else [],
                # 列表接口通常不需要返回所有消息
                "messages": []
            })
        return items
    except Exception as e:
        logging.error(f"List consultations failed: {e}")
        return []

@app.post("/api/consultations")
@app.post("/consultations")
async def create_consultation(request: Request, user: dict = Depends(get_current_user)):
    payload = await request.json()
    uid = _get_user_id(user)
    title = payload.get("title")
    ctype = payload.get("type", "general")
    question = payload.get("question", "")
    session_id = payload.get("session_id", "")
    tags = payload.get("tags", [])

    # 如果没有提供 title，用 question 截取
    if not title and question:
        title = question[:20] + "..." if len(question) > 20 else question
    if not title:
        title = "新咨询"

    cid = payload.get("consultation_id") or payload.get("id") or uuid.uuid4().hex
    now = datetime.utcnow().isoformat()

    try:
        dbm = get_db_manager()
        _ensure_consultation_tables(dbm)

        # 检查是否存在
        exists = dbm.execute_query(
            "SELECT consultation_id FROM consultations WHERE consultation_id=%s",
            (cid,),
        )
        if not exists:
            dbm.execute_update(
                """
                INSERT INTO consultations (
                    consultation_id, user_id, title, consultation_type, created_at, updated_at,
                    question, session_id, tags
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (cid, uid, title, ctype, now, now, question, session_id, json.dumps(tags)),
            )

        return {
            "id": cid,
            "title": title,
            "type": ctype,
            "userId": uid,
            "createdAt": now,
            "messages": []
        }
    except Exception as e:
        logging.error(f"Create consultation failed: {e}")
        return {"error": str(e)}


@app.get("/api/consultations/{cid}/messages")
@app.get("/consultations/{cid}/messages")
async def get_consultation_messages_legacy(cid: str, user: dict = Depends(get_current_user)):
    uid = _get_user_id(user)
    try:
        dbm = get_db_manager()
        _ensure_consultation_tables(dbm)

        # 验证归属
        c_rows = dbm.execute_query(
            """
            SELECT consultation_id
            FROM consultations
            WHERE consultation_id=%s AND user_id=%s
            """,
            (cid, uid),
        )
        if not c_rows:
            # 也许是刚创建还没同步？或者无权访问
            return {"messages": []}

        rows = dbm.execute_query(
            """
            SELECT id, role, content, files, created_at
            FROM chat_messages
            WHERE consultation_id=%s
            ORDER BY created_at ASC
            """,
            (cid,)
        )
        messages = []
        for r in rows:
            files = r.get("files")
            if isinstance(files, str):
                try:
                    files = json.loads(files)
                except Exception:
                    files = []

            messages.append({
                "id": r.get("id"),
                "role": r.get("role"),
                "content": r.get("content"),
                "files": files or [],
                "created_at": str(r.get("created_at"))
            })
        return {"success": True, "messages": messages}
    except Exception as e:
        logging.error(f"Get messages failed: {e}")
        return {"success": False, "messages": [], "error": str(e)}

@app.post("/api/consultations/message")
async def save_consultation_message_endpoint(request: Request, user: dict = Depends(get_current_user)):
    """保存单条消息 (兼容 api.js saveConsultationMessage)"""
    body = await request.json()
    uid = _get_user_id(user)
    cid = body.get("consultation_id")
    role = body.get("role", "user")
    content = body.get("content", "")
    files = body.get("files", [])

    if not cid:
        return {"error": "consultation_id required"}

    try:
        dbm = get_db_manager()
        _ensure_consultation_tables(dbm)

        # 自动创建会话如果不存在 (容错)
        exists = dbm.execute_query(
            "SELECT consultation_id FROM consultations WHERE consultation_id=%s",
            (cid,),
        )
        if not exists:
            now = datetime.utcnow().isoformat()
            dbm.execute_update(
                """
                INSERT INTO consultations (
                    consultation_id, user_id, title, consultation_type, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (cid, uid, "自动保存会话", "general", now, now),
            )

        msg_id = uuid.uuid4().hex
        dbm.execute_update(
            """
            INSERT INTO chat_messages (id, consultation_id, role, content, files, created_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, now())
            """,
            (msg_id, cid, role, content, json.dumps(files))
        )
        return {"success": True, "id": msg_id}
    except Exception as e:
        logging.error(f"Save message failed: {e}")
        return {"error": str(e)}


@app.post("/consultations/{cid}/messages")
async def send_consultation_message_legacy(cid: str, request: Request, user: dict = Depends(get_current_user)):
    """兼容旧接口"""
    body = await request.json()
    body["consultation_id"] = cid
    # 复用逻辑
    # ... 这里为了简单直接调用上面的逻辑比较麻烦，重新写一下
    uid = _get_user_id(user)
    content = body.get("content", "")
    files = body.get("files", [])

    try:
        dbm = get_db_manager()
        _ensure_consultation_tables(dbm)

        # 确保会话存在
        exists = dbm.execute_query(
            "SELECT consultation_id FROM consultations WHERE consultation_id=%s",
            (cid,),
        )
        if not exists:
            now = datetime.utcnow().isoformat()
            dbm.execute_update(
                """
                INSERT INTO consultations (
                    consultation_id, user_id, title, consultation_type, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (cid, uid, "快速咨询", "general", now, now),
            )

        # User message
        user_msg_id = uuid.uuid4().hex
        dbm.execute_update(
            """
            INSERT INTO chat_messages (id, consultation_id, role, content, files, created_at)
            VALUES (%s, %s, 'user', %s, %s::jsonb, now())
            """,
            (user_msg_id, cid, content, json.dumps(files)),
        )

        # AI reply (placeholder)
        ai_text = f"收到: {content[:20]}... (请使用流式接口获取完整回复)"
        ai_msg_id = uuid.uuid4().hex
        dbm.execute_update(
            """
            INSERT INTO chat_messages (id, consultation_id, role, content, created_at)
            VALUES (%s, %s, 'ai', %s, now())
            """,
            (ai_msg_id, cid, ai_text),
        )

        return {
            "content": ai_text,
            "suggestions": []
        }
    except Exception as e:
        return {"error": str(e)}


SUMMARIES_DB_PATH = os.path.join(os.path.dirname(__file__), "visit_summaries.json")


def _ensure_visit_summaries_table(dbm):
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS visit_summaries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            visit_date DATE,
            doctor TEXT,
            hospital TEXT,
            department TEXT,
            chief_complaint TEXT,
            symptoms TEXT,
            examination TEXT,
            diagnosis TEXT,
            treatment TEXT,
            prescription TEXT,
            follow_up TEXT,
            notes TEXT,
            files JSONB,
            tests JSONB,
            is_deleted SMALLINT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT now(),
            updated_at TIMESTAMPTZ DEFAULT now()
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_visit_summaries_user_date
        ON visit_summaries(user_id, visit_date)
        """,
        "ALTER TABLE visit_summaries ADD COLUMN IF NOT EXISTS tests JSONB",
    ]
    for s in stmts:
        try:
            dbm.execute_update(s)
        except Exception:
            pass

def _normalize_date(val) -> str:
    """标准化日期格式，返回 YYYY-MM-DD 字符串"""
    if not val:
        return ""
    try:
        # 允许完整ISO日期时间字符串，提取日期部分
        s = str(val)
        if len(s) >= 10:
            # 提取前10个字符作为日期部分 (YYYY-MM-DD)
            date_part = s[:10]
            # 验证格式是否正确
            date.fromisoformat(date_part)
            return date_part
        return ""
    except Exception:
        return ""

def _load_user_summaries(user_id: str) -> list:
    try:
        if not os.path.exists(SUMMARIES_DB_PATH):
            return []
        with open(SUMMARIES_DB_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            # 旧版本：文件内容为列表，视为所有用户共享
            return data
        return data.get(user_id, [])
    except Exception:
        return []

def _save_user_summaries(user_id: str, items: list) -> None:
    try:
        db = {}
        if os.path.exists(SUMMARIES_DB_PATH):
            try:
                with open(SUMMARIES_DB_PATH, 'r', encoding='utf-8') as f:
                    db = json.load(f)
            except Exception:
                db = {}
        if isinstance(db, list):
            db = {user_id: items}
        else:
            db[user_id] = items
        with open(SUMMARIES_DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"保存用户就诊摘要失败: {e}")


@app.get("/summaries")
async def list_summaries(
    user: dict = Depends(get_current_user),
    startDate: str | None = None,
    endDate: str | None = None,
    view: str | None = None,
):
    uid = _get_user_id(user)
    sd = _normalize_date(startDate) if startDate else ""
    ed = _normalize_date(endDate) if endDate else ""
    items: list = []
    try:
        dbm = get_db_manager()
        _ensure_visit_summaries_table(dbm)
        params = [uid]
        where = "user_id = %s AND is_deleted = 0"
        if sd:
            where += " AND visit_date >= %s"
            params.append(sd)
        if ed:
            where += " AND visit_date <= %s"
            params.append(ed)
        query = f"""
            SELECT
                id, user_id, title, visit_date, doctor, hospital, department,
                chief_complaint, symptoms, examination, diagnosis, treatment,
                prescription, follow_up, notes, files, tests, created_at, updated_at
            FROM visit_summaries
            WHERE {where}
            ORDER BY visit_date DESC NULLS LAST
        """
        rows = dbm.execute_query(
            query,
            tuple(params)
        )
        for r in rows:
            fv = r.get("files") if isinstance(r, dict) else None
            if isinstance(fv, str):
                try:
                    fv = json.loads(fv)
                except Exception:
                    fv = []
            tv = r.get("tests") if isinstance(r, dict) else None
            if isinstance(tv, str):
                try:
                    tv = json.loads(tv)
                except Exception:
                    tv = []
            visit_date_val = r.get("visit_date")
            visitDateStr = str(visit_date_val)[:10] if visit_date_val else ""
            doctorStr = r.get("doctor") or ""
            hospitalStr = r.get("hospital") or ""
            titleStr = r.get("title") or ""
            if not titleStr:
                base = doctorStr or hospitalStr or "就诊摘要"
                titleStr = f"{base} - {visitDateStr}" if visitDateStr else base
            elif "未填医生" in titleStr and doctorStr:
                titleStr = f"{doctorStr} - {visitDateStr}" if visitDateStr else doctorStr
            join_tests = ""
            if tv:
                parts = []
                for x in tv or []:
                    if not isinstance(x, dict):
                        continue
                    name = str(x.get("name") or x.get("test_name") or "").strip()
                    value = str(x.get("value") or "").strip()
                    unit = str(x.get("unit") or "").strip()
                    status = str(x.get("status") or "").strip()
                    s = " ".join([p for p in [name, value + unit, status] if p])
                    if s:
                        parts.append(s)
                join_tests = "\n".join(parts)
            exam_text = r.get("examination") or join_tests
            items.append({
                "id": str(r.get("id")),
                "title": titleStr,
                "visitDate": visitDateStr,
                "doctor": doctorStr,
                "hospital": hospitalStr,
                "department": r.get("department") or "",
                "chiefComplaint": r.get("chief_complaint") or "",
                "symptoms": r.get("symptoms") or "",
                "examination": exam_text,
                "tests": tv or [],
                "diagnosis": r.get("diagnosis") or "",
                "treatment": r.get("treatment") or "",
                "prescription": r.get("prescription") or "",
                "followUp": r.get("follow_up") or "",
                "notes": r.get("notes") or "",
                "files": fv or [],
                "createdAt": str(r.get("created_at") or ""),
                "updatedAt": str(r.get("updated_at") or ""),
                "userId": uid,
            })
    except Exception:
        items = []
    json_items = _load_user_summaries(uid)
    existing = set([str(it.get("id")) for it in items])

    def _sig(obj: dict) -> str:
        return "|".join([
            str(obj.get("visitDate") or ""),
            str(obj.get("doctor") or ""),
            str(obj.get("hospital") or ""),
            str(obj.get("department") or ""),
            str(obj.get("diagnosis") or ""),
            str(obj.get("chiefComplaint") or "")
        ])
    existing_sig = set([_sig(it) for it in items])
    for it in json_items:
        sid = str(it.get("id"))
        sig = _sig(it)
        if sid not in existing and sig not in existing_sig:
            items.append(it)
    try:
        items.sort(key=lambda x: x.get("visitDate", ""), reverse=True)
    except Exception:
        pass
    v = str(view or "").strip().lower()
    if v == "doctor":
        agg = {}
        for it in items:
            k = it.get("doctor") or ""
            if k not in agg:
                agg[k] = {
                    "doctor": k,
                    "count": 0,
                    "lastVisit": it.get("visitDate"),
                    "items": [],
                }
            agg[k]["count"] += 1
            if (it.get("visitDate") or "") > (agg[k]["lastVisit"] or ""):
                agg[k]["lastVisit"] = it.get("visitDate")
            agg[k]["items"].append(it)
        res = list(agg.values())
        try:
            res.sort(key=lambda x: x.get("lastVisit") or "", reverse=True)
        except Exception:
            pass
        return res
    if v == "hospital":
        agg = {}
        for it in items:
            k = it.get("hospital") or ""
            if k not in agg:
                agg[k] = {
                    "hospital": k,
                    "count": 0,
                    "lastVisit": it.get("visitDate"),
                    "items": [],
                }
            agg[k]["count"] += 1
            if (it.get("visitDate") or "") > (agg[k]["lastVisit"] or ""):
                agg[k]["lastVisit"] = it.get("visitDate")
            agg[k]["items"].append(it)
        res = list(agg.values())
        try:
            res.sort(key=lambda x: x.get("lastVisit") or "", reverse=True)
        except Exception:
            pass
        return res
    return items


@app.post("/summaries")
async def create_summary(request: Request, user: dict = Depends(get_current_user)):
    payload = await request.json()
    uid = _get_user_id(user)
    new_id = uuid.uuid4().hex
    vd = _normalize_date(payload.get("visitDate"))
    files = payload.get("files") or []
    tests = payload.get("tests") or []
    try:
        dbm = get_db_manager()
        dbm.execute_update(
            """
            INSERT INTO visit_summaries (
                id, user_id, title, visit_date, doctor, hospital, department,
                chief_complaint, symptoms, examination, diagnosis, treatment,
                prescription, follow_up, notes, files, tests, is_deleted, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s::jsonb, %s::jsonb, 0, now(), now()
            )
            """,
            (
                new_id,
                uid,
                payload.get("title") or "就诊摘要",
                vd,
                payload.get("doctor") or "",
                payload.get("hospital") or "",
                payload.get("department") or "",
                payload.get("chiefComplaint") or "",
                payload.get("symptoms") or "",
                payload.get("examination") or "",
                payload.get("diagnosis") or "",
                payload.get("treatment") or "",
                payload.get("prescription") or "",
                payload.get("followUp") or "",
                payload.get("notes") or "",
                json.dumps(files),
                json.dumps(tests),
            )
        )
    except Exception:
        pass
    items = _load_user_summaries(uid)
    summary = {
        "id": new_id,
        "title": payload.get("title") or "就诊摘要",
        "visitDate": vd,
        "doctor": payload.get("doctor") or "",
        "hospital": payload.get("hospital") or "",
        "department": payload.get("department") or "",
        "chiefComplaint": payload.get("chiefComplaint") or "",
        "symptoms": payload.get("symptoms") or "",
        "examination": payload.get("examination") or "",
        "diagnosis": payload.get("diagnosis") or "",
        "treatment": payload.get("treatment") or "",
        "prescription": payload.get("prescription") or "",
        "followUp": payload.get("followUp") or "",
        "notes": payload.get("notes") or "",
        "files": files,
        "tests": tests,
        "createdAt": datetime.utcnow().isoformat(),
        "updatedAt": datetime.utcnow().isoformat(),
        "userId": uid,
    }
    items.append(summary)
    _save_user_summaries(uid, items)
    return summary


@app.put("/summaries/{sid}")
async def update_summary(sid: str, request: Request, user: dict = Depends(get_current_user)):
    payload = await request.json()
    uid = _get_user_id(user)
    vd = (
        _normalize_date(payload.get("visitDate")) if payload.get("visitDate") else None
    )
    files = payload.get("files") if "files" in payload else None
    tests = payload.get("tests") if "tests" in payload else None
    try:
        dbm = get_db_manager()
        sets = [
            "title = %s",
            "doctor = %s",
            "hospital = %s",
            "department = %s",
            "chief_complaint = %s",
            "symptoms = %s",
            "examination = %s",
            "diagnosis = %s",
            "treatment = %s",
            "prescription = %s",
            "follow_up = %s",
            "notes = %s",
            "updated_at = now()",
        ]
        params = [
            payload.get("title"),
            payload.get("doctor"),
            payload.get("hospital"),
            payload.get("department"),
            payload.get("chiefComplaint"),
            payload.get("symptoms"),
            payload.get("examination"),
            payload.get("diagnosis"),
            payload.get("treatment"),
            payload.get("prescription"),
            payload.get("followUp"),
            payload.get("notes"),
        ]
        if vd is not None:
            sets.insert(0, "visit_date = %s")
            params.insert(0, vd)
        if files is not None:
            sets.append("files = %s::jsonb")
            params.append(json.dumps(files))
        if tests is not None:
            sets.append("tests = %s::jsonb")
            params.append(json.dumps(tests))
        sql = (
            f"UPDATE visit_summaries SET {', '.join(sets)} "
            "WHERE id = %s AND user_id = %s"
        )
        params.extend([sid, uid])
        dbm.execute_update(sql, tuple(params))
    except Exception:
        pass
    items = _load_user_summaries(uid)
    updated = None
    for i, s in enumerate(items):
        if str(s.get("id")) == str(sid):
            s.update({
                "title": payload.get("title", s.get("title")),
                "visitDate": _normalize_date(payload.get("visitDate", s.get("visitDate"))),
                "doctor": payload.get("doctor", s.get("doctor")),
                "hospital": payload.get("hospital", s.get("hospital")),
                "department": payload.get("department", s.get("department")),
                "chiefComplaint": payload.get("chiefComplaint", s.get("chiefComplaint")),
                "symptoms": payload.get("symptoms", s.get("symptoms")),
                "examination": payload.get("examination", s.get("examination")),
                "diagnosis": payload.get("diagnosis", s.get("diagnosis")),
                "treatment": payload.get("treatment", s.get("treatment")),
                "prescription": payload.get("prescription", s.get("prescription")),
                "followUp": payload.get("followUp", s.get("followUp")),
                "notes": payload.get("notes", s.get("notes")),
                "files": payload.get("files", s.get("files")),
                "tests": payload.get("tests", s.get("tests")),
                "updatedAt": datetime.utcnow().isoformat(),
            })
            s["userId"] = uid
            updated = s
            items[i] = s
            break
    if updated is None:
        return {"success": False, "message": "摘要不存在"}
    _save_user_summaries(uid, items)
    return updated


@app.delete("/summaries/{sid}")
async def delete_summary(sid: str, user: dict = Depends(get_current_user)):
    uid = _get_user_id(user)
    try:
        dbm = get_db_manager()
        dbm.execute_update(
            """
            UPDATE visit_summaries
            SET is_deleted = 1, updated_at = now()
            WHERE id = %s AND user_id = %s
            """,
            (sid, uid)
        )
    except Exception:
        pass
    items = _load_user_summaries(uid)
    new_items = [s for s in items if str(s.get("id")) != str(sid)]
    _save_user_summaries(uid, new_items)
    return {"success": True, "deleted": str(sid)}


@app.post("/summaries/generate")
async def generate_ai_summary(request: Request, user: dict = Depends(get_current_user)):
    payload = await request.json()
    visit_date = _normalize_date(payload.get("visitDate"))
    doctor = payload.get("doctor") or ""
    hospital = payload.get("hospital") or ""
    files = payload.get("files") or []
    title = payload.get("title") or f"{doctor or '未填医生'} - {visit_date}"

    try:
        import importlib
        backend_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "backend")
        )
        if backend_dir not in sys.path:
            sys.path.append(backend_dir)
        health_api = importlib.import_module("health_records_api")
        doc_tool = importlib.import_module(
            "VisitSummaryGenerator.mcpserver.document_tool"
        )

        def _to_doc_type(rt: str | None) -> str:
            if not rt:
                return "其他"
            v = str(rt)
            if v in ("medical_report", "lab_result", "examination"):
                return "检验报告"
            if v in ("prescription",):
                return "处方单"
            if v in ("symptom", "diagnosis"):
                return "门诊记录"
            if v in ("imaging", "radiology"):
                return "影像报告"
            return "其他"

        sd = None
        ed = None
        if visit_date:
            try:
                sd = date.fromisoformat(visit_date)
                ed = date.fromisoformat(visit_date)
            except Exception:
                sd = None
                ed = None
        user_id = _get_user_id(user)
        records = await health_api.get_health_records(
            skip=0,
            limit=200,
            record_type=None,
            importance=None,
            search=None,
            start_date=sd,
            end_date=ed,
            user_id=user_id,
        )
        documents = []
        for r in records:
            get = (lambda k: getattr(r, k, None)) if hasattr(r, "dict") else (lambda k: r.get(k))
            back_type = get("record_type")
            tval = back_type.value if hasattr(back_type, "value") else back_type
            doc_type = _to_doc_type(tval)
            content_src = get("summary") or get("content") or ""
            if isinstance(content_src, dict):
                content_text = json.dumps(content_src, ensure_ascii=False)
            else:
                content_text = str(content_src or "")
            documents.append({"type": doc_type, "content": content_text})

        summary_type = str(payload.get("summaryType") or "comprehensive")
        gen = doc_tool.generate_visit_summary(documents, summary_type)
        if isinstance(gen, dict) and gen.get("success"):
            data = gen.get("data") or {}
            content = data.get("content") or {}
            patient = content.get("patient_info") or {}
            visit = content.get("visit_overview") or {}
            diag = content.get("diagnosis_treatment") or {}
            meds = content.get("medications") or []
            tests = content.get("test_results") or []
            follow = content.get("follow_up") or {}

            def _join_tests(ts: list) -> str:
                parts = []
                for it in ts:
                    if isinstance(it, dict):
                        name = str(it.get("test_name") or "").strip()
                        val = str(it.get("value") or "").strip()
                        unit = str(it.get("unit") or "").strip()
                        status = str(it.get("status") or "").strip()
                        s = " ".join(
                            [p for p in [name, val + (unit or ""), status] if p]
                        )
                        if s:
                            parts.append(s)
                return "\n".join(parts)

            def _join_meds(ms: list) -> str:
                parts = []
                for it in ms:
                    if isinstance(it, dict):
                        name = str(it.get("name") or "").strip()
                        dosage = str(it.get("dosage") or "").strip()
                        usage = str(it.get("usage") or "").strip()
                        duration = str(it.get("duration") or "").strip()
                        s = " ".join([p for p in [name, dosage, usage, duration] if p])
                        if s:
                            parts.append(s)
                return "\n".join(parts)

            tests_json = []
            for x in tests:
                if isinstance(x, dict):
                    tests_json.append(
                        {
                            "name": str(x.get("test_name") or x.get("name") or ""),
                            "value": str(x.get("value") or ""),
                            "unit": str(x.get("unit") or ""),
                            "status": str(x.get("status") or ""),
                            "date": visit_date,
                        }
                    )
            generated = {
                "id": uuid.uuid4().hex,
                "title": title,
                "visitDate": visit_date,
                "doctor": doctor or str(patient.get("doctor") or ""),
                "hospital": hospital or str(patient.get("hospital") or ""),
                "department": payload.get("department") or "",
                "chiefComplaint": str(visit.get("chief_complaint") or ""),
                "symptoms": str(visit.get("present_illness") or ""),
                "examination": _join_tests(tests),
                "tests": tests_json,
                "diagnosis": "；".join(diag.get("diagnosis") or []),
                "treatment": str(diag.get("treatment_plan") or ""),
                "prescription": _join_meds(meds),
                "followUp": str(follow.get("plan") or ""),
                "notes": payload.get("notes") or "",
                "files": files,
                "createdAt": datetime.utcnow().isoformat(),
                "updatedAt": datetime.utcnow().isoformat(),
                "userId": user_id,
            }
        else:
            generated = {
                "id": uuid.uuid4().hex,
                "title": title,
                "visitDate": visit_date,
                "doctor": doctor,
                "hospital": hospital,
                "department": payload.get("department") or "",
                "chiefComplaint": payload.get("chiefComplaint") or "",
                "symptoms": payload.get("symptoms") or "",
                "examination": payload.get("examination") or "",
                "tests": payload.get("tests") or [],
                "diagnosis": payload.get("diagnosis") or "",
                "treatment": payload.get("treatment") or "",
                "prescription": payload.get("prescription") or "",
                "followUp": payload.get("followUp") or "",
                "notes": payload.get("notes") or "",
                "files": files,
                "createdAt": datetime.utcnow().isoformat(),
                "updatedAt": datetime.utcnow().isoformat(),
                "userId": str(user.get("id")),
            }
    except Exception:
        generated = {
            "id": uuid.uuid4().hex,
            "title": title,
            "visitDate": visit_date,
            "doctor": doctor,
            "hospital": hospital,
            "department": payload.get("department") or "",
            "chiefComplaint": payload.get("chiefComplaint") or "",
            "symptoms": payload.get("symptoms") or "",
            "examination": payload.get("examination") or "",
            "tests": payload.get("tests") or [],
            "diagnosis": payload.get("diagnosis") or "",
            "treatment": payload.get("treatment") or "",
            "prescription": payload.get("prescription") or "",
            "followUp": payload.get("followUp") or "",
            "notes": payload.get("notes") or "",
            "files": files,
            "createdAt": datetime.utcnow().isoformat(),
            "updatedAt": datetime.utcnow().isoformat(),
            "userId": str(user.get("id")),
        }

    try:
        dbm = get_db_manager()
        _ensure_visit_summaries_table(dbm)
        dbm.execute_update(
            """
            INSERT INTO visit_summaries (
                id, user_id, title, visit_date, doctor, hospital, department,
                chief_complaint, symptoms, examination, diagnosis, treatment,
                prescription, follow_up, notes, files, tests, is_deleted, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s::jsonb, %s::jsonb, 0, now(), now()
            )
            """,
            (
                generated.get("id"),
                _get_user_id(user),
                generated.get("title") or "就诊摘要",
                _normalize_date(generated.get("visitDate")),
                generated.get("doctor") or "",
                generated.get("hospital") or "",
                generated.get("department") or "",
                generated.get("chiefComplaint") or "",
                generated.get("symptoms") or "",
                generated.get("examination") or "",
                generated.get("diagnosis") or "",
                generated.get("treatment") or "",
                generated.get("prescription") or "",
                generated.get("followUp") or "",
                generated.get("notes") or "",
                json.dumps(generated.get("files") or []),
                json.dumps(generated.get("tests") or []),
            ),
        )
    except Exception:
        pass
    try:
        items = _load_user_summaries(_get_user_id(user))
        items.append(generated)
        _save_user_summaries(_get_user_id(user), items)
    except Exception:
        pass
    return generated


@app.api_route("/ping", methods=["GET", "POST"])
async def ping():
    return "Pong"

@app.post("/api/audio/transcribe")
async def transcribe_audio_with_qwen(
    file: UploadFile = File(...),
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    del current_user
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="音频文件为空")

    model_name = (os.getenv("QWEN_ASR_MODEL") or "qwen-audio-asr").strip()
    api_key = (
        os.getenv("QWEN_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("ALIYUN_DASHSCOPE_API_KEY")
    )
    if not api_key:
        raise HTTPException(status_code=500, detail="未配置QWEN_API_KEY或DASHSCOPE_API_KEY")

    api_base = (os.getenv("QWEN_ASR_API_BASE") or "https://dashscope.aliyuncs.com/compatible/v1").rstrip("/")
    endpoint = f"{api_base}/audio/transcriptions"
    mime_type = (file.content_type or "audio/mpeg").strip() or "audio/mpeg"
    file_name = (file.filename or "audio.mp3").strip() or "audio.mp3"
    language = (os.getenv("QWEN_ASR_LANGUAGE") or "").strip()

    data = {"model": model_name}
    if language:
        data["language"] = language

    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = httpx.Timeout(connect=15.0, read=120.0, write=120.0, pool=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                endpoint,
                data=data,
                files={"file": (file_name, file_bytes, mime_type)},
                headers=headers,
            )
    except Exception as e:
        logger.error(f"语音识别请求失败: {e}")
        raise HTTPException(status_code=502, detail="语音识别服务不可用")

    payload: Dict[str, Any]
    try:
        payload = resp.json()
    except Exception:
        payload = {"raw": (resp.text or "")[:3000]}

    if resp.status_code < 200 or resp.status_code >= 300:
        detail = payload.get("error") if isinstance(payload, dict) else payload
        raise HTTPException(status_code=502, detail=f"语音识别失败: {detail}")

    text = ""
    if isinstance(payload, dict):
        text = (
            str(payload.get("text") or "").strip()
            or str((payload.get("result") or {}).get("text") or "").strip()
            or str((payload.get("output") or {}).get("text") or "").strip()
            or str(
                ((payload.get("output") or {}).get("choices") or [{}])[0]
                .get("message", {})
                .get("content", "")
            ).strip()
        )
    if not text:
        raise HTTPException(status_code=502, detail="语音识别返回为空")

    return {"text": text, "model": model_name}

# 智能路由接口 - 统一API入口

@app.post("/smart_chat")
async def smart_chat(
    request: Request,
    current_user: Optional[Dict[str, Any]] = Depends(get_current_user_optional),
):
    """
    智能路由接口：根据用户输入自动选择合适的智能体
    """
    try:
        # Robust body decoding: try UTF-8 then fallback to GBK
        raw = await request.body()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("gbk")
            except Exception:
                # last resort, replace invalid bytes to avoid 500
                text = raw.decode("utf-8", errors="replace")
        data = json.loads(text) if text else {}
        user_message = data.get('message', '')

        if not user_message:
            return {"error": "消息内容不能为空"}

        # 智能路由逻辑：根据关键词判断应该调用哪个智能体
        agent_mapping = {
            "健康档案管理员": ["档案", "病史", "记录", "健康记录", "医疗记录", "病历"],
            "健康顾问": ["建议", "咨询", "症状", "诊断", "治疗", "健康问题", "医疗建议"],
            "用药提醒助手": ["用药", "药物", "提醒", "服药", "药品", "medication"],
            "就诊摘要生成": ["摘要", "总结", "就诊", "报告", "文档", "解析"]
        }

        # 找到最匹配的智能体
        selected_agent = None
        max_matches = 0

        for agent_name, keywords in agent_mapping.items():
            matches = sum(1 for keyword in keywords if keyword in user_message)
            if matches > max_matches:
                max_matches = matches
                selected_agent = agent_name

        # 如果没有明确匹配，默认使用健康顾问
        if not selected_agent:
            selected_agent = "健康顾问"

        # 创建会话并发送消息
        conversation = agent_server.manager.create_conversation()

        # 构造消息
        from A2AServer.common.A2Atypes import Message, TextPart
        message = Message(
            role="user",
            parts=[TextPart(text=user_message)],
            metadata={
                'conversation_id': conversation.conversation_id,
                'message_id': str(uuid.uuid4()),
                'selected_agent': selected_agent
            }
        )

        # 注入当前用户ID（优先使用登录用户，其次环境变量兜底）
        try:
            user_id = None
            if current_user and isinstance(current_user, dict):
                user_id = str(
                    current_user.get("user_id") or current_user.get("id") or ""
                ).strip()
            if not user_id:
                env_uid = (
                    os.getenv("A2A_CURRENT_USER_ID")
                    or os.getenv("USER_ID")
                    or os.getenv("FRONTEND_USER_ID")
                )
                user_id = str(env_uid or "").strip()
            if user_id:
                message.metadata['user_id'] = user_id
                os.environ['A2A_CURRENT_USER_ID'] = user_id
                os.environ['USER_ID'] = user_id
                if 'DEFAULT_USER_ID' in os.environ:
                    try:
                        os.environ.pop('DEFAULT_USER_ID', None)
                    except Exception:
                        pass
        except Exception:
            pass

        # 发送消息到智能体
        try:
            message = agent_server.manager.sanitize_message(message)
        except Exception as e:
            import traceback
            logging.error(f"[smart_chat] sanitize_message FAILED: {type(e).__name__}: {e}")
            logging.error(f"[smart_chat] TRACEBACK: {traceback.format_exc()}")
            raise
        # 阶段27：先尝试 v2，失败/禁用再 v1（与 server.py process_message 同样的灰度逻辑）
        v2_attempted = False
        try:
            logging.info("[smart_chat] DEBUG: enter v2 try block")
            from A2AServer.v2.bridge import is_v2_request, v2_process_message
            logging.info(f"[smart_chat] DEBUG: imported is_v2_request={is_v2_request}")
            v2_enabled = is_v2_request(request)
            logging.info(f"[smart_chat] DEBUG: v2_enabled={v2_enabled}")
            logging.info(f"[smart_chat] v2 attempt: is_v2_request={v2_enabled}")
            if v2_enabled:
                v2_attempted = True
                logging.info("[smart_chat][PHA v2] routing to v2 HostGraph")
                async def _v2_runner():
                    try:
                        r = await v2_process_message(message)
                        if r.get("error"):
                            logging.warning(f"[smart_chat][PHA v2] error, fallback to v1: {r['error']}")
                            await agent_server.manager.process_message(message)
                        elif r.get("message") is not None:
                            try:
                                agent_server.manager._messages.append(r["message"])
                                conv = agent_server.manager.get_conversation(conversation.conversation_id)
                                if conv:
                                    conv.messages.append(r["message"])
                                # 阶段29 debug: 打印 v2 真返回的 content
                                msg_obj = r["message"]
                                content_text = ""
                                if hasattr(msg_obj, 'parts') and msg_obj.parts:
                                    content_text = getattr(msg_obj.parts[0], 'text', str(msg_obj.parts[0]))[:200]
                                logging.info(f"[smart_chat][PHA v2] agent={r.get('result', {}).get('agent')} content_len={len(content_text)} content_preview={content_text!r}")
                            except Exception as inner_e:
                                logging.warning(f"[smart_chat][PHA v2] inject failed: {inner_e}")
                            logging.info(f"[smart_chat][PHA v2] success: agent={r.get('result', {}).get('agent')}")
                    except Exception as e:
                        import traceback
                        logging.error(f"[smart_chat][PHA v2] exception, fallback to v1: {type(e).__name__}: {e}")
                        logging.error(traceback.format_exc())
                        await agent_server.manager.process_message(message)
                task = asyncio.create_task(_v2_runner())
        except ImportError as e:
            logging.warning(f"[smart_chat][PHA v2] import failed: {e}")
        except Exception as e:
            import traceback
            import sys
            tb_str = traceback.format_exc()
            logging.error(f"[smart_chat][PHA v2] setup failed: {type(e).__name__}: {e}")
            logging.error(f"[smart_chat][PHA v2] TRACEBACK:\n{tb_str}")

        if not v2_attempted:
            task = asyncio.create_task(agent_server.manager.process_message(message))

        def _done_cb(t):
            try:
                exc = t.exception()
            except Exception:
                exc = None
            if exc:
                logger.error(f"智能路由任务异常: {exc}")
                try:
                    conv_id = conversation.conversation_id
                    conv = agent_server.manager.get_conversation(conv_id)
                    if conv:
                        from A2AServer.common.A2Atypes import (
                            Message as AMsg,
                            TextPart as AText,
                        )
                        err_msg = AMsg(
                            role='agent',
                            parts=[AText(text=f"路由任务失败：{str(exc)}")],
                            metadata={
                                'conversation_id': conv_id,
                                'last_message_id': message.metadata.get('message_id'),
                                'message_id': str(uuid.uuid4()),
                            },
                        )
                        conv.messages.append(err_msg)
                except Exception:
                    pass
                try:
                    mid = message.metadata.get('message_id')
                    if mid in agent_server.manager._pending_message_ids:
                        agent_server.manager._pending_message_ids.remove(mid)
                except Exception:
                    pass
        task.add_done_callback(_done_cb)

        return {
            "success": True,
            "message": f"已将您的请求转发给{selected_agent}",
            "conversation_id": conversation.conversation_id,
            "message_id": message.metadata['message_id'],
            "selected_agent": selected_agent
        }

    except Exception as e:
        logger.error(f"智能路由处理错误: {str(e)}")
        return {"error": f"处理请求时发生错误: {str(e)}"}


# ============================================================
# 阶段37: v2 流式端点（解决前端轮询问题）
# ============================================================
from fastapi.responses import StreamingResponse
import json as _json


@app.post("/v2/chat/stream")
async def v2_chat_stream(request: Request):
    """
    v2 流式端点：调用 LangGraph 真流式输出 LLM 答案

    返回：SSE (text/event-stream) 格式
    事件类型：
      - event: routing
        data: {"agent": "health_advisor", "routing": {...}}
      - event: chunk
        data: {"text": "你好"}
      - event: done
        data: {"content": "完整答案", "agent": "health_advisor"}
    """
    from A2AServer.v2.bridge import v2_process_message
    from A2AServer.v2 import route_and_invoke

    try:
        body = await request.json()
        print(f"[v2/chat/stream] received body keys: {list(body.keys()) if isinstance(body, dict) else 'not dict'}", flush=True)
    except Exception as e:
        print(f"[v2/chat/stream] body parse failed: {e}", flush=True)
        return {"error": "invalid json"}

    message = body.get("message", "")
    conversation_id = body.get("conversation_id") or f"stream_{uuid.uuid4().hex[:8]}"
    user_id = body.get("user_id") or "default_user"
    metadata = body.get("metadata") or {}
    if "selected_agent" in body and body["selected_agent"]:
        metadata["selected_agent"] = body["selected_agent"]
    # 阶段38-2: multi_model 路由选项
    task_type = body.get("task_type", "chat")
    prefer_provider = body.get("prefer_provider", "")
    mode = body.get("mode", "single")

    async def event_generator():
        try:
            # 1) 先调 v2_process_message 拿 routing 结果
            from A2AServer.common.A2Atypes import Message as _AMsg
            a2a_msg = _AMsg(
                role="user",
                parts=[{"type": "text", "text": message}],
                metadata={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    **metadata,
                },
            )
            result = await v2_process_message(a2a_msg)
            content = result.get("result", {}).get("content", "")
            agent = result.get("result", {}).get("agent", "unknown")
            routing = result.get("result", {}).get("routing", {})

            # 2) 推送 routing 事件
            yield f"event: routing\ndata: {_json.dumps({'agent': agent, 'routing': routing}, ensure_ascii=False)}\n\n"

            # 3) 把 content 拆成块流式推送
            chunk_size = 10
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                yield f"event: chunk\ndata: {_json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)  # 20ms 间隔模拟流式

            # 4) 推送 done
            yield f"event: done\ndata: {_json.dumps({'content': content, 'agent': agent}, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logging.error(f"[v2/chat/stream] error: {e}\n{tb}")
            yield f"event: error\ndata: {_json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# 阶段38-2: 多 LLM provider 路由 SSE 端点
@app.post("/v2/models/stream")
async def v2_models_stream(request: Request):
    """
    阶段38-2: 多模型 SSE 流式端点

    - task_type: chat / code / analysis / summary / translation / creative
    - prefer_provider: deepseek / qwen / claude / local
    - 自动 fallback (deepseek → qwen → claude → local)
    - 限流: 60 次/分钟/provider

    事件: routing → chunk × N → done
    """
    from A2AServer.v2 import multi_model
    from A2AServer.v2.multi_model import ChatMessage

    try:
        body = await request.json()
        print(f"[v2/models/stream] body keys: {list(body.keys())}", flush=True)
    except Exception as e:
        print(f"[v2/models/stream] parse failed: {e}", flush=True)
        return {"error": "invalid json"}

    messages = body.get("messages", [])
    if not messages:
        return {"error": "messages required"}
    task_type = body.get("task_type", "chat")
    prefer_provider = body.get("prefer_provider", "") or None
    max_tokens = body.get("max_tokens", 2048)
    temperature = body.get("temperature", 0.7)

    async def event_generator():
        try:
            # 1. routing
            chosen = prefer_provider or multi_model.TASK_ROUTING.get(task_type, "deepseek")
            yield f"event: routing\ndata: {__import__('json').dumps({'provider': chosen, 'task_type': task_type, 'fallback_chain': multi_model.FALLBACK_CHAIN}, ensure_ascii=False)}\n\n"

            # 2. 转 ChatMessage
            chat_msgs = [ChatMessage(role=m["role"], content=m["content"]) for m in messages]

            # 3. 查缓存（阶段39-3 集成）
            from A2AServer.v2.semantic_cache import get_cache
            cache = get_cache()
            entry = cache.get(messages, task_type=task_type, max_tokens=max_tokens, temperature=temperature)
            if entry is not None:
                # 缓存命中
                yield f"event: cache_hit\ndata: {__import__('json').dumps({'cached': True, 'key': entry.key, 'hit_count': entry.hit_count, 'provider': entry.provider}, ensure_ascii=False)}\n\n"
                content = entry.text
                chunk_size = 10
                for i in range(0, len(content), chunk_size):
                    chunk = content[i:i + chunk_size]
                    yield f"event: chunk\ndata: {__import__('json').dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.02)
                yield f"event: done\ndata: {__import__('json').dumps({'content': content, 'provider': entry.provider + ' (cached)', 'model': entry.model, 'latency_ms': 0, 'fallback_used': False, 'prompt_tokens': entry.prompt_tokens, 'completion_tokens': entry.completion_tokens, 'cached': True}, ensure_ascii=False)}\n\n"
                return

            # 4. 缓存 miss → 调 router
            router = multi_model.get_router()
            result = await router.chat(
                messages=chat_msgs,
                task_type=task_type,
                max_tokens=max_tokens,
                temperature=temperature,
                prefer_provider=prefer_provider,
            )

            # 5. 存缓存
            if result and result.text and not result.error:
                cache.set(
                    messages,
                    result.text,
                    provider=result.provider,
                    model=result.model,
                    task_type=task_type,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    prompt_tokens=result.prompt_tokens,
                    completion_tokens=result.completion_tokens,
                )

            # 6. 流式 chunk
            content = result.text or ""
            chunk_size = 10
            for i in range(0, len(content), chunk_size):
                chunk = content[i:i + chunk_size]
                yield f"event: chunk\ndata: {__import__('json').dumps({'text': chunk}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)

            # 7. done
            yield f"event: done\ndata: {__import__('json').dumps({'content': content, 'provider': result.provider, 'model': result.model, 'latency_ms': result.latency_ms, 'fallback_used': result.fallback_used, 'prompt_tokens': result.prompt_tokens, 'completion_tokens': result.completion_tokens, 'cached': False}, ensure_ascii=False)}\n\n"

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"[v2/models/stream] error: {e}\n{tb}", flush=True)
            yield f"event: error\ndata: {__import__('json').dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# 包含路由
app.include_router(auth_router)  # 认证路由
app.include_router(router)       # 会话路由

# 启动服务
if __name__ == "__main__":
    import uvicorn
    import socket
    # 允许通过环境变量配置绑定地址与端口，默认与现状一致
    env_port = os.getenv("HOST_API_PORT", "13002")
    host = os.getenv("HOST_API_BIND", "0.0.0.0")

    def _resolve_port(port_str: str, bind_host: str) -> int:
        """支持 auto/0：自动选择可用端口"""
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
        # 非法值时回退默认
        return 13002

    port = _resolve_port(env_port, host)
    print(f"启动A2A的多Agent协调者后端服务，地址 {host}，端口为{port}")
    try:
        uvicorn.run(app, host=host, port=port)
    except OSError as e:
        # Windows 上若遇到 [WinError 10013] 权限不允许，自动回退到 127.0.0.1
        winerr = getattr(e, "winerror", None)
        if winerr == 10013 or getattr(e, "errno", None) == 13:
            fallback_host = "127.0.0.1"
            # 若原端口受限，尝试自动选择可用端口
            alt_port = _resolve_port(
                "auto" if str(env_port).lower() != "auto" else env_port,
                fallback_host,
            )
            logging.error(
                f"[HostAPI] 绑定 {host}:{port} 失败（权限/防火墙限制），回退到 {fallback_host}:{alt_port}"
            )
            uvicorn.run(app, host=fallback_host, port=alt_port)
        else:
            raise
