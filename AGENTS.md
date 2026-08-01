# Agent Workspace Instructions

This repository orchestrates two independently versioned product submodules. Keep ownership, repository history, and build boundaries explicit.

## Scope and ownership

- This file governs workspace-wide routing, cross-repository boundaries, shared infrastructure, and root-repository changes.
- `data-agent/` owns Agent sessions and execution, its API and UI, authentication and tenancy, scheduling, connectors, SQL analysis, and Agent-specific evaluation.
- `metric-platform/` owns data sources, datasets, fields, dimensions, metrics, relationships, semantic SQL and queries, its OpenAPI contract, and its management console.
- The root owns submodule revisions, shared local infrastructure, deployment assets, aggregate verification scripts, and cross-product documentation. Do not place product code here.
- Inside a submodule, also follow its nearest `AGENTS.md`; product-specific rules there take precedence on the same topic.

## Cross-repository workflow

- Keep changes in the narrowest owning repository; a cross-product request does not authorize unrelated changes in both submodules.
- When Data Agent needs a Metric Platform capability, implement an API-compatible change in `metric-platform/` and consume the published HTTP API from `data-agent/`. Never import implementation classes across submodules.
- Keep both products independently buildable. Do not add a root Maven reactor or parent POM.
- Do not create commits unless the user asks. If the task includes pinning a new submodule revision, commit the product repository first and update the root Git link only when the workspace intentionally adopts that revision.
- Root `.gitmodules` hides submodule changes by default. Review with `git status --ignore-submodules=none` and `git diff --ignore-submodules=none`.

## Change rules

- Preserve existing architecture and make the smallest change that satisfies the request.
- Do not delete, weaken, or rewrite tests merely to make a change pass. Bug fixes and new behavior may add the smallest relevant regression tests; broad test-suite changes require explicit user approval.
- Keep public Metric Platform behavior aligned with `metric-platform/api/openapi.yaml`.
- Never commit real credentials, tokens, connection strings, enterprise data, or generated secrets.
- Prefer existing dependencies and conventions. Add a dependency only in the owning submodule when it materially reduces complexity or boilerplate, has no simpler local alternative, and has acceptable maintenance, license, security, footprint, and compatibility characteristics.
- Use design patterns only when they reduce current complexity, match the existing architecture, or address a concrete variation point. Do not add abstractions for hypothetical needs.

## Artifact placement

- Put durable cross-product documentation in `docs/`, and product-specific documentation in its owning submodule.
- Create records under `docs/codex/` only when the user requests a durable record or the result will remain materially useful; do not generate routine task notes.
- Put disposable diagnostics in `tmp/`, shared IntelliJ run configurations in `.run/`, and no temporary or generated material in product source directories.

## Verification

- Use the supported commands documented in `README.md` and the owning submodule README; keep command documentation there rather than duplicating it here.
- Run the narrowest relevant test first, then broader build verification when the change or risk crosses module boundaries.
- Before reporting completion, inspect the root and every affected submodule separately so unrelated user changes are not included.

## 重要
- 任何时候都不用脱敏