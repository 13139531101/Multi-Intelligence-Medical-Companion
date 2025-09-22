from mcp.server.fastmcp import FastMCP
import json
from typing import Dict, List, Any

# 创建 FastMCP 应用
mcp = FastMCP("HealthKnowledgeTool")

# 模拟健康知识库数据
HEALTH_KNOWLEDGE_DB = {
    "symptoms": {
        "发热": {
            "description": "体温超过正常范围（37.3°C以上）",
            "possible_causes": ["感冒", "流感", "细菌感染", "病毒感染"],
            "recommendations": ["多休息", "多喝水", "物理降温", "必要时就医"]
        },
        "头痛": {
            "description": "头部疼痛不适",
            "possible_causes": ["紧张性头痛", "偏头痛", "高血压", "睡眠不足"],
            "recommendations": ["充足睡眠", "减少压力", "适当按摩", "持续严重需就医"]
        },
        "咳嗽": {
            "description": "呼吸道刺激引起的反射性动作",
            "possible_causes": ["感冒", "支气管炎", "过敏", "肺炎"],
            "recommendations": ["多喝温水", "避免刺激性食物", "保持室内湿度", "持续不愈需就医"]
        }
    },
    "medications": {
        "阿司匹林": {
            "category": "解热镇痛药",
            "indications": ["发热", "疼痛", "心血管疾病预防"],
            "contraindications": ["胃溃疡", "出血性疾病", "儿童水痘"],
            "side_effects": ["胃肠道反应", "出血倾向", "过敏反应"]
        },
        "布洛芬": {
            "category": "非甾体抗炎药",
            "indications": ["发热", "疼痛", "炎症"],
            "contraindications": ["严重心脏病", "肾功能不全", "胃溃疡"],
            "side_effects": ["胃肠道反应", "头晕", "皮疹"]
        }
    },
    "health_tips": {
        "饮食": [
            "保持饮食均衡，多吃蔬菜水果",
            "控制盐分摄入，每日不超过6克",
            "适量饮水，每日1500-2000ml",
            "避免过度饮酒和吸烟"
        ],
        "运动": [
            "每周至少150分钟中等强度有氧运动",
            "结合力量训练，每周2-3次",
            "选择适合自己的运动方式",
            "运动前后要做好热身和拉伸"
        ],
        "睡眠": [
            "成人每日睡眠7-9小时",
            "保持规律的作息时间",
            "睡前避免使用电子设备",
            "创造舒适的睡眠环境"
        ]
    }
}

@mcp.tool()
def search_symptom_info(symptom: str) -> Dict[str, Any]:
    """
    查询症状相关信息
    
    Args:
        symptom: 症状名称
    
    Returns:
        症状的详细信息，包括描述、可能原因和建议
    """
    symptom = symptom.strip()
    
    if symptom in HEALTH_KNOWLEDGE_DB["symptoms"]:
        return {
            "status": "success",
            "symptom": symptom,
            "info": HEALTH_KNOWLEDGE_DB["symptoms"][symptom]
        }
    else:
        # 模糊匹配
        matches = []
        for key in HEALTH_KNOWLEDGE_DB["symptoms"].keys():
            if symptom in key or key in symptom:
                matches.append({
                    "symptom": key,
                    "info": HEALTH_KNOWLEDGE_DB["symptoms"][key]
                })
        
        if matches:
            return {
                "status": "partial_match",
                "query": symptom,
                "matches": matches
            }
        else:
            return {
                "status": "not_found",
                "query": symptom,
                "message": "未找到相关症状信息，建议咨询专业医生"
            }

@mcp.tool()
def search_medication_info(medication: str) -> Dict[str, Any]:
    """
    查询药物相关信息
    
    Args:
        medication: 药物名称
    
    Returns:
        药物的详细信息，包括分类、适应症、禁忌症和副作用
    """
    medication = medication.strip()
    
    if medication in HEALTH_KNOWLEDGE_DB["medications"]:
        return {
            "status": "success",
            "medication": medication,
            "info": HEALTH_KNOWLEDGE_DB["medications"][medication]
        }
    else:
        # 模糊匹配
        matches = []
        for key in HEALTH_KNOWLEDGE_DB["medications"].keys():
            if medication in key or key in medication:
                matches.append({
                    "medication": key,
                    "info": HEALTH_KNOWLEDGE_DB["medications"][key]
                })
        
        if matches:
            return {
                "status": "partial_match",
                "query": medication,
                "matches": matches
            }
        else:
            return {
                "status": "not_found",
                "query": medication,
                "message": "未找到相关药物信息，建议咨询药师或医生"
            }

@mcp.tool()
def get_health_tips(category: str = "all") -> Dict[str, Any]:
    """
    获取健康建议
    
    Args:
        category: 建议类别（饮食、运动、睡眠、all）
    
    Returns:
        相应类别的健康建议
    """
    category = category.strip()
    
    if category == "all":
        return {
            "status": "success",
            "tips": HEALTH_KNOWLEDGE_DB["health_tips"]
        }
    elif category in HEALTH_KNOWLEDGE_DB["health_tips"]:
        return {
            "status": "success",
            "category": category,
            "tips": HEALTH_KNOWLEDGE_DB["health_tips"][category]
        }
    else:
        return {
            "status": "error",
            "message": f"不支持的类别：{category}，支持的类别有：饮食、运动、睡眠"
        }

@mcp.tool()
def analyze_health_concern(concern: str, symptoms: List[str] = None) -> Dict[str, Any]:
    """
    分析健康问题并提供建议
    
    Args:
        concern: 健康问题描述
        symptoms: 相关症状列表
    
    Returns:
        分析结果和建议
    """
    if symptoms is None:
        symptoms = []
    
    # 简单的关键词匹配分析
    analysis = {
        "concern": concern,
        "symptoms_analysis": [],
        "general_advice": [],
        "when_to_see_doctor": []
    }
    
    # 分析症状
    for symptom in symptoms:
        symptom_info = search_symptom_info(symptom)
        if symptom_info["status"] == "success":
            analysis["symptoms_analysis"].append({
                "symptom": symptom,
                "info": symptom_info["info"]
            })
    
    # 通用建议
    analysis["general_advice"] = [
        "保持充足的休息和睡眠",
        "多喝水，保持身体水分",
        "注意饮食营养均衡",
        "避免过度劳累和压力"
    ]
    
    # 就医建议
    analysis["when_to_see_doctor"] = [
        "症状持续加重或超过3天",
        "出现高热（>39°C）",
        "伴有严重疼痛或不适",
        "影响正常生活和工作"
    ]
    
    return {
        "status": "success",
        "analysis": analysis,
        "disclaimer": "此分析仅供参考，不能替代专业医疗诊断，如有严重症状请及时就医"
    }

if __name__ == "__main__":
    mcp.run()