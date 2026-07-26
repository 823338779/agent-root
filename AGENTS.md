# Agent Workspace Instructions

This repository orchestrates two independent Git submodules. Keep product ownership, repository history, and build boundaries explicit.

## Work routing

| Scope | Owning path | Includes |
| --- | --- | --- |
| Data Agent | `data-agent/` | Agent sessions and execution, API and UI, authentication and tenancy, scheduling, connectors, SQL analysis, and Agent-specific evaluation. |
| Metric Platform | `metric-platform/` | Data sources, datasets, fields, dimensions, metrics, relationships, semantic SQL and queries, OpenAPI, and the management console. |
| Workspace integration | Root | Submodule revisions, aggregate builds, shared local infrastructure, deployment assets, and cross-product documentation. |

Do not place product code in the root repository. When a Data Agent requirement needs a Metric Platform capability, make the API-compatible change in `metric-platform/` and consume it from `data-agent/`; never import implementation classes across submodules.

## Submodule workflow

- Make and verify product changes inside the owning submodule.
- Commit the product repository before updating its root Git link.
- Update the root Git link only when the workspace intentionally pins the new revision.
- Do not add a root Maven reactor or parent POM. The two products have independent build graphs and must be verified separately.
- The root `.gitmodules` hides submodule changes by default. Use `git status --ignore-submodules=none` or `git diff --ignore-submodules=none` when reviewing them.

## Implementation rules

- Preserve existing architecture and choose the smallest change that satisfies the request.
- Add sufficient comments for new or non-obvious behavior, invariants, security boundaries, and operational constraints. Do not comment self-evident code.
- Do not add, delete, or modify test-related code unless the user explicitly requests it. Repository migration may update filesystem paths in harness scripts but must not change assertions or expected behavior.
- Keep public Metric Platform behavior aligned with `metric-platform/api/openapi.yaml`.
- Never commit real credentials, tokens, connection strings, enterprise data, or generated secrets.

## Documentation and generated material

- Put durable cross-product architecture, operational guidance, migration notes, and reports in `docs/`.
- Put all Codex discussion records, implementation notes, research summaries, and review reports in `docs/codex/`; do not keep them in either product submodule.
- Keep product-specific documentation in its owning submodule.
- Put disposable output and diagnostics in `tmp/`, under a descriptive task directory.
- Keep shared IntelliJ IDEA run configurations in `.run/`.
- Do not place temporary or generated material in product source directories.

## Verification

Run the narrowest relevant verification in the changed repository first. The supported backend package checks are:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -B -DskipTests package
mvn -f .\metric-platform\pom.xml -B -DskipTests package
```

Before reporting completion, inspect the root and affected submodule statuses separately so unrelated user changes are not included.
