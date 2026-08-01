# Agent Workspace Instructions

This repository orchestrates two independent Git submodules. Keep product ownership, repository history, and build boundaries explicit.

## Instruction scope

- This file governs workspace-wide routing, cross-repository boundaries, shared infrastructure, and root-repository changes.
- When working inside a submodule, also read its nearest `AGENTS.md`; product-specific rules there supplement this file and take precedence on the same topic.
- Keep changes in the narrowest owning repository. A cross-product request does not authorize unrelated changes in both submodules.

## Work routing

| Scope | Owning path | Includes |
| --- | --- | --- |
| Data Agent | `data-agent/` | Agent sessions and execution, API and UI, authentication and tenancy, scheduling, connectors, SQL analysis, and Agent-specific evaluation. |
| Metric Platform | `metric-platform/` | Data sources, datasets, fields, dimensions, metrics, relationships, semantic SQL and queries, OpenAPI, and the management console. |
| Workspace integration | Root | Submodule revisions, orchestration and aggregate verification scripts, shared local infrastructure, deployment assets, and cross-product documentation. |

Do not place product code in the root repository. When a Data Agent requirement needs a Metric Platform capability, make the API-compatible change in `metric-platform/` and consume it from `data-agent/`; never import implementation classes across submodules.

## Submodule workflow

- Make and verify product changes inside the owning submodule.
- If the task explicitly includes pinning a new submodule revision, commit the product repository before updating its root Git link. Do not create commits unless the user asks for them.
- Update the root Git link only when the workspace intentionally pins the new revision.
- Do not add a root Maven reactor or parent POM. The two products have independent build graphs and must be verified separately.
- The root `.gitmodules` hides submodule changes by default. Use `git status --ignore-submodules=none` or `git diff --ignore-submodules=none` when reviewing them.

## Implementation rules

- Preserve existing architecture and choose the smallest change that satisfies the request.
- Add sufficient comments for new or non-obvious behavior, invariants, security boundaries, and operational constraints. Do not comment self-evident code.
- Do not delete, weaken, or rewrite existing tests merely to make a change pass. Bug fixes and new behavior may add the smallest relevant regression tests; broad test-suite changes require explicit user approval. Repository migration may update filesystem paths in harness scripts but must not change assertions or expected behavior.
- Keep public Metric Platform behavior aligned with `metric-platform/api/openapi.yaml`.
- Never commit real credentials, tokens, connection strings, enterprise data, or generated secrets.
- Prefer existing dependencies and project conventions. Introduce a new dependency only in the owning submodule, and only when it materially reduces complexity or boilerplate without a simpler local solution; check maintenance status, license, security risk, footprint, and compatibility first.
- Libraries such as Lombok, Redisson, and MyBatis-Plus are acceptable candidates when they meet those criteria, but they are not default choices.
- Use a design pattern only when it reduces current complexity, matches the existing architecture, or addresses a concrete variation point. Do not add abstraction for hypothetical future needs.

## Documentation and generated material

- Put durable cross-product architecture, operational guidance, migration notes, and reports in `docs/`.
- When the user requests a durable Codex record, or the work produces material that will remain useful, put discussion records, implementation notes, research summaries, and review reports in `docs/codex/`; do not create routine task notes by default or keep them in either product submodule.
- Keep product-specific documentation in its owning submodule.
- Put disposable output and diagnostics in `tmp/`, under a descriptive task directory.
- Keep shared IntelliJ IDEA run configurations in `.run/`.
- Do not place temporary or generated material in product source directories.

## Verification

Run the narrowest relevant verification in the changed repository first. For behavior changes, run the smallest relevant existing tests before broader build checks.

The supported backend packaging checks below skip tests and should not be described as complete test verification:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -B -DskipTests package
mvn -f .\metric-platform\pom.xml -B -DskipTests package
```

The supported frontend production build checks are:

```powershell
npm --prefix .\data-agent\frontend run build
npm --prefix .\metric-platform\frontend run build
```

Before reporting completion, inspect the root and affected submodule statuses separately so unrelated user changes are not included.

