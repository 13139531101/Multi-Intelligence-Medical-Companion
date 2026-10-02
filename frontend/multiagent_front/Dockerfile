# multiagent_front Dockerfile
# 构建: docker build -f frontend/multiagent_front/Dockerfile -t a2aserver-multiagent-front:latest .
# 运行: docker run -p 5174:80 --network a2aserver_default a2aserver-multiagent-front:latest

FROM node:22-alpine AS builder

WORKDIR /app

# 复制 package.json
COPY package*.json ./

# 安装依赖
RUN npm ci

# 复制源代码
COPY . .

# 构建 (VITE_HOSTAGENT_API 是前端在构建时需要的 API 地址)
# Docker 部署时不传该参数，使用相对路径 ""
ARG VITE_HOSTAGENT_API=""
ENV VITE_HOSTAGENT_API=$VITE_HOSTAGENT_API

# 阶段48-config: 智能体显示名（构建时注入）
ARG VITE_HEALTH_ADVISOR_NAME="健康顾问"
ENV VITE_HEALTH_ADVISOR_NAME=$VITE_HEALTH_ADVISOR_NAME
ARG VITE_HEALTH_RECORDS_NAME="健康档案"
ENV VITE_HEALTH_RECORDS_NAME=$VITE_HEALTH_RECORDS_NAME
ARG VITE_MEDICATION_REMINDER_NAME="用药提醒"
ENV VITE_MEDICATION_REMINDER_NAME=$VITE_MEDICATION_REMINDER_NAME
ARG VITE_VISIT_SUMMARY_NAME="就诊摘要"
ENV VITE_VISIT_SUMMARY_NAME=$VITE_VISIT_SUMMARY_NAME

# 构建
RUN npm run build

# 生产镜像 - nginx
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# nginx 配置 - 版本控制文件（此前硬编码在此处，改一次要重建镜像）
# 见 nginx.conf 顶部注释：动态 DNS 解析 + SSE 透传
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
