# Agent Workspace

`agent-root` is the integration workspace for two independently versioned products:

| Project | Responsibility |
| --- | --- |
| [Data Agent](data-agent/) | Conversational data analysis, agent sessions and execution, authentication and tenancy, data-source connections, scheduling, and the primary user interface. |
| [Metric Platform](metric-platform/) | Governed data sources, datasets, fields, dimensions, metrics, relationships, semantic SQL compilation, metric queries, and the metric-management console. |

Both projects are Git submodules with independent builds and release lifecycles. The root POM must not become the parent of either product.

## Workspace layout

| Path | Purpose |
| --- | --- |
| `data-agent/` | Data Agent product repository. |
| `metric-platform/` | Metric Platform product repository and published OpenAPI contract. |
| `.run/` | Shared IntelliJ IDEA launch configurations for both backends. |
| `infra/compose/` | Local PostgreSQL and Redis dependencies shared by the applications. |
| `infra/data-agent/` | Data Agent migration and database fixtures. |
| `infra/swarm/` | Docker Swarm packaging and deployment assets. |
| `docs/` | Durable cross-product architecture, operations, and migration documents. |
| `tmp/` | Disposable diagnostics and generated scratch material. |

## Prerequisites

- Git with submodule support
- JDK 21 and Maven
- Node.js and npm
- Docker Desktop
- Ollama with `qwen3.5:9b` when running Data Agent conversations locally

## Get started

Clone the workspace and initialize the submodules:

```powershell
git clone --recurse-submodules https://github.com/823338779/agent-root.git
Set-Location agent-root
```

For an existing checkout:

```powershell
git submodule update --init --recursive
```

Start the local PostgreSQL and Redis dependencies. This Compose project creates both the `data_agent` and `metric_platform` databases with settings that match the applications' default local configuration:

```powershell
docker compose -f .\infra\compose\data-agent.yml up -d
```

Build the backend reactors independently:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -B -DskipTests package
mvn -f .\metric-platform\pom.xml -B -DskipTests package
```

The current root reactor is not a supported build entry point: it loads duplicate `com.datagent:data-agent:0.1.0-SNAPSHOT` coordinates. Use the independent builds above until the root reactor layout is corrected.

Open the root directory in IntelliJ IDEA and use the launch configurations in [`.run/`](.run/):

- `MetricPlatformApplication` starts Metric Platform on port `8090`.
- `DataAgentApplication` starts Data Agent with the `local` profile on port `8080`.

Start the frontends in separate terminals:

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

The Vite development servers proxy `/api` requests to their corresponding backend.

## Work in the owning repository

Product code belongs in the submodule that owns the behavior. When Data Agent needs a new semantic-layer capability, implement and publish the compatible Metric Platform API first, then update the Data Agent integration.

Commit product changes inside the owning submodule. Update and commit the root Git link only when the workspace should pin that submodule revision.

The root repository defaults to hiding submodule worktree changes. Inspect them explicitly when needed:

```powershell
git status --ignore-submodules=none
git diff --ignore-submodules=none
```

## Infrastructure and fixture documentation

- [Docker Swarm deployment](infra/swarm/README.md)
- [Data Agent control-plane fixture](infra/data-agent/postgres-control-plane-fixture/README.md)
- [Data Agent legacy-session migration fixture](infra/data-agent/postgres-session-migration-fixture/README.md)

Read the relevant fixture documentation before running any reset, reconciliation, or destructive migration verification.
