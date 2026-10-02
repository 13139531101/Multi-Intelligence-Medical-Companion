# -*- coding: utf-8 -*-
# @File  : page_control_tool.py
# @Desc  : 让 AI 把用户"带到"某一份档案 —— 跳转到档案页并打开该条记录的详情

"""
为什么单独一个文件、而不是塞进 storage_tool.py
------------------------------------------------
storage_tool.py 在 import 时就构造 HealthDataStorage → 立刻建数据库连接。
本工具希望惰性建连（宿主启动时不必要地占一条连接，且连不上会拖慢导入）。
所以这里自己拿 db_manager，不 import storage_tool。

关于 user_id 的信任边界（重要）
------------------------------
LLM 理论上可以幻觉出一个 user_id。缓解有两层，都不在本文件里：
  1. 前端只会在**自己已拉取的、按用户隔离的**列表里找这条 id
     （见 NewHealthRecords.jsx 的 pendingRecordId effect）。幻觉出来的 id
     在列表里找不到 → 退化为关键字过滤 + 提示，不会打开任何东西。
  2. 本工具的返回体只带 id/title/type，不带 content，不构成档案内容外泄。
"""

import os
import re
import sys
import json
import logging

# 去掉空白后再比 —— 库里存"胸部 CT 检查"，用户说"胸部CT"，直接比匹配不上
_WS = re.compile(r"\s+")
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)
mcp = FastMCP("健康档案页面控制")

# 惰性单例 —— 首次调用工具时才建连
_db_manager = None

# 记录类型别名 → health_records.record_type 的实际取值
_TYPE_ALIASES = {
    "血常规": "lab_result",
    "化验": "lab_result",
    "检验": "lab_result",
    "化验单": "lab_result",
    "检验单": "lab_result",
    "lab": "lab_result",
    "test_report": "lab_result",
    "inspection_report": "lab_result",
    "检查": "lab_result",
    "检查报告": "lab_result",
    "影像": "medical_record",
    "病理": "medical_record",
    "报告": "medical_record",
    "medical_report": "medical_record",
    "病历": "medical_record",
    "处方": "prescription",
    "处方单": "prescription",
    "prescription": "prescription",
    "住院": "hospital_record",
    "hospital_record": "hospital_record",
    "疫苗": "vaccination",
    "vaccination": "vaccination",
    "手术": "surgery",
    "surgery": "surgery",
}

# 化简关键字时**只能**剥这些"结构性"的类型词。
# 不能拿 _TYPE_ALIASES 来剥 —— 里面既有"报告"这种纯类型词，也有"血常规"
# 这种**恰恰是关键词本身**的实义词。用 _TYPE_ALIASES 剥，"血常规报告"会
# 被剥成空串，真正的关键词反而丢了。
_GENERIC_TYPE_WORDS = [
    "检查报告", "化验单", "检验单", "体检报告",
    "报告", "检查", "记录", "档案", "单据", "单子",
]

# 只用于兜底化简：LLM 把整句原话传进来时，把这些虚词剥掉再试一次。
# 刻意保持克制 —— 剥多了会把"上个月"这类真实限定也抹掉，反而更不精确。
_FILLER_WORDS = [
    "帮我", "请帮我", "请", "麻烦", "我要", "我想", "想要", "把", "给我",
    "打开", "调出", "找出", "查找", "查看", "看看", "看下", "看一下",
    "跳转", "跳到", "定位", "切换", "进入", "前往",
    "那一份", "那一条", "那份", "那条", "这个", "那个", "这份", "这条",
    "上个月", "这个月", "上个月份", "最近", "之前", "以前的", "上次",
    "的", "一下",
    # 存在性提问的虚词 —— "有没有心电图检查报告吗"。
    # 用户问"有没有 X 报告"时，LLM 常把整句原样塞进 query；不剥掉这些，
    # 整句拿去 ILIKE 必然落空 → success=False → 不发 page_update → 页面不跳，
    # 而模型又会顺势退到 RAG，最后回一句"未找到"（实测约 3/10 的概率）。
    # 长度降序由 _strip 内部保证："有没有"先于"没有"、"没有"先于"有"，
    # 否则 "有没有血脂报告" 会先被剥成 "没血脂报告"，真正的关键词反而丢了。
    "有没有", "没有", "有", "是否", "是不是", "吗", "呢", "吧", "么",
    "请问", "问一下", "查一下", "找一下", "帮我看", "帮我查",
    # 存在性提问的另外几种常见句式，漏一个整句就化简不掉：
    #   "我做过心电图吗"   → 我做过 / 做过 / 我
    #   "心电图检查报告在吗" → 在吗 / 在不在
    #   "上次的体检报告还在吗" → 还在吗 / 还
    # 这几个都是单/双字虚词，不会与检查项目名（血常规、心电图、CT…）撞车。
    "我做过", "做过", "我", "在吗", "在不在", "还在吗", "还有吗", "还",
]


