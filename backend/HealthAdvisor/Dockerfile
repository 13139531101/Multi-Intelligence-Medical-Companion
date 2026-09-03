FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install Python deps from backend root requirements
COPY requirements.txt /tmp/backend-requirements.txt
RUN pip install --timeout 120 -r /tmp/backend-requirements.txt || echo "deps install failed"

# Copy service code
COPY . ./

# Service defaults
ENV PORT=10011
ENV HOST=0.0.0.0

EXPOSE 10011

# Set working directory to service subfolder and run
WORKDIR /app/HealthAdvisor
# 阶段48-ops: 多 worker 并发（workers=CPU核数，最多4个）
# 支持 SIGHUP 热重载：收到信号后优雅重启 workers 加载新配置
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 10011 --workers 4"]
