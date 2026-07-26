FROM node:22-alpine AS build
WORKDIR /workspace
COPY data-agent/frontend/package.json data-agent/frontend/package-lock.json ./
RUN npm ci
COPY data-agent/frontend ./
RUN npm run build

FROM nginx:1.27-alpine
COPY infra/docker/nginx/data-agent.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/dist /usr/share/nginx/html
EXPOSE 80
