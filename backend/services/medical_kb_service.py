from __future__ import annotations

import asyncio
import io
import base64
import json
import os
import time
import zipfile
import uuid
import unicodedata
from urllib.parse import urlparse
from xml.etree import ElementTree
from typing import Any

import anyio
import requests


_MEDICAL_KB_UPLOAD_JOBS: dict[str, dict[str, Any]] = {}
_MEDICAL_KB_UPLOAD_JOBS_LOCK = asyncio.Lock()


def _now_ts() -> float:
    return time.time()


def _prune_medical_kb_jobs_unlocked() -> None:
    try:
        max_jobs = int(os.getenv("A2A_MEDICAL_KB_UPLOAD_JOB_MAX_KEEP", "200"))
    except Exception:
        max_jobs = 200
    if max_jobs <= 0:
        return
    if len(_MEDICAL_KB_UPLOAD_JOBS) <= max_jobs:
        return
    items = list(_MEDICAL_KB_UPLOAD_JOBS.items())
    items.sort(key=lambda kv: float((kv[1] or {}).get("created_at") or 0.0))
    drop_n = max(0, len(items) - max_jobs)
    for i in range(drop_n):
        try:
            _MEDICAL_KB_UPLOAD_JOBS.pop(items[i][0], None)
        except Exception:
            continue


async def admin_get_medical_kb_upload_job(api: Any, *, job_id: str, request: Any) -> dict[str, Any]:
    api._require_admin(request)
    jid = (job_id or "").strip()
    if not jid:
        raise api.HTTPException(status_code=400, detail="job_id不能为空")
    async with _MEDICAL_KB_UPLOAD_JOBS_LOCK:
        job = _MEDICAL_KB_UPLOAD_JOBS.get(jid)
        if not job:
            raise api.HTTPException(status_code=404, detail="job不存在或已过期")
        return {"success": True, "job": job}


def _decode_text_bytes(data: bytes) -> str:
    b = data or b""
    if not b:
        return ""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    try:
        return b.decode("latin-1", errors="ignore")
    except Exception:
        return ""


