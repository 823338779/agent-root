FROM node:22-alpine AS build
WORKDIR /workspace
COPY metric-platform/frontend/package.json metric-platform/frontend/package-lock.json ./
RUN npm ci
COPY metric-platform/frontend ./
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/docker/nginx/metric-platform.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/dist /usr/share/nginx/html
EXPOSE 80
