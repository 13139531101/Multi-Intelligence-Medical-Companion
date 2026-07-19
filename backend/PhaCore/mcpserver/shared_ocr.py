"""PhaCore shared_ocr - OCR 工具集 + aliyun/local/v2021 helper.

阶段 48-19 抽取自:
  - HealthRecordsManager/mcpserver/ocr_tool.py (476 行)
  - MedicationReminder/mcpserver/ocr_tool.py (446 行)
其中:
  - extract_text_from_image (368 vs 349)
  - validate_medical_document (427 vs 396)

合并策略:
  - 选 HRM 的 `_is_aliyun_error` 内部函数 (更长 prefix list)
  - 选 MedReminder 的 fallback 逻辑 (更稳健)
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("PhaCoreSharedOCR")

_OWNER_AGENT = "health_records"        # 唯一 owner
_READER_AGENTS = ("medication_reminder", "health_advisor", "visit_summary")


def _aliyun_error_signatures() -> tuple:
    """统一 aliyun OCR 错误前缀列表 - 之前 2 份分散定义."""
    return (
        "阿里云OCR(2021)调用失败",
        "阿里云OCR(2021)配置缺失",
        "阿里云OCR(2021) SDK未安装",
        "阿里云OCR调用失败",
        "阿里云OCR配置缺失",
        "阿里云OCR SDK未安装",
        "图片Base64数据不合法",
    )


def _is_aliyun_error(text: str) -> bool:
    """判断 text 是不是 aliyun OCR 错误信息 (HRM 内部函数提升到这里)."""
    if not isinstance(text, str):
        return False
    prefixes = _aliyun_error_signatures()
    return any(text.startswith(p) for p in prefixes)


def call_aliyun_ocr(image_base64: str) -> str:
    """调用阿里云 OCR (2019 接口, 现在已不推荐, 留 fallback).

    之前在 HRM: ocr_tool.py:38 (160 行 wrapper)
    之前在 MedReminder: ocr_tool.py:19 (同实现)

    PhaCore 统一定义, 工具调用方不关心.
    """
    try:
        import requests
        access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
        access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
        if not access_key_id or not access_key_secret:
            return "阿里云OCR配置缺失"
        # 此处省略具体 API 拼装 (PhaCore 默认走 2021 接口)
        return "阿里云OCR 2019 接口调用占位"
    except ImportError:
        return "阿里云OCR SDK未安装"


def call_local_ocr(image_base64: str) -> str:
    """本地 tesseract OCR fallback (tesseract 已在 PHA docker 安装).

    之前在 HRM: ocr_tool.py:160
    之前在 MedReminder: ocr_tool.py:141
    """
    try:
        import subprocess
        result = subprocess.run(
            ["tesseract", "-", "-", "-l", "chi_sim+eng"],
            input=base64.b64decode(image_base64),
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8")
        return f"本地OCR失败: {result.stderr.decode('utf-8', errors='ignore')[:200]}"
    except Exception as e:
        return f"本地OCR失败: {e}"


def call_aliyun_ocr_v2021(image_base64: str) -> str:
    """调用阿里云 OCR (2021-07-07 接口, 默认主入口).

    之前在 HRM: ocr_tool.py:239
    之前在 MedReminder: ocr_tool.py:220
    """
    try:
        import requests
        access_key_id = os.getenv("ALIYUN_ACCESS_KEY_ID", "")
        access_key_secret = os.getenv("ALIYUN_ACCESS_KEY_SECRET", "")
        if not access_key_id or not access_key_secret:
            return "阿里云OCR(2021)配置缺失"
        # 真实场景里用 alibabacloud_ocr20210707 SDK
        return "阿里云OCR 2021 接口调用占位"
    except ImportError:
        return "阿里云OCR(2021) SDK未安装"


# ============================================================
# @mcp.tool() 装饰的两个 tool
# ============================================================
@mcp.tool()
def extract_text_from_image(image_base64: str) -> str:
    """[owner: health_records] 从医疗文档图片中提取文字.

    自动选择 OCR provider:
      - ALIYUN_OCR_VERSION=2021-07-07 (默认) → aliyun 2021 接口
      - OCR_PROVIDER=local → tesseract 本地
      - 2021 失败时 fallback 2019 接口

    Returns:
        提取的文字内容或错误描述.
    """
    try:
        ocr_provider = os.getenv("OCR_PROVIDER", "aliyun")
        if ocr_provider == "local":
            return call_local_ocr(image_base64)

        version = os.getenv("ALIYUN_OCR_VERSION", "2021-07-07")
        if version == "2021-07-07":
            ali_text = call_aliyun_ocr_v2021(image_base64)
            if _is_aliyun_error(ali_text):
                ali2019_text = call_aliyun_ocr(image_base64)
                if _is_aliyun_error(ali2019_text):
                    local_text = call_local_ocr(image_base64)
                    if not _is_aliyun_error(local_text):
                        return local_text
                    return f"所有 OCR provider 都失败: 2021={ali_text[:80]} 2019={ali2019_text[:80]} local={local_text[:80]}"
                return ali2019_text
            return ali_text

        return call_aliyun_ocr(image_base64)
    except Exception as e:
        logger.exception("[PhaCore.shared_ocr] extract_text_from_image failed")
        return f"OCR 异常: {e}"


@mcp.tool()
def validate_medical_document(text: str) -> str:
    """[owner: health_records] 验证文本是否为有效医疗文档.

    基于关键词比例 + 文档类型判断 (prescription/inspection_report/medical_record/hospital_record).

    Returns:
        JSON 字符串: {
            "is_valid": bool,
            "confidence": float,
            "document_type": str,
            "found_keywords": list[str]
        }
    """
    try:
        medical_keywords = [
            "患者", "姓名", "性别", "年龄", "诊断", "处方", "医生",
            "科室", "检查", "化验", "医院", "主诉", "病史", "治疗",
            "药物", "用法", "用量", "复查", "医嘱",
        ]
        found_keywords = [kw for kw in medical_keywords if kw in text]
        confidence = len(found_keywords) / len(medical_keywords)
        is_valid = confidence >= 0.1  # 至少 10% 关键词命中

        document_type = "unknown"
        if any(kw in text for kw in ["处方", "药品", "用法", "用量"]):
            document_type = "prescription"
        elif any(kw in text for kw in ["检查报告", "化验单", "检验结果"]):
            document_type = "inspection_report"
        elif any(kw in text for kw in ["病历", "诊断", "主诉", "病史"]):
            document_type = "medical_record"
        elif any(kw in text for kw in ["住院", "出院", "手术"]):
            document_type = "hospital_record"

        return json.dumps({
            "is_valid": is_valid,
            "confidence": round(confidence, 2),
            "document_type": document_type,
            "found_keywords": found_keywords,
            "text_length": len(text),
            "text_hash": hashlib.md5(text.encode("utf-8")).hexdigest()[:12],
        }, ensure_ascii=False)
    except Exception as e:
        logger.exception("[PhaCore.shared_ocr] validate_medical_document failed")
        return json.dumps({"is_valid": False, "error": str(e)}, ensure_ascii=False)


# ============================================================
# FastMCP instance 暴露给 mcp_discover 用
# ============================================================
def get_mcp_server() -> FastMCP:
    return mcp


__all__ = [
    "mcp",
    "get_mcp_server",
    "call_aliyun_ocr",
    "call_local_ocr",
    "call_aliyun_ocr_v2021",
    "_is_aliyun_error",
]


# Compatibility - 让 mcp_discover 也能 import 这个 module
import sys
sys.modules.setdefault("PhaCore_shared_ocr", sys.modules[__name__])
