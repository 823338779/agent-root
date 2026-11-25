# Docker Compose 部署

根仓库 Compose 是本地部署入口，统一管理 PostgreSQL、Redis 和 Forgejo Git。`full` profile 还可构建运行Data Agent V2 与 Metric Platform 的 API 和前端。

Docker Desktop 中统一显示在 `data-agent` 分组，Compose 服务名保留为 `git`，容器名为 `forgejo`。

## 只启动基础设施

首次使用先初始化 Forgejo 管理员、私有仓库和本机 SSH 身份，再启动基础设施；Java 和 Vite 可继续从宿主机运行：

```powershell
.\infra\git\Initialize-GitService.ps1
docker compose -f .\infra\compose\compose.yml up -d
```

这会启动 PostgreSQL，创建 `data_agent`、`data_agent_v2`、`metric_platform` 数据库，并启动 Redis 和 Forgejo。初始化脚本会交互读取密码且可重复运行；详细的 Agent 连接和数据持久化说明见 [Forgejo Git 服务部署](../git/README.md)。

## 完整本地栈

V3 复用同一 PostgreSQL 实例。已有数据卷可单独运行 `docker compose -f infra/compose/compose.yml run --rm data-agent-v3-db-init` 创建 `data_agent_v3` 库，重复运行会保留历史。

可将 `infra/compose/.env.example` 复制为 `infra/compose/.env` 并调整本地值，然后构建和启动服务：

```powershell
docker compose --env-file .\infra\compose\.env `
  -f .\infra\compose\compose.yml `
  --profile full up -d --build
```

未指定 `.env` 时使用 Compose 中声明的开发默认值。Git 首次启动前仍需完成上面的初始化。

| 端点 | 服务 |
| --- | --- |
| `http://localhost:8080` | Data Agent web application and `/api` proxy |
| `http://localhost:8090` | Metric Platform web application and `/api` proxy |
| `localhost:5432` | Shared PostgreSQL |
| `localhost:6379` | Shared Redis |
| `http://127.0.0.1:3000` | Forgejo Web 管理界面 |
| `127.0.0.1:2222` | Forgejo SSH，私有仓库 `agent-admin/metrics` |

容器化旧版 Data Agent 默认通过 `host.docker.internal:11434` 访问 Ollama，可用 `OLLAMA_BASE_URL` 覆盖。

停止服务并保留数据：

```powershell
docker compose -f .\infra\compose\compose.yml --profile full down
```

只有明确要删除 PostgreSQL、Redis 数据时，才追加 `--volumes`。Forgejo 的 SQLite、仓库及 SSH 主机密钥使用外部卷 `agent-platform_forgejo-data`，该命令不会删除它们；旧 Git 卷也不会被自动迁移或删除。

## 本地指标平台和三个 dbt-service 副本

在 Windows Docker Desktop 上，叠加 `metric-dbt.local.yml` 可在 `data-agent` 分组中运行指标平台（API、Web）、Neo4j 和三个 dbt-service。该配置复用已运行的 PostgreSQL、Redis、StarRocks，以及 `dbt-metricflow-service/config/service.yaml` 指向的已初始化服务库。Neo4j 使用原有的 `metric-platform_metric-platform-neo4j` 数据卷和 `metric-platform_default` 网络。共享基础设施若使用自定义 Compose 环境文件，请同时传入原文件。

在根目录执行：

```powershell
$stack = @('--env-file', "$HOME/.metric-platform/ontology.properties", '-f', 'infra/compose/compose.yml', '-f', 'infra/compose/metric-dbt.local.yml')
$services = @('dbt-service', 'metric-platform-api', 'metric-platform-web')
docker compose @stack build @services
docker compose @stack up -d --no-deps --wait neo4j
docker compose @stack up -d --no-deps --wait @services
docker compose @stack ps @services
```

控制台地址为 `http://127.0.0.1:8090`。宿主机通过 `http://127.0.0.1:8000` 访问 dbt-service，平台 API 通过同一 Nginx 在容器网络内的入口访问三个副本。每个副本使用独立临时目录，共享构建记录和产物。停止这组应用可执行 `docker compose @stack stop @services`。

## 指标开发分支

默认 Compose 为新分支流程提供基础设施。dbt-service 可按上节在容器运行，也可按产品 README 在宿主机运行。

Forgejo 事件目标使用 `host.docker.internal:<服务端口>/internal/git-branch-events`；启用事件补偿扫描并停用旧平台发布者。
