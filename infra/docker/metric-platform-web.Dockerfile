FROM node:22-alpine AS build
WORKDIR /workspace
COPY metric-platform/frontend/package.json metric-platform/frontend/package-lock.json ./
RUN npm ci
COPY metric-platform/frontend ./
# Vite在构建时固化浏览器可访问的Agent地址。
ARG VITE_AGENT_URL
ENV VITE_AGENT_URL=${VITE_AGENT_URL}
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/docker/nginx/metric-platform.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/dist /usr/share/nginx/html
EXPOSE 80
