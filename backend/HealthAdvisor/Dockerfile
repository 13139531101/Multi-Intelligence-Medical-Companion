FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install uv CLI via PyPI (avoids GitHub download in build)
RUN pip install --no-cache-dir uv

# Install Python deps from backend root requirements if present
COPY requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt

# Copy service code
COPY . ./

# Service defaults
ENV PORT=10011
ENV HOST=0.0.0.0

EXPOSE 10011

# Set working directory to service subfolder and run
WORKDIR /app/HealthAdvisor
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "10011", "--agent_url", "http://health_advisor:10011/"]