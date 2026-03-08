FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install uv CLI via PyPI (avoids GitHub download in build)
RUN --mount=type=cache,target=/root/.cache/pip pip install uv

COPY requirements.txt /tmp/backend-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/backend-requirements.txt

COPY . ./

ENV PORT=10013
ENV HOST=0.0.0.0

EXPOSE 10013

WORKDIR /app/VisitSummaryGenerator
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "10013", "--agent_url", "http://visit_summary:10013/"]
