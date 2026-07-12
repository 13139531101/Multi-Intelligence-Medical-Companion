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
ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
RUN --mount=type=cache,target=/root/.cache/pip pip install -i ${PIP_INDEX_URL} -r requirements.txt || pip install -i https://pypi.org/simple -r requirements.txt

# 同步安装后端健康档案管理模块的 OCR 相关依赖
COPY backend/HealthRecordsManager/requirements.txt ./hrm_requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -i ${PIP_INDEX_URL} -r hrm_requirements.txt || pip install -i https://pypi.org/simple -r hrm_requirements.txt

# App source (Host API)
COPY frontend/hostAgentAPI ./

# Provide backend modules used by Host API integrations (WeChat subscribe messages, etc.)
COPY backend/notification_service.py ./backend/notification_service.py
COPY backend/health_records_api.py ./backend/health_records_api.py
COPY backend/visit_summary_api.py ./backend/visit_summary_api.py
COPY backend/memory_system.py ./backend/memory_system.py
COPY backend/services ./backend/services
COPY backend/api ./backend/api
COPY backend/HealthRecordsManager ./backend/HealthRecordsManager
COPY backend/AgentMemorySystem ./backend/AgentMemorySystem

# Provide A2AServer package required by Host API
COPY backend/A2AServer/src/A2AServer ./A2AServer

# === 阶段28：v2 LangGraph MCP 工具源 ===
# v2 mcp_discover AST 扫描这些目录找 tool 函数
COPY backend/HealthAdvisor/mcpserver ./backend/HealthAdvisor/mcpserver
COPY backend/HealthRecordsManager/mcpserver ./backend/HealthRecordsManager/mcpserver
COPY backend/MedicationReminder/mcpserver ./backend/MedicationReminder/mcpserver
COPY backend/VisitSummaryGenerator/mcpserver ./backend/VisitSummaryGenerator/mcpserver

# Ensure Python can resolve local package and backend modules
ENV PYTHONPATH=/app:/app/backend

# Point Host API to the bundled backend module directory
ENV BACKEND_DIR=/app/backend

# Runtime env with sensible defaults
ENV HOST_API_PORT=13002
ENV HOST_API_BIND=0.0.0.0

# Expose service port
EXPOSE 13002

# Start FastAPI via uvicorn
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "13002"]
