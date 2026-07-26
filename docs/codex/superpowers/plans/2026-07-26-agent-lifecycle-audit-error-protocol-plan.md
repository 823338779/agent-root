# Agent Lifecycle, Audit, and Error Protocol Types Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox checklists and must be completed in order.

**Goal:** Remove raw stable status, audit-action, and error-code strings from business logic while preserving database and HTTP contracts.

**Architecture:** Existing lifecycle enums remain authoritative and gain explicit wire conversion where needed. Audit actions and public error codes are represented by small domain-owned enums. String conversion occurs only in DAO, JSON, HTTP, and external-system adapters.

**Tech Stack:** Java 21, Spring MVC, Jackson, MyBatis-Plus, Maven, JUnit 5, AssertJ

## Global Constraints

- Execute after the authorization protocol plan.
- Reuse existing enums; do not create parallel status types.
- Preserve all persisted and HTTP wire values exactly.
- Do not change database schemas or migrations.
- Keep user-facing messages as ordinary text; only the stable machine-readable code becomes typed.
- Do not alter tests or create commits until the user explicitly authorizes those actions.

## Task 1: Inventory and strengthen existing lifecycle enums

**Files:**

- Inspect every file below and modify each file that still performs raw string conversion or comparison:
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/AgentRunStatus.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/AgentEventType.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/ai/ToolObservationStatus.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/ToolResultStatus.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/PendingInteractionStatus.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/PendingInteractionType.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/AgentRunPhase.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/InteractionMode.java`
  - `data-agent/backend/agent-scheduler/src/main/java/com/datagent/agent/scheduler/domain/TaskTypes.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/admin/EvaluationMutationStatusController.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/ai/MetricMutationCoordinator.java`
  - `data-agent/backend/agent-dao/src/main/java/com/datagent/agent/dao/mutation/PendingMetricMutationEntity.java`

- [ ] Inventory every raw comparison/write for values represented by these enums.
- [ ] Add `wireValue()` only where the external value is not already safely represented by `name()`.
- [ ] Add strict `fromWire(String)` conversion at persistence/JSON boundaries.
- [ ] Preserve existing casing and spelling.
- [ ] Do not change `TaskTypes` nested enum ownership; route all scheduler parsing through those existing enums.
- [ ] Introduce one domain enum for pending metric mutation states only if no existing enum owns `PENDING`, `APPROVED`, `EXECUTED`, and companion values; use it in the coordinator, entity adapter, and evaluation controller.

## Task 2: Type Run, Tool invocation, and pending-interaction persistence boundaries

**Files:**

- Modify:
  - `data-agent/backend/agent-core/src/main/java/com/datagent/agent/core/AgentSessionService.java`
  - `data-agent/backend/agent-dao/src/main/java/com/datagent/agent/dao/runtime/PendingInteractionEntity.java`
  - `data-agent/backend/agent-dao/src/main/java/com/datagent/agent/dao/runtime/PendingInteractionPersistenceService.java`
  - `data-agent/backend/agent-dao/src/main/java/com/datagent/agent/dao/runtime/ToolInvocationEntity.java`
  - `data-agent/backend/agent-dao/src/main/java/com/datagent/agent/dao/runtime/ToolInvocationPersistenceService.java`
  - `data-agent/backend/agent-dao/src/main/java/com/datagent/agent/dao/runtime/ToolInvocationMapper.java`
  - `data-agent/backend/agent-dao/src/main/java/com/datagent/agent/dao/runtime/AgentRunRuntimeEntity.java`
  - `data-agent/backend/agent-dao/src/main/java/com/datagent/agent/dao/mutation/PendingMetricMutationPersistenceService.java`
  - `data-agent/backend/agent-dao/src/main/java/com/datagent/agent/dao/mutation/PendingMetricMutationMapper.java`

- [ ] Keep entity columns as strings where MyBatis/database compatibility requires it.
- [ ] Add typed entity adapter accessors such as `statusValue()`/`setStatusValue(...)`; prevent services from directly comparing the raw column.
- [ ] Replace `"PENDING"`, `"RESOLVED"`, `"EXPIRED"`, Run status, and Tool status comparisons with enum values.
- [ ] Keep compare-and-set SQL predicates serialized through `wireValue()`.
- [ ] Reject unknown persisted values with an exception that identifies the entity and raw value.
- [ ] Confirm idempotent pending-interaction resolution semantics remain unchanged.

## Task 3: Introduce domain-owned audit action types

**Files:**

- Create:
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/AgentAuditAction.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/controlplane/TenantAuditEventType.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metricidentity/MetricIdentityAuditEventType.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/artifact/MetricArtifactAuditEventType.java`
- Modify:
  - `data-agent/backend/agent-core/src/main/java/com/datagent/agent/core/AgentSessionService.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/controlplane/TenantControlPlaneService.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metricidentity/MetricIdentityAuditWriter.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/artifact/MetricArtifactAuditWriter.java`
  - relevant DAO write adapters

