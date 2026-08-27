FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install uv CLI via PyPI (avoids GitHub download in build)
RUN --mount=type=cache,target=/root/.cache/pip pip install uv

# Service-specific deps
COPY HealthRecordsManager/requirements.txt /tmp/service-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/service-requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || true

# LangChain + 全局依赖（使用 backend 层的 pip cache）
COPY requirements.txt /tmp/backend-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/backend-requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || true

COPY . ./

ENV PORT=10010
ENV HOST=0.0.0.0

EXPOSE 10010

# Run from service subfolder so main.py is found
WORKDIR /app/HealthRecordsManager
# 阶段48-ops: 多 worker 并发（workers=CPU核数，最多4个）
# 支持 SIGHUP 热重载
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 10010 --workers 4 --sighup-term"]
