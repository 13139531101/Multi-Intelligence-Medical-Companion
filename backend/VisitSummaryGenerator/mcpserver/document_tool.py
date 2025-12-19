#!/usr/bin/env python3
"""
就诊摘要生成智能体 - 文档处理工具
提供医疗文档解析、信息提取和摘要生成功能
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Any, Optional
from mcp.server.fastmcp import FastMCP

# 创建MCP服务器实例
mcp = FastMCP("DocumentTool")

# 模拟医疗文档数据
SAMPLE_DOCUMENTS = {
    "visit_record_001": {
        "type": "门诊记录",
        "content": "患者：张三，男，45岁。主诉：胸闷气短3天。现病史：患者3天前无明显诱因出现胸闷气短，活动后加重，伴有轻微胸痛。既往史：高血压病史5年，规律服用降压药。体格检查：血压150/90mmHg，心率85次/分，心律齐，双肺呼吸音清晰。辅助检查：心电图示窦性心律，ST段轻度压低。诊断：1.冠心病？2.高血压病。处理：建议进一步行冠脉造影检查，调整降压药物剂量。",
        "date": "2024-01-15",
        "doctor": "李医生",
        "department": "心内科",
    },
    "prescription_001": {
        "type": "处方单",
        "content": "Rx: 1.阿司匹林肠溶片 100mg 每日1次 饭后服用 30天 2.美托洛尔缓释片 47.5mg 每日1次 晨起服用 30天 3.阿托伐他汀钙片 20mg 每日1次 睡前服用 30天。注意事项：定期复查肝功能，如有肌肉疼痛及时就诊。",
        "date": "2024-01-15",
        "doctor": "李医生",
        "department": "心内科",
    },
    "lab_report_001": {
        "type": "检验报告",
        "content": "血常规：白细胞计数 6.5×10^9/L（正常），红细胞计数 4.2×10^12/L（正常），血红蛋白 135g/L（正常），血小板计数 280×10^9/L（正常）。生化检查：总胆固醇 6.2mmol/L（偏高），甘油三酯 2.8mmol/L（偏高），低密度脂蛋白 4.1mmol/L（偏高），高密度脂蛋白 1.0mmol/L（偏低），空腹血糖 5.8mmol/L（正常）。",
        "date": "2024-01-15",
        "department": "检验科",
    },
}


@mcp.tool()
def parse_medical_document(
    document_text: str, document_type: str = "auto"
) -> Dict[str, Any]:
    """
    解析医疗文档，提取关键信息

    Args:
        document_text: 医疗文档文本内容
        document_type: 文档类型（auto/门诊记录/处方单/检验报告/影像报告）

    Returns:
        解析后的结构化信息
    """
    try:
        # 自动识别文档类型
        if document_type == "auto":
            if "主诉" in document_text and "现病史" in document_text:
                document_type = "门诊记录"
            elif (
                "诊断证明" in document_text
                or "诊断书" in document_text
                or "疾病证明" in document_text
                or "疾病诊断证明" in document_text
            ):
                document_type = "诊断证明"
            elif "Rx:" in document_text or "处方" in document_text:
                document_type = "处方单"
            elif "检验" in document_text or "化验" in document_text:
                document_type = "检验报告"
            elif (
                "影像" in document_text
                or "CT" in document_text
                or "MRI" in document_text
            ):
                document_type = "影像报告"
            else:
                document_type = "其他"

        parsed_info = {
            "document_type": document_type,
            "parse_time": datetime.now().isoformat(),
            "extracted_info": {},
        }

        if document_type == "门诊记录":
            parsed_info["extracted_info"] = _parse_visit_record(document_text)
        elif document_type == "处方单":
            parsed_info["extracted_info"] = _parse_prescription(document_text)
        elif document_type == "诊断证明":
            parsed_info["extracted_info"] = _parse_diagnosis_certificate(document_text)
        elif document_type == "检验报告":
            parsed_info["extracted_info"] = _parse_lab_report(document_text)
        elif document_type == "影像报告":
            parsed_info["extracted_info"] = _parse_imaging_report(document_text)
        else:
            parsed_info["extracted_info"] = {"raw_text": document_text}

        return {
            "success": True,
            "data": parsed_info,
            "message": f"成功解析{document_type}",
        }

    except Exception as e:
        return {"success": False, "error": str(e), "message": "文档解析失败"}


def _parse_visit_record(text: str) -> Dict[str, Any]:
    """解析门诊记录"""
    info = {}

    # 提取患者信息
    patient_match = re.search(r"患者[：:]([^，,]+)", text)
    if patient_match:
        info["patient_name"] = patient_match.group(1).strip()

    # 提取年龄和性别
    age_match = re.search(r"(\d+)岁", text)
    if age_match:
        info["age"] = age_match.group(1)

    gender_match = re.search(r"[，,]([男女])[，,]", text)
    if gender_match:
        info["gender"] = gender_match.group(1)

    # 提取主诉
    chief_complaint_match = re.search(r"主诉[：:]([^。]+)", text)
    if chief_complaint_match:
        info["chief_complaint"] = chief_complaint_match.group(1).strip()

    # 提取现病史
    history_match = re.search(r"现病史[：:]([^。]*(?:。[^既往史诊断处理]*)*)", text)
    if history_match:
        info["present_illness"] = history_match.group(1).strip()

    # 提取既往史
    past_history_match = re.search(
        r"既往史[：:]([^。]*(?:。[^体格检查诊断处理]*)*)", text
    )
    if past_history_match:
        info["past_history"] = past_history_match.group(1).strip()

    # 提取诊断
    diag_match = re.search(
        r"(?:诊断印象|诊断意见|临床诊断|初步诊断|入院诊断|出院诊断|诊断|印象)[：:]?\s*([\s\S]{2,300}?)(?:处理|医嘱|建议|$)",
        text,
    )
    if diag_match:
        seg = (diag_match.group(1) or "").strip()
        if seg:
            info["diagnosis"] = [ln.strip() for ln in seg.splitlines() if ln.strip()]

    # 提取处理方案
    treatment_match = re.search(r"处理[：:]([^$]+)", text)
    if treatment_match:
        info["treatment"] = treatment_match.group(1).strip()

    return info


def _parse_prescription(text: str) -> Dict[str, Any]:
    """解析处方单"""
    info = {"medications": []}

    # 提取药物信息
    # 匹配格式：药名 剂量 用法 天数
    med_pattern = r"(\d+\.)?([^\d\n]+?)\s+(\d+(?:\.\d+)?\s*(?:mg|g|ml|IU|μg|ug|单位))\s+([^\n]+?)\s+(?:(\d+)\s*天)?"
    matches = re.findall(med_pattern, text, flags=re.IGNORECASE)
    for match in matches:
        name = (match[1] or "").strip().replace("Rx:", "").strip()
        dosage = (match[2] or "").strip()
        usage = (match[3] or "").strip()
        duration = (match[4] or "").strip()
        if not name or not dosage:
            continue
        medication = {
            "name": name,
            "dosage": dosage,
            "usage": usage,
            "duration": (duration + "天") if duration else "",
        }
        info["medications"].append(medication)

    if not info["medications"]:
        line_candidates = [ln.strip() for ln in text.splitlines() if ln and ln.strip()]
        for ln in line_candidates:
            if len(info["medications"]) >= 20:
                break
            if not any(
                k in ln
                for k in (
                    "片",
                    "粒",
                    "胶囊",
                    "丸",
                    "袋",
                    "支",
                    "喷雾",
                    "滴眼",
                    "注射",
                    "mg",
                    "g",
                    "ml",
                )
            ):
                continue
            m = re.search(
                r"([^\d]{2,30}?)(?:\s+|\t)+(\d+(?:\.\d+)?\s*(?:mg|g|ml|IU|μg|ug|单位))",
                ln,
                flags=re.IGNORECASE,
            )
            if not m:
                continue
            name = (m.group(1) or "").strip().replace("Rx:", "").strip()
            dosage = (m.group(2) or "").strip()
            if name and dosage:
                info["medications"].append(
                    {"name": name, "dosage": dosage, "usage": ln, "duration": ""}
                )

    # 提取注意事项
    notes_match = re.search(r"注意事项[：:]([^$]+)", text)
    if notes_match:
        info["notes"] = notes_match.group(1).strip()

    return info


def _parse_diagnosis_certificate(text: str) -> Dict[str, Any]:
    info: Dict[str, Any] = {}

    name_match = re.search(r"(?:患者|姓名)[：:\s]*([^\s，,；;。\n]{2,20})", text)
    if name_match:
        info["patient_name"] = name_match.group(1).strip()

    gender_match = re.search(r"(?:性别|性別)[：:\s]*([男女])", text)
    if gender_match:
        info["gender"] = gender_match.group(1).strip()

    age_match = re.search(r"(?:年龄|年齡)[：:\s]*(\d{1,3})\s*岁", text)
    if age_match:
        info["age"] = age_match.group(1).strip()

    hospital_match = re.search(
        r"(?:医院|医疗机构名称|医疗机构|机构名称)[：:\s]*([^\n，,；;。]{2,60})", text
    )
    if hospital_match:
        info["hospital"] = hospital_match.group(1).strip()

    diag_match = re.search(
        r"^(?:疾病诊断|临床诊断|诊断印象|诊断意见|诊断)[：:][ \t]*([^\n；;。]{2,200})",
        text,
        flags=re.MULTILINE,
    )
    if diag_match:
        info["diagnosis"] = [diag_match.group(1).strip()]

    dt_match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if dt_match:
        info["date"] = (
            f"{dt_match.group(1)}-{dt_match.group(2).zfill(2)}-{dt_match.group(3).zfill(2)}"
        )
    else:
        dt_match = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)
        if dt_match:
            info["date"] = (
                f"{dt_match.group(1)}-{dt_match.group(2).zfill(2)}-{dt_match.group(3).zfill(2)}"
            )

    advice_match = re.search(r"(?:建议|医嘱)[：:\s]*([^\n]+)", text)
    if advice_match:
        info["advice"] = advice_match.group(1).strip()

    return info


def _parse_lab_report(text: str) -> Dict[str, Any]:
    """解析检验报告"""
    info = {"test_results": []}

    # 提取检验项目和结果
    # 匹配格式：项目名 数值 单位 (状态)
    result_pattern = r"([^\d：:]+?)\s+(\d+(?:\.\d+)?)(?:×10\^\d+)?\s*([^（(]*?)(?:[（(]([^）)]*)[）)])?"
    matches = re.findall(result_pattern, text)

    for match in matches:
        if match[1]:  # 确保有数值
            result = {
                "test_name": match[0].strip(),
                "value": match[1],
                "unit": match[2].strip() if match[2] else "",
                "status": match[3].strip() if match[3] else "正常",
            }
            info["test_results"].append(result)

    return info


def _parse_imaging_report(text: str) -> Dict[str, Any]:
    """解析影像报告"""
    info = {}

    # 提取检查方法
    method_match = re.search(r"(CT|MRI|X线|超声|心电图)", text)
    if method_match:
        info["imaging_method"] = method_match.group(1)

    # 提取影像所见
    findings_match = re.search(r"(影像所见|检查所见)[：:]([^诊断结论]+)", text)
    if findings_match:
        info["findings"] = findings_match.group(2).strip()

    # 提取诊断结论
    conclusion_match = re.search(r"(诊断结论|影像诊断)[：:]([^$]+)", text)
    if conclusion_match:
        info["conclusion"] = conclusion_match.group(2).strip()

    return info


@mcp.tool()
def generate_visit_summary(
    documents: List[Dict[str, Any]], summary_type: str = "comprehensive"
) -> Dict[str, Any]:
    """
    生成就诊摘要

    Args:
        documents: 医疗文档列表，每个文档包含type和content字段
        summary_type: 摘要类型（comprehensive/brief/focused）

    Returns:
        生成的就诊摘要
    """
    try:
        # 解析所有文档
        parsed_docs = []
        for doc in documents:
            parsed = parse_medical_document(
                doc.get("content", ""), doc.get("type", "auto")
            )
            if parsed["success"]:
                parsed_docs.append(parsed["data"])

        # 生成摘要
        summary = {
            "summary_type": summary_type,
            "generation_time": datetime.now().isoformat(),
            "document_count": len(parsed_docs),
            "content": {},
        }

        if summary_type == "comprehensive":
            summary["content"] = _generate_comprehensive_summary(parsed_docs)
        elif summary_type == "brief":
            summary["content"] = _generate_brief_summary(parsed_docs)
        elif summary_type == "focused":
            summary["content"] = _generate_focused_summary(parsed_docs)

        return {
            "success": True,
            "data": summary,
            "message": f"成功生成{summary_type}摘要",
        }

    except Exception as e:
        return {"success": False, "error": str(e), "message": "摘要生成失败"}


def _generate_comprehensive_summary(docs: List[Dict]) -> Dict[str, Any]:
    """生成详细摘要"""
    summary = {
        "patient_info": {},
        "visit_overview": {},
        "diagnosis_treatment": {},
        "medications": [],
        "test_results": [],
        "follow_up": {},
    }

    for doc in docs:
        doc_type = doc["document_type"]
        extracted = doc["extracted_info"]

        if doc_type == "门诊记录":
            summary["patient_info"].update(
                {
                    "name": extracted.get("patient_name", ""),
                    "age": extracted.get("age", ""),
                    "gender": extracted.get("gender", ""),
                }
            )
            summary["visit_overview"].update(
                {
                    "chief_complaint": extracted.get("chief_complaint", ""),
                    "present_illness": extracted.get("present_illness", ""),
                    "past_history": extracted.get("past_history", ""),
                }
            )
            summary["diagnosis_treatment"].update(
                {
                    "diagnosis": extracted.get("diagnosis", []),
                    "treatment_plan": extracted.get("treatment", ""),
                }
            )
        elif doc_type == "诊断证明":
            summary["patient_info"].update(
                {
                    "name": extracted.get("patient_name", ""),
                    "age": extracted.get("age", ""),
                    "gender": extracted.get("gender", ""),
                }
            )
            summary["diagnosis_treatment"].update(
                {
                    "diagnosis": extracted.get("diagnosis", []),
                }
            )
            if extracted.get("advice"):
                summary["follow_up"].update(
                    {"recommendations": extracted.get("advice", "")}
                )

        elif doc_type == "处方单":
            summary["medications"].extend(extracted.get("medications", []))

        elif doc_type == "检验报告":
            summary["test_results"].extend(extracted.get("test_results", []))

    return summary


def _generate_brief_summary(docs: List[Dict]) -> Dict[str, Any]:
    """生成简要摘要"""
    summary = {
        "key_points": [],
        "main_diagnosis": "",
        "key_medications": [],
        "important_findings": [],
    }

    for doc in docs:
        doc_type = doc["document_type"]
        extracted = doc["extracted_info"]

        if doc_type == "门诊记录":
            if extracted.get("chief_complaint"):
                summary["key_points"].append(f"主诉：{extracted['chief_complaint']}")
            if extracted.get("diagnosis"):
                summary["main_diagnosis"] = "；".join(extracted["diagnosis"])

        elif doc_type == "处方单":
            for med in extracted.get("medications", []):
                summary["key_medications"].append(med["name"])

    return summary


def _generate_focused_summary(docs: List[Dict]) -> Dict[str, Any]:
    """生成重点摘要"""
    summary = {
        "focus_area": "诊断与治疗",
        "key_findings": [],
        "treatment_summary": "",
        "risk_factors": [],
        "recommendations": [],
    }

    # 重点关注诊断、治疗和风险因素
    for doc in docs:
        doc_type = doc["document_type"]
        extracted = doc["extracted_info"]

        if doc_type == "门诊记录":
            if extracted.get("diagnosis"):
                summary["key_findings"].extend(extracted["diagnosis"])
            if extracted.get("treatment"):
                summary["treatment_summary"] = extracted["treatment"]

    return summary


@mcp.tool()
def get_sample_document(document_id: str) -> Dict[str, Any]:
    """
    获取示例医疗文档

    Args:
        document_id: 文档ID（visit_record_001/prescription_001/lab_report_001）

    Returns:
        示例文档内容
    """
    if document_id in SAMPLE_DOCUMENTS:
        return {
            "success": True,
            "data": SAMPLE_DOCUMENTS[document_id],
            "message": "成功获取示例文档",
        }
    else:
        available_ids = list(SAMPLE_DOCUMENTS.keys())
        return {
            "success": False,
            "error": f"文档ID不存在，可用ID：{available_ids}",
            "message": "文档获取失败",
        }


if __name__ == "__main__":
    mcp.run()
