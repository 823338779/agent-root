FROM node:22-alpine AS build
WORKDIR /workspace
COPY data-agent-v2/frontend/package.json data-agent-v2/frontend/package-lock.json ./
RUN npm ci
COPY data-agent-v2/frontend ./
# Vite在构建时固化浏览器可访问的指标平台地址。
ARG VITE_METRIC_PLATFORM_URL
ENV VITE_METRIC_PLATFORM_URL=${VITE_METRIC_PLATFORM_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/docker/nginx/data-agent.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/dist /usr/share/nginx/html
EXPOSE 80
