#!/usr/bin/env python3
"""
用药提醒记忆集成工具
为用药提醒智能体提供长期记忆功能的MCP服务器
"""

import asyncio
import json
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence

# 添加AgentMemorySystem到路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'AgentMemorySystem'))

from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.fastmcp import FastMCP
from memory_system import AgentMemorySystem

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("medication_memory_integration")

# 创建服务器实例
server = Server("medication-memory-integration")
# FastMCP 高层封装（用于简化运行与注册）
mcp = FastMCP("MemoryIntegrationTool")

# 全局记忆系统实例
memory_system: Optional[AgentMemorySystem] = None

# 惰性初始化记忆系统（CLI 运行时不会触发 __main__）
async def ensure_memory_system() -> None:
    global memory_system
    if memory_system is not None:
        return
    try:
        ms = AgentMemorySystem()
        await ms.initialize()
        memory_system = ms
        logger.info("用药提醒记忆系统初始化成功(惰性)")
    except Exception as e:
        logger.error(f"惰性初始化记忆系统失败: {e}")
        memory_system = None

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """列出可用的记忆资源"""
    return [
        types.Resource(
            uri="memory://medication/recent_medications",
            name="最近用药记录",
            description="用户最近的用药记录和提醒历史",
            mimeType="application/json",
        ),
        types.Resource(
            uri="memory://medication/adherence_patterns",
            name="服药依从性模式",
            description="用户的服药依从性分析和模式识别",
            mimeType="application/json",
        ),
        types.Resource(
            uri="memory://medication/medication_profiles",
            name="用药档案",
            description="用户的药物过敏史、相互作用和用药偏好",
            mimeType="application/json",
        ),
        types.Resource(
            uri="memory://medication/appointment_history",
            name="复诊历史",
            description="用户的复诊预约和就医记录",
            mimeType="application/json",
        ),
        types.Resource(
            uri="memory://medication/medication_insights",
            name="用药洞察",
            description="基于历史数据的用药建议和风险提醒",
            mimeType="application/json",
        ),
    ]

