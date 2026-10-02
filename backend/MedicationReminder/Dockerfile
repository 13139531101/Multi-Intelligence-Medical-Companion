FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# Install uv CLI via PyPI (avoids GitHub download in build)
RUN --mount=type=cache,target=/root/.cache/pip pip install uv

# 阶段48-fix: 此前是 `pip install -i <清华镜像> ... || true`。
# 镜像 403 时 pip 直接失败, 而 `|| true` 把失败吞掉 → 构建"成功"却产出一个
# 连 uvicorn 都没有的镜像, 容器起来就 `sh: uvicorn: not found` 无限重启。
# 改为: 先试镜像源, 失败回退官方 PyPI, 两边都失败就让构建**失败** (不再 || true)。
ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

# Service-specific deps
COPY MedicationReminder/requirements.txt /tmp/service-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    (pip install -r /tmp/service-requirements.txt -i ${PIP_INDEX_URL} \
     || pip install -r /tmp/service-requirements.txt -i https://pypi.org/simple)

# LangChain + 全局依赖
COPY requirements.txt /tmp/backend-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    (pip install -r /tmp/backend-requirements.txt -i ${PIP_INDEX_URL} \
     || pip install -r /tmp/backend-requirements.txt -i https://pypi.org/simple)

COPY . ./

ENV PORT=10012
ENV HOST=0.0.0.0

EXPOSE 10012

WORKDIR /app/MedicationReminder
# 阶段48-ops: 多 worker 并发（workers=CPU核数，最多4个）
# 支持 SIGHUP 热重载
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port 10012 --workers 4 "]
