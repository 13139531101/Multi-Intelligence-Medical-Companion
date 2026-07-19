# PHA 智能体职责重构计划（Stage 48-19）

> **状态**: 已立项, 计划阶段  
> **作者**: Claude (协助)  
> **优先级**: 高 (技术债 + 路由冲突双重问题)  
> **预计工期**: 10-13 小时 (1.5 个工作日)

---

## 1. 问题陈述

PHA 4 个 sub-agent (`health_advisor / health_records / medication_reminder / visit_summary`) 在多个维度存在**功能重复**, 已影响开发效率与运行可靠性。

### 1.1 量化数据

| 重复类型 | 数量 | 严重度 |
|---|---|---|
| `@mcp.tool()` 总数 | **66 个** | — |
| 同名 + 同实现 (整块 copy-paste) | **6 个核心 tool** + 4 份 helper | 🚨 高 |
| 同名 + 不同实现 (逻辑重复) | **7 组** | 🚨 高 |
| 同语义 + 不同名 (路由混乱) | **13 组** | 🚨 高 |
| `_normalize_pg_dsn` 复制 | **4 份** | ⚠️ 中 |
| `call_aliyun_ocr` 复制 | **2 份** | 🚨 高 |
| `memory_integration_tool.py` 复制 | **2 份 × ~1180 行** | 🚨 高 |
| 总计问题代码行数 | **≈ 5000 行** (估) | — |

### 1.2 真实危害

1. **LLM 路由混乱**: `add_medication_reminder` 在 HRM 与 MedReminder 都暴露, `dangerous_tools.py` HITL 配置两边打架
2. **Bug 修复不收敛**: 修了 HRM 的 OCR, MedReminder 的 OCR 还是 bug
3. **死代码风险**: HRM 的 `analyze_health_trends_async` 实际是 mock, 但仍 export
4. **认知负担**: 新人需要 4 份相似的 `_normalize_pg_dsn` 才能定位问题
5. **schema 漂移**: `personal_health_assistant.sql` 与 `database/postgres/init/*.sql` 不一致, **`visit_summaries` 表从未纳入 init sql**

---

## 2. 现状: 4 Agent + 1 Host Graph

```
backend/
├── HealthAdvisor/mcpserver/        22 tools (~3148 行)
├── HealthRecordsManager/mcpserver/ 18 tools (~3500 行)
├── MedicationReminder/mcpserver/   14 tools (~1900 行)
├── VisitSummaryGenerator/mcpserver/ 12 tools (~1360 行)
└── A2AServer/src/A2AServer/v2/
    ├── sub_agents.py       (4 个 @register_agent 类)
    ├── agent_registry.py   (registry 机制)
    ├── dangerous_tools.py  (HITL 配置, 硬编码)
    ├── host_graph.py       (LangGraph 路由)
    └── mcp_discover.py     (AST scan tool)
```

---

## 3. 目标: 引入 PhaCore 共享库

### 3.1 新路径

```
backend/
├── PhaCore/                                ← 新建 (与 4 agent 平级)
│   ├── mcpserver/
│   │   ├── __init__.py
│   │   ├── shared_ocr.py                   (~250 行, 由 2 份 ocr_tool.py 合并)
│   │   ├── shared_reminder.py              (~450 行, 由 2 份 reminder_tool.py 合并)
│   │   ├── shared_storage.py               (~400 行, 由 HRM storage + VSG database 合并)
│   │   ├── shared_health_analysis.py       (~500 行, 由 3 份 analysis 合并)
│   │   ├── shared_notification.py          (~400 行, 仅 MedReminder owner, 但抽出共享)
│   │   ├── shared_a2a.py                   (~150 行, A2A 跨 agent helper)
│   │   └── shared_db.py                    (~200 行, DSN + DatabaseManager 单点)
│   ├── db/
│   │   └── 00_full_schema.sql              (合并所有 init sql + visit_summaries)
│   ├── mcp_config_shared.json
│   └── README.md
├── HealthAdvisor/mcpserver/        12-15 tools (从 22 砍到 12-15)
├── HealthRecordsManager/mcpserver/  6-8 tools (从 18 砍到 6-8)
├── MedicationReminder/mcpserver/   9-11 tools (从 14 砍到 9-11)
└── VisitSummaryGenerator/mcpserver/ 5-6 tools (从 12 砍到 5-6)
```

