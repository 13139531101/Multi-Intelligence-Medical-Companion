# Build stage
FROM node:20-alpine as build

WORKDIR /app
COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm npm install

COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Custom Nginx config to handle SPA routing and API proxy
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
