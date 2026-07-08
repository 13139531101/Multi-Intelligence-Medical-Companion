# 阶段1 推进记录

> 启动时间：2026-03-XX
> 目标：基础设施升级（零业务影响）

## 已完成 ✅

1. **创建 v2 统一依赖清单**：`pyproject.toml`（项目根目录）
   - 锁定 LangChain 1.2.10+ / LangGraph 1.0.2+ / langchain-postgres 0.0.15+ / a2a-sdk 0.3.0+
   - 参考 [REFACTOR_PLAN_v2.md §2](REFACTOR_PLAN_v2.md)

2. **生成 pip 兼容依赖文件**：[requirements-v2.txt](../../requirements-v2.txt)
   - 保留旧业务包，向后兼容
   - 现阶段可继续 `pip install -r backend/requirements.txt` 跑老业务

3. **可观测性模块**：[backend/observability.py](../../backend/observability.py)
   - 零侵入：仅需在服务入口 `setup_observability("service-name")` 一行
   - 自动按环境变量启用 LangSmith / Langfuse / OpenTelemetry
   - 没配置时静默跳过，不影响开发

4. **阶段验收脚本**：[scripts/verify_stage1.py](../../scripts/verify_stage1.py)
   - 自动检测所有关键依赖
   - 验证现有业务模块仍可导入

## 下一步

- [ ] 在 dev 环境运行 `pip install -r requirements-v2.txt`
- [ ] 运行 `python scripts/verify_stage1.py` 验收
- [ ] 在 `hostAgentAPI/server.py` 入口加 `setup_observability("host-agent-api")`
- [ ] 在 `backend/api/main.py` 入口加 `setup_observability("health-api")`
- [ ] 跑现有 pytest 套件验证不破坏
- [ ] 阶段1 PR 合入 main 后开始阶段2

## 风险

- ⚠️ pydantic 2.x 大版本升级可能影响旧代码的 model_validator，需要逐个测
- ⚠️ fastapi 0.128 较老代码 0.115 有 breaking change（极少见），但建议先灰度
- ⚠️ langchain 1.x 不会影响旧代码（独立 namespace），但不要 `from langchain.chat_models import ...` 这种旧写法