**目标**: `@mcp.tool()` 总数从 **66 → 40~45**, 4 个 agent 文件总代码量 **从 ~10000 行 → ~5000 行**。

### 3.2 重构后职责分配

| Agent | 唯一职责 | 引用 PhaCore | 本地独有 |
|---|---|---|---|
| **health_advisor** | AI 问诊 / 健康建议 | shared_health_analysis, shared_ocr, shared_storage (read-only) | search_symptom_info, search_medication_info, upsert KB, analyze_symptoms, ai_medical_diagnosis, a2a_integration |
| **health_records** | 档案存储 | shared_ocr (主入口), shared_storage (主 owner), shared_data_extraction | create_user_profile, extract_medical_info (短期 alias) |
| **medication_reminder** | 用药 + 通知 | shared_reminder (主 owner), shared_notification (主 owner), shared_ocr (med-relevant), shared_storage | check_drug_interaction (从 advisor 搬过来) |
| **visit_summary** | 汇总 / 报告 | shared_storage (read-only + visit_summary), shared_health_analysis | parse_medical_document (input=text), generate_visit_summary, get_sample_document |

---

## 4. 实施路线 (6 个 Phase)

### Phase 1: PhaCore 框架 + shared_ocr (1-2h)

**目标**: OCR tool 单一来源, kill 2 份 `ocr_tool.py`

**步骤**:
1. 创建 `backend/PhaCore/mcpserver/__init__.py` (空)
2. 创建 `backend/PhaCore/mcpserver/shared_db.py`: 唯一 `DatabaseManager` + `_build_pg_dsn` + `_normalize_pg_dsn`
3. 创建 `backend/PhaCore/mcpserver/shared_ocr.py`:
   ```python
   from mcp.server.fastmcp import FastMCP
   from ..db_helper import call_aliyun_ocr, call_local_ocr, call_aliyun_ocr_v2021
   
   mcp = FastMCP("PhaCoreSharedOCR")
   
   @mcp.tool()
   def extract_text_from_image(image_base64: str) -> str: ...
   
   @mcp.tool()
   def validate_medical_document(text: str) -> str: ...
   ```
4. 修改 `mcp_discover.py` 的 `_find_mcp_tool_files()`: 加 PhaCore 路径
5. `AGENT_DIR_MAP` 加: `"PhaCore": ".../backend/PhaCore/mcpserver"`
6. 修改 HRM + MedReminder 的 `sub_agents.py`: 它们的 `tools_module` 改成 list (允许 PhaCore + 本地), 或在 `get_tools()` 里手动 `load_mcp_tools("PhaCore_ocr")`
7. 删除 `HRM/mcpserver/ocr_tool.py` + `MedReminder/mcpserver/ocr_tool.py` (共 ~922 行)
8. 测试: `tests/mcp/test_ocr.sh` 必须通过

**验收**: 调用 OCR tool 只命中 1 个 (不再是 2 个同名重复)

### Phase 2: shared_reminder (2-3h)

**目标**: `add_medication_reminder / get_medication_reminders / log_medication_taken` 统一, kill HRM 的 reminder_tool.py

**步骤**:
1. 创建 `shared_reminder.py`, 合并 HRM (106+85+117 行) + MedReminder (114+130+115 行)
2. **签名统一**:
   - HRM `reminder_times: str` (JSON) → MedReminder `reminder_times: List[str]`
   - HRM `return str` (JSON) → MedReminder `return Dict[str, Any]`
   - 选 MedReminder 的 (更现代)
3. 名字统一: `mark_reminder_taken → log_medication_taken` (MedReminder 名字)
4. HRM 删除 `reminder_tool.py` (整 ~580 行); MedReminder 保留 `add_appointment_reminder` 的部分, 其余删除
5. 改 `dangerous_tools.py`:
   - 删除 HRM 的 `add_medication_reminder / mark_reminder_taken / log_medication_taken`
   - MedReminder 留下 `add_medication_reminder: True`
