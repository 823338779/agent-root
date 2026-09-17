# Docker Compose 部署

根仓库 Compose 是本地部署入口，统一管理 PostgreSQL、Redis 和 Git。`full` profile 还可构建运行旧版 Data Agent 与 Metric Platform 的 API 和前端；Agent V2 当前从宿主机启动。

Docker Desktop 中统一显示在 `data-agent` 分组，Git 容器名为 `git`。

## 只启动基础设施

首次使用先初始化 Git 的本机 SSH 身份，再启动基础设施；Java 和 Vite 可继续从宿主机运行：

```powershell
.\infra\git\Initialize-GitService.ps1
docker compose -f .\infra\compose\compose.yml up -d
```

这会启动 PostgreSQL，创建 `data_agent`、`data_agent_v2`、`metric_platform` 数据库，并启动 Redis 和 Git。Git 初始化脚本可重复运行，详细的 Agent 连接和数据持久化说明见 [Git 服务部署](../git/README.md)。

## 完整本地栈

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
| `127.0.0.1:2222` | Git SSH，固定仓库 `/srv/git/metrics.git` |

容器化旧版 Data Agent 默认通过 `host.docker.internal:11434` 访问 Ollama，可用 `OLLAMA_BASE_URL` 覆盖。

停止服务并保留数据：

```powershell
docker compose -f .\infra\compose\compose.yml --profile full down
```

只有明确要删除 PostgreSQL、Redis 数据时，才追加 `--volumes`。Git 仓库及 SSH 主机密钥使用外部卷，该命令不会删除它们。
