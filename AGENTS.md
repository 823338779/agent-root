# Agent Workspace Root

This repository is the orchestration root for two independent projects. Treat
`data-agent/` and `metric-platform/` as Git submodules: make code changes in
the owning submodule and commit them there before updating the root gitlink.

## Repository routing

| Path | Responsibility | Route work here when it concerns |
| --- | --- | --- |
| `data-agent/` | Conversational data-agent product | Agent sessions and execution, backend services, frontend UI, authentication and tenancy, SQL analysis, data-source connections, and Agent-specific evaluation. |
| `metric-platform/` | Governed metric and semantic layer | Data sources, datasets, fields, dimensions, metrics, dataset relationships, semantic SQL compilation, metric queries, and the metric-management console. |
| Root (`pom.xml`, `.gitmodules`, `docs/`, `tmp/`) | Workspace integration | Submodule versions, cross-repository build orchestration, architecture and operational material that applies to both projects. |

## Cross-repository changes

- Keep ownership explicit. Change only the repository that owns the behavior.
- When Agent requirements require a Metric Platform capability, make the
  compatible Metric Platform change in `metric-platform/` and update the
  root's submodule reference after its commit is available.
- Do not make product-code changes directly in the root repository.

## Non-code artifacts

Codex-generated material that is not product code must be stored at the root,
never inside either submodule unless it is a source-controlled document that
belongs to that product.

- Put durable documentation, plans, migration notes, and reports in `docs/`.
- Put disposable scratch files, command output, and generated temporary files
  in `tmp/`.
- Use a descriptive subdirectory when the material belongs to a particular
  task, for example `docs/submodule-migration/` or `tmp/build-diagnostics/`.
- Do not place temporary files in project source directories or repository
  roots.

# Workspace Projects

Do not add, delete, or modify test-related code unless the user explicitly requests it. Repository-migration work may update filesystem paths in existing harness scripts, but must not change assertions or expected behavior.

This workspace contains two projects:

增量的代码和功能要写好充足的注释;

在迭代data-agent工程中可以要求metric-platform服务做改造来适配data-agent的需求。

## Data Agent

Data Agent is the main project in this repository. Its backend is located in `backend/` and its frontend is located in `frontend/`.

It provides the conversational data agent, including agent sessions and execution, authentication and tenant management, SQL analysis, data-source connections, and the primary user interface.

## Metric Platform

Metric Platform is an independent project registered as the `metric-platform/` Git submodule.

It manages governed data sources, datasets, fields, dimensions, metrics, dataset relationships, semantic SQL compilation, metric queries, and the Metric Platform management console.

