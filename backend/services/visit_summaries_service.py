from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import anyio

_VISIT_SUMMARY_BATCHES: dict[str, dict[str, Any]] = {}


def prune_visit_summary_batches(api: Any) -> None:
    ttl_seconds = int(os.getenv("VISIT_SUMMARY_BATCH_TTL_SECONDS", "3600"))
    now_ts = time.time()
    for bid, b in list(_VISIT_SUMMARY_BATCHES.items()):
        try:
            created = float(b.get("created_ts") or 0.0)
        except Exception:
            created = 0.0
        if created <= 0:
            _VISIT_SUMMARY_BATCHES.pop(bid, None)
            continue
        if now_ts - created > ttl_seconds:
            _VISIT_SUMMARY_BATCHES.pop(bid, None)


def merge_visit_summary_fields(items: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "visit_date": None,
        "hospital": None,
        "department": None,
        "doctor": None,
        "chief_complaint": None,
        "symptoms": None,
        "examination": None,
        "diagnosis": None,
        "treatment": None,
        "prescription": None,
        "follow_up": None,
        "notes": None,
    }

    def first_non_empty(key: str) -> None:
        if merged.get(key):
            return
        for it in items:
            v = (it.get(key) if isinstance(it, dict) else None) or None
            if isinstance(v, str) and not v.strip():
                v = None
            if v:
                merged[key] = v
                return

    for k in [
        "hospital",
        "department",
        "doctor",
        "chief_complaint",
        "symptoms",
        "treatment",
        "follow_up",
    ]:
        first_non_empty(k)

    for it in items:
        vd = it.get("visit_date") if isinstance(it, dict) else None
        if isinstance(vd, date):
            merged["visit_date"] = vd
            break

    def merge_text(key: str, sep: str = "\n") -> None:
        parts: list[str] = []
        for it in items:
            v = it.get(key) if isinstance(it, dict) else None
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
        if not parts:
            return
        uniq: list[str] = []
        seen: set[str] = set()
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            uniq.append(p)
        merged[key] = sep.join(uniq).strip()

    merge_text("examination")
    merge_text("diagnosis", sep="；")
    merge_text("prescription")
    merge_text("notes", sep="\n\n")
    return merged


async def process_visit_summary_batch_item_ocr(
    api: Any,
    *,
    batch_id: str,
    user_id: str,
    file_id: str,
    file_path: str,
    mime_type: str,
    original_filename: str,
) -> None:
    try:
        p = Path(file_path)
        file_bytes = await anyio.to_thread.run_sync(p.read_bytes)
        if not file_bytes:
            raise ValueError("empty file")

        if not api.extract_text_from_image:
            raise ValueError("ocr tool missing")

        b64 = base64.b64encode(file_bytes).decode("utf-8")
        raw_ocr = await anyio.to_thread.run_sync(
            lambda: (
                api.extract_text_from_image.fn(b64)
                if hasattr(api.extract_text_from_image, "fn")
                else api.extract_text_from_image(b64)
            )
        )
        if isinstance(raw_ocr, str):
            ocr_err_prefixes = (
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
            if raw_ocr.startswith(ocr_err_prefixes):
                raise ValueError(raw_ocr[:200])
        ocr_text = api._normalize_ocr_text(raw_ocr)
        extracted = api._extract_visit_summary_fields(ocr_text) if ocr_text.strip() else {}

        batch = _VISIT_SUMMARY_BATCHES.get(batch_id)
        if not isinstance(batch, dict) or batch.get("user_id") != user_id:
            return
        items = batch.get("items")
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("file_id") or "") != str(file_id):
                continue
            it["ocr_text"] = ocr_text
            it["extracted"] = extracted
            it["ocr_status"] = "done"
            it.pop("ocr_error", None)
            break
    except Exception as e:
        batch = _VISIT_SUMMARY_BATCHES.get(batch_id)
        if not isinstance(batch, dict) or batch.get("user_id") != user_id:
            return
        items = batch.get("items")
        if not isinstance(items, list):
            return
        for it in items:
            if not isinstance(it, dict):
                continue
            if str(it.get("file_id") or "") != str(file_id):
                continue
            it["ocr_status"] = "failed"
            it["ocr_error"] = str(e)[:300]
            break


