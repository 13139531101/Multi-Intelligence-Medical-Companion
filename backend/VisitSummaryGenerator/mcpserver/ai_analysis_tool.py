#!/usr/bin/env python3
"""
就诊摘要生成智能体 - AI分析工具
提供智能化的医疗文档分析、趋势识别和建议生成功能
"""

import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from mcp.server.fastmcp import FastMCP

# 创建MCP服务器实例
mcp = FastMCP("AIAnalysisTool")

# 医疗知识库（简化版）
MEDICAL_KNOWLEDGE = {
    "symptoms": {
        "胸闷气短": {
            "possible_causes": ["冠心病", "心肌炎", "肺部疾病", "焦虑症"],
            "severity": "中等",
            "urgent_signs": ["持续性胸痛", "呼吸困难加重", "晕厥"]
        },
        "胸痛": {
            "possible_causes": ["冠心病", "心绞痛", "肋间神经痛", "胃食管反流"],
            "severity": "高",
            "urgent_signs": ["剧烈胸痛", "放射至左臂", "出汗"]
        },
        "头痛": {
            "possible_causes": ["紧张性头痛", "偏头痛", "高血压", "脑血管疾病"],
            "severity": "中等",
            "urgent_signs": ["突发剧烈头痛", "伴有呕吐", "意识改变"]
        }
    },
    "diseases": {
        "冠心病": {
            "risk_factors": ["高血压", "糖尿病", "高血脂", "吸烟", "肥胖"],
            "complications": ["心肌梗死", "心力衰竭", "心律失常"],
            "monitoring": ["定期心电图", "血脂检查", "血压监测"]
        },
        "高血压": {
            "risk_factors": ["遗传", "高盐饮食", "肥胖", "缺乏运动"],
            "complications": ["脑卒中", "心肌梗死", "肾脏疾病"],
            "monitoring": ["血压监测", "肾功能检查", "眼底检查"]
        },
        "糖尿病": {
            "risk_factors": ["遗传", "肥胖", "缺乏运动", "高糖饮食"],
            "complications": ["糖尿病肾病", "糖尿病视网膜病变", "糖尿病足"],
            "monitoring": ["血糖监测", "糖化血红蛋白", "尿蛋白检查"]
        }
    },
    "medications": {
        "阿司匹林": {
            "category": "抗血小板药",
            "indications": ["冠心病", "脑血管疾病预防"],
            "side_effects": ["胃肠道出血", "过敏反应"],
            "monitoring": ["定期检查血常规", "注意出血倾向"]
        },
        "美托洛尔": {
            "category": "β受体阻滞剂",
            "indications": ["高血压", "冠心病", "心律失常"],
            "side_effects": ["心动过缓", "低血压", "疲劳"],
            "monitoring": ["监测心率血压", "注意呼吸系统症状"]
        },
        "阿托伐他汀": {
            "category": "他汀类降脂药",
            "indications": ["高胆固醇血症", "冠心病预防"],
            "side_effects": ["肌肉疼痛", "肝功能异常"],
            "monitoring": ["定期检查肝功能", "监测肌酸激酶"]
        }
    }
}

@mcp.tool()
def analyze_health_trends(visit_history: List[Dict[str, Any]], analysis_period: int = 90) -> Dict[str, Any]:
    """
    分析健康趋势
    
    Args:
        visit_history: 就诊历史记录列表
        analysis_period: 分析周期（天数，默认90天）
    
    Returns:
        健康趋势分析结果
    """
    try:
        current_date = datetime.now()
        cutoff_date = current_date - timedelta(days=analysis_period)
        
        # 筛选分析周期内的记录
        recent_visits = []
        for visit in visit_history:
            visit_date = datetime.fromisoformat(visit.get("date", current_date.isoformat()))
            if visit_date >= cutoff_date:
                recent_visits.append(visit)
        
        analysis = {
            "analysis_period": f"{analysis_period}天",
            "total_visits": len(recent_visits),
            "visit_frequency": _calculate_visit_frequency(recent_visits),
            "symptom_trends": _analyze_symptom_trends(recent_visits),
            "diagnosis_patterns": _analyze_diagnosis_patterns(recent_visits),
            "medication_changes": _analyze_medication_changes(recent_visits),
            "health_indicators": _analyze_health_indicators(recent_visits),
            "risk_assessment": _assess_health_risks(recent_visits)
        }
        
        return {
            "success": True,
            "data": analysis,
            "message": f"成功分析{analysis_period}天内的健康趋势"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "健康趋势分析失败"
        }