@server.read_resource()
async def handle_read_resource(uri: types.AnyUrl) -> str:
    """读取记忆资源"""
    if not memory_system:
        return json.dumps({"error": "记忆系统未初始化"}, ensure_ascii=False)
    
    try:
        if uri == "memory://medication/recent_medications":
            # 获取最近的用药记录
            memories = await memory_system.search_memories(
                query="medication OR reminder OR dosage",
                filters={"memory_type": "medication_record"},
                limit=20
            )
            
            recent_medications = []
            for memory in memories:
                try:
                    content = json.loads(memory.content)
                    recent_medications.append({
                        "medication_name": content.get("medication_name", ""),
                        "dosage": content.get("dosage", ""),
                        "frequency": content.get("frequency", ""),
                        "start_date": content.get("start_date", ""),
                        "end_date": content.get("end_date", ""),
                        "adherence_rate": content.get("adherence_rate", 0),
                        "last_taken": content.get("last_taken", ""),
                        "created_at": memory.created_at.isoformat() if memory.created_at else ""
                    })
                except json.JSONDecodeError:
                    continue
            
            return json.dumps(recent_medications, ensure_ascii=False)
        
        elif uri == "memory://medication/adherence_patterns":
            # 获取服药依从性模式
            memories = await memory_system.search_memories(
                query="adherence OR compliance OR missed",
                filters={"memory_type": "adherence_record"},
                limit=50
            )
            
            adherence_data = []
            for memory in memories:
                try:
                    content = json.loads(memory.content)
                    adherence_data.append({
                        "medication_name": content.get("medication_name", ""),
                        "adherence_rate": content.get("adherence_rate", 0),
                        "missed_doses": content.get("missed_doses", 0),
                        "reasons": content.get("reasons", []),
                        "period": content.get("period", ""),
                        "recorded_at": content.get("recorded_at", "")
                    })
                except json.JSONDecodeError:
                    continue
            
            return json.dumps(adherence_data, ensure_ascii=False)
        
        elif uri == "memory://medication/medication_profiles":
            # 获取用药档案
            memories = await memory_system.search_memories(
                query="profile OR allergy OR interaction",
                filters={"memory_type": "medication_profile"},
                limit=10
            )
            
            profiles = []
            for memory in memories:
                try:
                    content = json.loads(memory.content)
                    profiles.append({
                        "user_id": content.get("user_id", ""),
                        "allergies": content.get("allergies", []),
                        "drug_interactions": content.get("drug_interactions", []),
                        "preferences": content.get("preferences", {}),
                        "medical_conditions": content.get("medical_conditions", []),
                        "emergency_contacts": content.get("emergency_contacts", []),
                        "last_updated": content.get("last_updated", "")
                    })
                except json.JSONDecodeError:
                    continue
            
            return json.dumps(profiles, ensure_ascii=False)
        
        elif uri == "memory://medication/appointment_history":
            # 获取复诊历史
            memories = await memory_system.search_memories(
                query="appointment OR visit OR checkup",
                filters={"memory_type": "appointment_record"},
                limit=30
            )
            
            appointments = []
            for memory in memories:
                try:
                    content = json.loads(memory.content)
                    appointments.append({
                        "appointment_date": content.get("appointment_date", ""),
                        "doctor_name": content.get("doctor_name", ""),
                        "department": content.get("department", ""),
                        "purpose": content.get("purpose", ""),
                        "outcome": content.get("outcome", ""),
                        "next_appointment": content.get("next_appointment", ""),
                        "medications_prescribed": content.get("medications_prescribed", []),
                        "notes": content.get("notes", "")
                    })
                except json.JSONDecodeError:
                    continue
            
            return json.dumps(appointments, ensure_ascii=False)
        
        elif uri == "memory://medication/medication_insights":
            # 生成用药洞察
            insights = await _generate_medication_insights()
            return json.dumps(insights, ensure_ascii=False)
        
        else:
            return json.dumps({"error": "未知的资源URI"}, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"读取资源失败: {e}")
        return json.dumps({"error": f"读取资源失败: {str(e)}"}, ensure_ascii=False)

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """列出可用的记忆工具"""
    return [
        types.Tool(
            name="store_medication_record",
            description="存储用药记录和提醒信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "medication_name": {"type": "string", "description": "药物名称"},
                    "dosage": {"type": "string", "description": "剂量"},
                    "frequency": {"type": "string", "description": "用药频率"},
                    "start_date": {"type": "string", "description": "开始日期"},
                    "end_date": {"type": "string", "description": "结束日期"},
                    "user_id": {"type": "string", "description": "用户ID"},
                    "doctor_name": {"type": "string", "description": "开药医生"},
                    "notes": {"type": "string", "description": "备注信息"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"}
                },
                "required": ["medication_name", "dosage", "frequency", "user_id"]
            },
        ),
        types.Tool(
            name="search_medication_history",
            description="搜索用药历史记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "user_id": {"type": "string", "description": "用户ID。如果已知当前用户，请务必提供。"},
                    "medication_name": {"type": "string", "description": "药物名称（可选）"},
                    "date_range": {"type": "string", "description": "日期范围（可选）"},
                    "limit": {"type": "integer", "description": "返回结果数量限制", "default": 10}
                },
                "required": ["query"]
            },
        ),
        types.Tool(
            name="store_adherence_record",
            description="存储服药依从性记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "medication_name": {"type": "string", "description": "药物名称"},
                    "adherence_rate": {"type": "number", "description": "依从性比率（0-1）"},
                    "missed_doses": {"type": "integer", "description": "漏服次数"},
                    "reasons": {"type": "array", "items": {"type": "string"}, "description": "漏服原因"},
                    "period": {"type": "string", "description": "统计周期"},
                    "notes": {"type": "string", "description": "备注"}
                },
                "required": ["user_id", "medication_name", "adherence_rate"]
            },
        ),
        types.Tool(
            name="store_medication_profile",
            description="存储用户用药档案",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "allergies": {"type": "array", "items": {"type": "string"}, "description": "药物过敏史"},
                    "drug_interactions": {"type": "array", "items": {"type": "string"}, "description": "药物相互作用"},
                    "preferences": {"type": "object", "description": "用药偏好"},
                    "medical_conditions": {"type": "array", "items": {"type": "string"}, "description": "疾病史"},
                    "emergency_contacts": {"type": "array", "items": {"type": "object"}, "description": "紧急联系人"}
                },
                "required": ["user_id"]
            },
        ),
        types.Tool(
            name="store_appointment_record",
            description="存储复诊预约记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "appointment_date": {"type": "string", "description": "预约日期"},
                    "doctor_name": {"type": "string", "description": "医生姓名"},
                    "department": {"type": "string", "description": "科室"},
                    "purpose": {"type": "string", "description": "就诊目的"},
                    "outcome": {"type": "string", "description": "就诊结果"},
                    "next_appointment": {"type": "string", "description": "下次预约"},
                    "medications_prescribed": {"type": "array", "items": {"type": "string"}, "description": "开具药物"},
                    "notes": {"type": "string", "description": "备注"}
                },
                "required": ["user_id", "appointment_date", "doctor_name"]
            },
        ),
        types.Tool(
            name="get_medication_insights",
            description="获取用药洞察和建议",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID"},
                    "analysis_type": {"type": "string", "description": "分析类型", "enum": ["adherence", "interactions", "patterns", "recommendations"]},
                    "time_period": {"type": "integer", "description": "分析时间段（天数）", "default": 30}
                },
                "required": ["user_id"]
            },
        ),
        types.Tool(
            name="cleanup_medication_memories",
            description="清理过期的用药记忆",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID（可选）"},
                    "older_than_days": {"type": "integer", "description": "清理多少天前的记录", "default": 365}
                }
            },
        ),
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """处理工具调用"""
    try:
        # 惰性初始化，确保记忆系统可用
        await ensure_memory_system()

        if name == "store_medication_record":
            result = await _store_medication_record(arguments)
        elif name == "search_medication_history":
            result = await _search_medication_history(arguments)
        elif name == "store_adherence_record":
            result = await _store_adherence_record(arguments)
        elif name == "store_medication_profile":
            result = await _store_medication_profile(arguments)
        elif name == "store_appointment_record":
            result = await _store_appointment_record(arguments)
        elif name == "get_medication_insights":
            result = await _get_medication_insights(arguments)
        elif name == "cleanup_medication_memories":
            result = await _cleanup_medication_memories(arguments)
        else:
            result = {"error": f"未知的工具: {name}"}
        
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    
    except Exception as e:
        logger.error(f"工具调用失败: {e}")
        return [types.TextContent(type="text", text=json.dumps({"error": f"工具调用失败: {str(e)}"}, ensure_ascii=False))]