async def finalize_visit_summary_batch(
    api: Any,
    *,
    summary_id: str,
    user_id: str,
    batch_id: str,
    visit_date_override: date | None,
) -> None:
    started = datetime.now()
    batch = _VISIT_SUMMARY_BATCHES.get(batch_id)
    try:
        if not isinstance(batch, dict) or batch.get("user_id") != user_id:
            raise ValueError("batch missing")

        tasks_map = batch.get("tasks")
        tasks = list(tasks_map.values()) if isinstance(tasks_map, dict) else []
        timeout_sec = float(
            os.getenv("VISIT_SUMMARY_BATCH_PROCESS_TIMEOUT_SECONDS", "900")
        )
        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=timeout_sec,
                )
            except asyncio.TimeoutError:
                raise ValueError("batch processing timeout")

        items = batch.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("empty batch")

        file_ids: list[str] = []
        ocr_texts: list[str] = []
        extracted_list: list[dict[str, Any]] = []
        ocr_failed = 0
        for it in items:
            if not isinstance(it, dict):
                continue
            fid = str(it.get("file_id") or "").strip()
            if fid:
                file_ids.append(fid)
            if str(it.get("ocr_status") or "") == "failed":
                ocr_failed += 1
            txt = str(it.get("ocr_text") or "")
            if txt.strip():
                ocr_texts.append(txt.strip())
            ext = it.get("extracted")
            if isinstance(ext, dict):
                extracted_list.append(ext)

        if not ocr_texts:
            raise ValueError("no ocr text")

        extracted_merged = merge_visit_summary_fields(extracted_list)
        if visit_date_override:
            extracted_merged["visit_date"] = visit_date_override

        combined_text = "\n\n".join(ocr_texts).strip()
        agent_summary_text, agent_fields, agent_raw = (
            api._try_generate_visit_summary_with_agent_multi(ocr_texts)
        )
        llm_summary = await api._maybe_llm_summary(combined_text, extracted_merged)
        summary_content = (
            llm_summary
            or agent_summary_text
            or api._generate_ai_summary(combined_text, extracted_merged)
        )

        diagnosis_val = extracted_merged.get("diagnosis")
        if (not diagnosis_val) and isinstance(agent_fields, dict):
            diagnosis_val = agent_fields.get("diagnosis") or diagnosis_val
        extracted_merged["diagnosis"] = diagnosis_val

        prescription_val = extracted_merged.get("prescription")
        if (not prescription_val) and isinstance(agent_fields, dict):
            med_names = agent_fields.get("medication_names")
            if isinstance(med_names, list) and med_names:
                prescription_val = "；".join(
                    [str(x).strip() for x in med_names if str(x).strip()]
                )
        if prescription_val:
            extracted_merged["prescription"] = prescription_val

        notes_val = extracted_merged.get("notes")
        if summary_content:
            if notes_val:
                notes_val = f"{notes_val}\n\n{summary_content}"
            else:
                notes_val = summary_content
        summary_content = api._sanitize_text_value(summary_content)
        notes_val = api._sanitize_text_value(notes_val)
        agent_raw = api._ensure_jsonable(agent_raw)

        cleaned_fields = {
            "doctor": api._sanitize_text_value(extracted_merged.get("doctor")),
            "hospital": api._sanitize_text_value(extracted_merged.get("hospital")),
            "department": api._sanitize_text_value(extracted_merged.get("department")),
            "chief_complaint": api._sanitize_text_value(
                extracted_merged.get("chief_complaint")
            ),
            "symptoms": api._sanitize_text_value(extracted_merged.get("symptoms")),
            "examination": api._sanitize_text_value(extracted_merged.get("examination")),
            "diagnosis": api._sanitize_text_value(diagnosis_val),
            "treatment": api._sanitize_text_value(extracted_merged.get("treatment")),
            "prescription": api._sanitize_text_value(
                extracted_merged.get("prescription")
            ),
            "follow_up": api._sanitize_text_value(extracted_merged.get("follow_up")),
        }

        tests_val: list[dict[str, Any]] = []
        tests_val.append(
            {
                "type": "batch",
                "data": {
                    "batch_id": batch_id,
                    "total": len(file_ids),
                    "ocr_failed": int(ocr_failed),
                    "started_at": started.isoformat(),
                    "completed_at": datetime.now().isoformat(),
                },
            }
        )
        if agent_raw:
            tests_val.append({"type": "agent_summary", "data": agent_raw})

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                notify_openid = None
                try:
                    cursor.execute(
                        "SELECT openid FROM users WHERE user_id = %s LIMIT 1",
                        (user_id,),
                    )
                    urow = cursor.fetchone()
                    if isinstance(urow, dict):
                        notify_openid = (urow.get("openid") or "").strip() or None
                except Exception:
                    notify_openid = None
                cursor.execute(
                    """
                    UPDATE visit_summaries
                    SET
                        visit_date = %s,
                        doctor = %s,
                        hospital = %s,
                        department = %s,
                        chief_complaint = %s,
                        symptoms = %s,
                        examination = %s,
                        diagnosis = %s,
                        treatment = %s,
                        prescription = %s,
                        follow_up = %s,
                        summary_content = %s,
                        notes = %s,
                        tests = %s,
                        status = %s,
                        error_message = NULL,
                        updated_at = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (
                        extracted_merged.get("visit_date"),
                        cleaned_fields["doctor"],
                        cleaned_fields["hospital"],
                        cleaned_fields["department"],
                        cleaned_fields["chief_complaint"],
                        cleaned_fields["symptoms"],
                        cleaned_fields["examination"],
                        cleaned_fields["diagnosis"],
                        cleaned_fields["treatment"],
                        cleaned_fields["prescription"],
                        cleaned_fields["follow_up"],
                        summary_content,
                        notes_val,
                        api.Json(tests_val),
                        "done",
                        datetime.now(),
                        summary_id,
                        user_id,
                    ),
                )
                conn.commit()

        try:
            from notification_service import notification_service as notify_svc

            template_id = (
                getattr(notify_svc, "template_ids", {}).get("task_complete", "")
                if notify_svc
                else ""
            )
            if notify_svc and template_id and notify_openid:
                raw = os.getenv("WECHAT_VISIT_SUMMARY_TEMPLATE_DATA_JSON", "").strip()
                visit_dt = extracted_merged.get("visit_date")
                try:
                    visit_dt_str = (
                        visit_dt.isoformat()
                        if hasattr(visit_dt, "isoformat")
                        else str(visit_dt or "")
                    )
                except Exception:
                    visit_dt_str = str(visit_dt or "")

                vars_map = {
                    "visit_date": visit_dt_str,
                    "hospital": str(cleaned_fields.get("hospital") or "").strip(),
                    "department": str(cleaned_fields.get("department") or "").strip(),
                    "doctor": str(cleaned_fields.get("doctor") or "").strip(),
                    "diagnosis": str(cleaned_fields.get("diagnosis") or "").strip(),
                    "summary": str(summary_content or "").strip(),
                    "datetime": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "time": datetime.now().strftime("%H:%M"),
                }
                if raw:
                    try:
                        mapping = json.loads(raw)
                        if isinstance(mapping, dict):
                            data = {}
                            for k, v in mapping.items():
                                try:
                                    data[str(k)] = {"value": str(v).format(**vars_map)}
                                except Exception:
                                    data[str(k)] = {"value": str(v)}
                        else:
                            data = None
                    except Exception:
                        data = None
                else:
                    data = None
                if not isinstance(data, dict):
                    title = vars_map["hospital"] or "就诊摘要"
                    subtitle = vars_map["diagnosis"] or "已生成"
                    data = {
                        "thing1": {"value": title},
                        "thing2": {"value": subtitle},
                        "time3": {"value": vars_map["datetime"]},
                    }

                dedupe_key = f"wechat:visit_summary:done:{summary_id}"
                enqueued = False
                try:
                    enqueued = notify_svc.enqueue_subscribe_message(
                        openid=notify_openid,
                        template_id=template_id,
                        data=data,
                        page="pages/visit-summary/visit-summary",
                        dedupe_key=dedupe_key,
                        dedupe_ttl_sec=24 * 3600,
                        extra={
                            "type": "visit_summary_done",
                            "summary_id": str(summary_id),
                            "batch_id": str(batch_id),
                            "user_id": str(user_id),
                        },
                    )
                except Exception:
                    enqueued = False
                if not enqueued:
                    try:
                        await notify_svc.send_subscribe_message(
                            openid=notify_openid,
                            template_id=template_id,
                            data=data,
                            page="pages/visit-summary/visit-summary",
                        )
                    except Exception:
                        pass
        except Exception:
            pass
    except Exception as e:
        try:
            with api.get_db_connection() as conn:
                with conn.cursor(row_factory=api.dict_row) as cursor:
                    cursor.execute(
                        """
                        UPDATE visit_summaries
                        SET status = %s, error_message = %s, updated_at = %s
                        WHERE id = %s AND user_id = %s
                        """,
                        ("failed", str(e)[:800], datetime.now(), summary_id, user_id),
                    )
                    conn.commit()
        except Exception:
            pass
    finally:
        _VISIT_SUMMARY_BATCHES.pop(batch_id, None)


async def analyze_visit_summary_image(
    api: Any,
    *,
    file: Any,
    user_id: Any,
    visit_date: Any,
    request: Any,
) -> Any:
    limiter = api._get_upload_limiter()
    await limiter.acquire()
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise api.HTTPException(status_code=401, detail="未认证用户")

        ct = (getattr(file, "content_type", None) or "").strip().lower()
        if not ct.startswith("image/"):
            raise api.HTTPException(status_code=400, detail="仅支持图片上传")

        file_id = api.generate_id()
        ext = Path(file.filename or "").suffix
        saved_name = f"{file_id}{ext}"
        saved_path = api.UPLOAD_DIR / saved_name

        max_size = 10 * 1024 * 1024
        chunk_size = int(
            os.getenv("HEALTH_RECORDS_UPLOAD_CHUNK_BYTES", str(1024 * 1024))
        )
        file_size = 0
        content_buf = bytearray()
        try:
            with open(saved_path, "wb") as out:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    if file_size > max_size:
                        try:
                            out.close()
                        except Exception:
                            pass
                        try:
                            os.remove(saved_path)
                        except Exception:
                            pass
                        raise api.HTTPException(
                            status_code=400, detail="文件大小超过限制（10MB）"
                        )
                    await anyio.to_thread.run_sync(out.write, chunk)
                    content_buf.extend(chunk)
        finally:
            try:
                await file.close()
            except Exception:
                pass

        content = bytes(content_buf)

        with api.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO file_attachments (id, record_id, filename, original_filename, file_path, file_size, mime_type)
                    VALUES (%s, NULL, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id,
                        saved_name,
                        file.filename or saved_name,
                        str(saved_path),
                        file_size,
                        ct,
                    ),
                )
                conn.commit()

        if not api.extract_text_from_image:
            raise api.HTTPException(status_code=503, detail="OCR模块未加载，无法识别图片")

        b64 = base64.b64encode(content).decode("utf-8")
        raw_ocr = (
            api.extract_text_from_image.fn(b64)
            if hasattr(api.extract_text_from_image, "fn")
            else api.extract_text_from_image(b64)
        )
        if isinstance(raw_ocr, str):
            ocr_err_prefixes = (
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
            if raw_ocr.startswith(ocr_err_prefixes):
                raise api.HTTPException(status_code=503, detail=raw_ocr[:800])
        ocr_text = api._normalize_ocr_text(raw_ocr)
        if not ocr_text.strip():
            raise api.HTTPException(status_code=422, detail="OCR识别结果为空")

        extracted = api._extract_visit_summary_fields(ocr_text)
        vd_override = (
            api._parse_date_str(visit_date) if isinstance(visit_date, str) else None
        )
        if vd_override:
            extracted["visit_date"] = vd_override

        summary_id = api.generate_id()
        summary_title = f"就诊记录OCR - {(file.filename or '').strip() or 'image'}"
        agent_summary_text, agent_fields, agent_raw = api._try_generate_visit_summary_with_agent(
            ocr_text
        )
        llm_summary = await api._maybe_llm_summary(ocr_text, extracted)
        summary_content = (
            llm_summary
            or agent_summary_text
            or api._generate_ai_summary(ocr_text, extracted)
        )
        diagnosis_val = extracted.get("diagnosis")
        if (not diagnosis_val) and isinstance(agent_fields, dict):
            diagnosis_val = agent_fields.get("diagnosis") or diagnosis_val
        if not diagnosis_val:
            for src in (summary_content, ocr_text):
                s = (src or "").strip()
                if not s:
                    continue
                m = api.re.search(
                    r"(?:诊断印象|诊断意见|临床诊断|初步诊断|入院诊断|出院诊断|诊断|印象)\s*[:：]?\s*([^\n；;。]{2,80})",
                    s,
                )
                if m:
                    v = (m.group(1) or "").strip()
                    if v:
                        diagnosis_val = v
                        break
        extracted["diagnosis"] = diagnosis_val

        prescription_val = extracted.get("prescription")
        if (not prescription_val) and isinstance(agent_fields, dict):
            med_names = agent_fields.get("medication_names")
            if isinstance(med_names, list) and med_names:
                prescription_val = "；".join(
                    [str(x).strip() for x in med_names if str(x).strip()]
                )
        if prescription_val:
            extracted["prescription"] = prescription_val
        notes_val = extracted.get("notes")
        if summary_content:
            if notes_val:
                notes_val = f"{notes_val}\n\n{summary_content}"
            else:
                notes_val = summary_content
        summary_content = api._sanitize_text_value(summary_content)
        notes_val = api._sanitize_text_value(notes_val)
        agent_raw = api._ensure_jsonable(agent_raw)
        cleaned_fields = {
            "doctor": api._sanitize_text_value(extracted.get("doctor")),
            "hospital": api._sanitize_text_value(extracted.get("hospital")),
            "department": api._sanitize_text_value(extracted.get("department")),
            "chief_complaint": api._sanitize_text_value(
                extracted.get("chief_complaint")
            ),
            "symptoms": api._sanitize_text_value(extracted.get("symptoms")),
            "examination": api._sanitize_text_value(extracted.get("examination")),
            "diagnosis": api._sanitize_text_value(diagnosis_val),
            "treatment": api._sanitize_text_value(extracted.get("treatment")),
            "prescription": api._sanitize_text_value(extracted.get("prescription")),
            "follow_up": api._sanitize_text_value(extracted.get("follow_up")),
        }

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                cursor.execute(
                    """
                    INSERT INTO visit_summaries (
                        id, user_id, title, visit_date, doctor, hospital, department,
                        chief_complaint, symptoms, examination, diagnosis, treatment,
                        prescription, follow_up, summary_content, notes, files, tests, is_deleted,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s
                    ) RETURNING id
                    """,
                    (
                        summary_id,
                        uid,
                        summary_title,
                        extracted.get("visit_date"),
                        cleaned_fields["doctor"],
                        cleaned_fields["hospital"],
                        cleaned_fields["department"],
                        cleaned_fields["chief_complaint"],
                        cleaned_fields["symptoms"],
                        cleaned_fields["examination"],
                        cleaned_fields["diagnosis"],
                        cleaned_fields["treatment"],
                        cleaned_fields["prescription"],
                        cleaned_fields["follow_up"],
                        summary_content,
                        notes_val,
                        api.Json([file_id]),
                        api.Json(
                            [{"type": "agent_summary", "data": agent_raw}] if agent_raw else []
                        ),
                        0,
                        datetime.now(),
                        datetime.now(),
                    ),
                )
                new_id = cursor.fetchone()["id"]
                conn.commit()
                cursor.execute(
                    "SELECT * FROM visit_summaries WHERE id = %s", (new_id,)
                )
                row = cursor.fetchone()

        for k in list(row.keys()):
            row[k] = api._sanitize_json_value(row.get(k))
        for field in ["files", "tests"]:
            if isinstance(row.get(field), str):
                try:
                    row[field] = json.loads(row[field])
                except Exception:
                    row[field] = []
            elif row.get(field) is None:
                row[field] = []

        return api.VisitSummary(**row)
    except api.HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"就诊摘要图片识别失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))
    finally:
        limiter.release()


async def collect_visit_summary_image(
    api: Any,
    *,
    file: Any,
    batch_id: Any,
    user_id: Any,
    request: Any,
) -> dict[str, Any]:
    limiter = api._get_upload_limiter()
    await limiter.acquire()
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise api.HTTPException(status_code=401, detail="未认证用户")

        bid = (batch_id or "").strip()
        if len(bid) < 4:
            raise api.HTTPException(status_code=400, detail="batch_id 无效")

        ct = (getattr(file, "content_type", None) or "").strip().lower()
        if not ct.startswith("image/"):
            raise api.HTTPException(status_code=400, detail="仅支持图片上传")

        file_id = api.generate_id()
        ext = Path(file.filename or "").suffix
        saved_name = f"{file_id}{ext}"
        saved_path = api.UPLOAD_DIR / saved_name

        max_size = 10 * 1024 * 1024
        chunk_size = int(
            os.getenv("HEALTH_RECORDS_UPLOAD_CHUNK_BYTES", str(1024 * 1024))
        )
        file_size = 0
        try:
            with open(saved_path, "wb") as out:
                while True:
                    chunk = await file.read(chunk_size)
                    if not chunk:
                        break
                    file_size += len(chunk)
                    if file_size > max_size:
                        try:
                            out.close()
                        except Exception:
                            pass
                        try:
                            os.remove(saved_path)
                        except Exception:
                            pass
                        raise api.HTTPException(
                            status_code=400, detail="文件大小超过限制（10MB）"
                        )
                    await anyio.to_thread.run_sync(out.write, chunk)
        finally:
            try:
                await file.close()
            except Exception:
                pass

        with api.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO file_attachments (id, record_id, filename, original_filename, file_path, file_size, mime_type)
                    VALUES (%s, NULL, %s, %s, %s, %s, %s)
                    """,
                    (
                        file_id,
                        saved_name,
                        file.filename or saved_name,
                        str(saved_path),
                        file_size,
                        ct,
                    ),
                )
                conn.commit()

        prune_visit_summary_batches(api)
        batch = _VISIT_SUMMARY_BATCHES.get(bid)
        if not batch:
            batch = {
                "user_id": uid,
                "created_ts": time.time(),
                "items": [],
                "tasks": {},
            }
            _VISIT_SUMMARY_BATCHES[bid] = batch
        if batch.get("user_id") != uid:
            raise api.HTTPException(status_code=403, detail="batch_id 不属于当前用户")

        batch_items = batch.get("items")
        if not isinstance(batch_items, list):
            batch_items = []
            batch["items"] = batch_items
        tasks_map = batch.get("tasks")
        if not isinstance(tasks_map, dict):
            tasks_map = {}
            batch["tasks"] = tasks_map
        batch_items.append(
            {
                "file_id": str(file_id),
                "original_filename": (file.filename or saved_name),
                "file_path": str(saved_path),
                "mime_type": ct,
                "ocr_status": "pending",
            }
        )
        tasks_map[str(file_id)] = asyncio.create_task(
            process_visit_summary_batch_item_ocr(
                api,
                batch_id=bid,
                user_id=uid,
                file_id=str(file_id),
                file_path=str(saved_path),
                mime_type=ct,
                original_filename=(file.filename or saved_name),
            )
        )

        return {
            "batch_id": bid,
            "count": len(batch_items),
            "file_id": str(file_id),
        }
    finally:
        limiter.release()