def _get_db():
    global _db_manager
    if _db_manager is None:
        from database_config import get_db_manager

        _db_manager = get_db_manager()
    return _db_manager


def _resolve_user_id(user_id: str) -> str:
    """优先用调用方注入的值，退化到进程环境变量。"""
    uid = (user_id or "").strip()
    if uid:
        return uid
    return (os.environ.get("PHA_USER_ID") or "").strip()


def _normalize_month(month: str) -> Optional[str]:
    """'2026-09' / '2026/09' / '2026年9月' → '2026-09'；无法识别返回 None。"""
    if not month:
        return None
    raw = str(month).strip().replace("/", "-").replace("年", "-").replace("月", "")
    raw = raw.rstrip("-")
    parts = [p for p in raw.split("-") if p.strip()]
    if len(parts) < 2:
        return None
    try:
        year, mon = int(parts[0]), int(parts[1])
    except (TypeError, ValueError):
        return None
    if not (1 <= mon <= 12):
        return None
    return f"{year:04d}-{mon:02d}"


def _guess_type(record_type: str, query: str) -> str:
    """把用户/LLM 给的词映射到 record_type。query 里的名词也算数 ——
    '打开上个月的血常规报告' 里 record_type 可能为空，但 query 含'血常规'。"""
    for src in (record_type, query):
        key = (src or "").strip()
        if not key:
            continue
        if key in _TYPE_ALIASES:
            return _TYPE_ALIASES[key]
        for alias, mapped in _TYPE_ALIASES.items():
            if alias in key:
                return mapped
    return ""


