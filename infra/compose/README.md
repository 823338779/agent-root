# Docker Compose deployment

The root Compose project is the supported local deployment entry point for the workspace. It owns the shared PostgreSQL and Redis services and can also build and run both APIs and both web applications.

## Dependency-only development

Run infrastructure while starting Java and Vite from the host:

```powershell
docker compose -f .\infra\compose\compose.yml up -d
```

This starts PostgreSQL, creates the `data_agent` and `metric_platform` databases, and starts Redis.

## Complete local stack

Optionally copy `infra/compose/.env.example` to `infra/compose/.env` and adjust local values. Then build and start all services:

```powershell
docker compose --env-file .\infra\compose\.env `
  -f .\infra\compose\compose.yml `
  --profile full up -d --build
```

If no `.env` file is supplied, Compose uses the development defaults declared in the file.

| Endpoint | Service |
| --- | --- |
| `http://localhost:8080` | Data Agent web application and `/api` proxy |
| `http://localhost:8090` | Metric Platform web application and `/api` proxy |
| `localhost:5432` | Shared PostgreSQL |
| `localhost:6379` | Shared Redis |

Data Agent reaches Ollama through `host.docker.internal:11434` by default. Override `OLLAMA_BASE_URL` when Ollama runs elsewhere.

Stop the stack without deleting data:

```powershell
docker compose -f .\infra\compose\compose.yml --profile full down
```

Add `--volumes` only when the PostgreSQL and Redis data should be deliberately removed.
