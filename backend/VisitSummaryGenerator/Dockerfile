FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install uv CLI via PyPI (avoids GitHub download in build)
RUN --mount=type=cache,target=/root/.cache/pip pip install uv -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY requirements.txt /tmp/backend-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/backend-requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . ./

ENV PORT=10013
ENV HOST=0.0.0.0

EXPOSE 10013

WORKDIR /app/VisitSummaryGenerator
# 阶段48-ops: 多 worker 并发（workers=CPU核数，最多4个）
# 支持 SIGHUP 热重载
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 10013 --workers 4 "]