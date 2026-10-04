# Docker Compose 部署

根仓库 Compose 是本地部署入口，统一管理 PostgreSQL、Redis 和 Forgejo Git。`full` profile 还可构建运行旧版 Data Agent 与 Metric Platform 的 API 和前端；Agent V2 当前从宿主机启动。

Docker Desktop 中统一显示在 `data-agent` 分组，Compose 服务名保留为 `git`，容器名为 `forgejo`。

## 只启动基础设施

首次使用先初始化 Forgejo 管理员、私有仓库和本机 SSH 身份，再启动基础设施；Java 和 Vite 可继续从宿主机运行：

```powershell
.\infra\git\Initialize-GitService.ps1
docker compose -f .\infra\compose\compose.yml up -d
```

这会启动 PostgreSQL，创建 `data_agent`、`data_agent_v2`、`metric_platform` 数据库，并启动 Redis 和 Forgejo。初始化脚本会交互读取密码且可重复运行；详细的 Agent 连接和数据持久化说明见 [Forgejo Git 服务部署](../git/README.md)。

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
| `http://127.0.0.1:3000` | Forgejo Web 管理界面 |
| `127.0.0.1:2222` | Forgejo SSH，私有仓库 `agent-admin/metrics` |

容器化旧版 Data Agent 默认通过 `host.docker.internal:11434` 访问 Ollama，可用 `OLLAMA_BASE_URL` 覆盖。

停止服务并保留数据：

```powershell
docker compose -f .\infra\compose\compose.yml --profile full down
```

只有明确要删除 PostgreSQL、Redis 数据时，才追加 `--volumes`。Forgejo 的 SQLite、仓库及 SSH 主机密钥使用外部卷 `agent-platform_forgejo-data`，该命令不会删除它们；旧 Git 卷也不会被自动迁移或删除。

## 指标开发分支

当前 Compose 继续只为新分支流程提供基础设施，dbt-service 与 Agent V2 按各自 README 在宿主机运行。`.env.example` 中新增的分支配置需注入对应宿主机进程，Compose 不会自动为宿主机设置环境变量。签名与服务凭据保持空占位，不提交实际值。

Forgejo 事件目标使用 `host.docker.internal:<服务端口>/internal/git-branch-events`；启用事件补偿扫描并停用旧平台发布者。预检、接线与验收命令见 [分支验证说明](../verification/README.md)。
