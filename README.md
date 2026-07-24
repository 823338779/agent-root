# Agent Workspace

This workspace combines two independent Git submodules that provide a governed, conversational data-analysis experience:

| Project | Responsibility |
| --- | --- |
| [Data Agent](data-agent/) | Conversational data analysis: sessions and execution, authentication and tenancy, data-source connections, SQL analysis, scheduled work, and the user-facing application. |
| [Metric Platform](metric-platform/) | Governed semantic layer: data sources, datasets, fields, dimensions, metrics, dataset relationships, semantic SQL compilation, metric queries, and its management console. |

The root Maven project aggregates both backend reactors for local compatibility checks. It is not the parent POM of either product; each submodule owns its source code, dependencies, and release lifecycle.

## Prerequisites

- Git with submodule support
- JDK 21 and Maven
- Node.js and npm for frontend work
- Docker Desktop for local PostgreSQL services and database fixtures

## Quick start

```powershell
git clone --recurse-submodules https://github.com/823338779/agent-root.git
Set-Location agent-root
mvn -B -DskipTests package
```

For an existing checkout with missing submodules:

```powershell
git submodule update --init --recursive
```

The root build checks the combined backend checkout. Build and verify the changed product in its own submodule as part of product development.

## Run locally

Open the root directory in IntelliJ IDEA and run either configuration stored in [`.run/`](.run/):

- `DataAgentApplication` starts Data Agent with the `local` Spring profile on port `8080`.
- `MetricPlatformApplication` starts Metric Platform on port `8090`.

For command-line frontend development, install the locked dependencies and start the relevant Vite application:

```powershell
Set-Location data-agent/frontend       # or metric-platform/frontend
npm ci
npm run dev
```

Metric Platform's local PostgreSQL service is defined in `metric-platform/docker-compose.yml` and is exposed on host port `5433`:

```powershell
Set-Location metric-platform
docker compose up -d postgres
```

Use each application's local configuration and the IDEA run configuration as the source of truth for backend startup settings.

## Workspace layout

| Path | Purpose |
| --- | --- |
| `data-agent/` | Data Agent submodule, including its backend and frontend. |
| `metric-platform/` | Metric Platform submodule, including its backend, frontend, and local PostgreSQL Compose definition. |
| `.run/` | Shared IntelliJ IDEA run configurations. |
| `infra/data-agent/` | Data Agent database migration and control-plane fixtures. |
| `docs/` | Durable workspace and cross-product documentation. |
| `tmp/` | Disposable scratch artifacts and diagnostics. |

## Working across products

Make product-code changes in the submodule that owns the behavior. When Data Agent requires a semantic-layer capability, implement the compatible Metric Platform change first, then update the integration point. Commit changes in the owning submodule before updating the root Git link when the workspace should pin that revision.

Do not make the root POM a parent of either submodule or add a Maven parent-child relationship between the products.

## Fixtures and documentation

The Data Agent fixtures use deterministic synthetic data. Read their instructions before running a reset or destructive verification command:

- [Tenant control-plane fixture](infra/data-agent/postgres-control-plane-fixture/README.md)
- [Legacy session migration fixture](infra/data-agent/postgres-session-migration-fixture/README.md)

For durable workspace material, use [docs/](docs/). The detailed [workspace build-governance guide](docs/workspace-governance/README.md) covers submodule and aggregate-build boundaries.
