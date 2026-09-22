# Agent 工作区

`agent-root` 是三个独立版本化产品的集成工作区：

| 项目 | 职责 |
| --- | --- |
| [Data Agent](data-agent/) | 对话式数据分析、Agent 会话与执行、身份认证与租户、数据源连接、调度，以及主要用户界面。 |
| [Data Agent V2](data-agent-v2/) | 重建后的 Data Agent 产品及其契约；本次工作中的 `data-agent/` 仅供参考。 |
| [Metric Platform](metric-platform/) | 受治理的数据源、数据集、字段、维度、指标、关系、语义 SQL 编译、指标查询，以及指标管理控制台。 |

三个项目均为 Git 子模块，拥有独立的构建与发布生命周期。根目录 POM 不得成为任一产品的父 POM。

## 工作区结构

| 路径 | 用途 |
| --- | --- |
| `data-agent/` | Data Agent 产品仓库。 |
| `data-agent-v2/` | 重建后的 Data Agent 产品仓库及其契约；本次工作中的 `data-agent/` 仅供参考。 |
| `metric-platform/` | Metric Platform 产品仓库及其对外发布的 OpenAPI 契约。 |
| `.run/` | 两个后端共用的 IntelliJ IDEA 启动配置。 |
| `infra/docker/` | 共用镜像定义和反向代理配置。 |
| `infra/compose/` | 仅本地依赖及完整多服务 Docker Compose 部署。 |
| `infra/data-agent/` | Data Agent 迁移与数据库固件。 |
| `infra/swarm/` | Docker Swarm 打包和部署资源。 |
| `docs/codex/` | Codex 讨论、调研、评审和实现记录。 |
| `docs/` | 其他长期维护的跨产品架构、运维和迁移文档。 |
| `tmp/` | 可随时丢弃的诊断和临时生成文件。 |

## 环境要求

- 支持子模块的 Git
- JDK 21 和 Maven
- Node.js 和 npm
- Docker Desktop
- 本地运行 Data Agent 对话时，需要 Ollama 及 `qwen3.5:9b` 模型

## 组件访问信息

下表中的账号和密码是仓库内置的**本地开发默认值**，以明文列出便于本地联调。它们不适用于生产环境，也不要在这里记录生产账号、令牌或连接串。完整 Compose 栈可通过 `infra/compose/.env` 覆盖这些默认值。

### 完整 Compose 栈

| 组件 | 宿主机访问地址 | 容器内访问地址 | 账号 | 密码 | 说明 |
| --- | --- | --- | --- | --- | --- |
| Data Agent Web/API | `http://localhost:8080` | `http://data-agent-api:8080` | `admin` | `admin` | Web 入口通过 `/api` 将请求反向代理到内部 API；容器内健康检查地址为 `http://data-agent-api:8080/actuator/health`。 |
| Metric Platform Web/API | `http://localhost:8090` | `http://metric-platform-api:8090` | `admin` | `admin` | Web 入口通过 `/api` 将请求反向代理到内部 API；容器内健康检查地址为 `http://metric-platform-api:8090/actuator/health`。 |
| PostgreSQL（Data Agent 数据库） | `jdbc:postgresql://localhost:5432/data_agent` | `jdbc:postgresql://postgres:5432/data_agent` | `data_agent` | `data_agent_local_dev` | 数据库名：`data_agent`。 |
| PostgreSQL（Metric Platform 数据库） | `jdbc:postgresql://localhost:5432/metric_platform` | `jdbc:postgresql://postgres:5432/metric_platform` | `data_agent` | `data_agent_local_dev` | 数据库名：`metric_platform`。 |
| Redis | `localhost:6379` | `redis:6379` | `default` | `redis_local_dev` | 用于身份令牌状态和完整栈中的集群事件。 |
| Ollama | `http://localhost:11434` | `http://host.docker.internal:11434` | 无 | 无 | 默认模型为 `qwen3.5:9b`；Ollama 运行在宿主机，不由 Compose 创建。 |

Compose 默认值及对应覆盖项：

| 用途 | 默认值 | `infra/compose/.env` 配置项 |
| --- | --- | --- |
| PostgreSQL 密码 | `data_agent_local_dev` | `POSTGRES_PASSWORD` |
| Redis 密码 | `redis_local_dev` | `REDIS_PASSWORD` |
| Data Agent 登录密码 | `admin` | `DATA_AGENT_ADMIN_PASSWORD` |
| Metric Platform 登录密码 | `admin` | `METRIC_PLATFORM_ADMIN_PASSWORD` |
| Ollama 地址 | `http://host.docker.internal:11434` | `OLLAMA_BASE_URL` |
| Data Agent 对外端口 | `8080` | `DATA_AGENT_PORT` |
| Metric Platform 对外端口 | `8090` | `METRIC_PLATFORM_PORT` |

PostgreSQL 的完整本地默认访问信息：

```text
主机：localhost
端口：5432
账号：data_agent
密码：data_agent_local_dev
Data Agent 数据库：data_agent
Metric Platform 数据库：metric_platform
Data Agent JDBC：jdbc:postgresql://localhost:5432/data_agent
Metric Platform JDBC：jdbc:postgresql://localhost:5432/metric_platform
```

