import logging
import uuid
import asyncio
import os
import sys
from fastapi import FastAPI, APIRouter, Response, Request, UploadFile, File, Depends
from typing import List
from fastapi.middleware.cors import CORSMiddleware
from server import ConversationServer
from auth import router as auth_router, get_current_user
from dotenv import load_dotenv
import json
from datetime import date, datetime

load_dotenv(override=False)

backend_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env"))
try:
    if os.path.exists(backend_env_path):
        load_dotenv(backend_env_path, override=False)
except Exception:
    pass

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
            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))
        except Exception:
            pass
        try:
            import importlib
            health_api = importlib.import_module("health_records_api")
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

@app.middleware("http")
async def log_request_body(request: Request, call_next):
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
    response = await call_next(request)
    return response
router = APIRouter()
agent_server = ConversationServer(router)

# === 集成健康档案 API（方案B：将后端 API 挂载到 hostAgentAPI）===
# 为了在同一进程内复用后端实现，这里将请求转发到 backend/health_records_api.py 中已实现的处理函数
try:
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
    if backend_dir not in sys.path:
        sys.path.append(backend_dir)
    import health_records_api as health_api  # noqa: E402

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
        conf = ocr_info.get("confidence")
        cn_ratio = _ch_ratio(summary_src)
        # 默认长度 400；检验报告/处方放宽到 1200
        tval = back_type.value if hasattr(back_type, "value") else back_type
        if tval in ("medical_report", "lab_result", "examination", "prescription"):
            max_len = 3000
        else:
            max_len = 400
        # 若置信度低或中文占比低，收紧到 200，并给出友好提示
        try:
            if (isinstance(conf, (int, float)) and conf < 0.5) or (cn_ratio < 0.2 and len(summary_src) >= 40):
                max_len = 200
        except Exception:
            pass
        summary = _shorten(summary_src, max_len=max_len)
        # 当识别质量较差时提供友好回退文案
        try:
            if max_len == 200:
                summary = "识别结果不佳，请点击预览原文"
        except Exception:
            pass
        record_date = get("record_date")
        # pydantic datetime/date 直接序列化
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
            "tags": get("tags") or [],
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
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid") or "")
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
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid") or "")
        r = await health_api.get_health_record(record_id, user_id=user_id)
        return to_front_record(r)

    @health_router.post("/api/health-records")
    async def create_record_proxy(request: Request, user: dict = Depends(get_current_user)):
        payload = await request.json()
        converted = transform_record_payload(payload or {})
        record = health_api.HealthRecordCreate(**converted)
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid") or "")
        r = await health_api.create_health_record(record, user_id=user_id, request=request)
        return to_front_record(r)

    @health_router.put("/api/health-records/{record_id}")
    async def update_record_proxy(record_id: str, request: Request, user: dict = Depends(get_current_user)):
        payload = await request.json()
        converted = transform_update_payload(payload or {})
        record = health_api.HealthRecordUpdate(**converted)
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid") or "")
        r = await health_api.update_health_record(record_id, record, user_id=user_id, request=request)
        return to_front_record(r)

    @health_router.delete("/api/health-records/{record_id}")
    async def delete_record_proxy(record_id: str, request: Request, user: dict = Depends(get_current_user)):
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid") or "")
        return await health_api.delete_health_record(record_id, user_id=user_id, request=request)

    @health_router.post("/api/health-records/upload")
    async def upload_file_proxy(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid") or "")
        return await health_api.upload_file(file, user_id=user_id)

    # 新增：批量上传代理，转发到后端批量上传端点
    @health_router.post("/api/health-records/upload/multiple")
    async def upload_files_proxy(files: List[UploadFile] = File(...), user: dict = Depends(get_current_user)):
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid") or "")
        return await health_api.upload_multiple_files(files, user_id=user_id)

    # 新增：文件直链转发（按file_id读取并以内联方式返回）
    @health_router.get("/api/health-records/files/{file_id}")
    async def get_file_proxy(file_id: str):
        return await health_api.get_file_attachment(file_id)

    @health_router.get("/api/health-records/ocr/status")
    async def ocr_status_proxy():
        return {"status": "ok"}

    app.include_router(health_router)
except Exception as e:
    # 集成失败不阻塞 HostAPI，降级为警告以避免噪音
    logging.warning(f"集成健康档案API失败（未挂载 backend 或模块缺失）: {e}")

# === 用药管理与提醒 API ===
try:
    # 优先将 backend 下的具体 Agent 目录按文件路径动态加载，避免 "mcpserver" 包名冲突
    import importlib.util
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend"))
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

    # 统一封装：兼容两种“标记服药”函数签名（HRM: 需要 user_id；MR: 不需要）
    def _call_mark_taken(reminder_id: int, taken_time: str, user_id: str):
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
                    "WHERE id = %s AND user_id = %s AND is_deleted = 0"
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
            # 提醒工具的获取接口为 get_medication_reminders(user_id, active_only=True)
            raw = storage_get_reminders(user_id, active_only)
            data = json.loads(raw) if isinstance(raw, str) else raw
            rows = data.get("reminders") if isinstance(data, dict) else data
            from datetime import datetime
            target_date = (date or (datetime.utcnow().date().isoformat()))
            result = []
            dbm = None
            try:
                dbm = get_db_manager()
            except Exception:
                dbm = None
            for r in rows or []:
                med_id = r.get("medication_id")
                if not med_id and dbm:
                    try:
                        res = dbm.execute_query("SELECT medication_id FROM medication_reminders WHERE id = %s", (r.get("id"),))
                        if res:
                            med_id = res[0].get("medication_id")
                    except Exception:
                        pass
                scheduled = f"{str(target_date)} {str(r.get('reminder_time'))}:00"

                # 计算已服用状态：查询当天对应提醒的日志
                taken_flag = False
                if dbm:
                    try:
                        # 先查主提醒ID（medication_reminders.reminder_id）
                        rid_rows = dbm.execute_query(
                            "SELECT reminder_id FROM medication_reminders WHERE id = %s",
                            (r.get("id"),)
                        )
                        main_rid = rid_rows[0].get("reminder_id") if rid_rows else None
                        if main_rid:
                            log_rows = dbm.execute_query(
                                "SELECT status FROM reminder_logs WHERE reminder_id = %s AND user_id = %s AND scheduled_time = %s ORDER BY completion_time DESC LIMIT 1",
                                (main_rid, user_id, scheduled)
                            )
                            if log_rows:
                                status = str(log_rows[0].get("status") or "").lower()
                                taken_flag = status in ("completed", "taken")
                    except Exception:
                        taken_flag = False

                result.append({
                    "id": r.get("id"),
                    "medicationId": med_id,
                    "scheduledTime": scheduled,
                    "taken": taken_flag,
                })
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

@meds_router.post("/medication-reminders/{reminder_id}/taken")
@meds_router.post("/api/medication-reminders/{reminder_id}/taken")
async def mark_medication_taken(reminder_id: int, taken_time: str = "", user: dict = Depends(get_current_user)):
        try:
            # 记录服药接口签名为 log_medication_taken(reminder_id, actual_time=None, notes=None)
            try:
                user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
                raw = _call_mark_taken(reminder_id, taken_time, user_id)
                data = json.loads(raw) if isinstance(raw, str) else raw
                return data
            except Exception:
                # 回退更新本地提醒状态
                ok = _mark_local_taken(reminder_id, taken_time)
                return {"success": ok}
        except Exception as e:
            logging.error(f"标记服药失败: {e}")
            return {"success": False, "message": f"标记服药失败: {str(e)}"}

app.include_router(meds_router)

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

def _create_local_reminder(user_id: str, drug_name: str, dosage: str, frequency: str,
                           start_date: str, times_list: list, end_date: str, notes: str) -> dict:
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

@app.get("/api/medication-reminders")
async def list_medication_reminders(user: dict = Depends(get_current_user)):
    uid = str(user.get("id") or user.get("user_id") or user.get("uid"))
    try:
        raw = storage_get_reminders(uid, True)
        data = json.loads(raw) if isinstance(raw, str) else raw
        rows = data.get("reminders") if isinstance(data, dict) else data
        return {"reminders": rows or []}
    except Exception:
        db = _load_local_reminders()
        res = [r for r in db.get("reminders", []) if str(r.get("user_id")) == uid]
        return {"reminders": res}

@app.get("/api/debug/db-tables")
async def _debug_db_tables():
    try:
        dbm = get_db_manager()
        _ensure_visit_summaries_table(dbm)
    except Exception:
        return {"error": "no_db_manager"}
    rows = dbm.execute_query("select table_name from information_schema.tables where table_schema='public' order by 1")
    names = []
    for r in rows:
        names.append(r.get("table_name") if isinstance(r, dict) else (r[0] if r else None))
    return {"tables": names}

@app.get("/api/debug/db-columns/{table}")
async def _debug_db_columns(table: str):
    try:
        dbm = get_db_manager()
        _ensure_visit_summaries_table(dbm)
    except Exception:
        return {"error": "no_db_manager"}
    rows = dbm.execute_query(
        "select column_name,data_type from information_schema.columns where table_schema='public' and table_name=%s order by ordinal_position",
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
        "ALTER TABLE reminder_logs ADD COLUMN IF NOT EXISTS user_id TEXT",
        "ALTER TABLE reminder_logs ADD COLUMN IF NOT EXISTS completion_time TIMESTAMPTZ",
    ]
    for s in stmts:
        dbm.execute_update(s)
    return {"ok": True}

# === 新增：健康咨询简易端点（供前端 /consultations 使用） ===
CONSULT_DB_PATH = os.path.join(os.path.dirname(__file__), "consultations.json")

def _load_consultations() -> dict:
    try:
        if not os.path.exists(CONSULT_DB_PATH):
            return {"consultations": []}
        with open(CONSULT_DB_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"consultations": []}

def _save_consultations(data: dict) -> None:
    try:
        with open(CONSULT_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"保存咨询数据失败: {e}")

@app.get("/consultations")
async def list_consultations():
    data = _load_consultations()
    items = data.get("consultations", [])
    # 按创建时间倒序
    items.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
    return items

@app.post("/consultations")
async def create_consultation(request: Request):
    payload = await request.json()
    title = payload.get("title", "新咨询")
    ctype = payload.get("type", "general")
    now = datetime.utcnow().isoformat()
    item = {
        "id": uuid.uuid4().hex,
        "title": title,
        "type": ctype,
        "createdAt": now,
        "messages": []
    }
    data = _load_consultations()
    data.setdefault("consultations", []).insert(0, item)
    _save_consultations(data)
    return item

@app.get("/consultations/{cid}/messages")
async def get_consultation_messages(cid: str):
    data = _load_consultations()
    for c in data.get("consultations", []):
        if c.get("id") == cid:
            return c.get("messages", [])
    return []

@app.post("/consultations/{cid}/messages")
async def send_consultation_message(cid: str, request: Request):
    body = await request.json()
    content = body.get("content", "")
    files = body.get("files", [])
    now = datetime.utcnow().isoformat()
    data = _load_consultations()
    # 查找咨询
    target = None
    for c in data.get("consultations", []):
        if c.get("id") == cid:
            target = c
            break
    if target is None:
        # 若不存在，则自动创建一个
        target = {
            "id": cid,
            "title": "快速咨询",
            "type": "general",
            "createdAt": now,
            "messages": []
        }
        data.setdefault("consultations", []).insert(0, target)
    # 记录用户消息
    user_msg = {
        "id": uuid.uuid4().hex,
        "type": "user",
        "content": content,
        "files": files,
        "timestamp": now
    }
    target.setdefault("messages", []).append(user_msg)
    # 生成简单AI回复（占位实现）
    ai_text = f"我已收到您的信息：{content[:100]}。基于健康咨询，我可以提供一般性的建议和引导，如需就诊请及时联系专业医生。"
    ai_msg = {
        "id": uuid.uuid4().hex,
        "type": "ai",
        "content": ai_text,
        "timestamp": datetime.utcnow().isoformat()
    }
    target["messages"].append(ai_msg)
    _save_consultations(data)
    # 前端期望的返回格式
    return {
        "content": ai_text,
        "suggestions": [
            "需要我为您整理成就诊摘要吗？",
            "是否要为此问题创建健康档案记录？"
        ]
    }

SUMMARIES_DB_PATH = os.path.join(os.path.dirname(__file__), "visit_summaries.json")
def _get_user_id(user: dict) -> str:
    return str(user.get("user_id") or user.get("id") or user.get("uid") or "")

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
        "CREATE INDEX IF NOT EXISTS idx_visit_summaries_user_date ON visit_summaries(user_id, visit_date)",
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
        rows = dbm.execute_query(
            f"SELECT id, user_id, title, visit_date, doctor, hospital, department, chief_complaint, symptoms, examination, diagnosis, treatment, prescription, follow_up, notes, files, tests, created_at, updated_at FROM visit_summaries WHERE {where} ORDER BY visit_date DESC NULLS LAST",
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
            visitDateStr = (str(r.get("visit_date"))[:10] if r.get("visit_date") else "")
            doctorStr = r.get("doctor") or ""
            hospitalStr = r.get("hospital") or ""
            titleStr = r.get("title") or ""
            if not titleStr:
                base = doctorStr or hospitalStr or "就诊摘要"
                titleStr = f"{base} - {visitDateStr}" if visitDateStr else base
            elif "未填医生" in titleStr and doctorStr:
                titleStr = f"{doctorStr} - {visitDateStr}" if visitDateStr else doctorStr
            join_tests = "\n".join([
                " ".join([
                    p for p in [
                        str(x.get("name") or x.get("test_name") or "").strip(),
                        (str(x.get("value") or "").strip() + str(x.get("unit") or "")),
                        str(x.get("status") or "").strip()
                    ] if p
                ])
                for x in (tv or [])
            ]) if tv else ""
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
                agg[k] = {"doctor": k, "count": 0, "lastVisit": it.get("visitDate"), "items": []}
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
                agg[k] = {"hospital": k, "count": 0, "lastVisit": it.get("visitDate"), "items": []}
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
                new_id, uid, payload.get("title") or "就诊摘要", vd,
                payload.get("doctor") or "", payload.get("hospital") or "", payload.get("department") or "",
                payload.get("chiefComplaint") or "", payload.get("symptoms") or "", payload.get("examination") or "",
                payload.get("diagnosis") or "", payload.get("treatment") or "",
                payload.get("prescription") or "", payload.get("followUp") or "", payload.get("notes") or "",
                json.dumps(files), json.dumps(tests)
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
    vd = _normalize_date(payload.get("visitDate")) if payload.get("visitDate") else None
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
        sql = f"UPDATE visit_summaries SET {', '.join(sets)} WHERE id = %s AND user_id = %s"
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
            "UPDATE visit_summaries SET is_deleted = 1, updated_at = now() WHERE id = %s AND user_id = %s",
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
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
        if backend_dir not in sys.path:
            sys.path.append(backend_dir)
        health_api = importlib.import_module("health_records_api")
        doc_tool = importlib.import_module("VisitSummaryGenerator.mcpserver.document_tool")

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
        user_id = str(user.get("id") or user.get("user_id") or user.get("uid") or "")
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
                        s = " ".join([p for p in [name, val + (unit or ""), status] if p])
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
                    tests_json.append({
                        "name": str(x.get("test_name") or x.get("name") or ""),
                        "value": str(x.get("value") or ""),
                        "unit": str(x.get("unit") or ""),
                        "status": str(x.get("status") or ""),
                        "date": visit_date
                    })
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

    return generated

@app.api_route("/ping", methods=["GET", "POST"])
async def ping():
    return "Pong"

# 智能路由接口 - 统一API入口
@app.post("/smart_chat")
async def smart_chat(request: Request):
    """
    智能路由接口：根据用户输入自动选择合适的智能体
    """
    try:
        # Robust body decoding: try UTF-8 then fallback to GBK (common on Windows CN)
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
            "就诊摘要生成器": ["摘要", "总结", "就诊", "报告", "文档", "解析"]
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
        
        # 发送消息到智能体
        message = agent_server.manager.sanitize_message(message)
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
                        from A2AServer.common.A2Atypes import Message as AMsg, TextPart as AText
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
            alt_port = _resolve_port("auto" if str(env_port).lower() != "auto" else env_port, fallback_host)
            logging.error(f"[HostAPI] 绑定 {host}:{port} 失败（权限/防火墙限制），回退到 {fallback_host}:{alt_port}")
            uvicorn.run(app, host=fallback_host, port=alt_port)
        else:
            raise
