#!/usr/bin/env python3
"""
健康档案管理器记忆集成工具

这个MCP服务器为健康档案管理器提供长期记忆功能，包括：
1. 存储健康档案相关记忆
2. 检索历史健康信息
3. 管理用户健康数据的记忆
4. 提供智能健康建议基于历史记忆
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# 添加 backend 根目录到 sys.path，支持从子目录运行
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

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
    # 移除不存在的 MemorySystemConfig 导入，避免启动失败
    # from memory_config import MemorySystemConfig
except ImportError as e:
    logging.error(f"无法导入记忆系统: {e}")
    sys.exit(1)

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("health_records_memory")

# 创建MCP服务器
server = Server("health-records-memory")

# 全局记忆系统实例
memory_system: Optional[AgentMemorySystem] = None

# 健康档案智能体ID
HEALTH_RECORDS_AGENT_ID = "health_records_manager"

def _to_datetime(v):
    if isinstance(v, datetime):
        return v
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v)
        except Exception:
            return None
    return None

def _resolve_user_id(v: Optional[str]) -> str:
    s = str(v or '').strip()
    if s and s.lower() != 'default_user':
        return s
    return (
        os.environ.get('A2A_CURRENT_USER_ID')
        or os.environ.get('DEFAULT_USER_ID')
        or os.environ.get('FRONTEND_USER_ID')
        or 'default_user'
    )

@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """列出可用的记忆资源"""
    return [
        Resource(
            uri=AnyUrl("memory://health-records/recent"),
            name="最近健康记忆",
            description="获取最近的健康档案相关记忆",
            mimeType="application/json",
        ),
        Resource(
            uri=AnyUrl("memory://health-records/important"),
            name="重要健康记忆",
            description="获取重要的健康档案记忆",
            mimeType="application/json",
        ),
        Resource(
            uri=AnyUrl("memory://health-records/patterns"),
            name="健康模式分析",
            description="分析用户的健康记忆模式",
            mimeType="application/json",
        )
    ]

@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    if not memory_system:
        return json.dumps({"error": "记忆系统未初始化"})
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(str(uri))
        qs = parse_qs(parsed.query)
        uid = (
            (qs.get("user_id", [None])[0])
            or os.environ.get("A2A_CURRENT_USER_ID")
            or os.environ.get("DEFAULT_USER_ID")
            or "default_user"
        )
        if parsed.scheme == "memory" and parsed.netloc == "health-records" and parsed.path == "/recent":
            memories = memory_system.get_recent_memories(
                agent_id=HEALTH_RECORDS_AGENT_ID,
                user_id=uid,
                hours=168,
                memory_types=['long_term', 'working'],
                limit=20
            )
            return json.dumps(memories, ensure_ascii=False, indent=2, default=str)
        if parsed.scheme == "memory" and parsed.netloc == "health-records" and parsed.path == "/important":
            memories = memory_system.get_important_memories(
                agent_id=HEALTH_RECORDS_AGENT_ID,
                user_id=uid,
                min_importance=0.7,
                memory_types=['long_term'],
                limit=20
            )
            return json.dumps(memories, ensure_ascii=False, indent=2, default=str)
        if parsed.scheme == "memory" and parsed.netloc == "health-records" and parsed.path == "/patterns":
            patterns = memory_system.analyze_memory_patterns(
                agent_id=HEALTH_RECORDS_AGENT_ID,
                user_id=uid,
                days=30
            )
            return json.dumps(patterns, ensure_ascii=False, indent=2, default=str)
        return json.dumps({"error": f"未知资源: {uri}"})
    except Exception as e:
        logger.error(f"读取资源失败: {e}")
        return json.dumps({"error": str(e)}, default=str)

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """列出可用的记忆工具"""
    return [
        Tool(
            name="store_health_memory",
            description="存储健康档案相关记忆",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "record_type": {
                        "type": "string",
                        "description": "健康记录类型（如：体检报告、诊断记录、处方单等）"
                    },
                    "record_data": {
                        "type": "object",
                        "description": "健康记录数据"
                    },
                    "summary": {
                        "type": "string",
                        "description": "记录摘要"
                    },
                    "importance": {
                        "type": "number",
                        "description": "重要性评分 (0.0-1.0)",
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "标签列表"
                    },
                    "urgent": {
                        "type": "boolean",
                        "description": "是否紧急"
                    }
                },
                "required": ["user_id", "record_type", "record_data"]
            },
        ),
        Tool(
            name="search_health_memories",
            description="搜索健康档案相关记忆",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "query": {
                        "type": "string",
                        "description": "搜索查询"
                    },
                    "record_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "记录类型过滤"
                    },
                    "time_range_days": {
                        "type": "integer",
                        "description": "时间范围（天）",
                        "minimum": 1
                    },
                    "min_importance": {
                        "type": "number",
                        "description": "最小重要性阈值",
                        "minimum": 0.0,
                        "maximum": 1.0
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制",
                        "minimum": 1,
                        "maximum": 100
                    }
                },
                "required": ["user_id", "query"]
            },
        ),
        Tool(
            name="get_health_history",
            description="获取用户健康历史记录",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "record_type": {
                        "type": "string",
                        "description": "记录类型（可选）"
                    },
                    "days": {
                        "type": "integer",
                        "description": "历史天数",
                        "minimum": 1,
                        "default": 365
                    },
                    "include_trends": {
                        "type": "boolean",
                        "description": "是否包含趋势分析",
                        "default": False
                    }
                },
                "required": ["user_id"]
            },
        ),
        Tool(
            name="store_ocr_result",
            description="存储OCR识别结果记忆",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "document_type": {
                        "type": "string",
                        "description": "文档类型"
                    },
                    "ocr_text": {
                        "type": "string",
                        "description": "OCR识别的文本"
                    },
                    "extracted_info": {
                        "type": "object",
                        "description": "提取的结构化信息"
                    },
                    "confidence": {
                        "type": "number",
                        "description": "识别置信度",
                        "minimum": 0.0,
                        "maximum": 1.0
                    }
                },
                "required": ["user_id", "document_type", "ocr_text"]
            },
        ),
        Tool(
            name="get_health_insights",
            description="基于历史记忆获取健康洞察",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID"
                    },
                    "focus_area": {
                        "type": "string",
                        "description": "关注领域（如：血压、血糖、体重等）"
                    },
                    "analysis_period_days": {
                        "type": "integer",
                        "description": "分析周期（天）",
                        "minimum": 7,
                        "default": 90
                    }
                },
                "required": ["user_id"]
            },
        ),
        Tool(
            name="cleanup_health_memories",
            description="清理健康记忆数据",
            inputSchema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "用户ID（可选，不提供则清理所有用户）"
                    },
                    "cleanup_type": {
                        "type": "string",
                        "enum": ["expired", "low_importance", "duplicates", "all"],
                        "description": "清理类型",
                        "default": "expired"
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
        if name == "store_health_memory":
            return await _store_health_memory(arguments)
        elif name == "search_health_memories":
            return await _search_health_memories(arguments)
        elif name == "get_health_history":
            return await _get_health_history(arguments)
        elif name == "store_ocr_result":
            return await _store_ocr_result(arguments)
        elif name == "get_health_insights":
            return await _get_health_insights(arguments)
        elif name == "cleanup_health_memories":
            return await _cleanup_health_memories(arguments)
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

async def _store_health_memory(arguments: dict) -> list[types.TextContent]:
    """存储健康档案记忆"""
    user_id = _resolve_user_id(arguments.get("user_id"))
    record_type = arguments["record_type"]
    record_data = arguments["record_data"]
    summary = arguments.get("summary", "")
    importance = arguments.get("importance", 0.8)
    tags = arguments.get("tags", [])
    urgent = arguments.get("urgent", False)
    
    # 添加默认标签
    default_tags = ["健康档案", record_type]
    if urgent:
        default_tags.append("紧急")
    
    all_tags = list(set(default_tags + tags))
    
    # 存储记忆
    memory_id = memory_system.store_health_record_memory(
        agent_id=HEALTH_RECORDS_AGENT_ID,
        user_id=user_id,
        record_type=record_type,
        record_data={
            **record_data,
            "summary": summary,
            "urgent": urgent
        },
        importance=importance
    )
    
    result = {
        "success": True,
        "memory_id": memory_id,
        "message": f"成功存储{record_type}记忆",
        "stored_data": {
            "record_type": record_type,
            "importance": importance,
            "tags": all_tags,
            "urgent": urgent
        }
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2, default=str)
    )]

async def _search_health_memories(arguments: dict) -> list[types.TextContent]:
    """搜索健康档案记忆"""
    user_id = _resolve_user_id(arguments.get("user_id"))
    query = arguments["query"]
    record_types = arguments.get("record_types", [])
    time_range_days = arguments.get("time_range_days")
    min_importance = arguments.get("min_importance", 0.0)
    limit = arguments.get("limit", 20)
    
    # 执行搜索
    memories = memory_system.search_memories(
        query=query,
        agent_id=HEALTH_RECORDS_AGENT_ID,
        user_id=user_id,
        memory_types=['long_term', 'working'],
        limit=limit,
        min_similarity=0.3
    )
    
    # 过滤结果
    filtered_memories = []
    for memory in memories:
        # 重要性过滤
        if memory.get('importance', 0) < min_importance:
            continue
        
        # 记录类型过滤
        if record_types:
            memory_tags = memory.get('tags', [])
            if not any(rt in memory_tags for rt in record_types):
                continue
        
        if time_range_days:
            _dt = _to_datetime(memory.get('created_at'))
            if not _dt:
                continue
            if (datetime.now() - _dt).days > time_range_days:
                continue
        
        filtered_memories.append(memory)
    
    result = {
        "success": True,
        "query": query,
        "total_found": len(filtered_memories),
        "memories": filtered_memories[:limit]
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2, default=str)
    )]

async def _get_health_history(arguments: dict) -> list[types.TextContent]:
    """获取用户健康历史记录"""
    user_id = _resolve_user_id(arguments.get("user_id"))
    record_type = arguments.get("record_type")
    days = arguments.get("days", 365)
    include_trends = arguments.get("include_trends", False)
    
    # 获取时间范围内的记忆
    start_time = datetime.now() - timedelta(days=days)
    end_time = datetime.now()
    
    memories = memory_system.search_by_time_range(
        start_time=start_time,
        end_time=end_time,
        agent_id=HEALTH_RECORDS_AGENT_ID,
        user_id=user_id,
        memory_types=['long_term', 'working'],
        limit=100
    )
    
    # 按记录类型过滤
    if record_type:
        memories = [
            m for m in memories 
            if record_type in m.get('tags', [])
        ]
    
    def _sort_key(x):
        v = x.get('created_at')
        dt = _to_datetime(v)
        return dt or datetime.min
    memories.sort(key=_sort_key, reverse=True)
    
    result = {
        "success": True,
        "user_id": user_id,
        "time_range_days": days,
        "record_type": record_type,
        "total_records": len(memories),
        "records": memories
    }
    
    # 如果需要趋势分析
    if include_trends and memories:
        trends = _analyze_health_trends(memories)
        result["trends"] = trends
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2, default=str)
    )]

async def _store_ocr_result(arguments: dict) -> list[types.TextContent]:
    """存储OCR识别结果记忆"""
    user_id = _resolve_user_id(arguments.get("user_id"))
    document_type = arguments["document_type"]
    ocr_text = arguments["ocr_text"]
    extracted_info = arguments.get("extracted_info", {})
    confidence = arguments.get("confidence", 0.8)
    
    # 构建记忆内容
    content = {
        'text': f"OCR识别结果: {document_type}\n{ocr_text[:500]}...",
        'structured_data': {
            'document_type': document_type,
            'ocr_text': ocr_text,
            'extracted_info': extracted_info,
            'confidence': confidence,
            'processing_time': datetime.now().isoformat()
        },
        'metadata': {
            'data_source': 'ocr_tool',
            'document_type': document_type,
            'confidence': confidence
        }
    }
    
    # 根据置信度设置重要性
    importance = min(0.9, confidence + 0.1)
    
    # 设置标签
    tags = ['OCR识别', document_type, '文档处理']
    if confidence > 0.9:
        tags.append('高置信度')
    elif confidence < 0.6:
        tags.append('低置信度')
    
    # 存储记忆
    memory_id = memory_system.store_memory(
        agent_id=HEALTH_RECORDS_AGENT_ID,
        user_id=user_id,
        content=content,
        memory_type='working',
        importance=importance,
        tags=tags,
        expires_hours=720  # 30天后过期
    )
    
    result = {
        "success": True,
        "memory_id": memory_id,
        "message": f"成功存储OCR识别结果: {document_type}",
        "ocr_summary": {
            "document_type": document_type,
            "text_length": len(ocr_text),
            "confidence": confidence,
            "extracted_fields": len(extracted_info)
        }
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2, default=str)
    )]

async def _get_health_insights(arguments: dict) -> list[types.TextContent]:
    """基于历史记忆获取健康洞察"""
    user_id = _resolve_user_id(arguments.get("user_id"))
    focus_area = arguments.get("focus_area")
    analysis_period_days = arguments.get("analysis_period_days", 90)
    
    # 获取分析周期内的记忆
    start_time = datetime.now() - timedelta(days=analysis_period_days)
    end_time = datetime.now()
    
    memories = memory_system.search_by_time_range(
        start_time=start_time,
        end_time=end_time,
        agent_id=HEALTH_RECORDS_AGENT_ID,
        user_id=user_id,
        memory_types=['long_term', 'working'],
        limit=200
    )
    
    # 如果指定了关注领域，进行过滤
    if focus_area:
        memories = [
            m for m in memories
            if focus_area.lower() in str(m.get('content', {})).lower()
        ]
    
    # 分析记忆模式
    patterns = memory_system.analyze_memory_patterns(
        agent_id=HEALTH_RECORDS_AGENT_ID,
        user_id=user_id,
        days=analysis_period_days
    )
    
    # 生成洞察
    insights = _generate_health_insights(memories, patterns, focus_area)
    
    result = {
        "success": True,
        "user_id": user_id,
        "focus_area": focus_area,
        "analysis_period_days": analysis_period_days,
        "total_memories_analyzed": len(memories),
        "insights": insights,
        "patterns": patterns
    }
    
    return [types.TextContent(
        type="text",
        text=json.dumps(result, ensure_ascii=False, indent=2)
    )]

async def _cleanup_health_memories(arguments: dict) -> list[types.TextContent]:
    """清理健康记忆数据"""
    user_id = arguments.get("user_id")
    cleanup_type = arguments.get("cleanup_type", "expired")
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
                    agent_id=HEALTH_RECORDS_AGENT_ID,
                    user_id=user_id,
                    threshold=0.3,
                    max_age_days=180
                )
                results["cleaned_count"] = cleaned
                results["details"].append(f"清理了 {cleaned} 条低重要性记忆")
            else:
                results["details"].append("试运行：将清理低重要性记忆")
        
        elif cleanup_type == "duplicates" and user_id:
            if not dry_run:
                compressed = memory_system.compress_memories(
                    agent_id=HEALTH_RECORDS_AGENT_ID,
                    user_id=user_id,
                    memory_type='long_term'
                )
                results["cleaned_count"] = compressed
                results["details"].append(f"压缩了 {compressed} 条重复记忆")
            else:
                results["details"].append("试运行：将压缩重复记忆")
        
        elif cleanup_type == "all":
            if not dry_run:
                total_cleaned = 0
                
                # 清理过期记忆
                expired = memory_system.cleanup_expired_memories()
                total_cleaned += expired
                results["details"].append(f"清理过期记忆: {expired} 条")
                
                # 如果有用户ID，清理低重要性记忆
                if user_id:
                    low_imp = memory_system.cleanup_low_importance_memories(
                        agent_id=HEALTH_RECORDS_AGENT_ID,
                        user_id=user_id
                    )
                    total_cleaned += low_imp
                    results["details"].append(f"清理低重要性记忆: {low_imp} 条")
                    
                    # 压缩记忆
                    compressed = memory_system.compress_memories(
                        agent_id=HEALTH_RECORDS_AGENT_ID,
                        user_id=user_id
                    )
                    total_cleaned += compressed
                    results["details"].append(f"压缩重复记忆: {compressed} 条")
                
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

def _analyze_health_trends(memories: List[Dict]) -> Dict[str, Any]:
    """分析健康趋势"""
    trends = {
        "record_frequency": {},
        "common_topics": {},
        "time_distribution": {},
        "importance_trend": []
    }
    
    for memory in memories:
        # 记录频率分析
        tags = memory.get('tags', [])
        for tag in tags:
            if tag != '健康档案':
                trends["record_frequency"][tag] = trends["record_frequency"].get(tag, 0) + 1

        # 时间分布与重要性趋势分析
        _ca = memory.get('created_at')
        _dt = _to_datetime(_ca)
        if _dt:
            _date = _dt.date()
            month_key = _date.strftime('%Y-%m')
            trends["time_distribution"][month_key] = trends["time_distribution"].get(month_key, 0) + 1

        importance = memory.get('importance', 0)
        trends["importance_trend"].append({
            "date": (_dt.isoformat() if _dt else (_ca if isinstance(_ca, str) else None)),
            "importance": importance
        })
    
    return trends

def _generate_health_insights(memories: List[Dict], patterns: Dict, focus_area: str = None) -> List[str]:
    """生成健康洞察"""
    insights = []
    
    if not memories:
        insights.append("暂无足够的健康记录数据进行分析")
        return insights
    
    # 记录数量洞察
    total_records = len(memories)
    insights.append(f"分析期间共有 {total_records} 条健康记录")
    
    # 记录类型分析
    record_types = {}
    for memory in memories:
        tags = memory.get('tags', [])
        for tag in tags:
            if tag != '健康档案':
                record_types[tag] = record_types.get(tag, 0) + 1
    
    if record_types:
        most_common = max(record_types.items(), key=lambda x: x[1])
        insights.append(f"最常见的记录类型是 '{most_common[0]}'，共 {most_common[1]} 条记录")
    
    # 重要性分析
    importance_scores = [m.get('importance', 0) for m in memories]
    if importance_scores:
        avg_importance = sum(importance_scores) / len(importance_scores)
        high_importance_count = len([s for s in importance_scores if s > 0.7])
        insights.append(f"平均重要性评分: {avg_importance:.2f}")
        insights.append(f"高重要性记录 (>0.7): {high_importance_count} 条")
    
    # 时间趋势分析
    if len(memories) > 1:
        recent_week = []
        for m in memories:
            _dt = _to_datetime(m.get('created_at'))
            if not _dt:
                continue
            if (datetime.now() - _dt).days <= 7:
                recent_week.append(m)
        if recent_week:
            insights.append(f"最近一周新增 {len(recent_week)} 条记录")
    
    # 关注领域特定洞察
    if focus_area:
        focus_memories = [
            m for m in memories
            if focus_area.lower() in str(m.get('content', {})).lower()
        ]
        if focus_memories:
            insights.append(f"关于 '{focus_area}' 的记录共 {len(focus_memories)} 条")
        else:
            insights.append(f"未找到关于 '{focus_area}' 的相关记录")
    
    return insights

async def main():
    """主函数"""
    global memory_system
    
    # 初始化记忆系统
    try:
        memory_system = AgentMemorySystem()
        logger.info("记忆系统初始化成功")
    except Exception as e:
        logger.error(f"记忆系统初始化失败: {e}")
        sys.exit(1)
    
    # 运行服务器
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="health-records-memory",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())