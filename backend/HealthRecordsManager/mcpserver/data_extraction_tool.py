# -*- coding: utf-8 -*-
# @Date  : 2025/1/20
# @File  : data_extraction_tool.py
# @Author: Health Assistant Team
# @Desc  : 医疗信息提取工具 - 从文本中提取结构化的医疗信息

import re
import json
import os
from datetime import datetime
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("医疗信息提取工具")

@mcp.tool()
def extract_medical_info(text: str) -> str:
    """
    从文本中提取结构化医疗信息
    :param text: OCR识别的文本
    :return: JSON格式的结构化信息
    """
    try:
        extracted_info = {
            'document_type': detect_document_type(text),
            'patient_info': extract_patient_info(text),
            'diagnosis': extract_diagnosis(text),
            'medications': extract_medications(text),
            'test_results': extract_test_results(text),
            'doctor_info': extract_doctor_info(text),
            'date': extract_date(text),
            'medical_advice': extract_medical_advice(text),
            'original_content': text,
            'extraction_time': datetime.now().isoformat()
        }
        
        return json.dumps(extracted_info, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({
            'error': f"信息提取失败: {str(e)}",
            'extraction_time': datetime.now().isoformat()
        }, ensure_ascii=False)

def detect_document_type(text: str) -> str:
    """检测文档类型"""
    if any(kw in text for kw in ['处方', '药品', '用法', '用量']):
        return 'prescription'
    elif any(kw in text for kw in ['检查报告', '化验单', '检验结果', 'B超', 'CT', 'MRI', 'X光']):
        return 'inspection_report'
    elif any(kw in text for kw in ['病历', '诊断', '主诉', '病史']):
        return 'medical_record'
    elif any(kw in text for kw in ['住院', '出院', '手术', '入院']):
        return 'hospital_record'
    elif any(kw in text for kw in ['疫苗', '接种', '免疫']):
        return 'vaccination_record'
    else:
        return 'unknown'

def extract_patient_info(text: str) -> dict:
    """提取患者信息"""
    patient_info = {}
    
    # 提取姓名
    name_patterns = [
        r'患者姓名[：:]?\s*([\u4e00-\u9fa5a-zA-Z]+)',
        r'姓名[：:]?\s*([\u4e00-\u9fa5a-zA-Z]+)',
        r'病人[：:]?\s*([\u4e00-\u9fa5a-zA-Z]+)'
    ]
    for pattern in name_patterns:
        match = re.search(pattern, text)
        if match:
            patient_info['name'] = match.group(1).strip()
            break
    
    # 提取年龄
    age_patterns = [
        r'年龄[：:]?\s*(\d+)\s*[岁年]?',
        r'(\d+)\s*岁',
        r'(\d+)\s*年'
    ]
    for pattern in age_patterns:
        match = re.search(pattern, text)
        if match:
            patient_info['age'] = int(match.group(1))
            break
    
    # 提取性别
    gender_patterns = [
        r'性别[：:]?\s*(男|女)',
        r'(男|女)\s*性',
        r'(男|女)\s*，'
    ]
    for pattern in gender_patterns:
        match = re.search(pattern, text)
        if match:
            patient_info['gender'] = match.group(1)
            break
    
    # 提取身份证号
    id_pattern = r'身份证[号]?[：:]?\s*([0-9X]{15,18})'
    id_match = re.search(id_pattern, text)
    if id_match:
        patient_info['id_number'] = id_match.group(1)
    
    # 提取联系电话
    phone_pattern = r'电话[：:]?\s*(1[3-9]\d{9})'
    phone_match = re.search(phone_pattern, text)
    if phone_match:
        patient_info['phone'] = phone_match.group(1)
    
    return patient_info

def extract_diagnosis(text: str) -> list:
    """提取诊断信息"""
    diagnosis_patterns = [
        r'诊断[：:]?\s*([^\n]+)',
        r'初步诊断[：:]?\s*([^\n]+)',
        r'临床诊断[：:]?\s*([^\n]+)',
        r'主要诊断[：:]?\s*([^\n]+)',
        r'疾病诊断[：:]?\s*([^\n]+)'
    ]
    
    diagnoses = []
    for pattern in diagnosis_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            # 清理诊断文本
            diagnosis = match.strip()
            # 分割多个诊断（通过数字编号或分号分割）
            if re.search(r'\d+[、.]', diagnosis):
                sub_diagnoses = re.split(r'\d+[、.]', diagnosis)
                diagnoses.extend([d.strip() for d in sub_diagnoses if d.strip()])
            elif ';' in diagnosis or '；' in diagnosis:
                sub_diagnoses = re.split(r'[;；]', diagnosis)
                diagnoses.extend([d.strip() for d in sub_diagnoses if d.strip()])
            else:
                diagnoses.append(diagnosis)
    
    return list(set(diagnoses))  # 去重

def extract_medications(text: str) -> list:
    """提取药物信息"""
    medications = []
    
    # 药物名称模式（中文药名 + 剂型）
    med_patterns = [
        r'([\u4e00-\u9fa5]+(?:片|胶囊|注射液|颗粒|丸|膏|栓|滴剂|喷雾剂|贴剂))\s*(\d+(?:\.\d+)?\s*(?:mg|g|ml|片|粒|支|盒|瓶)?)\s*([^\n]*)',
        r'(\w+(?:片|胶囊|注射液|颗粒|丸))\s*(\d+(?:\.\d+)?\s*(?:mg|g|ml|片|粒)?)\s*([^\n]*)'
    ]
    
    for pattern in med_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            med_name = match[0].strip()
            dosage = match[1].strip() if match[1] else ''
            usage = match[2].strip() if len(match) > 2 else ''
            
            # 提取用法用量信息
            frequency = ''
            duration = ''
            
            if '每日' in usage or '每天' in usage:
                freq_match = re.search(r'每[日天](\d+)次', usage)
                if freq_match:
                    frequency = f"每日{freq_match.group(1)}次"
            
            if '连续' in usage or '服用' in usage:
                dur_match = re.search(r'(\d+)[天日周月]', usage)
                if dur_match:
                    duration = dur_match.group(0)
            
            medications.append({
                'name': med_name,
                'dosage': dosage,
                'frequency': frequency,
                'duration': duration,
                'usage_instruction': usage
            })
    
    return medications

def _is_valid_test_name(name: str, unit: str = "") -> bool:
    text = (name or "").strip()
    if not text:
        return False
    if len(text) > 24:
        return False
    blacklist = [
        "test",
        "测试",
        "姓名",
        "性别",
        "年龄",
        "电话",
        "地址",
        "医生",
        "医师",
        "科室",
        "医院",
        "病区",
        "床号",
        "编号",
        "条码",
        "报告",
        "检验",
        "检查",
        "结果",
        "结论",
        "意见",
        "建议",
        "提示",
        "诊断",
        "病史",
        "处方",
        "药品",
        "用药",
        "主诉",
        "入院",
        "出院",
        "日期",
        "时间",
    ]
    for bad in blacklist:
        if bad in text:
            return False
    lower = text.lower()
    allowed_keywords = [
        "血压",
        "收缩压",
        "舒张压",
        "血糖",
        "空腹血糖",
        "餐后血糖",
        "糖化血红蛋白",
        "心率",
        "脉搏",
        "体温",
        "血氧",
        "呼吸",
        "体重",
        "身高",
        "尿酸",
        "肌酐",
        "尿素氮",
        "转氨酶",
        "胆固醇",
        "甘油三酯",
        "低密度",
        "高密度",
        "总胆固醇",
        "血红蛋白",
        "白细胞",
        "红细胞",
        "血小板",
    ]
    if any(kw in text for kw in allowed_keywords):
        return True
    allowed_abbr = {
        "hba1c",
        "hdl",
        "ldl",
        "hgb",
        "wbc",
        "rbc",
        "plt",
        "alt",
        "ast",
        "glu",
        "tg",
        "tc",
        "spo2",
        "bmi",
        "crp",
        "tsh",
        "ft3",
        "ft4",
    }
    if lower in allowed_abbr:
        return True
    if re.fullmatch(r"[a-z]{2,6}\d{0,2}", lower):
        return True
    unit_text = (unit or "").strip()
    if unit_text and len(unit_text) <= 12:
        return True
    return False


def _filter_test_results(tests: dict | None) -> dict | None:
    if not isinstance(tests, dict):
        return None
    cleaned: dict = {}
    for k, v in tests.items():
        if not k:
            continue
        unit = ""
        if isinstance(v, dict):
            unit = str(v.get("unit") or "").strip()
        if not _is_valid_test_name(str(k), unit):
            continue
        cleaned[str(k).strip()] = v
    return cleaned


def _extract_json_from_text(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _normalize_llm_test_results(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    tests = payload.get("test_results") or payload.get("tests") or payload.get("lab_results")
    if isinstance(tests, dict):
        return tests
    if isinstance(tests, list):
        normalized: dict = {}
        for item in tests:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("test_name") or "").strip()
            if not name:
                continue
            normalized[name] = {
                "value": item.get("value"),
                "unit": item.get("unit") or "",
            }
        return normalized
    return None


def _llm_extract_test_results(text: str) -> dict | None:
    provider = (os.getenv("HEALTH_RECORDS_LLM_PROVIDER") or os.getenv("LLM_PROVIDER") or "").strip().lower()
    model = (os.getenv("HEALTH_RECORDS_LLM_MODEL") or os.getenv("LLM_MODEL") or "deepseek-chat").strip()
    base_url = None
    api_key = None
    if provider in ("", "deepseek"):
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_API_BASE") or "https://api.deepseek.com/v1"
    elif provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE") or None
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except Exception:
        return None
    trimmed = (text or "").strip()
    if not trimmed:
        return None
    if len(trimmed) > 8000:
        trimmed = trimmed[:8000]
    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    system_prompt = "你是医学检验结果抽取助手，只输出JSON。"
    user_prompt = (
        "从以下文本中抽取检验/检查指标，输出JSON格式："
        '{"test_results":{"指标名":{"value":数值或字符串,"unit":"单位"}}}。'
        "优先抽取常见化验缩写与生命体征，例如：HGB、MCH、MCV、WBC、RBC、PLT、GLU、HbA1c、ALT、AST、Cr、UA、TC、TG、HDL、LDL、血压、心率、体温、血氧。"
        "不要输出其它字段。\n\n"
        f"{trimmed}"
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
        )
    except Exception:
        return None
    content = ""
    try:
        content = response.choices[0].message.content or ""
    except Exception:
        content = ""
    parsed = _extract_json_from_text(content)
    return _normalize_llm_test_results(parsed)


def extract_test_results(text: str) -> dict:
    """提取检查结果"""
    results = {}
    llm_results = _llm_extract_test_results(text)
    filtered = _filter_test_results(llm_results)
    if filtered:
        return filtered
    test_patterns = [
        r'([\u4e00-\u9fa5]+)\s*[：:]?\s*(\d+(?:\.\d+)?)\s*([a-zA-Z/μ]+)?',
        r'([A-Za-z]{2,6}\d{0,2})\s*[：:]?\s*([-+]?\d+(?:\.\d+)?)\s*([a-zA-Z/%μµ]+)?',
        r'([A-Za-z]{2,6}\d{0,2})\s+([-+]?\d+(?:\.\d+)?)\s*([a-zA-Z/%μµ]+)?',
        r'(血压)\s*[：:]?\s*(\d+/\d+)\s*(mmHg)?',
        r'(体温)\s*[：:]?\s*(\d+(?:\.\d+)?)\s*[℃°C]?',
        r'(心率)\s*[：:]?\s*(\d+)\s*次/分?'
    ]
    for pattern in test_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            test_name = match[0].strip()
            test_value = match[1].strip()
            test_unit = match[2].strip() if len(match) > 2 and match[2] else ''
            if not _is_valid_test_name(test_name, test_unit):
                continue
            results[test_name] = {
                'value': test_value,
                'unit': test_unit
            }
    return results

def extract_doctor_info(text: str) -> dict:
    """提取医生信息"""
    doctor_info = {}
    
    # 提取医生姓名
    doctor_patterns = [
        r'医生[：:]?\s*([\u4e00-\u9fa5a-zA-Z]+)',
        r'主治医师[：:]?\s*([\u4e00-\u9fa5a-zA-Z]+)',
        r'医师[：:]?\s*([\u4e00-\u9fa5a-zA-Z]+)'
    ]
    for pattern in doctor_patterns:
        match = re.search(pattern, text)
        if match:
            doctor_info['doctor'] = match.group(1).strip()
            break
    
    # 提取科室
    department_patterns = [
        r'科室[：:]?\s*([\u4e00-\u9fa5]+科)',
        r'([\u4e00-\u9fa5]+科)\s*医生',
        r'([\u4e00-\u9fa5]+科)\s*门诊'
    ]
    for pattern in department_patterns:
        match = re.search(pattern, text)
        if match:
            doctor_info['department'] = match.group(1)
            break
    
    # 提取医院
    hospital_patterns = [
        r'([\u4e00-\u9fa5]+医院)',
        r'([\u4e00-\u9fa5]+医疗中心)',
        r'([\u4e00-\u9fa5]+卫生院)'
    ]
    for pattern in hospital_patterns:
        match = re.search(pattern, text)
        if match:
            doctor_info['hospital'] = match.group(1)
            break
    
    return doctor_info

def extract_date(text: str) -> str:
    """提取日期信息"""
    date_patterns = [
        r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)',
        r'(\d{1,2}[-/月]\d{1,2}[-/日]\d{4}[年]?)',
        r'(\d{4}\.\d{1,2}\.\d{1,2})',
        r'就诊日期[：:]?\s*([^\n]+)',
        r'检查日期[：:]?\s*([^\n]+)'
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    
    return None

def extract_medical_advice(text: str) -> list:
    """提取医嘱建议"""
    advice = []
    
    # 查找医嘱相关内容
    advice_patterns = [
        r'医嘱[：:]?\s*([^\n]+)',
        r'建议[：:]?\s*([^\n]+)',
        r'注意事项[：:]?\s*([^\n]+)',
        r'复查[：:]?\s*([^\n]+)'
    ]
    
    for pattern in advice_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            advice_text = match.strip()
            # 分割多条建议
            if re.search(r'\d+[、.]', advice_text):
                sub_advice = re.split(r'\d+[、.]', advice_text)
                advice.extend([a.strip() for a in sub_advice if a.strip()])
            else:
                advice.append(advice_text)
    
    return advice

@mcp.tool()
def extract_prescription_info(text: str) -> str:
    """专门提取处方信息"""
    try:
        prescription_info = {
            'patient_info': extract_patient_info(text),
            'doctor_info': extract_doctor_info(text),
            'medications': extract_medications(text),
            'date': extract_date(text),
            'prescription_number': extract_prescription_number(text)
        }
        
        return json.dumps(prescription_info, ensure_ascii=False, indent=2)
        
    except Exception as e:
        return json.dumps({
            'error': f"处方信息提取失败: {str(e)}"
        }, ensure_ascii=False)

def extract_prescription_number(text: str) -> str:
    """提取处方号"""
    patterns = [
        r'处方号[：:]?\s*([A-Za-z0-9]+)',
        r'处方编号[：:]?\s*([A-Za-z0-9]+)',
        r'No[.:]?\s*([A-Za-z0-9]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    
    return None

if __name__ == '__main__':
    # 启动FastMCP服务器
    mcp.run()