@mcp.tool()
def open_health_record(
    query: str = "",
    record_type: str = "",
    month: str = "",
    user_id: str = "",
) -> Dict[str, Any]:
    """查询用户是否存有某份健康档案 / 检查报告，并把它打开给用户看。

    这是**检索用户自己档案的唯一入口**，两类场景都必须调用它：
      1. 导航类："打开上个月的血常规报告"、"帮我找到那份体检报告"、
         "跳到最近一次的病历" —— 用户明确要求跳转。
      2. 存在性提问："有没有心电图检查报告"、"我做过胸片吗"、
         "上次的体检报告还在吗" —— 用户只是问在不在。

    两类都要调，原因：本工具是唯一能读到 health_records 表的通道。
    存在性提问若不调它，就会退到向量检索（rag_chunks），而档案正文多数是
    加密的、根本没进向量库，结果必然是"未找到"，还会让用户以为档案丢了。

    按关键字与月份检索用户档案，返回最佳匹配，并指示前端跳转到档案页并打开
    该记录的详情弹窗。找不到时如实说没找到即可 —— 不要编造 id，也不要因此
    改口说"系统里没有您的档案"。

    一次提问**只调一次**，不要重复调用：每次成功调用都会产生一对前端跳转
    动作，重复调用会让详情弹窗被打开两次。

    :param query: 用户用来描述那份档案的词，如"血常规"、"胸片"、"体检"。
        可以直接传用户的整句原话，本工具会自行剥掉"有没有/吗"这类虚词。
    :param record_type: 记录类型（可选），如 lab_result / medical_record / prescription
    :param month: 限定月份（可选），格式 YYYY-MM，如 2026-09
    :param user_id: 由系统注入，不要自己编
    """
    try:
        uid = _resolve_user_id(user_id)
        if not uid:
            return {
                "success": False,
                "message": "无法确定当前用户，未执行跳转。",
            }

        rt = _guess_type(record_type, query)
        ym = _normalize_month(month)
        raw_kw = (query or "").strip()

        def _search(kw: str, with_type: bool) -> List[Dict[str, Any]]:
            # content 列可能是加密的（见 storage_tool.encrypt_data），
            # 所以只搜 title / summary 这两个明文列。
            where: List[str] = ["user_id = %s"]
            params: List[Any] = [uid]

            if with_type and rt:
                where.append("record_type = %s")
                params.append(rt)
            if ym:
                where.append("to_char(record_date, 'YYYY-MM') = %s")
                params.append(ym)
            if kw:
                like = "%" + _WS.sub("", kw) + "%"
                where.append(
                    "(regexp_replace(title, '\\s+', '', 'g') ILIKE %s"
                    " OR regexp_replace(COALESCE(summary, ''), '\\s+', '', 'g') ILIKE %s)"
                )
                params.extend([like, like])

            # 标题命中的排前面，其次按日期新→旧
            order = "COALESCE(record_date, created_at::date) DESC"
            if kw:
                order = "(regexp_replace(title, '\\s+', '', 'g') ILIKE %s) DESC, " + order
                params.append("%" + _WS.sub("", kw) + "%")

            sql = f"""
                SELECT id, record_type, title, record_date, created_at
                FROM health_records
                WHERE {' AND '.join(where)}
                ORDER BY {order}
                LIMIT 5
            """
            return _get_db().execute_query(sql, tuple(params)) or []

        if not raw_kw and not ym and not rt:
            return {
                "success": False,
                "message": "缺少检索条件，请说明要找哪一份档案。",
            }

        # 关键字候选，由紧到松。LLM 可能只传一个名词（"血常规"），也可能把
        # 整句话原样传进来（"帮我打开上个月的血常规报告"）—— 后者拿去 ILIKE
        # 是匹配不到的，所以要能把它化简回"血常规"。
        def _strip(text: str, words, min_len: int = 2) -> str:
            # 长的先剥："请帮我" 要在 "请" 之前，否则会剩下"帮我"。
            # min_len 分开给：类型词至少要 2 字（"的"这种不该算类型词），
            # 虚词则必须允许 1 字 —— "的"、"请"、"把" 正是最常见的那些。
            out = text
            for w in sorted(words, key=len, reverse=True):
                if len(w) >= min_len:
                    out = out.replace(w, "")
            return out.strip()

        # 顺序要紧：**先剥虚词，再剥结构性类型词**。
        # "帮我打开上个月的血常规报告" 若先剥类型词，会剩下"帮我打开上个月的"，
        # 再剥虚词就成了空串 —— 真正的关键词"血常规"反倒被一起剥掉了。
        # 反过来先剥虚词得到"血常规报告"，再剥掉"报告"才落到"血常规"。
        _no_filler = _strip(raw_kw, _FILLER_WORDS, min_len=1)
        candidates: List[str] = []
        for c in (
            raw_kw,
            _no_filler,
            _strip(_no_filler, _GENERIC_TYPE_WORDS),
            _strip(raw_kw, _GENERIC_TYPE_WORDS),
        ):
            # 太短的碎片（"的"、"单"）比不匹配更糟 —— 会命中一堆无关记录
            if len(c) >= 2 and c not in candidates:
                candidates.append(c)
        # 只在还有别的时间/类型约束时，才允许"无关键字"这一次尝试；
        # 否则会退化成"随便返回最新一条"，凭空跳到一个无关记录。
        if (ym or rt) and not candidates:
            candidates.append("")
        if not candidates:
            candidates = [raw_kw]

        # 类型只当"提示"，不当"硬过滤"：实测库里 血常规检查 的 record_type 是
        # other、处方单（JPG）也是 other，硬过滤会把该找到的记录排除掉。
        # 于是按"关键字由紧到松 × 先带类型后放开类型"逐个试。
        rows: List[Dict[str, Any]] = []
        used_kw = candidates[0]
        for kw in candidates:
            rows = _search(kw, with_type=True) if rt else []
            if not rows:
                rows = _search(kw, with_type=False)
            if rows:
                used_kw = kw
                break

        if not rows:
            # 不返回 page_update —— 让 LLM 用文字说明，而不是给前端一个空跳转
            return {
                "success": False,
                "message": "没有找到匹配的档案记录。",
                "searched": {"query": raw_kw, "record_type": rt, "month": ym},
            }
        kw = used_kw

        best = rows[0]
        rec_id = str(best.get("id"))
        title = best.get("title") or "健康档案"
        rec_date = best.get("record_date")
        rec_date = str(rec_date) if rec_date else ""

        return {
            "success": True,
            "matched": {
                "id": rec_id,
                "title": title,
                "record_type": best.get("record_type"),
                "date": rec_date,
                "candidates": len(rows),
            },
            "page_update": {
                "actions": [
                    {
                        # 第一步：把用户带到档案页。PageRouter 始终挂载，立即生效。
                        "component": "PageRouter",
                        "action": "navigateTo",
                        "params": {"path": "/v2/health-records"},
                    },
                    {
                        # 第二步：打开详情。此刻页面还没挂载，注册表会排队，
                        # 等 NewHealthRecords 注册时再排空执行。
                        "component": "HealthRecordsPage",
                        "action": "openRecord",
                        "params": {
                            "recordId": rec_id,
                            "title": title,
                            "query": kw or title,
                        },
                    },
                ],
                "summary": f"已打开档案：{title}",
            },
        }

    except Exception as e:
        logger.error(f"[open_health_record] 失败: {e}")
        return {"success": False, "message": f"检索档案失败: {e}"}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run()
