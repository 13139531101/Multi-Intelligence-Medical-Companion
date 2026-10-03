FROM python:3.11-slim

# Prevent interactive tzdata prompts
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# System deps (if any lightweight ones are needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY frontend/hostAgentAPI/requirements.txt ./requirements.txt
# 使用国内 PyPI 镜像以加速依赖安装，并允许 pip 缓存以提升重复构建速度
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
RUN --mount=type=cache,target=/root/.cache/pip pip install -i ${PIP_INDEX_URL} -r requirements.txt || pip install -i https://pypi.org/simple -r requirements.txt

# 同步安装后端健康档案管理模块的 OCR 相关依赖
COPY backend/HealthRecordsManager/requirements.txt ./hrm_requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -i ${PIP_INDEX_URL} -r hrm_requirements.txt || pip install -i https://pypi.org/simple -r hrm_requirements.txt

# App source (Host API)
COPY frontend/hostAgentAPI ./
# 阶段39-6: 复制 frontend/test_simple.html 和 test_page.html 用于浏览器测试
COPY frontend/test_simple.html ./test_simple.html
COPY frontend/test_page.html ./test_page.html
COPY frontend/serve_cors.py ./serve_cors.py

# Provide backend modules used by Host API integrations (WeChat subscribe messages, etc.)
COPY backend/notification_service.py ./backend/notification_service.py
COPY backend/health_records_api.py ./backend/health_records_api.py
COPY backend/visit_summary_api.py ./backend/visit_summary_api.py
COPY backend/memory_system.py ./backend/memory_system.py
COPY backend/services ./backend/services
COPY backend/api ./backend/api
COPY backend/HealthRecordsManager ./backend/HealthRecordsManager
COPY backend/AgentMemorySystem ./backend/AgentMemorySystem
COPY backend/PhaCore ./backend/PhaCore

# Provide A2AServer package required by Host API
COPY backend/A2AServer/src/A2AServer ./A2AServer

# === 阶段28：v2 LangGraph MCP 工具源 ===
# v2 mcp_discover AST 扫描这些目录找 tool 函数
COPY backend/HealthAdvisor/mcpserver ./backend/HealthAdvisor/mcpserver
COPY backend/HealthRecordsManager/mcpserver ./backend/HealthRecordsManager/mcpserver
COPY backend/MedicationReminder/mcpserver ./backend/MedicationReminder/mcpserver
COPY backend/VisitSummaryGenerator/mcpserver ./backend/VisitSummaryGenerator/mcpserver

# === 阶段48：四个 agent 各自的 system prompt ===
# sub_agents._load_prompt 按 agent 目录定位，四份内容完全不同。之前只整体 COPY
# 了 HealthRecordsManager（上面第 41 行），另外三个 agent 只有 mcpserver/，
# 于是四个 agent 全部加载了 HealthRecordsManager 那一份 —— 改别的 prompt 不生效。
COPY backend/HealthAdvisor/memory_enhanced_agent_prompt.md ./backend/HealthAdvisor/memory_enhanced_agent_prompt.md
COPY backend/MedicationReminder/memory_enhanced_agent_prompt.md ./backend/MedicationReminder/memory_enhanced_agent_prompt.md
COPY backend/VisitSummaryGenerator/memory_enhanced_agent_prompt.md ./backend/VisitSummaryGenerator/memory_enhanced_agent_prompt.md

# Ensure Python can resolve local package and backend modules
ENV PYTHONPATH=/app:/app/backend

# Point Host API to the bundled backend module directory
ENV BACKEND_DIR=/app/backend

# Runtime env with sensible defaults
ENV HOST_API_PORT=13002
ENV HOST_API_BIND=0.0.0.0
# 阶段48-perf: HOST_API_WORKERS 控制 uvicorn --workers 数量（默认 4）
# 每个 worker 都会执行 lifespan()，独立初始化 ConversationServer / ADKHostManager / metrics registry。
# 设为 1 可回退到单进程模式（便于本地调试）。
ENV HOST_API_WORKERS=2

# Expose service port
EXPOSE 13002

# Start FastAPI via uvicorn (multi-worker, lifespan per-worker)
CMD ["sh", "-c", "python -m uvicorn app:app --host ${HOST_API_BIND} --port ${HOST_API_PORT} --workers ${HOST_API_WORKERS}"]