# 工具实现函数
async def _store_medication_record(args: dict) -> dict:
    """存储用药记录"""
    await ensure_memory_system()
    try:
        if memory_system is None:
            return {"error": "记忆系统未初始化"}
        # 构建记录内容
        record_content = {
            "medication_name": args["medication_name"],
            "dosage": args["dosage"],
            "frequency": args["frequency"],
            "start_date": args.get("start_date", ""),
            "end_date": args.get("end_date", ""),
            "doctor_name": args.get("doctor_name", ""),
            "notes": args.get("notes", ""),
            "created_at": datetime.now().isoformat()
        }
        
        # 生成标签
        tags = ["medication", "reminder", args["medication_name"]]
        if args.get("tags"):
            tags.extend(args["tags"])
        
        # 元数据
        metadata = {
            "user_id": args["user_id"],
            "medication_name": args["medication_name"],
            "record_type": "medication_record"
        }
        
        # 存储记录
        memory_id = await memory_system.store_memory(
            content=json.dumps(record_content, ensure_ascii=False),
            memory_type="medication_record",
            tags=tags,
            importance_score=0.8,
            metadata=metadata
        )
        
        return {"success": True, "memory_id": memory_id, "message": "用药记录存储成功"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

# FastMCP 工具封装（确保与原有工具名称一致的语义）
@mcp.tool()
async def store_medication_record(
    user_id: str,
    medication_name: str,
    dosage: str,
    frequency: str,
    start_date: str,
    end_date: str | None = None,
    doctor_name: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    args = {
        "user_id": user_id,
        "medication_name": medication_name,
        "dosage": dosage,
        "frequency": frequency,
        "start_date": start_date,
        "end_date": end_date,
        "doctor_name": doctor_name,
        "notes": notes,
        "tags": tags or [],
    }
    return await _store_medication_record(args)

async def _search_medication_history(args: dict) -> dict:
    """搜索用药历史"""
    await ensure_memory_system()
    try:
        if memory_system is None:
            return {"error": "记忆系统未初始化"}
        # 构建搜索过滤器
        filters = {"memory_type": "medication_record"}
        if args.get("user_id"):
            filters["user_id"] = args["user_id"]
        if args.get("medication_name"):
            filters["medication_name"] = args["medication_name"]
        
        # 搜索记忆
        memories = await memory_system.search_memories(
            query=args["query"],
            limit=args.get("limit", 10),
            filters=filters
        )
        
        # 处理结果
        results = []
        for memory in memories:
            try:
                content = json.loads(memory.content)
                results.append({
                    "memory_id": memory.id,
                    "medication_name": content.get("medication_name", ""),
                    "dosage": content.get("dosage", ""),
                    "frequency": content.get("frequency", ""),
                    "start_date": content.get("start_date", ""),
                    "end_date": content.get("end_date", ""),
                    "doctor_name": content.get("doctor_name", ""),
                    "notes": content.get("notes", ""),
                    "created_at": content.get("created_at", ""),
                    "similarity_score": memory.similarity_score
                })
            except json.JSONDecodeError:
                continue
        
        return {"success": True, "results": results, "count": len(results)}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def search_medication_history(
    query: str,
    user_id: str | None = None,
    medication_name: str | None = None,
    limit: int = 10,
) -> dict:
    args = {
        "query": query,
        "user_id": user_id,
        "medication_name": medication_name,
        "limit": limit,
    }
    return await _search_medication_history(args)

async def _store_adherence_record(args: dict) -> dict:
    """存储依从性记录"""
    await ensure_memory_system()
    try:
        if memory_system is None:
            return {"error": "记忆系统未初始化"}
        # 构建记录内容
        adherence_content = {
            "user_id": args["user_id"],
            "medication_name": args["medication_name"],
            "adherence_rate": args["adherence_rate"],
            "missed_doses": args.get("missed_doses", 0),
            "reasons": args.get("reasons", []),
            "period": args.get("period", ""),
            "notes": args.get("notes", ""),
            "recorded_at": datetime.now().isoformat()
        }
        
        # 生成标签
        tags = ["adherence", "compliance", args["medication_name"]]
        if args["adherence_rate"] < 0.8:
            tags.append("poor_adherence")
        
        # 元数据
        metadata = {
            "user_id": args["user_id"],
            "medication_name": args["medication_name"],
            "adherence_rate": args["adherence_rate"]
        }
        
        # 存储记录
        memory_id = await memory_system.store_memory(
            content=json.dumps(adherence_content, ensure_ascii=False),
            memory_type="adherence_record",
            tags=tags,
            importance_score=0.9 if args["adherence_rate"] < 0.8 else 0.7,
            metadata=metadata
        )
        
        return {"success": True, "memory_id": memory_id, "message": "依从性记录存储成功"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def store_adherence_record(
    user_id: str,
    medication_name: str,
    adherence_rate: float,
    missed_doses: int = 0,
    reasons: list[str] | None = None,
    period: str | None = None,
    notes: str | None = None,
) -> dict:
    args = {
        "user_id": user_id,
        "medication_name": medication_name,
        "adherence_rate": adherence_rate,
        "missed_doses": missed_doses,
        "reasons": reasons or [],
        "period": period or "",
        "notes": notes or "",
    }
    return await _store_adherence_record(args)

async def _store_medication_profile(args: dict) -> dict:
    """存储用药档案"""
    await ensure_memory_system()
    try:
        if memory_system is None:
            return {"error": "记忆系统未初始化"}
        # 构建档案内容
        profile_content = {
            "user_id": args["user_id"],
            "allergies": args.get("allergies", []),
            "drug_interactions": args.get("drug_interactions", []),
            "preferences": args.get("preferences", {}),
            "medical_conditions": args.get("medical_conditions", []),
            "emergency_contacts": args.get("emergency_contacts", []),
            "last_updated": datetime.now().isoformat()
        }
        
        # 生成标签
        tags = ["medication_profile", "user_profile", args["user_id"]]
        if args.get("allergies"):
            tags.extend([f"allergy_{allergy}" for allergy in args["allergies"][:3]])
        
        # 元数据
        metadata = {
            "user_id": args["user_id"],
            "profile_type": "medication_profile"
        }
        
        # 存储档案
        memory_id = await memory_system.store_memory(
            content=json.dumps(profile_content, ensure_ascii=False),
            memory_type="medication_profile",
            tags=tags,
            importance_score=0.9,
            metadata=metadata
        )
        
        return {"success": True, "memory_id": memory_id, "message": "用药档案存储成功"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def store_medication_profile(
    user_id: str,
    allergies: list[str] | None = None,
    drug_interactions: list[str] | None = None,
    preferences: dict | None = None,
    medical_conditions: list[str] | None = None,
    emergency_contacts: list[dict] | None = None,
) -> dict:
    args = {
        "user_id": user_id,
        "allergies": allergies or [],
        "drug_interactions": drug_interactions or [],
        "preferences": preferences or {},
        "medical_conditions": medical_conditions or [],
        "emergency_contacts": emergency_contacts or [],
    }
    return await _store_medication_profile(args)

async def _store_appointment_record(args: dict) -> dict:
    """存储预约记录"""
    await ensure_memory_system()
    try:
        if memory_system is None:
            return {"error": "记忆系统未初始化"}
        # 构建记录内容
        appointment_content = {
            "user_id": args["user_id"],
            "appointment_date": args["appointment_date"],
            "doctor_name": args["doctor_name"],
            "department": args.get("department", ""),
            "purpose": args.get("purpose", ""),
            "outcome": args.get("outcome", ""),
            "next_appointment": args.get("next_appointment", ""),
            "medications_prescribed": args.get("medications_prescribed", []),
            "notes": args.get("notes", ""),
            "created_at": datetime.now().isoformat()
        }
        
        # 生成标签
        tags = ["appointment", "visit", args["doctor_name"]]
        if args.get("department"):
            tags.append(args["department"])
        
        # 元数据
        metadata = {
            "user_id": args["user_id"],
            "doctor_name": args["doctor_name"],
            "appointment_date": args["appointment_date"]
        }
        
        # 存储记录
        memory_id = await memory_system.store_memory(
            content=json.dumps(appointment_content, ensure_ascii=False),
            memory_type="appointment_record",
            tags=tags,
            importance_score=0.8,
            metadata=metadata
        )
        
        return {"success": True, "memory_id": memory_id, "message": "预约记录存储成功"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def store_appointment_record(
    user_id: str,
    appointment_date: str,
    doctor_name: str,
    department: str | None = None,
    purpose: str | None = None,
    outcome: str | None = None,
    next_appointment: str | None = None,
    medications_prescribed: list[str] | None = None,
    notes: str | None = None,
) -> dict:
    args = {
        "user_id": user_id,
        "appointment_date": appointment_date,
        "doctor_name": doctor_name,
        "department": department or "",
        "purpose": purpose or "",
        "outcome": outcome or "",
        "next_appointment": next_appointment or "",
        "medications_prescribed": medications_prescribed or [],
        "notes": notes or "",
    }
    return await _store_appointment_record(args)

async def _get_medication_insights(args: dict) -> dict:
    """获取用药洞察"""
    await ensure_memory_system()
    try:
        if memory_system is None:
            return {"error": "记忆系统未初始化"}
        user_id = args["user_id"]
        analysis_type = args.get("analysis_type", "recommendations")
        time_period = args.get("time_period", 30)
        
        insights = {
            "user_id": user_id,
            "analysis_type": analysis_type,
            "time_period_days": time_period,
            "generated_at": datetime.now().isoformat(),
            "insights": []
        }
        
        # 根据分析类型生成洞察
        if analysis_type == "adherence":
            # 依从性分析
            adherence_memories = await memory_system.search_memories(
                query=f"user_id:{user_id} adherence",
                filters={"memory_type": "adherence_record", "user_id": user_id},
                limit=20
            )
            
            total_rate = 0
            count = 0
            for memory in adherence_memories:
                try:
                    content = json.loads(memory.content)
                    total_rate += content.get("adherence_rate", 0)
                    count += 1
                except json.JSONDecodeError:
                    continue
            
            if count > 0:
                avg_adherence = total_rate / count
                insights["insights"].append({
                    "type": "adherence_summary",
                    "content": f"平均服药依从性: {avg_adherence:.1%}",
                    "severity": "high" if avg_adherence < 0.8 else "low"
                })
        
        elif analysis_type == "patterns":
            # 模式分析
            medication_memories = await memory_system.search_memories(
                query=f"user_id:{user_id}",
                filters={"memory_type": "medication_record", "user_id": user_id},
                limit=50
            )
            
            medication_counts = {}
            for memory in medication_memories:
                try:
                    content = json.loads(memory.content)
                    med_name = content.get("medication_name", "")
                    medication_counts[med_name] = medication_counts.get(med_name, 0) + 1
                except json.JSONDecodeError:
                    continue
            
            if medication_counts:
                most_common = max(medication_counts.items(), key=lambda x: x[1])
                insights["insights"].append({
                    "type": "medication_pattern",
                    "content": f"最常用药物: {most_common[0]} (使用{most_common[1]}次)",
                    "severity": "medium"
                })
        
        return {"success": True, "insights": insights}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def get_medication_insights(
    user_id: str,
    analysis_type: str = "recommendations",
    time_period: int = 30,
) -> dict:
    args = {
        "user_id": user_id,
        "analysis_type": analysis_type,
        "time_period": time_period,
    }
    return await _get_medication_insights(args)

async def _cleanup_medication_memories(args: dict) -> dict:
    """清理用药记忆"""
    await ensure_memory_system()
    try:
        if memory_system is None:
            return {"error": "记忆系统未初始化"}
        user_id = args.get("user_id")
        older_than_days = args.get("older_than_days", 365)
        
        # 构建过滤器
        filters = {}
        if user_id:
            filters["user_id"] = user_id
        
        # 执行清理
        cleanup_date = datetime.now() - timedelta(days=older_than_days)
        cleaned_count = await memory_system.cleanup_memories(
            older_than=cleanup_date,
            filters=filters
        )
        
        return {"success": True, "cleaned_count": cleaned_count, "message": f"清理了{cleaned_count}条记录"}
    
    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def cleanup_medication_memories(
    user_id: str | None = None,
    older_than_days: int = 365,
) -> dict:
    args = {
        "user_id": user_id,
        "older_than_days": older_than_days,
    }
    return await _cleanup_medication_memories(args)

async def _generate_medication_insights() -> dict:
    """生成用药洞察"""
    await ensure_memory_system()
    try:
        if memory_system is None:
            return {"error": "记忆系统未初始化"}
        # 获取最近的用药数据
        recent_medications = await memory_system.search_memories(
            query="medication",
            filters={"memory_type": "medication_record"},
            limit=100
        )
        
        insights = {
            "generated_at": datetime.now().isoformat(),
            "total_medications": len(recent_medications),
            "insights": [],
            "recommendations": []
        }
        
        # 分析用药模式
        medication_frequency = {}
        for memory in recent_medications:
            try:
                content = json.loads(memory.content)
                med_name = content.get("medication_name", "")
                medication_frequency[med_name] = medication_frequency.get(med_name, 0) + 1
            except json.JSONDecodeError:
                continue
        
        if medication_frequency:
            # 最常用药物
            most_common = sorted(medication_frequency.items(), key=lambda x: x[1], reverse=True)[:5]
            insights["insights"].append({
                "type": "common_medications",
                "content": "最常用药物",
                "data": most_common
            })
            
            # 生成建议
            insights["recommendations"].append({
                "type": "monitoring",
                "content": "建议定期监测常用药物的效果和副作用",
                "priority": "medium"
            })
        
        return insights
    
    except Exception as e:
        logger.error(f"生成用药洞察失败: {e}")
        return {"error": str(e)}

# FastMCP 显式运行入口
if __name__ == "__main__":
    mcp.run()