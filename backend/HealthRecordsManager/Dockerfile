FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install uv CLI via PyPI (avoids GitHub download in build)
RUN pip install --no-cache-dir uv

# Install service-specific dependencies
COPY HealthRecordsManager/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . ./

ENV PORT=10010
ENV HOST=0.0.0.0

EXPOSE 10010

# Run from service subfolder so main.py is found
WORKDIR /app/HealthRecordsManager
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "10010", "--agent_url", "http://health_records:10010/"]