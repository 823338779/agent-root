FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY metric-platform/backend /workspace/backend
COPY metric-platform/api /workspace/api
RUN mvn -f /workspace/backend/pom.xml -DskipTests package

FROM eclipse-temurin:21-jre
# 平台用 Git 枚举构建仓库的分支，curl 供就绪探针使用。
RUN apt-get update && apt-get install -y --no-install-recommends curl git && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=build /workspace/backend/metric-app/target/metric-app-*.jar /app/app.jar
USER appuser
EXPOSE 8090
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
