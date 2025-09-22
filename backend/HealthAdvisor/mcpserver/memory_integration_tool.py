#!/usr/bin/env python3
"""
健康顾问记忆集成工具

这个MCP服务器为健康顾问提供长期记忆功能，包括：
1. 存储用户健康咨询历史
2. 记忆症状分析和诊断建议
3. 保存用户健康偏好和关注点
4. 提供个性化健康建议基于历史记忆
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# 新增：加载.env 环境变量
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# 添加记忆系统路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'AgentMemorySystem'))
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource,
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
    LoggingLevel
)
from pydantic import AnyUrl
import mcp.types as types

# 导入记忆系统
try:
    from memory_system import AgentMemorySystem
    from config import MemorySystemConfig
except ImportError as e:
    logging.error(f"无法导入记忆系统: {e}")
    sys.exit(1)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("health_advisor_memory")

# 创建MCP服务器
server = Server("health-advisor-memory")

# 全局记忆系统实例
memory_system: Optional[AgentMemorySystem] = None

# 健康顾问智能体ID
HEALTH_ADVISOR_AGENT_ID = "health_advisor"

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """列出可用的记忆资源"""
    return [
        Resource(
            uri=AnyUrl("memory://health-advisor/consultations"),
            name="健康咨询记忆",
            description="获取用户的健康咨询历史记忆",
            mimeType="application/json",
        ),
        Resource(
            uri=AnyUrl("memory://health-advisor/symptoms"),
            name="症状分析记忆",
            description="获取症状分析和诊断建议记忆",
            mimeType="application/json",
        ),
        Resource(
            uri=AnyUrl("memory://health-advisor/preferences"),
            name="用户健康偏好",
            description="获取用户的健康偏好和关注点",
            mimeType="application/json",
        ),
        Resource(
            uri=AnyUrl("memory://health-advisor/insights"),
            name="健康洞察分析",
            description="基于历史记忆的健康洞察",
            mimeType="application/json",
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """读取记忆资源"""
    if not memory_system:
        return json.dumps({"error": "记忆系统未初始化"})
    
    try:
        if str(uri) == "memory://health-advisor/consultations":
            # 获取健康咨询记忆
            memories = memory_system.search_by_tags(
                tags=["健康咨询", "症状分析"],
                agent_id=HEALTH_ADVISOR_AGENT_ID,
                user_id="default_user",
                memory_types=['long_term', 'working'],
                limit=20
            )
            return json.dumps(memories, ensure_ascii=False, indent=2)
        
        elif str(uri) == "memory://health-advisor/symptoms":
            # 获取症状分析记忆
            memories = memory_system.search_by_tags(
                tags=["症状分析", "诊断建议"],
                agent_id=HEALTH_ADVISOR_AGENT_ID,
                user_id="default_user",
                memory_types=['long_term'],
                limit=20
            )
            return json.dumps(memories, ensure_ascii=False, indent=2)
        
        elif str(uri) == "memory://health-advisor/preferences":
            # 获取用户健康偏好
            memories = memory_system.search_by_tags(
                tags=["用户偏好", "健康关注"],
                agent_id=HEALTH_ADVISOR_AGENT_ID,
                user_id="default_user",
                memory_types=['long_term'],
                limit=10
            )
            return json.dumps(memories, ensure_ascii=False, indent=2)
        
        elif str(uri) == "memory://health-advisor/insights":
            # 分析健康洞察
            patterns = memory_system.analyze_memory_patterns(
                agent_id=HEALTH_ADVISOR_AGENT_ID,
                user_id="default_user",
                days=90
            )
            return json.dumps(patterns, ensure_ascii=False, indent=2)
        
        else:
            return json.dumps({"error": f"未知资源: {uri}"})
    
    except Exception as e:
        logger.error(f"读取资源失败: {e}")
        return json.dumps({"error": str(e)})

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """列出可用的记忆工具"""
    return [
        Tool(
            name="store_consultation_memory",
            description="存储健康咨询记忆",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "consultation_type": {
                        "type": "string",
                        "description": "咨询类型（如：症状咨询、疾病咨询、健康建议等）"
                    },
                    "user_query": {
                        "type": "string",
                        "description": "用户的咨询问题"
                    },
                    "advisor_response": {
                        "type": "string",
                        "description": "顾问的回复"
                    },
                    "symptoms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "涉及的症状列表"
                    },
                    "conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可能的疾病或健康状况"
                    },
                    "recommendations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "健康建议列表"
                    },
                    "importance": {
                        "type": "number",
                        "description": "重要性评分 (0.0-1.0)",
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "follow_up_needed": {
                        "type": "boolean",
                        "description": "是否需要后续跟进"
                    }
                },
                "required": ["user_id", "consultation_type", "user_query", "advisor_response"]
            },
        ),
        Tool(
            name="search_consultation_history",
            description="搜索健康咨询历史",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "query": {
                        "type": "string",
                        "description": "搜索查询（症状、疾病、关键词等）"
                    },
                    "consultation_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "咨询类型过滤"
                    },
                    "time_range_days": {
                        "type": "integer",
                        "description": "时间范围（天）",
                        "minimum": 1
                    },
                    "include_symptoms": {
                        "type": "boolean",
                        "description": "是否包含症状信息",
                        "default": True
                     },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制",
                        "minimum": 1,
                        "maximum": 50
                    }
                },
                "required": ["user_id", "query"]
            },
        ),
        Tool(
            name="store_user_health_profile",
            description="存储用户健康档案信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "profile_data": {
                        "type": "object",
                        "description": "健康档案数据",
                        "properties": {
                            "age": {"type": "integer"},
                            "gender": {"type": "string"},
                            "chronic_conditions": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "allergies": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "medications": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "health_goals": {
                                "type": "array",
                                "items": {"type": "string"}
                            },
                            "lifestyle_factors": {
                                "type": "object"
                            }
                        }
                    },
                    "update_type": {
                        "type": "string",
                        "enum": ["full_update", "partial_update", "append"],
                        "description": "更新类型",
                        "default": "partial_update"
                    }
                },
                "required": ["user_id", "profile_data"]
            },
        ),
        Tool(
            name="get_personalized_recommendations",
            description="基于历史记忆获取个性化健康建议",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "current_symptoms": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "当前症状（可选）"
                    },
                    "focus_area": {
                        "type": "string",
                        "description": "关注领域（如：预防、治疗、生活方式等）"
                    },
                    "recommendation_type": {
                        "type": "string",
                        "enum": ["lifestyle", "prevention", "treatment", "general"],
                        "description": "建议类型",
                        "default": "general"
                    }
                },
                "required": ["user_id"]
            },
        ),
        Tool(
            name="analyze_health_patterns",
            description="分析用户健康模式和趋势",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "analysis_period_days": {
                        "type": "integer",
                        "description": "分析周期（天）",
                        "minimum": 7,
                        "default": 90
                    },
                    "pattern_types": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["symptoms", "consultations", "conditions", "recommendations"]
                        },
                        "description": "要分析的模式类型"
                    },
                    "include_trends": {
                        "type": "boolean",
                        "description": "是否包含趋势分析",
                        "default": True
                     }
                },
                "required": ["user_id"]
            },
        ),
        Tool(
            name="store_diagnosis_feedback",
            description="存储诊断反馈和结果",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "original_consultation_id": {
                        "type": "string",
                        "description": "原始咨询记忆ID"
                    },
                    "actual_diagnosis": {
                        "type": "string",
                        "description": "实际诊断结果"
                    },
                    "advisor_accuracy": {
                        "type": "number",
                        "description": "顾问建议的准确性评分 (0.0-1.0)",
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "user_satisfaction": {
                        "type": "number",
                        "description": "用户满意度评分 (0.0-1.0)",
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "feedback_notes": {
                        "type": "string",
                        "description": "反馈备注"
                    }
                },
                "required": ["user_id", "actual_diagnosis"]
            },
        ),
        Tool(
            name="cleanup_advisor_memories",
            description="清理健康顾问记忆数据",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID（可选，不提供则清理所有用户）"
                    },
                    "cleanup_type": {
                        "type": "string",
                        "enum": ["expired", "low_importance", "old_consultations", "all"],
                        "description": "清理类型",
                        "default": "expired"
                    },
                    "retention_days": {
                        "type": "integer",
                        "description": "保留天数（用于old_consultations类型）",
                        "minimum": 30,
                        "default": 365
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "是否为试运行（不实际删除）",
                        "default": True
                    }
                },
                "required": []
            },
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """处理工具调用"""
    if not memory_system:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": "记忆系统未初始化"}, ensure_ascii=False)
        )]
    
    try:
        if name == "store_consultation_memory":
            return await _store_consultation_memory(arguments)
        elif name == "search_consultation_history":
            return await _search_consultation_history(arguments)
        elif name == "store_user_health_profile":
            return await _store_user_health_profile(arguments)
        elif name == "get_personalized_recommendations":
            return await _get_personalized_recommendations(arguments)
        elif name == "analyze_health_patterns":
            return await _analyze_health_patterns(arguments)
        elif name == "store_diagnosis_feedback":
            return await _store_diagnosis_feedback(arguments)
        elif name == "cleanup_advisor_memories":
            return await _cleanup_advisor_memories(arguments)
        else:
            return [types.TextContent(
                type="text",
                text=json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
            )]
    
    except Exception as e:
        logger.error(f"工具调用失败 {name}: {e}")
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": str(e)}, ensure_ascii=False)
        )]

async def _store_consultation_memory(arguments: dict) -> list[types.TextContent]:
    """存储健康咨询记忆"""
    user_id = arguments["user_id"]
    consultation_type = arguments["consultation_type"]
    user_query = arguments["user_query"]
    advisor_response = arguments["advisor_response"]
    symptoms = arguments.get("symptoms", [])
    conditions = arguments.get("conditions", [])
    recommendations = arguments.get("recommendations", [])
    importance = arguments.get("importance", 0.7)
    follow_up_needed = arguments.get("follow_up_needed", False)
    
    # 构建记忆内容
    content = {
        'text': f"健康咨询: {consultation_type}\n用户问题: {user_query}\n顾问回复: {advisor_response}",
        'structured_data': {
            'consultation_type': consultation_type,
            'user_query': user_query,
            'advisor_response': advisor_response,
            'symptoms': symptoms,
            'conditions': conditions,
            'recommendations': recommendations,
            'follow_up_needed': follow_up_needed,
            'consultation_time': datetime.now().isoformat()
        },
        'metadata': {
            'data_source': 'health_advisor',
            'consultation_type': consultation_type,
            'has_symptoms': len(symptoms) > 0,
            'has_conditions': len(conditions) > 0,
            'follow_up_needed': follow_up_needed
        }
    }
    
    # 设置标签
    tags = ['健康咨询', consultation_type]
    if symptoms:
        tags.extend(['症状分析'] + [f"症状:{s}" for s in symptoms[:3]])  # 限制症状标签数量
    if conditions:
        tags.extend(['疾病咨询'] + [f"疾病:{c}" for c in conditions[:2]])  # 限制疾病标签数量
    if follow_up_needed:
        tags.append('需要跟进')
    if importance > 0.8:
        tags.append('高重要性')
    
    # 存储记忆
    memory_id = memory_system.store_memory(
        agent_id=HEALTH_ADVISOR_AGENT_ID,
        user_id=user_id,
        content=content,
        memory_type='long_term',
        importance=importance,
        tags=tags,
        expires_hours=8760 if importance > 0.7 else 4380  # 高重要性1年，普通6个月
    )
    
    result = {
        "success": True,
        "memory_id": memory_id,
        "message": f"成功存储{consultation_type}咨询记忆",
        "consultation_summary": {
            "type": consultation_type,
            "symptoms_count": len(symptoms),
            "conditions_count": len(conditions),
            "recommendations_count": len(recommendations),
            "importance": importance,
            "follow_up_needed": follow_up_needed
        }
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2)
    )]

async def _search_consultation_history(arguments: dict) -> list[types.TextContent]:
    """搜索健康咨询历史"""
    user_id = arguments["user_id"]
    query = arguments["query"]
    consultation_types = arguments.get("consultation_types", [])
    time_range_days = arguments.get("time_range_days")
    include_symptoms = arguments.get("include_symptoms", True)
    limit = arguments.get("limit", 20)
    
    # 执行搜索
    memories = memory_system.search_memories(
        query=query,
        agent_id=HEALTH_ADVISOR_AGENT_ID,
        user_id=user_id,
        memory_types=['long_term', 'working'],
        limit=limit * 2,
        min_similarity=0.3
    )
    
    # 过滤结果
    filtered_memories = []
    for memory in memories:
        # 咨询类型过滤
        if consultation_types:
            memory_tags = memory.get('tags', [])
            if not any(ct in memory_tags for ct in consultation_types):
                continue
        
        # 时间范围过滤
        if time_range_days:
            created_at = memory.get('created_at', '')
            if created_at:
                try:
                    created_date = datetime.fromisoformat(created_at)
                    if (datetime.now() - created_date).days > time_range_days:
                        continue
                except:
                    continue
        
        # 处理症状信息
        if include_symptoms:
            structured_data = memory.get('content', {}).get('structured_data', {})
            memory['symptoms'] = structured_data.get('symptoms', [])
            memory['conditions'] = structured_data.get('conditions', [])
        
        filtered_memories.append(memory)
        
        if len(filtered_memories) >= limit:
            break
    
    result = {
        "success": True,
        "query": query,
        "total_found": len(filtered_memories),
        "consultations": filtered_memories
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2)
    )]

async def _store_user_health_profile(arguments: dict) -> list[types.TextContent]:
    """存储用户健康档案信息"""
    user_id = arguments["user_id"]
    profile_data = arguments["profile_data"]
    update_type = arguments.get("update_type", "partial_update")
    
    # 构建记忆内容
    content = {
        'text': f"用户健康档案更新: {update_type}",
        'structured_data': {
            'profile_data': profile_data,
            'update_type': update_type,
            'updated_at': datetime.now().isoformat()
        },
        'metadata': {
            'data_source': 'health_advisor',
            'profile_update': True,
            'update_type': update_type
        }
    }
    
    # 设置标签
    tags = ['用户档案', '健康信息', update_type]
    
    # 根据档案内容添加特定标签
    if 'chronic_conditions' in profile_data and profile_data['chronic_conditions']:
        tags.extend(['慢性病'] + [f"慢性病:{c}" for c in profile_data['chronic_conditions'][:2]])
    if 'allergies' in profile_data and profile_data['allergies']:
        tags.extend(['过敏信息'] + [f"过敏:{a}" for a in profile_data['allergies'][:2]])
    if 'medications' in profile_data and profile_data['medications']:
        tags.append('用药信息')
    if 'health_goals' in profile_data and profile_data['health_goals']:
        tags.append('健康目标')
    
    # 存储记忆（档案信息长期保存）
    memory_id = memory_system.store_memory(
        agent_id=HEALTH_ADVISOR_AGENT_ID,
        user_id=user_id,
        content=content,
        memory_type='long_term',
        importance=0.9,  # 档案信息高重要性
        tags=tags,
        expires_hours=None  # 不过期
    )
    
    result = {
        "success": True,
        "memory_id": memory_id,
        "message": f"成功存储用户健康档案: {update_type}",
        "profile_summary": {
            "update_type": update_type,
            "fields_updated": list(profile_data.keys()),
            "has_chronic_conditions": bool(profile_data.get('chronic_conditions')),
            "has_allergies": bool(profile_data.get('allergies')),
            "has_medications": bool(profile_data.get('medications'))
        }
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2)
    )]

async def _get_personalized_recommendations(arguments: dict) -> list[types.TextContent]:
    """获取个性化健康建议"""
    user_id = arguments["user_id"]
    current_symptoms = arguments.get("current_symptoms", [])
    focus_area = arguments.get("focus_area")
    recommendation_type = arguments.get("recommendation_type", "general")
    
    # 获取用户历史记忆
    user_memories = memory_system.search_by_tags(
        tags=["健康咨询", "用户档案"],
        agent_id=HEALTH_ADVISOR_AGENT_ID,
        user_id=user_id,
        memory_types=['long_term'],
        limit=50
    )
    
    # 如果有当前症状，搜索相关历史
    symptom_memories = []
    if current_symptoms:
        for symptom in current_symptoms:
            symptom_results = memory_system.search_memories(
                query=symptom,
                agent_id=HEALTH_ADVISOR_AGENT_ID,
                user_id=user_id,
                memory_types=['long_term'],
                limit=10
            )
            symptom_memories.extend(symptom_results)
    
    # 分析用户健康模式
    patterns = memory_system.analyze_memory_patterns(
        agent_id=HEALTH_ADVISOR_AGENT_ID,
        user_id=user_id,
        days=180
    )
    
    # 生成个性化建议
    recommendations = _generate_personalized_recommendations(
        user_memories, symptom_memories, patterns, 
        current_symptoms, focus_area, recommendation_type
    )
    
    result = {
        "success": True,
        "user_id": user_id,
        "current_symptoms": current_symptoms,
        "focus_area": focus_area,
        "recommendation_type": recommendation_type,
        "total_memories_analyzed": len(user_memories),
        "symptom_memories_found": len(symptom_memories),
        "recommendations": recommendations,
        "patterns_summary": patterns
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2)
    )]

async def _analyze_health_patterns(arguments: dict) -> list[types.TextContent]:
    """分析用户健康模式和趋势"""
    user_id = arguments["user_id"]
    analysis_period_days = arguments.get("analysis_period_days", 90)
    pattern_types = arguments.get("pattern_types", ["symptoms", "consultations", "conditions"])
    include_trends = arguments.get("include_trends", True)
    
    # 获取分析周期内的记忆
    start_time = datetime.now() - timedelta(days=analysis_period_days)
    end_time = datetime.now()
    
    memories = memory_system.search_by_time_range(
        start_time=start_time,
        end_time=end_time,
        agent_id=HEALTH_ADVISOR_AGENT_ID,
        user_id=user_id,
        memory_types=['long_term', 'working'],
        limit=200
    )
    
    # 分析不同类型的模式
    analysis_results = {}
    
    if "symptoms" in pattern_types:
        analysis_results["symptom_patterns"] = _analyze_symptom_patterns(memories)
    
    if "consultations" in pattern_types:
        analysis_results["consultation_patterns"] = _analyze_consultation_patterns(memories)
    
    if "conditions" in pattern_types:
        analysis_results["condition_patterns"] = _analyze_condition_patterns(memories)
    
    if "recommendations" in pattern_types:
        analysis_results["recommendation_patterns"] = _analyze_recommendation_patterns(memories)
    
    # 趋势分析
    if include_trends:
        analysis_results["trends"] = _analyze_health_trends(memories, analysis_period_days)
    
    # 整体模式分析
    overall_patterns = memory_system.analyze_memory_patterns(
        agent_id=HEALTH_ADVISOR_AGENT_ID,
        user_id=user_id,
        days=analysis_period_days
    )
    
    result = {
        "success": True,
        "user_id": user_id,
        "analysis_period_days": analysis_period_days,
        "total_memories_analyzed": len(memories),
        "pattern_types": pattern_types,
        "analysis_results": analysis_results,
        "overall_patterns": overall_patterns
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2)
    )]

async def _store_diagnosis_feedback(arguments: dict) -> list[types.TextContent]:
    """存储诊断反馈和结果"""
    user_id = arguments["user_id"]
    original_consultation_id = arguments.get("original_consultation_id")
    actual_diagnosis = arguments["actual_diagnosis"]
    advisor_accuracy = arguments.get("advisor_accuracy", 0.5)
    user_satisfaction = arguments.get("user_satisfaction", 0.5)
    feedback_notes = arguments.get("feedback_notes", "")
    
    # 构建记忆内容
    content = {
        'text': f"诊断反馈: {actual_diagnosis}\n准确性: {advisor_accuracy}\n满意度: {user_satisfaction}",
        'structured_data': {
            'original_consultation_id': original_consultation_id,
            'actual_diagnosis': actual_diagnosis,
            'advisor_accuracy': advisor_accuracy,
            'user_satisfaction': user_satisfaction,
            'feedback_notes': feedback_notes,
            'feedback_time': datetime.now().isoformat()
        },
        'metadata': {
            'data_source': 'diagnosis_feedback',
            'has_original_consultation': bool(original_consultation_id),
            'accuracy_level': 'high' if advisor_accuracy > 0.7 else 'medium' if advisor_accuracy > 0.4 else 'low',
            'satisfaction_level': 'high' if user_satisfaction > 0.7 else 'medium' if user_satisfaction > 0.4 else 'low'
        }
    }
    
    # 设置标签
    tags = ['诊断反馈', '准确性评估', actual_diagnosis]
    if advisor_accuracy > 0.7:
        tags.append('高准确性')
    elif advisor_accuracy < 0.4:
        tags.append('低准确性')
    
    if user_satisfaction > 0.7:
        tags.append('高满意度')
    elif user_satisfaction < 0.4:
        tags.append('低满意度')
    
    # 重要性基于准确性和满意度
    importance = (advisor_accuracy + user_satisfaction) / 2
    
    # 存储记忆
    memory_id = memory_system.store_memory(
        agent_id=HEALTH_ADVISOR_AGENT_ID,
        user_id=user_id,
        content=content,
        memory_type='long_term',
        importance=importance,
        tags=tags,
        expires_hours=8760  # 1年
    )
    
    result = {
        "success": True,
        "memory_id": memory_id,
        "message": "成功存储诊断反馈",
        "feedback_summary": {
            "actual_diagnosis": actual_diagnosis,
            "advisor_accuracy": advisor_accuracy,
            "user_satisfaction": user_satisfaction,
            "importance": importance
        }
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2)
    )]

async def _cleanup_advisor_memories(arguments: dict) -> list[types.TextContent]:
    """清理健康顾问记忆数据"""
    user_id = arguments.get("user_id")
    cleanup_type = arguments.get("cleanup_type", "expired")
    retention_days = arguments.get("retention_days", 365)
    dry_run = arguments.get("dry_run", True)
    
    results = {
        "success": True,
        "cleanup_type": cleanup_type,
        "dry_run": dry_run,
        "cleaned_count": 0,
        "details": []
    }
    
    try:
        if cleanup_type == "expired":
            if not dry_run:
                cleaned = memory_system.cleanup_expired_memories()
                results["cleaned_count"] = cleaned
                results["details"].append(f"清理了 {cleaned} 条过期记忆")
            else:
                results["details"].append("试运行：将清理过期记忆")
        
        elif cleanup_type == "low_importance" and user_id:
            if not dry_run:
                cleaned = memory_system.cleanup_low_importance_memories(
                    agent_id=HEALTH_ADVISOR_AGENT_ID,
                    user_id=user_id,
                    threshold=0.3,
                    max_age_days=180
                )
                results["cleaned_count"] = cleaned
                results["details"].append(f"清理了 {cleaned} 条低重要性记忆")
            else:
                results["details"].append("试运行：将清理低重要性记忆")
        
        elif cleanup_type == "old_consultations" and user_id:
            # 清理旧的咨询记录
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            if not dry_run:
                old_memories = memory_system.search_by_time_range(
                    start_time=datetime.min,
                    end_time=cutoff_date,
                    agent_id=HEALTH_ADVISOR_AGENT_ID,
                    user_id=user_id,
                    memory_types=['long_term', 'working'],
                    limit=1000
                )
                
                # 只删除低重要性的旧咨询
                deleted_count = 0
                for memory in old_memories:
                    if memory.get('importance', 0) < 0.6 and '健康咨询' in memory.get('tags', []):
                        memory_system.delete_memory(memory['id'])
                        deleted_count += 1
                
                results["cleaned_count"] = deleted_count
                results["details"].append(f"清理了 {deleted_count} 条旧咨询记录")
            else:
                results["details"].append(f"试运行：将清理 {retention_days} 天前的旧咨询记录")
        
        elif cleanup_type == "all":
            if not dry_run:
                total_cleaned = 0
                
                # 清理过期记忆
                expired = memory_system.cleanup_expired_memories()
                total_cleaned += expired
                results["details"].append(f"清理过期记忆: {expired} 条")
                
                if user_id:
                    # 清理低重要性记忆
                    low_imp = memory_system.cleanup_low_importance_memories(
                        agent_id=HEALTH_ADVISOR_AGENT_ID,
                        user_id=user_id
                    )
                    total_cleaned += low_imp
                    results["details"].append(f"清理低重要性记忆: {low_imp} 条")
                
                results["cleaned_count"] = total_cleaned
            else:
                results["details"].append("试运行：将执行全面清理")
        
        else:
            results["success"] = False
            results["error"] = f"不支持的清理类型: {cleanup_type}"
    
    except Exception as e:
        results["success"] = False
        results["error"] = str(e)
    
    return [types.TextContent(
        type="text",
        text=json.dumps(results, ensure_ascii=False, indent=2)
    )]

def _generate_personalized_recommendations(user_memories, symptom_memories, patterns, 
                                         current_symptoms, focus_area, recommendation_type):
    """生成个性化健康建议"""
    recommendations = []
    
    # 基于历史记忆的建议
    if user_memories:
        # 分析用户的健康关注点
        health_concerns = set()
        chronic_conditions = set()
        
        for memory in user_memories:
            tags = memory.get('tags', [])
            structured_data = memory.get('content', {}).get('structured_data', {})
            
            # 提取慢性病信息
            if 'chronic_conditions' in structured_data:
                chronic_conditions.update(structured_data['chronic_conditions'])
            
            # 提取健康关注点
            for tag in tags:
                if tag.startswith('症状:') or tag.startswith('疾病:'):
                    health_concerns.add(tag.split(':', 1)[1])
        
        if chronic_conditions:
            recommendations.append({
                "type": "chronic_condition_management",
                "title": "慢性病管理建议",
                "content": f"基于您的慢性病史（{', '.join(list(chronic_conditions)[:3])}），建议定期监测相关指标",
                "priority": "high"
            })
        
        if health_concerns:
            recommendations.append({
                "type": "preventive_care",
                "title": "预防性护理",
                "content": f"根据您的健康关注历史，建议关注：{', '.join(list(health_concerns)[:3])}",
                "priority": "medium"
            })
    
    # 基于当前症状的建议
    if current_symptoms and symptom_memories:
        symptom_recommendations = []
        for memory in symptom_memories[:5]:  # 取前5个相关记忆
            structured_data = memory.get('content', {}).get('structured_data', {})
            if 'recommendations' in structured_data:
                symptom_recommendations.extend(structured_data['recommendations'])
        
        if symptom_recommendations:
            recommendations.append({
                "type": "symptom_based",
                "title": "基于症状的建议",
                "content": f"根据您的症状历史，建议：{'; '.join(symptom_recommendations[:3])}",
                "priority": "high"
            })
    
    # 基于模式分析的建议
    if patterns:
        tag_patterns = patterns.get('by_tags', {})
        if tag_patterns:
            most_common_tags = sorted(tag_patterns.items(), key=lambda x: x[1], reverse=True)[:3]
            recommendations.append({
                "type": "pattern_based",
                "title": "基于健康模式的建议",
                "content": f"您经常关注的健康话题：{', '.join([tag for tag, _ in most_common_tags])}",
                "priority": "medium"
            })
    
    # 根据建议类型过滤
    if recommendation_type != "general":
        filtered_recommendations = []
        for rec in recommendations:
            if recommendation_type == "lifestyle" and rec["type"] in ["preventive_care", "pattern_based"]:
                filtered_recommendations.append(rec)
            elif recommendation_type == "prevention" and rec["type"] in ["preventive_care", "chronic_condition_management"]:
                filtered_recommendations.append(rec)
            elif recommendation_type == "treatment" and rec["type"] in ["symptom_based", "chronic_condition_management"]:
                filtered_recommendations.append(rec)
        recommendations = filtered_recommendations
    
    # 如果没有个性化建议，提供通用建议
    if not recommendations:
        recommendations.append({
            "type": "general",
            "title": "通用健康建议",
            "content": "建议保持规律作息、均衡饮食、适量运动，定期体检",
            "priority": "medium"
        })
    
    return recommendations

def _analyze_symptom_patterns(memories):
    """分析症状模式"""
    symptom_frequency = {}
    symptom_timeline = []
    
    for memory in memories:
        structured_data = memory.get('content', {}).get('structured_data', {})
        symptoms = structured_data.get('symptoms', [])
        created_at = memory.get('created_at', '')
        
        for symptom in symptoms:
            symptom_frequency[symptom] = symptom_frequency.get(symptom, 0) + 1
            if created_at:
                symptom_timeline.append({
                    'symptom': symptom,
                    'date': created_at
                })
    
    return {
        'frequency': symptom_frequency,
        'timeline': symptom_timeline,
        'most_common': sorted(symptom_frequency.items(), key=lambda x: x[1], reverse=True)[:5]
    }

def _analyze_consultation_patterns(memories):
    """分析咨询模式"""
    consultation_types = {}
    consultation_timeline = []
    
    for memory in memories:
        if '健康咨询' in memory.get('tags', []):
            structured_data = memory.get('content', {}).get('structured_data', {})
            consultation_type = structured_data.get('consultation_type', '未知')
            created_at = memory.get('created_at', '')
            
            consultation_types[consultation_type] = consultation_types.get(consultation_type, 0) + 1
            if created_at:
                consultation_timeline.append({
                    'type': consultation_type,
                    'date': created_at
                })
    
    return {
        'types_frequency': consultation_types,
        'timeline': consultation_timeline,
        'most_common_types': sorted(consultation_types.items(), key=lambda x: x[1], reverse=True)[:5]
    }

def _analyze_condition_patterns(memories):
    """分析疾病状况模式"""
    condition_frequency = {}
    condition_timeline = []
    
    for memory in memories:
        structured_data = memory.get('content', {}).get('structured_data', {})
        conditions = structured_data.get('conditions', [])
        created_at = memory.get('created_at', '')
        
        for condition in conditions:
            condition_frequency[condition] = condition_frequency.get(condition, 0) + 1
            if created_at:
                condition_timeline.append({
                    'condition': condition,
                    'date': created_at
                })
    
    return {
        'frequency': condition_frequency,
        'timeline': condition_timeline,
        'most_common': sorted(condition_frequency.items(), key=lambda x: x[1], reverse=True)[:5]
    }

def _analyze_recommendation_patterns(memories):
    """分析建议模式"""
    recommendation_frequency = {}
    
    for memory in memories:
        structured_data = memory.get('content', {}).get('structured_data', {})
        recommendations = structured_data.get('recommendations', [])
        
        for rec in recommendations:
            recommendation_frequency[rec] = recommendation_frequency.get(rec, 0) + 1
    
    return {
        'frequency': recommendation_frequency,
        'most_common': sorted(recommendation_frequency.items(), key=lambda x: x[1], reverse=True)[:10]
    }

def _analyze_health_trends(memories, period_days):
    """分析健康趋势"""
    trends = {
        'consultation_frequency_trend': {},
        'symptom_severity_trend': {},
        'follow_up_trend': {}
    }
    
    # 按月分组分析咨询频率
    for memory in memories:
        created_at = memory.get('created_at', '')
        if created_at:
            try:
                date = datetime.fromisoformat(created_at)
                month_key = date.strftime('%Y-%m')
                trends['consultation_frequency_trend'][month_key] = \
                    trends['consultation_frequency_trend'].get(month_key, 0) + 1
            except:
                pass
    
    # 分析跟进趋势
    follow_up_count = 0
    total_consultations = 0
    for memory in memories:
        if '健康咨询' in memory.get('tags', []):
            total_consultations += 1
            structured_data = memory.get('content', {}).get('structured_data', {})
            if structured_data.get('follow_up_needed', False):
                follow_up_count += 1
    
    if total_consultations > 0:
        trends['follow_up_trend']['follow_up_rate'] = follow_up_count / total_consultations
        trends['follow_up_trend']['total_consultations'] = total_consultations
        trends['follow_up_trend']['follow_up_needed'] = follow_up_count
    
    return trends

# 在启动服务器前，增加一个异步初始化记忆系统的函数，避免因数据库连接阻塞握手
async def _init_memory_system_background(timeout_seconds: int = 5) -> None:
    """在后台线程初始化记忆系统，设置超时，避免阻塞MCP握手。"""
    global memory_system
    try:
        loop = asyncio.get_running_loop()
        # 在默认线程池中执行同步的构造函数
        def _create_instance():
            return AgentMemorySystem()
        mem = await asyncio.wait_for(loop.run_in_executor(None, _create_instance), timeout=timeout_seconds)
        memory_system = mem
        logger.info("健康顾问记忆系统初始化成功（后台完成）")
    except asyncio.TimeoutError:
        logger.warning(f"记忆系统初始化超过 {timeout_seconds}s 超时，服务器将以无记忆模式先行启动")
    except Exception as e:
        logger.warning(f"记忆系统初始化失败（已降级为无记忆模式）: {e}")

async def main():
    """主函数"""
    global memory_system
    
    # 以后台方式初始化记忆系统，避免阻塞 stdio 握手
    asyncio.create_task(_init_memory_system_background(timeout_seconds=5))
    
    # 运行服务器
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="health-advisor-memory",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())