def _extract_text_from_docx_bytes(data: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml_bytes = z.read("word/document.xml")
    except Exception:
        return ""

    try:
        root = ElementTree.fromstring(xml_bytes)
    except Exception:
        return ""

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for p in root.findall(".//w:p", ns):
        texts: list[str] = []
        for t in p.findall(".//w:t", ns):
            if t.text:
                texts.append(t.text)
        s = "".join(texts).strip()
        if s:
            paragraphs.append(s)
    return "\n\n".join(paragraphs).strip()


def _extract_text_from_pdf_bytes(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        raise RuntimeError("缺少依赖 pypdf，请安装后再上传 PDF")

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in getattr(reader, "pages", []) or []:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        t = (t or "").strip()
        if t:
            parts.append(t)
    return "\n\n".join(parts).strip()


def _get_pdf_page_count(data: bytes) -> int | None:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = getattr(reader, "pages", None)
        return len(pages) if pages is not None else None
    except Exception:
        return None


def _garbled_text_metrics(text: str) -> dict[str, int | float]:
    s = text or ""
    s2 = "".join(ch for ch in s if not ch.isspace())
    total = len(s2)
    if total <= 0:
        return {"total": 0, "bad": 0, "ratio": 0.0}
    bad = 0
    for ch in s2:
        if ch == "\ufffd":
            bad += 1
            continue
        try:
            if unicodedata.category(ch) == "Co":
                bad += 1
                continue
        except Exception:
            continue
    return {"total": total, "bad": bad, "ratio": (bad / total) if total else 0.0}


def _should_reject_pdf_text(text: str) -> tuple[bool, dict[str, int | float]]:
    m = _garbled_text_metrics(text)
    total = int(m.get("total") or 0)
    bad = int(m.get("bad") or 0)
    ratio = float(m.get("ratio") or 0.0)

    try:
        min_chars = int(os.getenv("A2A_MEDICAL_KB_PDF_GARBLED_MIN_TEXT_CHARS", "200"))
    except Exception:
        min_chars = 200
    if total < max(1, min_chars):
        return False, m

    try:
        max_ratio = float(os.getenv("A2A_MEDICAL_KB_PDF_GARBLED_MAX_RATIO", "0.02"))
    except Exception:
        max_ratio = 0.02
    try:
        min_bad = int(os.getenv("A2A_MEDICAL_KB_PDF_GARBLED_MIN_BAD", "20"))
    except Exception:
        min_bad = 20

    reject = (bad >= max(1, min_bad)) and (ratio >= max(0.0, max_ratio))
    return bool(reject), m


def _normalize_ocr_text_like(raw: Any) -> str:
    try:
        s = raw if isinstance(raw, str) else ("" if raw is None else str(raw))
        s_strip = s.strip()
        if not s_strip:
            return ""
        if s_strip.startswith("{") or s_strip.startswith("["):
            try:
                obj = json.loads(s_strip)
            except Exception:
                return s_strip
            if isinstance(obj, dict):
                for key in ("content", "Content"):
                    v = obj.get(key)
                    if isinstance(v, str) and v.strip():
                        return v.strip()
                data = obj.get("data") or obj.get("Data")
                if isinstance(data, dict):
                    v = data.get("content") or data.get("Content")
                    if isinstance(v, str) and v.strip():
                        return v.strip()
                    lines = data.get("lines") or data.get("prism_wordsInfo")
                    if isinstance(lines, list) and lines:
                        parts: list[str] = []
                        for it in lines:
                            if isinstance(it, dict):
                                parts.append(str(it.get("text") or it.get("word") or "").strip())
                            elif isinstance(it, str):
                                parts.append(it.strip())
                        text = "\n".join([p for p in parts if p])
                        if text.strip():
                            return text.strip()
                if isinstance(data, str) and data.strip():
                    return data.strip()
            if isinstance(obj, list) and obj:
                parts: list[str] = []
                for it in obj:
                    if isinstance(it, dict):
                        parts.append(str(it.get("text") or it.get("word") or "").strip())
                    elif isinstance(it, str):
                        parts.append(it.strip())
                text = "\n".join([p for p in parts if p])
                if text.strip():
                    return text.strip()
        return s_strip.replace("\r", " ").strip()
    except Exception:
        try:
            return (str(raw) if raw is not None else "").strip()
        except Exception:
            return ""


def _is_ocr_error_text(text: str) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    prefixes = (
        "阿里云OCR(2021)调用失败",
        "阿里云OCR(2021)配置缺失",
        "阿里云OCR(2021) SDK未安装",
        "阿里云OCR调用失败",
        "阿里云OCR配置缺失",
        "阿里云OCR SDK未安装",
        "图片Base64数据不合法",
        "本地OCR兜底不可用",
        "本地OCR兜底失败",
        "本地OCR兜底异常",
        "OCR识别失败",
        "不支持的OCR服务提供商",
    )
    if s.startswith(prefixes):
        return True
    low = s.lower()
    if low == "test":
        return True
    if s in ("OCR识别结果", "识别结果"):
        return True
    return False


def _ocr_pdf_bytes_with_aliyun(pdf_bytes: bytes) -> str:
    b = pdf_bytes or b""
    if not b:
        return ""
    try:
        from HealthRecordsManager.mcpserver.ocr_tool import call_aliyun_ocr_v2021, call_aliyun_ocr  # type: ignore
    except Exception as e:
        return f"OCR模块不可用: {e}"
    b64 = base64.b64encode(b).decode("utf-8")
    out = call_aliyun_ocr_v2021(b64)
    if isinstance(out, str) and _is_ocr_error_text(out):
        out2 = call_aliyun_ocr(b64)
        return out2
    return out


def _extract_text_from_upload(data: bytes, filename: str) -> str:
    name = (filename or "").strip().lower()
    if name.endswith(".pdf"):
        return _extract_text_from_pdf_bytes(data)
    if name.endswith(".docx"):
        return _extract_text_from_docx_bytes(data)
    if name.endswith(".txt") or name.endswith(".md"):
        return _decode_text_bytes(data).strip()
    raise ValueError("仅支持上传 PDF / DOCX / TXT / MD 文件")


async def _process_medical_kb_upload_from_raw(
    api: Any,
    *,
    raw: bytes,
    filename: str,
    kb_uid: str,
    global_kb: bool,
    doc_id: str | None,
    doc_type: str | None,
    title: str | None,
) -> dict[str, Any]:
    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    try:
        content = _extract_text_from_upload(raw, filename)
    except ValueError as e:
        raise api.HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise api.HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise api.HTTPException(status_code=500, detail=f"解析文件失败: {e}")

    content = (content or "").strip()
    is_pdf = (filename or "").strip().lower().endswith(".pdf")
    ocr_fallback_flag = (os.getenv("A2A_MEDICAL_KB_PDF_OCR_FALLBACK", "1") or "").strip()
    ocr_fallback_on = bool(is_pdf) and (ocr_fallback_flag not in ("0", "false", "no", "off"))
    ocr_fallback_allowed = ocr_fallback_on
    ocr_fallback_reason = None
    if ocr_fallback_on:
        try:
            ocr_max_pages = int(os.getenv("A2A_MEDICAL_KB_PDF_OCR_MAX_PAGES", "30"))
        except Exception:
            ocr_max_pages = 30
        try:
            ocr_max_mb = int(os.getenv("A2A_MEDICAL_KB_PDF_OCR_MAX_MB", "20"))
        except Exception:
            ocr_max_mb = 20
        if ocr_max_mb > 0 and len(raw) > (ocr_max_mb * 1024 * 1024):
            ocr_fallback_allowed = False
            ocr_fallback_reason = f"PDF过大(bytes={len(raw)} > {ocr_max_mb}MB)，跳过OCR兜底"
        if ocr_fallback_allowed and ocr_max_pages > 0:
            pages = _get_pdf_page_count(raw)
            if pages is not None and pages > ocr_max_pages:
                ocr_fallback_allowed = False
                ocr_fallback_reason = f"PDF页数过多(pages={pages} > {ocr_max_pages})，跳过OCR兜底"
    if not content:
        if ocr_fallback_allowed:
            try:
                ocr_timeout_s = float(os.getenv("A2A_MEDICAL_KB_PDF_OCR_TIMEOUT_SECONDS", "25"))
            except Exception:
                ocr_timeout_s = 25.0
            try:
                with anyio.fail_after(max(1.0, ocr_timeout_s)):
                    raw_ocr = await anyio.to_thread.run_sync(lambda: _ocr_pdf_bytes_with_aliyun(raw))
            except TimeoutError:
                raw_ocr = f"OCR超时({ocr_timeout_s}s)"
            ocr_text = _normalize_ocr_text_like(raw_ocr)
            if not ocr_text or _is_ocr_error_text(ocr_text):
                raise api.HTTPException(
                    status_code=422,
                    detail=f"未能从PDF中提取到可用文本，OCR兜底也失败: {(raw_ocr or '')[:800]}",
                )
            content = ocr_text.strip()
        elif ocr_fallback_on and ocr_fallback_reason:
            raise api.HTTPException(
                status_code=422,
                detail=f"未能从PDF中提取到可用文本；{ocr_fallback_reason}",
            )
        else:
            raise api.HTTPException(
                status_code=422,
                detail="未能从文件中提取到可用文本（PDF 可能是扫描件）",
            )

    pdf_quality_warning = None
    if is_pdf:
        reject, m = _should_reject_pdf_text(content)
        strict = (os.getenv("A2A_MEDICAL_KB_PDF_GARBLED_STRICT", "1") or "").strip()
        strict_on = strict not in ("0", "false", "no", "off")
        if reject:
            msg = (
                "PDF文本抽取疑似乱码（可能是字体映射/扫描件导致）。"
                "建议改用 OCR 入库，或上传可复制文本的 PDF。"
                f" bad={int(m.get('bad') or 0)} total={int(m.get('total') or 0)} ratio={float(m.get('ratio') or 0.0):.3f}"
            )
            if ocr_fallback_allowed:
                try:
                    ocr_timeout_s = float(os.getenv("A2A_MEDICAL_KB_PDF_OCR_TIMEOUT_SECONDS", "25"))
                except Exception:
                    ocr_timeout_s = 25.0
                try:
                    with anyio.fail_after(max(1.0, ocr_timeout_s)):
                        raw_ocr = await anyio.to_thread.run_sync(lambda: _ocr_pdf_bytes_with_aliyun(raw))
                except TimeoutError:
                    raw_ocr = f"OCR超时({ocr_timeout_s}s)"
                ocr_text = _normalize_ocr_text_like(raw_ocr)
                if ocr_text and (not _is_ocr_error_text(ocr_text)):
                    reject2, m2 = _should_reject_pdf_text(ocr_text)
                    if not reject2:
                        content = ocr_text.strip()
                        pdf_quality_warning = msg + "；已自动使用OCR兜底入库"
                    else:
                        msg2 = (
                            msg
                            + "；OCR兜底文本仍疑似乱码"
                            + f" bad={int(m2.get('bad') or 0)} total={int(m2.get('total') or 0)} ratio={float(m2.get('ratio') or 0.0):.3f}"
                        )
                        if strict_on:
                            raise api.HTTPException(status_code=422, detail=msg2)
                        pdf_quality_warning = msg2
                else:
                    msg3 = msg + f"；OCR兜底失败: {(raw_ocr or '')[:300]}"
                    if strict_on:
                        raise api.HTTPException(status_code=422, detail=msg3)
                    pdf_quality_warning = msg3
            elif ocr_fallback_on and ocr_fallback_reason:
                msg_skip = msg + f"；{ocr_fallback_reason}"
                if strict_on:
                    raise api.HTTPException(status_code=422, detail=msg_skip)
                pdf_quality_warning = msg_skip
            else:
                if strict_on:
                    raise api.HTTPException(status_code=422, detail=msg)
                pdf_quality_warning = msg

    doc_id2 = (doc_id or "").strip() or str(uuid.uuid4())
    doc_type2 = (doc_type or "").strip() or "medical_kb"
    title2 = (title or "").strip() or filename
    text = "\n".join([f"标题: {title2}", f"内容: {content}"]).strip()

    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                inserted = api._upsert_rag_document(
                    cursor,
                    user_id=kb_uid,
                    source_type="medical_kb",
                    source_id=doc_id2,
                    record_type=doc_type2,
                    title=title2,
                    text=text,
                )
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise api.HTTPException(status_code=500, detail=f"知识库入库失败: {e}")

    embedding_ok = bool(inserted and int(inserted) > 0)
    warning = (
        None
        if embedding_ok
        else "嵌入生成失败或超时，未写入向量分块，暂时无法用于检索"
    )
    if pdf_quality_warning:
        warning = (warning + "；" + pdf_quality_warning) if warning else pdf_quality_warning

    return {
        "success": True,
        "doc_id": doc_id2,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "title": title2,
        "filename": filename,
        "bytes": len(raw),
        "inserted_chunks": int(inserted or 0),
        "embedding_ok": embedding_ok,
        "warning": warning,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def _run_medical_kb_upload_job(
    api: Any,
    *,
    job_id: str,
    raw: bytes,
    filename: str,
    kb_uid: str,
    global_kb: bool,
    doc_id: str | None,
    doc_type: str | None,
    title: str | None,
) -> None:
    jid = (job_id or "").strip()
    if not jid:
        return
    async with _MEDICAL_KB_UPLOAD_JOBS_LOCK:
        job = _MEDICAL_KB_UPLOAD_JOBS.get(jid) or {}
        job["status"] = "running"
        job["updated_at"] = _now_ts()
        _MEDICAL_KB_UPLOAD_JOBS[jid] = job
    try:
        result = await _process_medical_kb_upload_from_raw(
            api,
            raw=raw,
            filename=filename,
            kb_uid=kb_uid,
            global_kb=global_kb,
            doc_id=doc_id,
            doc_type=doc_type,
            title=title,
        )
        async with _MEDICAL_KB_UPLOAD_JOBS_LOCK:
            job = _MEDICAL_KB_UPLOAD_JOBS.get(jid) or {}
            job["status"] = "succeeded"
            job["updated_at"] = _now_ts()
            job["result"] = result
            job.pop("error", None)
            _MEDICAL_KB_UPLOAD_JOBS[jid] = job
            _prune_medical_kb_jobs_unlocked()
    except Exception as e:
        err: dict[str, Any] = {"message": str(e)}
        if hasattr(e, "status_code"):
            try:
                err["status_code"] = int(getattr(e, "status_code"))
            except Exception:
                pass
        if hasattr(e, "detail"):
            try:
                err["detail"] = getattr(e, "detail")
            except Exception:
                pass
        async with _MEDICAL_KB_UPLOAD_JOBS_LOCK:
            job = _MEDICAL_KB_UPLOAD_JOBS.get(jid) or {}
            job["status"] = "failed"
            job["updated_at"] = _now_ts()
            job["error"] = err
            job.pop("result", None)
            _MEDICAL_KB_UPLOAD_JOBS[jid] = job
            _prune_medical_kb_jobs_unlocked()


def _get_json_path(data: Any, path: str) -> Any:
    cur = data
    for p in [x for x in (path or "").split(".") if x]:
        if isinstance(cur, dict):
            cur = cur.get(p)
            continue
        return None
    return cur


async def upsert_medical_kb_doc(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    uid = api._resolve_user_id(request, getattr(payload, "user_id", None))
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    title = (getattr(payload, "title", None) or "").strip()
    content = (getattr(payload, "content", None) or "").strip()
    if not title or not content:
        raise api.HTTPException(status_code=400, detail="title 与 content 不能为空")

    kb_uid = api._GLOBAL_KB_USER_ID if bool(getattr(payload, "global_kb", True)) else uid
    doc_id = (getattr(payload, "doc_id", None) or "").strip() or str(uuid.uuid4())
    doc_type = (getattr(payload, "doc_type", None) or "").strip() or "medical_kb"

    text = "\n".join([f"标题: {title}", f"内容: {content}"]).strip()

    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                inserted = api._upsert_rag_document(
                    cursor,
                    user_id=kb_uid,
                    source_type="medical_kb",
                    source_id=doc_id,
                    record_type=doc_type,
                    title=title,
                    text=text,
                )
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise api.HTTPException(status_code=500, detail=f"知识库入库失败: {e}")

    embedding_ok = bool(inserted and int(inserted) > 0)
    warning = (
        None
        if embedding_ok
        else "嵌入生成失败或超时，未写入向量分块，暂时无法用于检索"
    )

    return {
        "success": True,
        "doc_id": doc_id,
        "user_id": kb_uid,
        "global_kb": bool(getattr(payload, "global_kb", True)),
        "inserted_chunks": int(inserted or 0),
        "embedding_ok": embedding_ok,
        "warning": warning,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def admin_upload_medical_kb_file(
    api: Any,
    *,
    file: Any,
    global_kb: bool,
    user_id: str | None,
    doc_id: str | None,
    doc_type: str | None,
    title: str | None,
    request: Any,
) -> dict[str, Any]:
    api._require_admin(request)

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    if bool(global_kb):
        kb_uid = api._GLOBAL_KB_USER_ID
    else:
        kb_uid = (user_id or "").strip()
        if not kb_uid:
            raise api.HTTPException(
                status_code=400, detail="global_kb=false时必须提供user_id"
            )

    max_mb = int(os.environ.get("A2A_MEDICAL_KB_MAX_UPLOAD_MB") or "20")
    max_bytes = max(1, max_mb) * 1024 * 1024

    filename = (getattr(file, "filename", None) or "").strip()
    if not filename:
        raise api.HTTPException(status_code=400, detail="文件名为空")

    raw = await file.read()
    if not raw:
        raise api.HTTPException(status_code=400, detail="文件内容为空")
    if len(raw) > max_bytes:
        raise api.HTTPException(
            status_code=413, detail=f"文件过大，最大允许 {max_mb}MB"
        )

    async_flag = (os.getenv("A2A_MEDICAL_KB_UPLOAD_ASYNC", "1") or "").strip().lower()
    async_on = async_flag not in ("0", "false", "no", "off")
    if not async_on:
        return await _process_medical_kb_upload_from_raw(
            api,
            raw=raw,
            filename=filename,
            kb_uid=kb_uid,
            global_kb=bool(global_kb),
            doc_id=doc_id,
            doc_type=doc_type,
            title=title,
        )

    job_id = str(uuid.uuid4())
    job = {
        "id": job_id,
        "status": "queued",
        "created_at": _now_ts(),
        "updated_at": _now_ts(),
        "filename": filename,
        "bytes": len(raw),
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "doc_id": (doc_id or "").strip() or None,
        "doc_type": (doc_type or "").strip() or "medical_kb",
        "title": (title or "").strip() or None,
    }
    async with _MEDICAL_KB_UPLOAD_JOBS_LOCK:
        _MEDICAL_KB_UPLOAD_JOBS[job_id] = job
        _prune_medical_kb_jobs_unlocked()
    try:
        asyncio.create_task(
            _run_medical_kb_upload_job(
                api,
                job_id=job_id,
                raw=raw,
                filename=filename,
                kb_uid=kb_uid,
                global_kb=bool(global_kb),
                doc_id=doc_id,
                doc_type=doc_type,
                title=title,
            )
        )
    except Exception as e:
        async with _MEDICAL_KB_UPLOAD_JOBS_LOCK:
            job2 = _MEDICAL_KB_UPLOAD_JOBS.get(job_id) or job
            job2["status"] = "failed"
            job2["updated_at"] = _now_ts()
            job2["error"] = {"message": f"启动后台任务失败: {e}"}
            _MEDICAL_KB_UPLOAD_JOBS[job_id] = job2
        raise api.HTTPException(status_code=500, detail=f"启动后台任务失败: {e}")

    return {"success": True, "job_id": job_id, "status": "queued"}


async def admin_import_medical_kb_from_api(
    api: Any, *, payload: Any, request: Any
) -> dict[str, Any]:
    api._require_admin(request)

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    if bool(getattr(payload, "global_kb", True)):
        kb_uid = api._GLOBAL_KB_USER_ID
    else:
        kb_uid = (getattr(payload, "user_id", None) or "").strip()
        if not kb_uid:
            raise api.HTTPException(
                status_code=400, detail="global_kb=false时必须提供user_id"
            )

    url = (getattr(payload, "url", None) or "").strip()
    if not url:
        raise api.HTTPException(status_code=400, detail="url不能为空")
    pr = urlparse(url)
    if pr.scheme not in ("http", "https"):
        raise api.HTTPException(status_code=400, detail="仅支持 http/https url")

    allowed_hosts = [
        x.strip().lower()
        for x in (os.environ.get("A2A_KB_IMPORT_ALLOWED_HOSTS") or "").split(",")
        if x.strip()
    ]
    if allowed_hosts:
        host = (pr.hostname or "").strip().lower()
        if host not in allowed_hosts:
            raise api.HTTPException(status_code=403, detail="目标主机不在允许列表中")

    method = (getattr(payload, "method", None) or "GET").strip().upper()
    if method not in ("GET", "POST"):
        raise api.HTTPException(status_code=400, detail="method仅支持 GET/POST")

    headers = getattr(payload, "headers", None) or None
    params = getattr(payload, "params", None) or None
    body_json = getattr(payload, "body_json", None)
    timeout = float(getattr(payload, "timeout", None) or 20.0)

    def _do_request():
        return requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=body_json,
            timeout=timeout,
        )

    try:
        resp = await anyio.to_thread.run_sync(_do_request)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise api.HTTPException(status_code=502, detail=f"调用上游 API 失败: {e}")

    items_path = (getattr(payload, "items_path", None) or "").strip()
    if items_path:
        items = _get_json_path(data, items_path)
    else:
        items = data.get("items") if isinstance(data, dict) else data

    if isinstance(items, dict):
        items_list = [items]
    elif isinstance(items, list):
        items_list = items
    else:
        items_list = [items]

    max_items = int(getattr(payload, "max_items", None) or 50)
    doc_type = (getattr(payload, "doc_type", None) or "").strip() or "medical_kb"
    doc_id_field = (getattr(payload, "doc_id_field", None) or "").strip()
    title_field = (getattr(payload, "title_field", None) or "").strip()
    content_field = (getattr(payload, "content_field", None) or "").strip()
    content_fields = getattr(payload, "content_fields", None) or []
    content_fields = [str(x).strip() for x in content_fields if str(x).strip()]

    results: list[dict[str, Any]] = []
    total_chunks = 0
    ingested = 0
    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            for i, item in enumerate(items_list[:max_items]):
                doc_id_val = ""
                title_val = ""
                content_val = ""
                if isinstance(item, dict):
                    if doc_id_field:
                        doc_id_val = str(item.get(doc_id_field) or "").strip()
                    if title_field:
                        title_val = str(item.get(title_field) or "").strip()
                    if content_field:
                        content_val = str(item.get(content_field) or "").strip()
                    elif content_fields:
                        parts: list[str] = []
                        for f in content_fields:
                            v = item.get(f)
                            if v is None:
                                continue
                            s = str(v).strip()
                            if s:
                                parts.append(f"{f}: {s}")
                        content_val = "\n".join(parts).strip()
                    else:
                        content_val = json.dumps(item, ensure_ascii=False, indent=2)
                else:
                    content_val = str(item).strip()

                doc_id2 = doc_id_val or str(uuid.uuid4())
                title2 = title_val or f"API导入-{i+1}"
                content2 = (content_val or "").strip()
                if not content2:
                    results.append(
                        {"success": False, "doc_id": doc_id2, "error": "内容为空"}
                    )
                    continue

                text = "\n".join([f"标题: {title2}", f"内容: {content2}"]).strip()
                try:
                    inserted = api._upsert_rag_document(
                        cursor,
                        user_id=kb_uid,
                        source_type="medical_kb",
                        source_id=doc_id2,
                        record_type=doc_type,
                        title=title2,
                        text=text,
                    )
                    conn.commit()
                    inserted_i = int(inserted or 0)
                    if inserted_i > 0:
                        total_chunks += inserted_i
                        ingested += 1
                        results.append(
                            {
                                "success": True,
                                "doc_id": doc_id2,
                                "inserted_chunks": inserted_i,
                            }
                        )
                    else:
                        results.append(
                            {
                                "success": False,
                                "doc_id": doc_id2,
                                "error": "嵌入生成失败或超时，未写入向量分块",
                            }
                        )
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    results.append({"success": False, "doc_id": doc_id2, "error": str(e)})

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(getattr(payload, "global_kb", True)),
        "requested": len(items_list[:max_items]),
        "ingested": ingested,
        "inserted_chunks": total_chunks,
        "docs": results,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def bulk_upsert_medical_kb_docs(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    uid = api._resolve_user_id(request, getattr(payload, "user_id", None))
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    kb_uid = api._GLOBAL_KB_USER_ID if bool(getattr(payload, "global_kb", True)) else uid
    docs = getattr(payload, "docs", None) or []
    if not docs:
        raise api.HTTPException(status_code=400, detail="docs不能为空")

    results: list[dict[str, Any]] = []
    total_chunks = 0
    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            for d in docs:
                title = (getattr(d, "title", None) or "").strip()
                content = (getattr(d, "content", None) or "").strip()
                if not title or not content:
                    results.append(
                        {
                            "success": False,
                            "doc_id": getattr(d, "doc_id", None),
                            "error": "title 与 content 不能为空",
                        }
                    )
                    continue
                doc_id = (getattr(d, "doc_id", None) or "").strip() or str(uuid.uuid4())
                doc_type = (getattr(d, "doc_type", None) or "").strip() or "medical_kb"
                text = "\n".join([f"标题: {title}", f"内容: {content}"]).strip()
                try:
                    inserted = api._upsert_rag_document(
                        cursor,
                        user_id=kb_uid,
                        source_type="medical_kb",
                        source_id=doc_id,
                        record_type=doc_type,
                        title=title,
                        text=text,
                    )
                    conn.commit()
                    total_chunks += int(inserted or 0)
                    results.append(
                        {
                            "success": True,
                            "doc_id": doc_id,
                            "inserted_chunks": int(inserted or 0),
                        }
                    )
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    results.append(
                        {"success": False, "doc_id": doc_id, "error": str(e)}
                    )

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(getattr(payload, "global_kb", True)),
        "docs": results,
        "inserted_chunks": total_chunks,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def admin_import_medical_kb(api: Any, *, payload: Any, request: Any) -> dict[str, Any]:
    api._require_admin(request)

    es = api._get_embedding_service()
    if es is None:
        raise api.HTTPException(
            status_code=500,
            detail="EmbeddingService不可用，无法入库知识库文档",
        )

    docs = getattr(payload, "docs", None) or []
    if not docs:
        raise api.HTTPException(status_code=400, detail="docs不能为空")

    if bool(getattr(payload, "global_kb", True)):
        kb_uid = api._GLOBAL_KB_USER_ID
    else:
        kb_uid = (getattr(payload, "user_id", None) or "").strip()
        if not kb_uid:
            raise api.HTTPException(
                status_code=400, detail="global_kb=false时必须提供user_id"
            )

    results: list[dict[str, Any]] = []
    total_chunks = 0
    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            for d in docs:
                title = (getattr(d, "title", None) or "").strip()
                content = (getattr(d, "content", None) or "").strip()
                if not title or not content:
                    results.append(
                        {
                            "success": False,
                            "doc_id": getattr(d, "doc_id", None),
                            "error": "title 与 content 不能为空",
                        }
                    )
                    continue
                doc_id = (getattr(d, "doc_id", None) or "").strip() or str(uuid.uuid4())
                doc_type = (getattr(d, "doc_type", None) or "").strip() or "medical_kb"
                text = "\n".join([f"标题: {title}", f"内容: {content}"]).strip()
                try:
                    inserted = api._upsert_rag_document(
                        cursor,
                        user_id=kb_uid,
                        source_type="medical_kb",
                        source_id=doc_id,
                        record_type=doc_type,
                        title=title,
                        text=text,
                    )
                    conn.commit()
                    total_chunks += int(inserted or 0)
                    results.append(
                        {
                            "success": True,
                            "doc_id": doc_id,
                            "inserted_chunks": int(inserted or 0),
                        }
                    )
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    results.append(
                        {"success": False, "doc_id": doc_id, "error": str(e)}
                    )

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(getattr(payload, "global_kb", True)),
        "docs": results,
        "inserted_chunks": total_chunks,
        "model": getattr(es, "model_name", None),
        "embedding_dim": getattr(es, "dimension", None),
    }


async def admin_delete_medical_kb_doc(
    api: Any,
    *,
    doc_id: str,
    global_kb: bool,
    user_id: Any,
    request: Any,
) -> dict[str, Any]:
    api._require_admin(request)

    did = (doc_id or "").strip()
    if not did:
        raise api.HTTPException(status_code=400, detail="doc_id不能为空")

    if global_kb:
        kb_uid = api._GLOBAL_KB_USER_ID
    else:
        kb_uid = (user_id or "").strip()
        if not kb_uid:
            raise api.HTTPException(
                status_code=400, detail="global_kb=false时必须提供user_id"
            )

    deleted = 0
    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                api._ensure_rag_schema(cursor)
                cursor.execute(
                    """
                    DELETE FROM rag_documents
                    WHERE user_id = %s AND source_type = 'medical_kb' AND source_id = %s
                    """,
                    (kb_uid, did),
                )
                cursor.execute(
                    """
                    DELETE FROM rag_chunks
                    WHERE user_id = %s AND source_type = 'medical_kb' AND source_id = %s
                    """,
                    (kb_uid, did),
                )
                deleted = int(cursor.rowcount or 0)
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise api.HTTPException(status_code=500, detail=f"删除知识库文档失败: {e}")

    return {
        "success": True,
        "doc_id": did,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "deleted_chunks": deleted,
    }


async def list_medical_kb_docs(
    api: Any,
    *,
    user_id: Any,
    global_kb: bool,
    limit: int,
    offset: int,
    request: Any,
) -> dict[str, Any]:
    uid = api._resolve_user_id(request, user_id)
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    kb_uid = api._GLOBAL_KB_USER_ID if global_kb else uid

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            api._ensure_rag_schema(cursor)
            cursor.execute(
                """
                SELECT
                    source_id AS doc_id,
                    COALESCE(title, '') AS title,
                    COALESCE(record_type, '') AS doc_type,
                    chunk_count AS chunks,
                    created_at,
                    updated_at
                FROM (
                    SELECT DISTINCT ON (source_id)
                        source_id, title, record_type, chunk_count, created_at, updated_at
                    FROM rag_documents
                    WHERE user_id = %s AND source_type = 'medical_kb'
                    ORDER BY source_id, updated_at DESC
                ) t
                ORDER BY updated_at DESC
                LIMIT %s OFFSET %s
                """,
                (kb_uid, limit, offset),
            )
            rows = cursor.fetchall() or []

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "count": len(rows),
        "items": rows,
        "limit": limit,
        "offset": offset,
    }


async def get_medical_kb_stats(
    api: Any, *, user_id: Any, global_kb: bool, request: Any
) -> dict[str, Any]:
    uid = api._resolve_user_id(request, user_id)
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    kb_uid = api._GLOBAL_KB_USER_ID if global_kb else uid

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            api._ensure_rag_schema(cursor)
            cursor.execute(
                """
                SELECT
                    COUNT(1) AS docs,
                    COALESCE(SUM(chunk_count), 0) AS chunks,
                    MAX(updated_at) AS last_updated
                FROM rag_documents
                WHERE user_id = %s AND source_type = 'medical_kb'
                """,
                (kb_uid,),
            )
            total = cursor.fetchone() or {}
            cursor.execute(
                """
                SELECT embedding_model, COUNT(1) AS docs
                FROM rag_documents
                WHERE user_id = %s AND source_type = 'medical_kb'
                GROUP BY embedding_model
                ORDER BY COUNT(1) DESC
                """,
                (kb_uid,),
            )
            models = cursor.fetchall() or []

    return {
        "success": True,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "docs": int(total.get("docs") or 0),
        "chunks": int(total.get("chunks") or 0),
        "last_updated": total.get("last_updated"),
        "models": models,
    }


async def delete_medical_kb_doc(
    api: Any, *, doc_id: str, user_id: Any, global_kb: bool, request: Any
) -> dict[str, Any]:
    uid = api._resolve_user_id(request, user_id)
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    kb_uid = api._GLOBAL_KB_USER_ID if global_kb else uid
    did = (doc_id or "").strip()
    if not did:
        raise api.HTTPException(status_code=400, detail="doc_id不能为空")

    with api.get_db_connection() as conn:
        with conn.cursor() as cursor:
            try:
                api._ensure_rag_schema(cursor)
                cursor.execute(
                    """
                    DELETE FROM rag_documents
                    WHERE user_id = %s AND source_type = 'medical_kb' AND source_id = %s
                    """,
                    (kb_uid, did),
                )
                cursor.execute(
                    """
                    DELETE FROM rag_chunks
                    WHERE user_id = %s AND source_type = 'medical_kb' AND source_id = %s
                    """,
                    (kb_uid, did),
                )
                deleted = int(cursor.rowcount or 0)
                conn.commit()
            except Exception as e:
                try:
                    conn.rollback()
                except Exception:
                    pass
                raise api.HTTPException(status_code=500, detail=f"删除知识库文档失败: {e}")

    return {
        "success": True,
        "doc_id": did,
        "user_id": kb_uid,
        "global_kb": bool(global_kb),
        "deleted_chunks": deleted,
    }
