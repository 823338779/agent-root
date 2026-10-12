# Docker Swarm 部署

此目录部署 Data Agent V2、指标平台、两个前端及 PostgreSQL/Redis。dbt-service 按自身 README 单独部署；两端统一调用其 `/v3` 协议。所有命令从工作区根目录执行。

## 部署前提

- 每个节点安装 Docker，并能访问镜像仓库、Ollama 和 dbt-service。多节点地址使用节点可达的 LAN 地址，不使用 `127.0.0.1`。
- 在各节点配置镜像仓库信任。Agent 的私有 Git 访问身份须由部署环境安全注入；不得把私钥或 token 写入镜像和仓库。
- 先停止旧协议写入，核对在途操作，备份各产品元数据和封存产物，在隔离副本完成来源冲突处理与迁移，再切换配套版本。数据库初始化只补建 `data_agent_v2` 与 `metric_platform`，保留旧 `data_agent` 库，不自动把旧库作为 V2 数据源。
- 新应用 secret 名为 `data-agent-v2-application` 和 `metric-platform-v3-application`，不能复用旧应用配置。Swarm 不支持 Compose 的启动依赖等待；数据库初始化完成前应用可能重启，开放写入前必须确认初始化任务成功和两个 API 健康。

## 静态验证

下面的命令校验模板、实际生成的配置形状、Vite 构建参数及 `docker stack config`。Docker 变更命令被测试替身拦截，不创建 secret、推送镜像或部署集群。

```powershell
.\infra\swarm\scripts\Test-SwarmConfig.ps1
```

## 部署顺序

初始化 manager、标记持久服务节点并部署镜像仓库：

```powershell
.\infra\swarm\scripts\Initialize-LocalSwarm.ps1 -ManagerAdvertiseAddress 192.168.1.10
```

通过受控交互或秘密管理工具设置下列 PowerShell 变量，不把真实值写入脚本、命令历史或 `.env`。dbt token 必须与已部署服务的凭据一致，服务地址必须可从 Swarm 网络访问。

```powershell
.\infra\swarm\scripts\New-SwarmSecrets.ps1 `
  -DatabasePassword $databasePassword `
  -RedisPassword $redisPassword `
  -OllamaBaseUrl 'http://ollama-host:11434' `
  -DbtServiceBaseUrl 'http://dbt-host:8000' `
  -DbtServiceToken $dbtServiceToken `
  -MetricPlatformAdminPassword $platformAdminPassword
```

升级已有栈时追加 `-ReuseInfrastructureSecrets`，仅复用现有 `postgres-password` 与 `redis-password`，不覆盖其值；传入的数据库/Redis 密码必须与它们匹配。其他 secret 若已存在，脚本拒绝覆盖。后续轮换使用新的版本化 secret 名，并明确更新 `stack.yml`。

构建并推送四个镜像。Agent 与指标平台不互相注入公开地址，两者独立连接 dbt-service。

```powershell
.\infra\swarm\scripts\Build-And-Push.ps1 `
  -LocalRegistry '192.168.1.10:5000' -ImageTag release-v3
```

配置 Agent 项目的规范 repository、PREVIEW/PRODUCTION binding 与 configVersion，并确认 dbt-service 对应绑定可用后，才开启开发能力。`.env.example` 只作值示例，部署脚本不会自动加载它。

```powershell
$env:DATA_AGENT_GIT_ENABLED = 'true'
$env:DATA_AGENT_DBT_ENABLED = 'true'
.\infra\swarm\scripts\Deploy-SwarmStack.ps1 `
  -LocalRegistry '192.168.1.10:5000' -ImageTag release-v3
```

要求至少两个 Ready 节点时追加 `-RequireMultipleNodes`。部署后核对数据库初始化任务、API 健康及三端新协议预检，再开放写入。统一验收说明见[指标构建协议部署与验收](../verification/README.md)。

## 运行边界

- PostgreSQL 与 Redis 固定到 `data-agent.stateful=true` 节点，单节点验证不具备主机故障容错。
- Agent 默认单副本，避免本地 Git 草稿在请求跨副本时丢失。容器更换后只保证已 push 的内容可恢复；本配置不提供未提交草稿持久化或多副本工作区路由。
- API 更新采用 `stop-first`，失败时暂停，避免迁移后自动回滚旧二进制或旧新发布者并行。恢复时先停写，再选择前向修复或匹配的备份，不直接把新版数据交给旧程序。
- 本静态校验不等于真实 Swarm 部署、Git 凭据验证或生产切换演练。
