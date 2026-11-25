FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /workspace
COPY data-agent-v2/pom.xml /workspace/pom.xml
COPY data-agent-v2/backend /workspace/backend
COPY data-agent-v2/contracts /workspace/contracts
RUN mvn -f /workspace/backend/pom.xml -pl agent-server -am -DskipTests package

FROM eclipse-temurin:21-jre
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --uid 10001 appuser
WORKDIR /app
COPY --from=build /workspace/backend/agent-server/target/agent-server-*.jar /app/app.jar
USER appuser
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