6. 加 1 周 alias: `mark_reminder_taken` 直接转发到 `log_medication_taken` 在 `safe_alias.py`
7. 加 backward compat alias: 1 周后删

**验收**: 
- HRM 没有自己的 `add_*_reminder` tool 了
- MedReminder 是唯一 owner, HITL 配置正确路由
- DB 行为一致 (写同一张表)

### Phase 3: shared_storage + schema 整合 (3-4h)

**目标**: 健康档案存储统一, schema 完整

**步骤**:
1. 创建 `shared_storage.py`, 合并 HRM `storage_tool.py` + VSG `database_tool.py`
2. 合并:
   - `save_health_record` (HRM 是 owner)
   - `get_health_records` + `get_health_records_by_range` → 统一一个版本 (加 `start_date` / `end_date`)
   - `get_health_record_detail` (HRM + VSG 同名)
   - `delete_health_record` (HRM 独有)
   - `save_visit_summary` / `get_visit_summaries_*` (VSG owner)
3. **schema 修复**:
   - 新建 `backend/PhaCore/db/00_full_schema.sql`
   - 合并 `database/postgres/init/01_pgvector.sql` + `02_reminders_and_records.sql` + VSG `visit_summaries` 表 (从 `database_tool.py:237-241` 提取)
4. HRM 删除 `storage_tool.py` (~435 行); VSG 删除 `database_tool.py` (~290 行)
5. 5 个 `database_config.py` 统一指向 `PhaCore/shared_db.py` 的 `DatabaseManager`

**验收**:
- `psql -d pha < backend/PhaCore/db/00_full_schema.sql` 一键建库
- HRM + VSG 不再各自写 SQL 直接通过 PhaCore

### Phase 4: shared_health_analysis (1h)

**目标**: 健康趋势分析统一, kill mock async 版本

**步骤**:
1. 创建 `shared_health_analysis.py`, 合并:
   - `HealthAdvisor\knowledge_tool.py` 的 `analyze_health_concern`
   - `HealthAdvisor\diagnosis_tool.py` 的 `analyze_symptoms` (改名 `analyze_symptoms_for_advisor`)
   - `VisitSummary\ai_analysis_tool.py` 全部 3 个 (`analyze_health_trends` / `generate_health_insights` / `detect_health_alerts`)
2. HRM 删除 `async_analysis_tool.py` (实际是 mock, ~130 行)
3. HealthAdvisor 删除 `analyze_health_concern` 本地副本 (保留 KB 搜索独有)
4. VisitSummary 删除 `ai_analysis_tool.py` (~560 行)

**验收**: HealthAdvisor advisor 工具保留 search_symptom_info / search_medication_info / KB CRUD, analysis 全走 PhaCore

### Phase 5: dedup test + 删除死代码 (2h)

**目标**: 自动化检测, 防止未来回归

**步骤**:
1. 写 `tests/test_tool_dedup.py`:
   - 用 `mcp_discover.discover_mcp_tools_static("PhaCore")` + 4 个 agent
   - 断言: 没有任何 (tool_name, agent) 在 PhaCore 出现且仍出现在其他 agent
2. 写 `tests/test_dangerous_tools_consistency.py`:
   - 验证 `dangerous_tools.py` 中所有 tool 名都能在 `mcp_discover` 找到
3. 删死代码: 6 个被取代的 `_tool.py` 文件已删, 检查仍能引用旧名的 `LEGACY_ALIAS` 已清理
4. 加 CI: `pytest tests/test_tool_dedup.py` 必须通过

**验收**: 跑 dedup test 一键报告现有重复

### Phase 6: 文档同步 (1h)

**目标**: 让未来开发者知道 PhaCore 的边界

