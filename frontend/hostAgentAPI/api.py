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

# 加载 hostAgentAPI 的 .env
load_dotenv()

# 额外加载后端 backend/.env（不覆盖已有环境变量）
backend_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend", ".env"))
try:
    if os.path.exists(backend_env_path):
        load_dotenv(backend_env_path, override=False)
except Exception:
    # 避免因环境文件问题影响服务启动
    pass

# 配置日志
logfile = "api.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(module)s - %(funcName)s - %(message)s",
    handlers=[
        logging.FileHandler(logfile, mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
app = FastAPI()

# Enable CORS for frontend React app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 在HostAgentAPI启动时预热后端工具（记忆系统与OCR），避免首次调用时冷启动
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
        # 优化摘要：优先使用 summary，并限制长度，减少OCR噪声对列表展示的影响
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
        summary_src = get("summary") or get("content") or ""
        summary = _shorten(summary_src)
        # 新增：当OCR置信度低或中文占比过低时提供友好回退摘要
        ocr_info = metadata.get("ocr_info") or {}
        conf = ocr_info.get("confidence")
        cn_ratio = _ch_ratio(summary_src)
        try:
            if (isinstance(conf, (int, float)) and conf < 0.5) or (cn_ratio < 0.2 and len(summary_src) >= 40):
                summary = "识别结果不佳，请点击预览原文"
        except Exception:
            pass
        back_type = get("record_type")
        record_date = get("record_date")
        # pydantic datetime/date 直接序列化
        return {
            "id": get("id"),
            "title": get("title") or "",
            "type": _map_type_backend_to_front(back_type.value if hasattr(back_type, "value") else back_type),
            "date": record_date,
            "description": summary,
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
        result = await health_api.get_health_records(
            skip=skip,
            limit=limit,
            record_type=rt,
            importance=imp,
            search=search,
            start_date=sd,
            end_date=ed,
        )
        # 统一映射为前端需要的字段
        return [to_front_record(r) for r in result]

    @health_router.get("/api/health-records/{record_id}")
    async def get_record_proxy(record_id: str):
        r = await health_api.get_health_record(record_id)
        return to_front_record(r)

    @health_router.post("/api/health-records")
    async def create_record_proxy(request: Request):
        payload = await request.json()
        converted = transform_record_payload(payload or {})
        record = health_api.HealthRecordCreate(**converted)
        r = await health_api.create_health_record(record)
        return to_front_record(r)

    @health_router.put("/api/health-records/{record_id}")
    async def update_record_proxy(record_id: str, request: Request):
        payload = await request.json()
        converted = transform_update_payload(payload or {})
        record = health_api.HealthRecordUpdate(**converted)
        r = await health_api.update_health_record(record_id, record)
        return to_front_record(r)

    @health_router.delete("/api/health-records/{record_id}")
    async def delete_record_proxy(record_id: str):
        return await health_api.delete_health_record(record_id)

    @health_router.post("/api/health-records/upload")
    async def upload_file_proxy(file: UploadFile = File(...)):
        return await health_api.upload_file(file)

    # 新增：批量上传代理，转发到后端批量上传端点
    @health_router.post("/api/health-records/upload/multiple")
    async def upload_files_proxy(files: List[UploadFile] = File(...)):
        return await health_api.upload_multiple_files(files)

    # 新增：文件直链转发（按file_id读取并以内联方式返回）
    @health_router.get("/api/health-records/files/{file_id}")
    async def get_file_proxy(file_id: str):
        return await health_api.get_file_attachment(file_id)

    @health_router.get("/api/health-records/ocr/status")
    async def ocr_status_proxy():
        return {"status": "ok"}

    app.include_router(health_router)

    # === 用药管理与提醒 API ===
    try:
        # 优先将 HealthRecordsManager 根目录置于 sys.path 前端，避免 database_config 名称冲突
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
        hrm_dir = os.path.join(backend_dir, "HealthRecordsManager")
        if hrm_dir not in sys.path:
            sys.path.insert(0, hrm_dir)
        # 导入 MySQL 存储与提醒工具（使用 hrm_dir 下的模块）
        from mcpserver.storage_tool import save_medication, get_medications as storage_get_medications
        from mcpserver.reminder_tool import (
            add_medication_reminder,
            get_medication_reminders as storage_get_reminders,
            mark_reminder_taken as storage_mark_taken,
        )
        from database_config import get_db_manager
    except Exception as e:
        logging.error(f"加载用药工具失败: {e}")
        # 回退：提供安全的占位实现，避免前端白屏
        def storage_get_medications(user_id: str, is_active: bool = True):
            return json.dumps({"medications": []})
        def add_medication_reminder(user_id: str, drug_name: str, dosage: str, reminder_times: str, start_date: str, end_date: str, notes: str):
            return json.dumps({"success": True, "reminders": []})
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
                reminder_times = json.dumps(norm_times)
                raw = add_medication_reminder(user_id, drug_name, dosage, reminder_times, start_date, end_date, notes)
            else:
                raw = save_medication(user_id, drug_name, dosage, frequency, start_date, end_date, notes)

            data = json.loads(raw) if isinstance(raw, str) else raw
            return data
        except Exception as e:
            logging.error(f"创建用药失败: {e}")
            return {"success": False, "message": f"创建用药失败: {str(e)}"}

    # 新增：更新用药信息
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
            raw = storage_get_reminders(user_id, date, active_only)
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
                result.append({
                    "id": r.get("id"),
                    "medicationId": med_id,
                    "scheduledTime": scheduled,
                    "taken": False,
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

            reminder_times = json.dumps(norm_times) if norm_times else "[]"
            raw = add_medication_reminder(user_id, name, dosage, reminder_times, start_date, end_date, notes)
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data
        except Exception as e:
            logging.error(f"创建用药提醒失败: {e}")
            return {"success": False, "message": f"创建用药提醒失败: {str(e)}"}

    @meds_router.post("/medication-reminders/{reminder_id}/taken")
    @meds_router.post("/api/medication-reminders/{reminder_id}/taken")
    async def mark_medication_taken(reminder_id: int, taken_time: str = "", user: dict = Depends(get_current_user)):
        try:
            user_id = str(user.get("id") or user.get("user_id") or user.get("uid"))
            raw = storage_mark_taken(user_id, reminder_id, taken_time)
            data = json.loads(raw) if isinstance(raw, str) else raw
            return data
        except Exception as e:
            logging.error(f"标记服药失败: {e}")
            return {"success": False, "message": f"标记服药失败: {str(e)}"}

    app.include_router(meds_router)

except Exception as e:
    logging.error(f"集成健康档案API失败: {e}")

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

# 添加 ping 路由
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
        import threading
        t = threading.Thread(target=lambda: asyncio.run(agent_server.manager.process_message(message)))
        t.start()
        
        return {
            "success": True,
            "message": f"已将您的请求转发给{selected_agent}",
            "conversation_id": conversation.conversation_id,
            "message_id": message.metadata['message_id'],
            "selected_agent": selected_agent
        }
        
    except Exception as e:
        logging.error(f"智能路由处理错误: {str(e)}")
        return {"error": f"处理请求时发生错误: {str(e)}"}

# 包含路由
app.include_router(auth_router)  # 认证路由
app.include_router(router)       # 会话路由

# 启动服务
if __name__ == "__main__":
    import uvicorn
    print(f"启动A2A的多Agent协调者后端服务，端口为13002")
    uvicorn.run(app, host="0.0.0.0", port=13002)
