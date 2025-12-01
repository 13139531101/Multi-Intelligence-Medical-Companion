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
        # 处理不同资源的请求
        if str(uri) == "memory://medication/recent_medications":
            return json.dumps({"error": "Resource request requires user context which is not currently supported via this URI scheme."}, ensure_ascii=False)

        elif str(uri) == "memory://medication/adherence_patterns":
             return json.dumps({"error": "Resource request requires user context."}, ensure_ascii=False)

        elif str(uri) == "memory://medication/medication_profiles":
             return json.dumps({"error": "Resource request requires user context."}, ensure_ascii=False)

        elif str(uri) == "memory://medication/appointment_history":
             return json.dumps({"error": "Resource request requires user context."}, ensure_ascii=False)

        elif str(uri) == "memory://medication/medication_insights":
             return json.dumps({"error": "Resource request requires user context."}, ensure_ascii=False)

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
                    "user_id": {"type": "string", "description": "用户ID (可选，自动获取)"},
                    "doctor_name": {"type": "string", "description": "开药医生"},
                    "notes": {"type": "string", "description": "备注信息"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"}
                },
                "required": ["medication_name", "dosage", "frequency"]
            },
        ),
        types.Tool(
            name="search_medication_history",
            description="搜索用药历史记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"},
                    "user_id": {"type": "string", "description": "用户ID (可选，自动获取)"},
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
                    "user_id": {"type": "string", "description": "用户ID (可选，自动获取)"},
                    "medication_name": {"type": "string", "description": "药物名称"},
                    "adherence_rate": {"type": "number", "description": "依从性比率（0-1）"},
                    "missed_doses": {"type": "integer", "description": "漏服次数"},
                    "reasons": {"type": "array", "items": {"type": "string"}, "description": "漏服原因"},
                    "period": {"type": "string", "description": "统计周期"},
                    "notes": {"type": "string", "description": "备注"}
                },
                "required": ["medication_name", "adherence_rate"]
            },
        ),
        types.Tool(
            name="store_medication_profile",
            description="存储用户用药档案",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID (可选，自动获取)"},
                    "allergies": {"type": "array", "items": {"type": "string"}, "description": "药物过敏史"},
                    "drug_interactions": {"type": "array", "items": {"type": "string"}, "description": "药物相互作用"},
                    "preferences": {"type": "object", "description": "用药偏好"},
                    "medical_conditions": {"type": "array", "items": {"type": "string"}, "description": "疾病史"},
                    "emergency_contacts": {"type": "array", "items": {"type": "object"}, "description": "紧急联系人"}
                },
                "required": []
            },
        ),
        types.Tool(
            name="store_appointment_record",
            description="存储复诊预约记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID (可选，自动获取)"},
                    "appointment_date": {"type": "string", "description": "预约日期"},
                    "doctor_name": {"type": "string", "description": "医生姓名"},
                    "department": {"type": "string", "description": "科室"},
                    "purpose": {"type": "string", "description": "就诊目的"},
                    "outcome": {"type": "string", "description": "就诊结果"},
                    "next_appointment": {"type": "string", "description": "下次预约"},
                    "medications_prescribed": {"type": "array", "items": {"type": "string"}, "description": "开具药物"},
                    "notes": {"type": "string", "description": "备注"}
                },
                "required": ["appointment_date", "doctor_name"]
            },
        ),
        types.Tool(
            name="get_medication_insights",
            description="获取用药洞察和建议",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID (可选，自动获取)"},
                    "analysis_type": {"type": "string", "description": "分析类型", "enum": ["adherence", "interactions", "patterns", "recommendations"]},
                    "time_period": {"type": "integer", "description": "分析时间段（天数）", "default": 30}
                },
                "required": []
            },
        ),
        types.Tool(
            name="cleanup_medication_memories",
            description="清理过期的用药记忆",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "用户ID (可选，自动获取)"},
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

        # 自动补充 user_id
        if not args.get("user_id"):
            args["user_id"] = os.environ.get("A2A_CURRENT_USER_ID")

        if not args.get("user_id"):
            return {"error": "缺少用户ID (user_id)"}

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

        # 构建完整的记忆内容结构
        memory_content = {
            "text": f"用药记录: {args['medication_name']} {args['dosage']} {args['frequency']}",
            "structured_data": record_content,
            "metadata": metadata
        }

        # 存储记录 (同步调用)
        memory_id = memory_system.store_memory(
            agent_id="medication_reminder",
            user_id=args["user_id"],
            content=memory_content,
            memory_type="medication_record",
            tags=tags,
            importance=0.8
        )

        return {"success": True, "memory_id": memory_id, "message": "用药记录存储成功"}

    except Exception as e:
        return {"success": False, "error": str(e)}