**步骤**:
1. 写 `backend/PhaCore/README.md` (边界, 开发规范)
2. 更新 `docs/Chinese/V2_DEVELOPER_GUIDE.md`: 加第 4 节 "Adding a new shared tool"
3. 更新 `docs/Chinese/REFACTOR_PLAN_v2.md`: 追加 Phase 7 节 "PhaCore extraction"
4. 更新 `docs/Chinese/CHANGELOG.md`: stage 48-19

---

## 5. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| **4 个 Dockerfile 都硬编码 `mcpserver/*.py` 路径** | 删文件后镜像 cache 失效 | 改 Dockerfile: ADD PhaCore + 各自 mcpserver 目录 |
| **`mcp_discover._find_mcp_tool_files` 只看 `<Agent>/mcpserver/`** | PhaCore 工具不被发现 | 修改 `_find_mcp_tool_files` + 加 PhaCore 到 `AGENT_DIR_MAP` |
| **`agent_registry.tools_module` 是字符串** | 多 module 时不兼容 | 改成 `tools_module: Optional[Union[str, List[str]]]` + 兼容 path |
| **`dangerous_tools.py` 字典 key 硬编码** | tool 改名后 HITL 失效 | 改成从 `mcp_discover` 动态收集 |
| **`database/postgres/init/*.sql` 缺 `visit_summaries` 表** | VSG 写到不存在的表会 fail | 在 Phase 3 一并修 |
| **dangling tool 在 K8s container 老镜像** | 高危 | CI 加 `test_tool_dedup` 必须通过 |
| **`personal_health_assistant.sql` 快照与 init sql 不一致** | 部署时容易漏 | 加 CI 校验 |
| **`memory_integration_tool.py` 1180 行 × 2 份** | 没在本轮重构 | 下一轮 (建议移 `AgentMemorySystem/mcpserver/`) |

---

## 6. 度量指标 (成功标准)

| 指标 | 重构前 | 重构后目标 |
|---|---|---|
| `@mcp.tool()` 总数 | 66 | 40-45 |
| 4 个 agent `mcpserver/*.py` 总行数 | ~10000 | ~5000 |
| 同名 tool 数量 (跨 agent) | ≥ 10 | **0** |
| `_normalize_pg_dsn` 副本 | 4 | **1** |
| DB schema 初始化脚本数 | 3 + 2 硬编码 | **1** (`00_full_schema.sql`) |
| `dangerous_tools.py` 需要手动同步的项 | ~12 | **0** (从 mcp_discover 自动收集) |
| 新增 shared tool 所需步骤 | 改 4 个文件 | **改 1 个文件** (PhaCore) |
| 数字式直接证据: `grep -rn "@mcp.tool" --include="*.py" backend/\| wc -l` | 66 | ≤ 45 |
| 数字式直接证据: 同名 tool 数 | `grep -rE "^@mcp.tool\\(\\)" backend/ -A 1\| grep -E "^def " \| sort \| uniq -c \| sort -rn \| head` 输出 > 1 的行 | **0** |

---

## 7. 不在本轮处理的事项 (后续)

- `memory_integration_tool.py` 1180 行 × 2 份 → 下一轮 (`AgentMemorySystem/mcpserver/`)
- K8s service map 拆分 `PhaCore/shared_a2a.py` (单点维护)
- `database_config.py` 5 个 agent 互相不一致 → 下一轮
- 记忆系统的 wrapper (`mcp.server.models`) 替换为官方 fastmcp → 下一轮

---

## 8. 待确认问题 (需要用户拍板)

1. **PhaCore 路径** - 推荐 `backend/PhaCore/` (与 4 个 agent 平级, path 短, 文件名显式)
2. **保留 backward compat alias** - 推荐保留 1 周 (用 `LEGACY_ALIAS = {...}` 字典, 自动转发)
3. **一次性切还是灰度** - 推荐分 Phase 渐进, 每个 Phase 单独 commit + 测试
4. **`memory_integration_tool.py` 1180 行 × 2 是否纳入本轮** - 推荐**不纳入** (工作量超 scope, 下一轮处理)
5. **Dockerfile 改写** - 必须在 Phase 1 之前完成, 否则镜像构建会 break
