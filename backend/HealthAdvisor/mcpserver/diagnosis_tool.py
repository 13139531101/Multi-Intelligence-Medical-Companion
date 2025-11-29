import json
import os
import requests
from typing import Dict, List, Any, Optional
from datetime import datetime
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv
import sys
import pathlib

# 加载环境变量
load_dotenv()

# 创建 FastMCP 应用
mcp = FastMCP("DiagnosisTool")

def call_spark_medical_llm(prompt: str) -> str:
    """
    调用讯飞医疗大模型进行诊断分析
    :param prompt: 输入的提示词
    :return: 大模型的响应
    """
    try:
        # 获取讯飞配置
        app_id = os.getenv('SPARK_APP_ID')
        api_key = os.getenv('SPARK_API_KEY')
        api_secret = os.getenv('SPARK_API_SECRET')
        api_version = os.getenv('SPARK_API_VERSION', 'v3.5')
        
        if not all([app_id, api_key, api_secret]):
            return "讯飞医疗大模型配置缺失，请检查环境变量"
        
        # 这里应该使用讯飞星火大模型的实际API调用
        # 由于讯飞API需要WebSocket连接和复杂的认证，这里提供一个简化的示例
        # 实际使用时建议使用讯飞官方SDK
        
        # 模拟调用讯飞医疗大模型
        mock_response = f"""[讯飞医疗大模型分析]
        
        基于您提供的症状信息，我进行了专业的医疗分析：
        
        {prompt}
        
        建议：
        1. 请及时就医，由专业医生进行详细检查
        2. 注意观察症状变化
        3. 保持良好的生活习惯
        
        注意：此分析仅供参考，不能替代专业医疗诊断。
        """
        
        return mock_response
        
    except Exception as e:
        return f"讯飞医疗大模型调用失败: {str(e)}"

# 模拟疾病诊断知识库
DISEASE_DB = {
    "感冒": {
        "symptoms": ["鼻塞", "流鼻涕", "咳嗽", "轻微发热", "喉咙痛"],
        "severity": "轻度",
        "duration": "3-7天",
        "treatment": ["多休息", "多喝水", "症状性治疗"],
        "complications": ["继发细菌感染", "中耳炎"]
    },
    "流感": {
        "symptoms": ["高热", "头痛", "肌肉酸痛", "乏力", "咳嗽"],
        "severity": "中度",
        "duration": "7-14天",
        "treatment": ["抗病毒药物", "退热药", "充分休息"],
        "complications": ["肺炎", "心肌炎", "脑炎"]
    },
    "高血压": {
        "symptoms": ["头痛", "头晕", "心悸", "视力模糊"],
        "severity": "慢性",
        "duration": "长期",
        "treatment": ["生活方式调整", "降压药物", "定期监测"],
        "complications": ["心脏病", "脑卒中", "肾病"]
    },
    "糖尿病": {
        "symptoms": ["多饮", "多尿", "多食", "体重下降", "乏力"],
        "severity": "慢性",
        "duration": "长期",
        "treatment": ["饮食控制", "运动", "药物治疗", "血糖监测"],
        "complications": ["糖尿病肾病", "糖尿病视网膜病变", "糖尿病足"]
    }
}

# 症状权重映射
SYMPTOM_WEIGHTS = {
    "发热": {"感冒": 0.3, "流感": 0.8},
    "高热": {"流感": 0.9},
    "头痛": {"流感": 0.6, "高血压": 0.7},
    "咳嗽": {"感冒": 0.7, "流感": 0.5},
    "鼻塞": {"感冒": 0.8},
    "流鼻涕": {"感冒": 0.8},
    "肌肉酸痛": {"流感": 0.7},
    "头晕": {"高血压": 0.6},
    "心悸": {"高血压": 0.5},
    "多饮": {"糖尿病": 0.8},
    "多尿": {"糖尿病": 0.8},
    "多食": {"糖尿病": 0.6},
    "体重下降": {"糖尿病": 0.7}
}