可直接使用以下命令连接：

```powershell
$env:PGPASSWORD = 'data_agent_local_dev'
psql -h localhost -p 5432 -U data_agent -d data_agent
psql -h localhost -p 5432 -U data_agent -d metric_platform
```

### 宿主机开发模式

| 组件 | 默认访问地址 | 账号 | 密码 | 补充说明 |
| --- | --- | --- | --- | --- |
| Data Agent 后端 | `http://localhost:8080` | `admin` | `admin` | 使用 `local` Profile；连接本机 PostgreSQL、Metric Platform 和 Ollama。 |
| Data Agent 前端 | `http://127.0.0.1:5173` | `admin` | `admin` | Vite 将 `/api` 代理到 `http://127.0.0.1:8080`。 |
| Metric Platform 后端 | `http://localhost:8090` | `admin` | `admin` | 连接本机 PostgreSQL 和 Redis。 |
| Metric Platform 前端 | `http://localhost:5173` | `admin` | `admin` | Vite 将 `/api` 代理到 `http://localhost:8090`。 |

两个 Vite 前端默认都尝试使用端口 `5173`。同时启动时，后启动的实例会自动选择下一个可用端口，终端会显示最终地址。

## 快速开始

克隆工作区并初始化子模块：

```powershell
git clone --recurse-submodules https://github.com/823338779/agent-root.git
Set-Location agent-root
```

对于已有的工作区：

```powershell
git submodule update --init --recursive
```

首次运行先初始化仅限本机访问的 Forgejo 服务和 SSH 身份，再统一启动 PostgreSQL、Redis 和 Git。初始化会交互读取管理员密码，并创建私有仓库 `agent-admin/metrics`；此 Compose 项目还会创建 `data_agent`、`data_agent_v2` 和 `metric_platform` 数据库：

```powershell
.\infra\git\Initialize-GitService.ps1
docker compose -f .\infra\compose\compose.yml up -d
```

如需构建并启动完整容器化栈：

```powershell
docker compose -f .\infra\compose\compose.yml --profile full up -d --build
```

如需覆盖默认值，先将 `infra/compose/.env.example` 复制为 `infra/compose/.env` 并修改，然后执行：

```powershell
docker compose --env-file .\infra\compose\.env `
  -f .\infra\compose\compose.yml `
  --profile full up -d --build
```

更多端点和环境变量说明见 [Compose 部署指南](infra/compose/README.md)。
Forgejo Web 只监听 `http://127.0.0.1:3000`，SSH 默认只监听 `127.0.0.1:2222`，SQLite、仓库和 SSH 主机密钥使用外部持久卷；Agent V2 的连接配置见 [Forgejo Git 服务部署](infra/git/README.md)。

分别快速打包两个后端（以下命令会跳过测试）：

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -B -DskipTests package
mvn -f .\metric-platform\pom.xml -B -DskipTests package
```

根目录刻意不提供 Maven 聚合构建。两个产品拥有独立的依赖图，必须在各自仓库中构建。

在 IntelliJ IDEA 中打开根目录，并使用 [`.run/`](.run/) 中的启动配置：

- `MetricPlatformApplication`：在端口 `8090` 启动 Metric Platform。
- `DataAgentApplication`：使用 `local` Profile 在端口 `8080` 启动 Data Agent。

在不同终端中启动前端：

```powershell
Set-Location data-agent\frontend
npm ci
npm run dev
```

```powershell
Set-Location metric-platform\frontend
npm ci
npm run dev
```

Vite 开发服务器会将 `/api` 请求代理到各自对应的后端。

## 验证

从工作区根目录执行完整后端验证：

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -B verify
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml -B verify
mvn -f .\metric-platform\pom.xml -B verify
```

执行前端测试和生产构建：

```powershell
npm --prefix .\data-agent\frontend test
npm --prefix .\data-agent\frontend run build
npm --prefix .\metric-platform\frontend test
npm --prefix .\metric-platform\frontend run build
```

开发时先执行受影响模块的最小测试，只在变更跨越模块或产品边界时扩大到上述完整验证。

## 在归属仓库中工作

产品代码必须放在拥有对应能力的子模块中。当 Data Agent 需要新的语义层能力时，应先在 Metric Platform 中实现并发布兼容 API，再更新 Data Agent 集成。

仅当任务需要固定新的子模块版本时，才先在归属子模块内提交产品变更，再更新根仓库中的 Git 链接。未经明确要求，不要自行创建提交。

根仓库默认隐藏子模块工作区的变更。需要时请显式检查：

```powershell
git status --ignore-submodules=none
git diff --ignore-submodules=none
```

## 基础设施和固件文档

- [Docker Compose 部署](infra/compose/README.md)
- [Docker Swarm 部署](infra/swarm/README.md)
- [Data Agent 控制平面固件](infra/data-agent/postgres-control-plane-fixture/README.md)
- [Data Agent 旧会话迁移固件](infra/data-agent/postgres-session-migration-fixture/README.md)
- [Codex 工作文档规范](docs/codex/README.md)
- [CodeGraph 工作区索引](docs/codex/codegraph.md)

执行任何重置、对账或破坏性迁移验证之前，请先阅读相关固件文档。
