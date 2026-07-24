# Docker Swarm deployment

This directory packages Data Agent, Metric Platform, both frontends, PostgreSQL, and Redis for a Docker Swarm deployment backed by a local registry.

## Contents

| Path | Purpose |
| --- | --- |
| `stack.yml` | Application and stateful-service stack. |
| `registry-stack.yml` | Local image registry. |
| `docker/` | Backend and frontend image definitions. |
| `nginx/` | Frontend reverse-proxy configuration. |
| `scripts/` | Swarm initialization, secret creation, image publishing, and deployment. |
| `.env.example` | Registry address and image-tag example. |

## Preconditions

- Run commands from the `agent-root` workspace root.
- Docker must be available on every node.
- Use the manager's LAN address, not `127.0.0.1`, for a multi-node registry.
- Configure every Swarm node to trust the local registry before pushing or deploying images.
- Ensure the configured Ollama URL is reachable from Swarm services.

## Deployment sequence

Initialize the Swarm manager, label its stateful node, and deploy the local registry:

```powershell
.\infra\swarm\scripts\Initialize-LocalSwarm.ps1 -ManagerAdvertiseAddress 192.168.1.10
```

Create the required Docker secrets. The script generates encryption keys in memory and refuses to overwrite an existing secret:

```powershell
.\infra\swarm\scripts\New-SwarmSecrets.ps1 `
  -DatabasePassword '<database-password>' `
  -RedisPassword '<redis-password>' `
  -OllamaBaseUrl 'http://<ollama-host>:11434' `
  -DataAgentAdminPassword '<data-agent-admin-password>' `
  -MetricPlatformAdminPassword '<metric-platform-admin-password>'
```

Build and push all four application images:

```powershell
.\infra\swarm\scripts\Build-And-Push.ps1 -LocalRegistry '192.168.1.10:5000' -ImageTag dev
```

Deploy the application stack:

```powershell
.\infra\swarm\scripts\Deploy-SwarmStack.ps1 -LocalRegistry '192.168.1.10:5000' -ImageTag dev
```

Add `-RequireMultipleNodes` when the deployment must fail unless at least two nodes are ready.

## Operational boundaries

- PostgreSQL and Redis are constrained to nodes labeled `data-agent.stateful=true`.
- Application replicas are not pinned to the stateful node.
- A single-node deployment is suitable for local validation but is not host-failure tolerant.
- Docker secrets are immutable in this workflow. Rotate them by creating versioned names and deliberately updating the stack.
- Never place real secret values in `.env` files or source control.