def _resolve_db_manager():
    try:
        from HealthAdvisor.database_config import get_db_manager as fn
        return fn
    except Exception:
        pass
    try:
        base = pathlib.Path(__file__).resolve().parents[1]
        p = str(base)
        if p not in sys.path:
            sys.path.append(p)
        from HealthAdvisor.database_config import get_db_manager as fn
        return fn
    except Exception:
        pass
    try:
        from database_config import get_db_manager as fn
        return fn
    except Exception:
        pass
    return None

@mcp.tool()
def analyze_symptoms(symptoms: List[str], patient_age: Optional[int] = None, patient_gender: Optional[str] = None, user_id: str = "", days: int = 180) -> Dict[str, Any]:
    """
    基于真实数据的症状关联检索与证据汇总
    """
    if not symptoms:
        return {"status": "error", "message": "请提供至少一个症状"}
    try:
        _get_db = _resolve_db_manager()
        if _get_db is None:
            return {
                "status": "success",
                "patient": {"age": patient_age, "gender": patient_gender},
                "symptoms": symptoms,
                "evidence_count": 0,
                "evidence": []
            }
        db = _get_db()
        clauses = ["(summary ILIKE %s OR content ILIKE %s)"] * len(symptoms)
        where_symptom = " OR ".join(clauses)
        params: List[Any] = []
        for s in symptoms:
            like = f"%{s.strip()}%"
            params.extend([like, like])
        if user_id:
            where_symptom = f"({where_symptom}) AND user_id = %s"
            params.append(user_id)
        rows = db.execute_query(
            f"""
            SELECT id, user_id, record_type, title, summary, content, created_at
            FROM health_records
            WHERE {where_symptom}
            ORDER BY created_at DESC
            LIMIT 100
            """,
            tuple(params)
        )
        evidence = [
            {
                "id": str(r.get("id")),
                "type": r.get("record_type"),
                "title": r.get("title"),
                "excerpt": (r.get("summary") or r.get("content") or "")[:200],
                "created_at": str(r.get("created_at")),
            }
            for r in rows
        ]
        return {
            "status": "success",
            "patient": {"age": patient_age, "gender": patient_gender},
            "symptoms": symptoms,
            "evidence_count": len(evidence),
            "evidence": evidence,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

@mcp.tool()
def get_disease_info(disease_name: str) -> Dict[str, Any]:
    """
    获取特定疾病的详细信息
    
    Args:
        disease_name: 疾病名称
    
    Returns:
        疾病的详细信息
    """
    disease_name = disease_name.strip()
    
    if disease_name in DISEASE_DB:
        return {
            "status": "success",
            "disease": disease_name,
            "info": DISEASE_DB[disease_name]
        }
    else:
        # 模糊匹配
        matches = []
        for disease in DISEASE_DB.keys():
            if disease_name in disease or disease in disease_name:
                matches.append({
                    "disease": disease,
                    "info": DISEASE_DB[disease]
                })
        
        if matches:
            return {
                "status": "partial_match",
                "query": disease_name,
                "matches": matches
            }
        else:
            return {
                "status": "not_found",
                "query": disease_name,
                "message": "未找到相关疾病信息"
            }

@mcp.tool()
def generate_health_assessment(symptoms: List[str], vital_signs: Optional[Dict[str, float]] = None, medical_history: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    生成综合健康评估报告
    
    Args:
        symptoms: 当前症状列表
        vital_signs: 生命体征数据（体温、血压、心率等）
        medical_history: 既往病史
    
    Returns:
        综合健康评估报告
    """
    if vital_signs is None:
        vital_signs = {}
    if medical_history is None:
        medical_history = []
    
    assessment = {
        "assessment_time": datetime.now().isoformat(),
        "current_symptoms": symptoms,
        "vital_signs_analysis": {},
        "risk_factors": [],
        "recommendations": [],
        "follow_up": []
    }
    
    # 分析生命体征
    if "temperature" in vital_signs:
        temp = vital_signs["temperature"]
        if temp > 37.3:
            assessment["vital_signs_analysis"]["temperature"] = {
                "value": temp,
                "status": "异常",
                "note": "体温偏高，可能存在感染"
            }
        else:
            assessment["vital_signs_analysis"]["temperature"] = {
                "value": temp,
                "status": "正常",
                "note": "体温正常"
            }
    
    if "blood_pressure_systolic" in vital_signs and "blood_pressure_diastolic" in vital_signs:
        sys_bp = vital_signs["blood_pressure_systolic"]
        dia_bp = vital_signs["blood_pressure_diastolic"]
        
        if sys_bp > 140 or dia_bp > 90:
            assessment["vital_signs_analysis"]["blood_pressure"] = {
                "value": f"{sys_bp}/{dia_bp}",
                "status": "异常",
                "note": "血压偏高，建议进一步监测"
            }
            assessment["risk_factors"].append("高血压风险")
        else:
            assessment["vital_signs_analysis"]["blood_pressure"] = {
                "value": f"{sys_bp}/{dia_bp}",
                "status": "正常",
                "note": "血压正常"
            }
    
    # 分析既往病史风险
    chronic_diseases = ["高血压", "糖尿病", "心脏病", "肾病"]
    for history in medical_history:
        for chronic in chronic_diseases:
            if chronic in history:
                assessment["risk_factors"].append(f"既往{chronic}病史")
    
    # 生成建议
    if assessment["risk_factors"]:
        assessment["recommendations"].extend([
            "定期监测相关指标",
            "保持健康的生活方式",
            "按医嘱服药",
            "定期复查"
        ])
    
    if symptoms:
        assessment["recommendations"].extend([
            "密切观察症状变化",
            "如症状加重请及时就医",
            "保持充足休息"
        ])
    
    # 随访建议
    assessment["follow_up"] = [
        "建议1周后复查",
        "如出现新症状立即就医",
        "保持与医生的沟通"
    ]
    
    return {
        "status": "success",
        "assessment": assessment,
        "disclaimer": "此评估仅供参考，具体诊疗请遵循专业医生建议"
    }

@mcp.tool()
def ai_medical_diagnosis(symptoms: List[str], patient_info: Dict[str, Any], medical_history: List[str] = None) -> Dict[str, Any]:
    """
    使用讯飞医疗大模型进行智能诊断分析
    
    Args:
        symptoms: 症状列表
        patient_info: 患者信息（年龄、性别等）
        medical_history: 既往病史（可选）
    
    Returns:
        AI诊断分析结果
    """
    try:
        # 构建提示词
        prompt = f"""
        患者信息：
        - 年龄：{patient_info.get('age', '未知')}
        - 性别：{patient_info.get('gender', '未知')}
        
        主要症状：
        {', '.join(symptoms)}
        
        既往病史：
        {', '.join(medical_history) if medical_history else '无特殊病史'}
        
        请基于以上信息进行专业的医疗分析，包括：
        1. 可能的诊断
        2. 建议的检查项目
        3. 治疗建议
        4. 注意事项
        """
        
        # 调用讯飞医疗大模型
        ai_response = call_spark_medical_llm(prompt)
        
        return {
            "status": "success",
            "ai_analysis": ai_response,
            "input_data": {
                "symptoms": symptoms,
                "patient_info": patient_info,
                "medical_history": medical_history
            },
            "analysis_time": datetime.now().isoformat(),
            "disclaimer": "此AI分析仅供参考，不能替代专业医疗诊断。请及时就医获得专业诊疗。"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"AI诊断分析失败: {str(e)}",
            "disclaimer": "请咨询专业医生进行诊断"
        }

if __name__ == "__main__":
    mcp.run()
