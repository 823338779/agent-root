FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY data-agent/backend /workspace/backend
RUN mvn -f /workspace/backend/pom.xml -pl agent-api -am -DskipTests package

FROM eclipse-temurin:21-jre
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=build /workspace/backend/agent-api/target/agent-api-*-exec.jar /app/app.jar
USER appuser
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