def _calculate_visit_frequency(visits: List[Dict]) -> Dict[str, Any]:
    """计算就诊频率"""
    if not visits:
        return {"frequency": 0, "trend": "无数据"}
    
    # 按月统计就诊次数
    monthly_counts = {}
    for visit in visits:
        visit_date = datetime.fromisoformat(visit.get("date", datetime.now().isoformat()))
        month_key = visit_date.strftime("%Y-%m")
        monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
    
    avg_monthly = sum(monthly_counts.values()) / len(monthly_counts) if monthly_counts else 0
    
    # 判断趋势
    months = sorted(monthly_counts.keys())
    if len(months) >= 2:
        recent_avg = sum(monthly_counts[m] for m in months[-2:]) / 2
        earlier_avg = sum(monthly_counts[m] for m in months[:-2]) / max(1, len(months) - 2)
        
        if recent_avg > earlier_avg * 1.2:
            trend = "增加"
        elif recent_avg < earlier_avg * 0.8:
            trend = "减少"
        else:
            trend = "稳定"
    else:
        trend = "数据不足"
    
    return {
        "monthly_average": round(avg_monthly, 1),
        "trend": trend,
        "monthly_breakdown": monthly_counts
    }

def _analyze_symptom_trends(visits: List[Dict]) -> Dict[str, Any]:
    """分析症状趋势"""
    symptom_counts = {}
    symptom_timeline = []
    
    for visit in visits:
        visit_date = visit.get("date", "")
        symptoms = visit.get("symptoms", [])
        
        for symptom in symptoms:
            symptom_counts[symptom] = symptom_counts.get(symptom, 0) + 1
            symptom_timeline.append({
                "date": visit_date,
                "symptom": symptom
            })
    
    # 识别最常见症状
    top_symptoms = sorted(symptom_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # 分析症状严重程度趋势
    severity_analysis = {}
    for symptom, count in top_symptoms:
        if symptom in MEDICAL_KNOWLEDGE["symptoms"]:
            severity_analysis[symptom] = {
                "frequency": count,
                "severity_level": MEDICAL_KNOWLEDGE["symptoms"][symptom]["severity"],
                "possible_causes": MEDICAL_KNOWLEDGE["symptoms"][symptom]["possible_causes"]
            }
    
    return {
        "top_symptoms": dict(top_symptoms),
        "severity_analysis": severity_analysis,
        "timeline": symptom_timeline[-10:]  # 最近10条记录
    }

def _analyze_diagnosis_patterns(visits: List[Dict]) -> Dict[str, Any]:
    """分析诊断模式"""
    diagnosis_counts = {}
    diagnosis_timeline = []
    
    for visit in visits:
        visit_date = visit.get("date", "")
        diagnoses = visit.get("diagnoses", [])
        
        for diagnosis in diagnoses:
            diagnosis_counts[diagnosis] = diagnosis_counts.get(diagnosis, 0) + 1
            diagnosis_timeline.append({
                "date": visit_date,
                "diagnosis": diagnosis
            })
    
    # 识别主要诊断
    primary_diagnoses = sorted(diagnosis_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    
    # 分析疾病进展
    disease_progression = {}
    for diagnosis, count in primary_diagnoses:
        if diagnosis in MEDICAL_KNOWLEDGE["diseases"]:
            disease_info = MEDICAL_KNOWLEDGE["diseases"][diagnosis]
            disease_progression[diagnosis] = {
                "frequency": count,
                "risk_factors": disease_info["risk_factors"],
                "potential_complications": disease_info["complications"],
                "monitoring_needs": disease_info["monitoring"]
            }
    
    return {
        "primary_diagnoses": dict(primary_diagnoses),
        "disease_progression": disease_progression,
        "timeline": diagnosis_timeline[-10:]
    }

def _analyze_medication_changes(visits: List[Dict]) -> Dict[str, Any]:
    """分析用药变化"""
    medication_history = []
    current_medications = set()
    discontinued_medications = set()
    
    for visit in sorted(visits, key=lambda x: x.get("date", "")):
        visit_date = visit.get("date", "")
        medications = visit.get("medications", [])
        
        medication_history.append({
            "date": visit_date,
            "medications": medications
        })
        
        # 更新当前用药
        visit_meds = set(med.get("name", "") for med in medications)
        
        # 识别停用的药物
        if current_medications:
            discontinued = current_medications - visit_meds
            discontinued_medications.update(discontinued)
        
        current_medications = visit_meds
    
    # 分析用药安全性
    safety_analysis = {}
    for med_name in current_medications:
        if med_name in MEDICAL_KNOWLEDGE["medications"]:
            med_info = MEDICAL_KNOWLEDGE["medications"][med_name]
            safety_analysis[med_name] = {
                "category": med_info["category"],
                "side_effects": med_info["side_effects"],
                "monitoring_requirements": med_info["monitoring"]
            }
    
    return {
        "current_medications": list(current_medications),
        "discontinued_medications": list(discontinued_medications),
        "medication_safety": safety_analysis,
        "change_history": medication_history[-5:]  # 最近5次变化
    }

def _analyze_health_indicators(visits: List[Dict]) -> Dict[str, Any]:
    """分析健康指标"""
    indicators = {
        "vital_signs": {},
        "lab_values": {},
        "trends": {}
    }
    
    # 收集生命体征数据
    bp_readings = []
    hr_readings = []
    
    for visit in visits:
        vital_signs = visit.get("vital_signs", {})
        
        if "blood_pressure" in vital_signs:
            bp_readings.append({
                "date": visit.get("date", ""),
                "systolic": vital_signs["blood_pressure"].get("systolic", 0),
                "diastolic": vital_signs["blood_pressure"].get("diastolic", 0)
            })
        
        if "heart_rate" in vital_signs:
            hr_readings.append({
                "date": visit.get("date", ""),
                "value": vital_signs["heart_rate"]
            })
    
    # 分析血压趋势
    if bp_readings:
        avg_systolic = sum(r["systolic"] for r in bp_readings) / len(bp_readings)
        avg_diastolic = sum(r["diastolic"] for r in bp_readings) / len(bp_readings)
        
        indicators["vital_signs"]["blood_pressure"] = {
            "average_systolic": round(avg_systolic, 1),
            "average_diastolic": round(avg_diastolic, 1),
            "control_status": "良好" if avg_systolic < 140 and avg_diastolic < 90 else "需要改善",
            "readings": bp_readings[-5:]  # 最近5次读数
        }
    
    # 分析心率趋势
    if hr_readings:
        avg_hr = sum(r["value"] for r in hr_readings) / len(hr_readings)
        
        indicators["vital_signs"]["heart_rate"] = {
            "average": round(avg_hr, 1),
            "status": "正常" if 60 <= avg_hr <= 100 else "异常",
            "readings": hr_readings[-5:]
        }
    
    return indicators

def _assess_health_risks(visits: List[Dict]) -> Dict[str, Any]:
    """评估健康风险"""
    risk_factors = []
    risk_level = "低"
    recommendations = []
    
    # 分析诊断相关风险
    all_diagnoses = []
    for visit in visits:
        all_diagnoses.extend(visit.get("diagnoses", []))
    
    unique_diagnoses = list(set(all_diagnoses))
    
    for diagnosis in unique_diagnoses:
        if diagnosis in MEDICAL_KNOWLEDGE["diseases"]:
            disease_info = MEDICAL_KNOWLEDGE["diseases"][diagnosis]
            risk_factors.extend(disease_info["risk_factors"])
            
            # 添加监测建议
            for monitoring in disease_info["monitoring"]:
                if monitoring not in recommendations:
                    recommendations.append(monitoring)
    
    # 评估整体风险等级
    high_risk_conditions = ["冠心病", "糖尿病", "高血压"]
    if any(condition in unique_diagnoses for condition in high_risk_conditions):
        if len([c for c in unique_diagnoses if c in high_risk_conditions]) >= 2:
            risk_level = "高"
        else:
            risk_level = "中"
    
    # 生成个性化建议
    if "高血压" in unique_diagnoses:
        recommendations.extend(["控制盐分摄入", "规律运动", "定期监测血压"])
    
    if "冠心病" in unique_diagnoses:
        recommendations.extend(["戒烟限酒", "低脂饮食", "规律服药"])
    
    return {
        "overall_risk_level": risk_level,
        "identified_risk_factors": list(set(risk_factors)),
        "active_conditions": unique_diagnoses,
        "recommendations": list(set(recommendations))
    }

@mcp.tool()
def generate_health_insights(analysis_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    生成健康洞察和建议
    
    Args:
        analysis_data: 健康趋势分析数据
    
    Returns:
        健康洞察和个性化建议
    """
    try:
        insights = {
            "key_insights": [],
            "health_score": 0,
            "priority_actions": [],
            "lifestyle_recommendations": [],
            "medical_follow_up": []
        }
        
        # 生成关键洞察
        visit_freq = analysis_data.get("visit_frequency", {})
        if visit_freq.get("trend") == "增加":
            insights["key_insights"].append("就诊频率呈上升趋势，建议关注健康状况变化")
        
        symptom_trends = analysis_data.get("symptom_trends", {})
        top_symptoms = symptom_trends.get("top_symptoms", {})
        if top_symptoms:
            most_common = max(top_symptoms.items(), key=lambda x: x[1])
            insights["key_insights"].append(f"最常见症状：{most_common[0]}，出现{most_common[1]}次")
        
        # 计算健康评分（简化算法）
        base_score = 80
        
        # 根据风险等级调整评分
        risk_assessment = analysis_data.get("risk_assessment", {})
        risk_level = risk_assessment.get("overall_risk_level", "低")
        
        if risk_level == "高":
            base_score -= 30
        elif risk_level == "中":
            base_score -= 15
        
        # 根据就诊频率调整评分
        if visit_freq.get("trend") == "增加":
            base_score -= 10
        elif visit_freq.get("trend") == "减少":
            base_score += 5
        
        insights["health_score"] = max(0, min(100, base_score))
        
        # 生成优先行动建议
        if risk_level == "高":
            insights["priority_actions"].extend([
                "立即咨询主治医生",
                "严格按医嘱服药",
                "定期监测关键指标"
            ])
        
        # 生成生活方式建议
        active_conditions = risk_assessment.get("active_conditions", [])
        if "高血压" in active_conditions:
            insights["lifestyle_recommendations"].extend([
                "减少钠盐摄入（每日<6g）",
                "增加有氧运动（每周150分钟）",
                "保持健康体重"
            ])
        
        if "冠心病" in active_conditions:
            insights["lifestyle_recommendations"].extend([
                "采用地中海饮食模式",
                "戒烟限酒",
                "管理压力和情绪"
            ])
        
        # 生成医疗随访建议
        recommendations = risk_assessment.get("recommendations", [])
        insights["medical_follow_up"] = recommendations[:5]  # 取前5个建议
        
        return {
            "success": True,
            "data": insights,
            "message": "成功生成健康洞察"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "健康洞察生成失败"
        }

@mcp.tool()
def detect_health_alerts(recent_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    检测健康预警信号
    
    Args:
        recent_data: 最近的健康数据
    
    Returns:
        健康预警信息
    """
    try:
        alerts = {
            "urgent_alerts": [],
            "warning_signs": [],
            "monitoring_alerts": [],
            "medication_alerts": []
        }
        
        # 检测紧急预警
        symptoms = recent_data.get("symptoms", [])
        for symptom in symptoms:
            if symptom in MEDICAL_KNOWLEDGE["symptoms"]:
                symptom_info = MEDICAL_KNOWLEDGE["symptoms"][symptom]
                if symptom_info["severity"] == "高":
                    alerts["urgent_alerts"].append({
                        "symptom": symptom,
                        "severity": "高",
                        "action": "建议立即就医"
                    })
        
        # 检测生命体征异常
        vital_signs = recent_data.get("vital_signs", {})
        if "blood_pressure" in vital_signs:
            bp = vital_signs["blood_pressure"]
            systolic = bp.get("systolic", 0)
            diastolic = bp.get("diastolic", 0)
            
            if systolic >= 180 or diastolic >= 110:
                alerts["urgent_alerts"].append({
                    "indicator": "血压",
                    "value": f"{systolic}/{diastolic}mmHg",
                    "action": "高血压危象，立即就医"
                })
            elif systolic >= 140 or diastolic >= 90:
                alerts["warning_signs"].append({
                    "indicator": "血压",
                    "value": f"{systolic}/{diastolic}mmHg",
                    "action": "血压偏高，需要关注"
                })
        
        # 检测用药相关预警
        medications = recent_data.get("medications", [])
        for med in medications:
            med_name = med.get("name", "")
            if med_name in MEDICAL_KNOWLEDGE["medications"]:
                med_info = MEDICAL_KNOWLEDGE["medications"][med_name]
                alerts["medication_alerts"].append({
                    "medication": med_name,
                    "monitoring": med_info["monitoring"],
                    "side_effects": med_info["side_effects"]
                })
        
        # 检测监测提醒
        last_visit_date = recent_data.get("last_visit_date")
        if last_visit_date:
            last_visit = datetime.fromisoformat(last_visit_date)
            days_since_visit = (datetime.now() - last_visit).days
            
            if days_since_visit > 90:
                alerts["monitoring_alerts"].append({
                    "type": "定期复查",
                    "message": f"距离上次就诊已{days_since_visit}天，建议定期复查"
                })
        
        return {
            "success": True,
            "data": alerts,
            "message": "健康预警检测完成"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "健康预警检测失败"
        }

if __name__ == "__main__":
    mcp.run()