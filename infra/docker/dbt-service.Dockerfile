FROM python:3.12-slim

# Git 用于检出固定版本，socat 使已有执行快照中的回环地址继续指向本地 StarRocks。
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update && apt-get -o Acquire::Retries=3 install -y --no-install-recommends git socat \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.12.17
WORKDIR /app

# 锁文件引用本工程维护的 dbt 和 MetricFlow 源码。
COPY . .
RUN uv sync --frozen --no-dev --no-editable && uv cache clean \
    && useradd --system --create-home --uid 10001 dbt
ENV PATH="/app/.venv/bin:${PATH}" SERVICE_TEMP_ROOT=/tmp/dbt SERVICE_HOST=0.0.0.0
USER dbt
EXPOSE 8000
CMD ["dbt-metricflow-service"]