# FastMCP 工具封装（确保与原有工具名称一致的语义）
@mcp.tool()
async def store_medication_record(
    medication_name: str,
    dosage: str,
    frequency: str,
    start_date: str,
    user_id: str | None = None,
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

        user_id = args.get("user_id", "")
        if not user_id:
             user_id = os.environ.get("A2A_CURRENT_USER_ID", "")

        if not user_id:
             return {"error": "缺少用户ID (user_id)"}

        # 搜索记忆 (同步调用)
        # 注意：AgentMemorySystem.search_memories 返回 List[Dict]
        memories = memory_system.search_memories(
            query=args["query"],
            agent_id="medication_reminder",
            user_id=user_id,
            memory_types=["medication_record"],
            limit=args.get("limit", 10)
        )

        # 处理结果
        results = []
        for memory in memories:
            try:
                # memory 是字典，不是对象
                content_str = memory.get("content_text", "")
                # structured_data 已经在 memory_storage 中被 json.loads (如果它是JSON列)
                # 但在 memory_system.py 的 search_memories -> retrieval -> search_by_content
                # 返回的是 Dict。需要确认 content_structured 是字典还是字符串。
                # memory_storage.get_memory 会 parse JSON。
                # memory_retrieval.search_by_content 返回的也是 dict_row (psycopg)。
                # 数据库中 content_structured 是 JSONB 吗？如果是，psycopg 会自动转 dict。
                # 如果是 TEXT，则需要 loads。
                # 假设它是 dict (psycopg automatic conversion for jsonb or explicit loads in retrieval)

                # 查看 memory_retrieval.py，search_by_content 直接返回 fetchall()
                # 如果是 JSONB 列，psycopg3 会自动转换。

                content = memory.get("content_structured", {})
                if isinstance(content, str):
                     try:
                         content = json.loads(content)
                     except:
                         content = {}

                results.append({
                    "memory_id": memory.get("memory_id"),
                    "medication_name": content.get("medication_name", ""),
                    "dosage": content.get("dosage", ""),
                    "frequency": content.get("frequency", ""),
                    "start_date": content.get("start_date", ""),
                    "end_date": content.get("end_date", ""),
                    "doctor_name": content.get("doctor_name", ""),
                    "notes": content.get("notes", ""),
                    "created_at": str(memory.get("created_at", "")),
                    "similarity_score": memory.get("similarity", 0)
                })
            except Exception as e:
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

        # 自动补充 user_id
        if not args.get("user_id"):
            args["user_id"] = os.environ.get("A2A_CURRENT_USER_ID")

        if not args.get("user_id"):
            return {"error": "缺少用户ID (user_id)"}

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

        # 构建完整的记忆内容结构
        memory_content = {
            "text": f"依从性记录: {args['medication_name']} {args['adherence_rate']}",
            "structured_data": adherence_content,
            "metadata": metadata
        }

        # 存储记录 (同步调用)
        memory_id = memory_system.store_memory(
            agent_id="medication_reminder",
            user_id=args["user_id"],
            content=memory_content,
            memory_type="adherence_record",
            tags=tags,
            importance=0.9 if args["adherence_rate"] < 0.8 else 0.7
        )

        return {"success": True, "memory_id": memory_id, "message": "依从性记录存储成功"}

    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def store_adherence_record(
    medication_name: str,
    adherence_rate: float,
    user_id: str | None = None,
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

        # 自动补充 user_id
        if not args.get("user_id"):
            args["user_id"] = os.environ.get("A2A_CURRENT_USER_ID")

        if not args.get("user_id"):
            return {"error": "缺少用户ID (user_id)"}

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

        # 构建完整的记忆内容结构
        memory_content = {
            "text": f"用药档案: {args['user_id']}",
            "structured_data": profile_content,
            "metadata": metadata
        }

        # 存储档案 (同步调用)
        memory_id = memory_system.store_memory(
            agent_id="medication_reminder",
            user_id=args["user_id"],
            content=memory_content,
            memory_type="medication_profile",
            tags=tags,
            importance=0.9
        )

        return {"success": True, "memory_id": memory_id, "message": "用药档案存储成功"}

    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def store_medication_profile(
    user_id: str | None = None,
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

        # 自动补充 user_id
        if not args.get("user_id"):
            args["user_id"] = os.environ.get("A2A_CURRENT_USER_ID")

        if not args.get("user_id"):
            return {"error": "缺少用户ID (user_id)"}

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

        # 构建完整的记忆内容结构
        memory_content = {
            "text": f"复诊预约: {args['appointment_date']} {args['doctor_name']}",
            "structured_data": appointment_content,
            "metadata": metadata
        }

        # 存储记录 (同步调用)
        memory_id = memory_system.store_memory(
            agent_id="medication_reminder",
            user_id=args["user_id"],
            content=memory_content,
            memory_type="appointment_record",
            tags=tags,
            importance=0.8
        )

        return {"success": True, "memory_id": memory_id, "message": "预约记录存储成功"}

    except Exception as e:
        return {"success": False, "error": str(e)}

@mcp.tool()
async def store_appointment_record(
    appointment_date: str,
    doctor_name: str,
    user_id: str | None = None,
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

        # 自动补充 user_id
        if not args.get("user_id"):
            args["user_id"] = os.environ.get("A2A_CURRENT_USER_ID")

        if not args.get("user_id"):
            return {"error": "缺少用户ID (user_id)"}

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
            adherence_memories = memory_system.search_memories(
                query=f"user_id:{user_id} adherence",
                agent_id="medication_reminder",
                user_id=user_id,
                memory_types=["adherence_record"],
                limit=20
            )

            total_rate = 0
            count = 0
            for memory in adherence_memories:
                try:
                    content = memory.get("content_structured", {})
                    if isinstance(content, str):
                        content = json.loads(content)
                    total_rate += content.get("adherence_rate", 0)
                    count += 1
                except Exception:
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
            medication_memories = memory_system.search_memories(
                query=f"user_id:{user_id}",
                agent_id="medication_reminder",
                user_id=user_id,
                memory_types=["medication_record"],
                limit=50
            )

            medication_counts = {}
            for memory in medication_memories:
                try:
                    content = memory.get("content_structured", {})
                    if isinstance(content, str):
                        content = json.loads(content)
                    med_name = content.get("medication_name", "")
                    medication_counts[med_name] = medication_counts.get(med_name, 0) + 1
                except Exception:
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
    user_id: str | None = None,
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

        # 自动补充 user_id
        if not args.get("user_id"):
            args["user_id"] = os.environ.get("A2A_CURRENT_USER_ID")

        # 清理功能可能不需要user_id，如果只是清理过期记忆
        # 但AgentMemorySystem.cleanup_expired_memories可能需要上下文?
        # 实际上AgentMemorySystem.cleanup_expired_memories()没有参数
        # 但为了保持一致性，如果后续需要基于用户清理，我们还是加上

        # AgentMemorySystem 只支持 cleanup_expired_memories (基于过期时间)
        # 或 cleanup_low_importance_memories (基于重要性和时间)
        # 这里我们调用 cleanup_expired_memories

        cleaned_count = memory_system.cleanup_expired_memories()

        return {"success": True, "cleaned_count": cleaned_count, "message": f"清理了{cleaned_count}条过期记忆"}

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
