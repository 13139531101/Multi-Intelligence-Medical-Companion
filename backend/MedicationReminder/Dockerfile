FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install uv CLI via PyPI (avoids GitHub download in build)
RUN --mount=type=cache,target=/root/.cache/pip pip install uv

# Service-specific deps
COPY MedicationReminder/requirements.txt /tmp/service-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/service-requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || true

# LangChain + 全局依赖
COPY requirements.txt /tmp/backend-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/backend-requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || true

COPY . ./

ENV PORT=10012
ENV HOST=0.0.0.0

EXPOSE 10012

WORKDIR /app/MedicationReminder
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "10012", "--agent_url", "http://medication_reminder:10012/"]