- [ ] Put Run/session actions such as `SESSION_CREATED`, `RUN_COMPLETED`, `RUN_FAILED`, and `RUN_CANCELLED` in `AgentAuditAction`.
- [ ] Put tenant, identity, and artifact actions in their own domain enum rather than one global catch-all enum.
- [ ] Change audit-writer method signatures to accept their domain enum.
- [ ] Serialize only at the persistence adapter.
- [ ] Keep audit payload maps dynamic when their shape is genuinely event-specific.

## Task 4: Type stable public error codes

**Files:**

- Create:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/PendingInteractionErrorCode.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metricidentity/MetricIdentityErrorCode.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/artifact/ArtifactErrorCode.java`
  - `data-agent/backend/agent-scheduler/src/main/java/com/datagent/agent/scheduler/domain/SchedulerErrorCode.java`
- Modify:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/PendingInteractionOperationException.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/PendingInteractionController.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metricidentity/MetricIdentityOperationException.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/artifact/ArtifactOperationException.java`
  - `data-agent/backend/agent-scheduler/src/main/java/com/datagent/agent/scheduler/domain/SchedulerOperationException.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/ApiExceptionHandler.java`

- [ ] Inventory current stable error-code values for each exception family.
- [ ] Define one enum per domain with the exact current wire code.
- [ ] Change exception constructors/accessors to carry the enum.
- [ ] Convert to `wireValue()` only when building the HTTP error response.
- [ ] Keep the HTTP status and human-readable message independent from the code.
- [ ] Do not type ad hoc internal exception messages that are not consumed as protocol identifiers.

## Task 5: Update evaluation and ordinary consumers

**Files:**

- Modify production/evaluation Java consumers under:
  - `data-agent/backend/agent-evals/src/main/java`
  - `data-agent/backend/agent-api/src/main/java`
- Modify tests only after authorization.

- [ ] Replace status/audit/error branching with enum comparisons.
- [ ] At JSON fixture boundaries, deserialize to the domain enum or explicitly call `fromWire`.
- [ ] Preserve raw strings in third-party fixtures and historical payload samples.
- [ ] Ensure reports render `wireValue()` rather than Java enum names when the values differ.

## Task 6: Verify protocol compatibility

- [ ] Run authorized focused tests:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -pl :agent-model,:agent-core,:agent-dao,:agent-scheduler,:agent-api -am -Dtest=AgentSessionServiceTest,SpringAiAgentRunnerTest,AuditAndTenantPersistenceContractTest -Dsurefire.failIfNoSpecifiedTests=false test
```

- [ ] Search for remaining raw lifecycle/error comparisons:

```powershell
rg -n '"(PENDING|RESOLVED|EXPIRED|SESSION_CREATED|RUN_COMPLETED|RUN_FAILED|RUN_CANCELLED|INTERACTION_[A-Z_]+)"' data-agent/backend --glob '*.java'
```

- [ ] Classify every remaining match as a boundary contract assertion, enum declaration, or violation.
- [ ] Run the supported backend package check:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -B -DskipTests package
```

- [ ] Inspect root and `data-agent` statuses independently.
- [ ] If commit authorization is granted:

```powershell
git -C data-agent add backend
git -C data-agent commit -m "refactor: type lifecycle audit and error protocols"
```