async def complete_visit_summary_batch(
    api: Any,
    *,
    payload: Any,
    user_id: Any,
    request: Any,
) -> Any:
    uid = api._resolve_user_id(request, user_id)
    if not uid:
        raise api.HTTPException(status_code=401, detail="未认证用户")

    bid = (payload.batch_id or "").strip()
    batch = _VISIT_SUMMARY_BATCHES.get(bid)
    if not batch:
        raise api.HTTPException(status_code=404, detail="未找到批量任务")
    if batch.get("user_id") != uid:
        raise api.HTTPException(status_code=403, detail="无权访问该批量任务")

    batch_items = batch.get("items") if isinstance(batch, dict) else None
    if not isinstance(batch_items, list) or not batch_items:
        raise api.HTTPException(status_code=400, detail="批量任务为空")

    vd_override = api._parse_date_str(payload.visit_date) if payload.visit_date else None
    summary_id = api.generate_id()
    summary_title = "就诊记录批量汇总"
    file_ids: list[str] = []
    for it in batch_items:
        if not isinstance(it, dict):
            continue
        fid = str(it.get("file_id") or "").strip()
        if fid:
            file_ids.append(fid)

    with api.get_db_connection() as conn:
        with conn.cursor(row_factory=api.dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO visit_summaries (
                    id, user_id, title, visit_date, doctor, hospital, department,
                    chief_complaint, symptoms, examination, diagnosis, treatment,
                    prescription, follow_up, summary_content, notes, files, tests, is_deleted,
                    status, error_message, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                ) RETURNING id
                """,
                (
                    summary_id,
                    uid,
                    summary_title,
                    vd_override,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    api.Json(file_ids),
                    api.Json(
                        [
                            {
                                "type": "batch",
                                "data": {
                                    "batch_id": bid,
                                    "total": len(file_ids),
                                    "submitted_at": datetime.now().isoformat(),
                                },
                            }
                        ]
                    ),
                    0,
                    "processing",
                    None,
                    datetime.now(),
                    datetime.now(),
                ),
            )
            new_id = cursor.fetchone()["id"]
            conn.commit()
            cursor.execute("SELECT * FROM visit_summaries WHERE id = %s", (new_id,))
            row = cursor.fetchone()

    for k in list(row.keys()):
        row[k] = api._sanitize_json_value(row.get(k))
    for field in ["files", "tests"]:
        if isinstance(row.get(field), str):
            try:
                row[field] = json.loads(row[field])
            except Exception:
                row[field] = []
        elif row.get(field) is None:
            row[field] = []

    asyncio.create_task(
        finalize_visit_summary_batch(
            api,
            summary_id=summary_id,
            user_id=uid,
            batch_id=bid,
            visit_date_override=vd_override,
        )
    )
    return api.VisitSummary(**row)


async def get_visit_summary_count(
    api: Any,
    *,
    user_id: Any,
    request: Any,
) -> dict[str, int]:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            return {"count": 0}

        with api.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(1) FROM visit_summaries WHERE user_id = %s",
                    (uid,),
                )
                row = cursor.fetchone()
                count = int(row[0] or 0) if row else 0
        return {"count": count}
    except Exception as e:
        api.logger.error(f"获取就诊摘要数量失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))


async def get_visit_summaries(
    api: Any,
    *,
    skip: int,
    limit: int,
    user_id: Any,
    request: Any,
) -> Any:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            return []

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT * FROM visit_summaries
                    WHERE user_id = %s
                    ORDER BY visit_date DESC NULLS LAST, created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (uid, limit, skip),
                )
                rows = cursor.fetchall()
                results = []
                for row in rows:
                    for k in list(row.keys()):
                        row[k] = api._sanitize_json_value(row.get(k))
                    for field in ["files", "tests"]:
                        if isinstance(row.get(field), str):
                            try:
                                row[field] = json.loads(row[field])
                            except Exception:
                                row[field] = []
                        elif row.get(field) is None:
                            row[field] = []
                    if not (row.get("diagnosis") or "").strip():
                        for src in (row.get("summary_content"), row.get("notes")):
                            s = (src or "").strip()
                            if not s:
                                continue
                            m = re.search(
                                r"(?:诊断印象|诊断意见|临床诊断|初步诊断|入院诊断|出院诊断|诊断|印象)\s*[:：]?\s*([^\n；;。]{2,80})",
                                s,
                            )
                            if m:
                                v = (m.group(1) or "").strip()
                                if v:
                                    row["diagnosis"] = v
                                    break
                    if not (row.get("hospital") or "").strip():
                        for src in (row.get("summary_content"), row.get("notes")):
                            s = (src or "").strip()
                            if not s:
                                continue
                            m = re.search(
                                r"(?:医院|医疗机构名称|医疗机构|机构名称)\s*[:：]?\s*([^\n；;。]{2,80})",
                                s,
                            )
                            if m:
                                v = (m.group(1) or "").strip()
                                if v:
                                    row["hospital"] = v
                                    break
                    results.append(api.VisitSummary(**row))
                return results
    except Exception as e:
        api.logger.error(f"获取就诊摘要失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))


async def get_visit_summary_detail(
    api: Any,
    *,
    summary_id: str,
    user_id: Any,
    request: Any,
) -> Any:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise api.HTTPException(status_code=401, detail="未认证用户")

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                cursor.execute(
                    "SELECT * FROM visit_summaries WHERE id = %s AND user_id = %s",
                    (summary_id, uid),
                )
                row = cursor.fetchone()
                if not row:
                    raise api.HTTPException(status_code=404, detail="就诊摘要不存在或无权访问")

                for k in list(row.keys()):
                    row[k] = api._sanitize_json_value(row.get(k))

                for field in ["files", "tests"]:
                    if isinstance(row.get(field), str):
                        try:
                            row[field] = json.loads(row[field])
                        except Exception:
                            row[field] = []
                    elif row.get(field) is None:
                        row[field] = []

                if not (row.get("diagnosis") or "").strip():
                    for src in (row.get("summary_content"), row.get("notes")):
                        s = (src or "").strip()
                        if not s:
                            continue
                        m = re.search(
                            r"(?:诊断印象|诊断意见|临床诊断|初步诊断|入院诊断|出院诊断|诊断|印象)\s*[:：]?\s*([^\n；;。]{2,80})",
                            s,
                        )
                        if m:
                            v = (m.group(1) or "").strip()
                            if v:
                                row["diagnosis"] = v
                                break

                if not (row.get("hospital") or "").strip():
                    for src in (row.get("summary_content"), row.get("notes")):
                        s = (src or "").strip()
                        if not s:
                            continue
                        m = re.search(
                            r"(?:医院|医疗机构名称|医疗机构|机构名称)\s*[:：]?\s*([^\n；;。]{2,80})",
                            s,
                        )
                        if m:
                            v = (m.group(1) or "").strip()
                            if v:
                                row["hospital"] = v
                                break

                return api.VisitSummary(**row)
    except api.HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"获取就诊摘要详情失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))


async def create_visit_summary(
    api: Any,
    *,
    summary: Any,
    user_id: Any,
    request: Any,
) -> Any:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise api.HTTPException(status_code=401, detail="未认证用户")

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                new_id = summary.summary_id or api.generate_id()
                now = datetime.now()
                title = (summary.title or "").strip() or "就诊摘要"
                summary_content_val = (summary.summary_content or "").strip() or None
                notes = summary.notes
                if (not notes) and summary_content_val:
                    notes = summary_content_val

                cursor.execute("SELECT id FROM visit_summaries WHERE id = %s", (new_id,))
                if cursor.fetchone():
                    raise api.HTTPException(status_code=400, detail="摘要ID已存在")

                cursor.execute(
                    """
                    INSERT INTO visit_summaries (
                        id, user_id, title, visit_date, doctor, hospital, department,
                        chief_complaint, symptoms, examination, diagnosis, treatment,
                        prescription, follow_up, summary_content, notes, files, tests, is_deleted,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s
                    ) RETURNING id
                    """,
                    (
                        new_id,
                        uid,
                        title,
                        summary.visit_date,
                        summary.doctor,
                        summary.hospital,
                        summary.department,
                        summary.chief_complaint,
                        summary.symptoms,
                        summary.examination,
                        summary.diagnosis,
                        summary.treatment,
                        summary.prescription,
                        summary.follow_up,
                        summary_content_val,
                        notes,
                        api.Json(summary.files or []),
                        api.Json(summary.tests or []),
                        0,
                        now,
                        now,
                    ),
                )
                new_id = cursor.fetchone()["id"]
                conn.commit()

                cursor.execute("SELECT * FROM visit_summaries WHERE id = %s", (new_id,))
                row = cursor.fetchone()

                for field in ["files", "tests"]:
                    if isinstance(row.get(field), str):
                        try:
                            row[field] = json.loads(row[field])
                        except Exception:
                            row[field] = []
                    elif row.get(field) is None:
                        row[field] = []

                try:
                    text = "\n".join(
                        [
                            f"标题: {row.get('title') or ''}",
                            f"就诊日期: {row.get('visit_date') or ''}",
                            f"医院: {row.get('hospital') or ''}",
                            f"科室: {row.get('department') or ''}",
                            f"医生: {row.get('doctor') or ''}",
                            f"主诉: {row.get('chief_complaint') or ''}",
                            f"症状: {row.get('symptoms') or ''}",
                            f"检查: {row.get('examination') or ''}",
                            f"诊断: {row.get('diagnosis') or ''}",
                            f"治疗: {row.get('treatment') or ''}",
                            f"处方: {row.get('prescription') or ''}",
                            f"复查/随访: {row.get('follow_up') or ''}",
                            f"摘要: {row.get('summary_content') or ''}",
                            f"备注: {row.get('notes') or ''}",
                        ]
                    ).strip()
                    api._upsert_rag_document(
                        cursor,
                        user_id=uid,
                        source_type="visit_summaries",
                        source_id=str(row.get("id")),
                        record_type="visit_summary",
                        title=row.get("title"),
                        text=text,
                    )
                    conn.commit()
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    api.logger.warning(f"创建就诊摘要后RAG入库失败：{e}")

                return api.VisitSummary(**row)
    except api.HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"创建就诊摘要失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))


async def update_visit_summary(
    api: Any,
    *,
    summary_id: str,
    summary: Any,
    user_id: Any,
    request: Any,
) -> Any:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise api.HTTPException(status_code=401, detail="未认证用户")

        with api.get_db_connection() as conn:
            with conn.cursor(row_factory=api.dict_row) as cursor:
                cursor.execute(
                    "SELECT * FROM visit_summaries WHERE id = %s AND user_id = %s",
                    (summary_id, uid),
                )
                existing = cursor.fetchone()
                if not existing:
                    raise api.HTTPException(
                        status_code=404, detail="就诊摘要不存在或无权修改"
                    )

                update_fields = []
                params = []

                if summary.title is not None:
                    update_fields.append("title = %s")
                    params.append(summary.title)
                if summary.visit_date is not None:
                    update_fields.append("visit_date = %s")
                    params.append(summary.visit_date)
                if summary.doctor is not None:
                    update_fields.append("doctor = %s")
                    params.append(summary.doctor)
                if summary.hospital is not None:
                    update_fields.append("hospital = %s")
                    params.append(summary.hospital)
                if summary.department is not None:
                    update_fields.append("department = %s")
                    params.append(summary.department)
                if summary.chief_complaint is not None:
                    update_fields.append("chief_complaint = %s")
                    params.append(summary.chief_complaint)
                if summary.symptoms is not None:
                    update_fields.append("symptoms = %s")
                    params.append(summary.symptoms)
                if summary.examination is not None:
                    update_fields.append("examination = %s")
                    params.append(summary.examination)
                if summary.diagnosis is not None:
                    update_fields.append("diagnosis = %s")
                    params.append(summary.diagnosis)
                if summary.treatment is not None:
                    update_fields.append("treatment = %s")
                    params.append(summary.treatment)
                if summary.prescription is not None:
                    update_fields.append("prescription = %s")
                    params.append(summary.prescription)
                if summary.follow_up is not None:
                    update_fields.append("follow_up = %s")
                    params.append(summary.follow_up)
                if summary.notes is not None:
                    update_fields.append("notes = %s")
                    params.append(summary.notes)
                if summary.files is not None:
                    update_fields.append("files = %s")
                    params.append(api.Json(summary.files))
                if summary.tests is not None:
                    update_fields.append("tests = %s")
                    params.append(api.Json(summary.tests))
                if summary.summary_content is not None:
                    update_fields.append("summary_content = %s")
                    params.append(summary.summary_content)

                if not update_fields:
                    for field in ["files", "tests"]:
                        if isinstance(existing.get(field), str):
                            try:
                                existing[field] = json.loads(existing[field])
                            except Exception:
                                existing[field] = []
                        elif existing.get(field) is None:
                            existing[field] = []
                    return api.VisitSummary(**existing)

                query = f"UPDATE visit_summaries SET {', '.join(update_fields)} WHERE id = %s RETURNING *"
                params.append(summary_id)

                cursor.execute(query, tuple(params))
                row = cursor.fetchone()
                conn.commit()

                for field in ["files", "tests"]:
                    if isinstance(row.get(field), str):
                        try:
                            row[field] = json.loads(row[field])
                        except Exception:
                            row[field] = []
                    elif row.get(field) is None:
                        row[field] = []

                try:
                    text = "\n".join(
                        [
                            f"标题: {row.get('title') or ''}",
                            f"就诊日期: {row.get('visit_date') or ''}",
                            f"医院: {row.get('hospital') or ''}",
                            f"科室: {row.get('department') or ''}",
                            f"医生: {row.get('doctor') or ''}",
                            f"主诉: {row.get('chief_complaint') or ''}",
                            f"症状: {row.get('symptoms') or ''}",
                            f"检查: {row.get('examination') or ''}",
                            f"诊断: {row.get('diagnosis') or ''}",
                            f"治疗: {row.get('treatment') or ''}",
                            f"处方: {row.get('prescription') or ''}",
                            f"复查/随访: {row.get('follow_up') or ''}",
                            f"摘要: {row.get('summary_content') or ''}",
                            f"备注: {row.get('notes') or ''}",
                        ]
                    ).strip()
                    api._upsert_rag_document(
                        cursor,
                        user_id=uid,
                        source_type="visit_summaries",
                        source_id=str(row.get("id")),
                        record_type="visit_summary",
                        title=row.get("title"),
                        text=text,
                    )
                    conn.commit()
                except Exception as e:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    api.logger.warning(f"更新就诊摘要后RAG入库失败：{e}")

                return api.VisitSummary(**row)

    except api.HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"更新就诊摘要失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))


async def delete_visit_summary(
    api: Any,
    *,
    summary_id: str,
    user_id: Any,
    request: Any,
) -> dict[str, Any]:
    try:
        uid = api._resolve_user_id(request, user_id)
        if not uid:
            raise api.HTTPException(status_code=401, detail="未认证用户")

        with api.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM visit_summaries WHERE id = %s AND user_id = %s RETURNING id",
                    (summary_id, uid),
                )
                deleted = cursor.fetchone()
                if not deleted:
                    raise api.HTTPException(
                        status_code=404, detail="就诊摘要不存在或无权删除"
                    )
                conn.commit()
                return {"message": "删除成功", "id": summary_id}

    except api.HTTPException:
        raise
    except Exception as e:
        api.logger.error(f"删除就诊摘要失败: {e}")
        raise api.HTTPException(status_code=500, detail=str(e))
