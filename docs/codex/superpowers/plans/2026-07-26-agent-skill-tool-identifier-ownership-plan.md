# Agent Skill and Tool Identifier Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox checklists and must be completed in order.

**Goal:** Give every Skill and Tool wire name one Java owner while preserving every existing external value.

**Architecture:** Skill names are centralized in `AgentSkillConstants`. Tool names move to the concrete Tool class that implements the wire operation. Registries and catalogs assemble inventories from those owners instead of redeclaring strings.

**Tech Stack:** Java 21, Spring Boot, Spring AI Tool annotations, Maven, JUnit 5, AssertJ

## Global Constraints

- Work only in `data-agent/backend`; do not modify `metric-platform`, frontend code, migrations, or raw third-party fixtures.
- Preserve all current wire names exactly.
- External `SKILL.md` front matter may retain literal names.
- Only a dedicated wire-contract test may directly assert production Skill/Tool literals.
- Do not alter tests or create commits until the user explicitly authorizes those actions.
- Preserve unrelated worktree changes.

## Task 1: Freeze the wire-name compatibility surface

**Files:**

- Modify, only after test authorization: `data-agent/backend/agent-api/src/test/java/com/datagent/agent/api/ai/MetricSkillContractTest.java`
- Create, only after test authorization: `data-agent/backend/agent-api/src/test/java/com/datagent/agent/api/ai/AgentProtocolWireNameContractTest.java`

- [ ] Record the seven approved Skill wire values in one parameterized contract test.
- [ ] Record every currently exposed Tool wire value from annotated and legacy catalogs.
- [ ] Assert uniqueness of Skill names and Tool names.
- [ ] Keep literal production values confined to this test; use owner constants in all other tests.
- [ ] Run the new contract test and confirm it passes before refactoring:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -pl :agent-api -am -Dtest=AgentProtocolWireNameContractTest -Dsurefire.failIfNoSpecifiedTests=false test
```

## Task 2: Replace `AgentSkillDefinitions` with `AgentSkillConstants`

**Files:**

- Create: `data-agent/backend/agent-capabilities/src/main/java/com/datagent/agent/capabilities/AgentSkillConstants.java`
- Delete: `data-agent/backend/agent-capabilities/src/main/java/com/datagent/agent/capabilities/AgentSkillDefinitions.java`
- Modify all Java references under:
  - `data-agent/backend/agent-api/src/main/java`
  - `data-agent/backend/agent-evals/src/main/java`
  - authorized test sources under `data-agent/backend`

- [ ] Define exactly seven `public static final String` fields in `AgentSkillConstants`.
- [ ] Define an immutable, deterministic `ALL` inventory from those fields.
- [ ] Add a private constructor that prevents instantiation.
- [ ] Replace imports and references to `AgentSkillDefinitions`.
- [ ] Remove local aliases such as `ANALYSIS_SKILL_ID`; reference `AgentSkillConstants` directly.
- [ ] Verify no production Java code contains a literal approved Skill name:

```powershell
rg -n '"(metric-platform-(analysis|exploration|data-source-management|dataset-management|semantic-definition-management|relationship-management)|scheduled-task-management)"' data-agent/backend --glob '*.java' --glob '!**/AgentProtocolWireNameContractTest.java'
```

Expected result: no matches outside explicitly documented resource-validation fixtures.

The target public inventory is:

```java
public final class AgentSkillConstants {
    public static final String METRIC_PLATFORM_ANALYSIS = "metric-platform-analysis";
    public static final String METRIC_PLATFORM_EXPLORATION = "metric-platform-exploration";
    public static final String METRIC_PLATFORM_DATA_SOURCE_MANAGEMENT =
            "metric-platform-data-source-management";
    public static final String METRIC_PLATFORM_DATASET_MANAGEMENT =
            "metric-platform-dataset-management";
    public static final String METRIC_PLATFORM_SEMANTIC_DEFINITION_MANAGEMENT =
            "metric-platform-semantic-definition-management";
    public static final String METRIC_PLATFORM_RELATIONSHIP_MANAGEMENT =
            "metric-platform-relationship-management";
    public static final String SCHEDULED_TASK_MANAGEMENT = "scheduled-task-management";
    public static final Set<String> ALL = Set.of(
            METRIC_PLATFORM_ANALYSIS,
            METRIC_PLATFORM_EXPLORATION,
            METRIC_PLATFORM_DATA_SOURCE_MANAGEMENT,
            METRIC_PLATFORM_DATASET_MANAGEMENT,
            METRIC_PLATFORM_SEMANTIC_DEFINITION_MANAGEMENT,
            METRIC_PLATFORM_RELATIONSHIP_MANAGEMENT,
            SCHEDULED_TASK_MANAGEMENT);
}
```

## Task 3: Move read and analysis Tool names to their implementation owners

**Files:**

- Modify:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/read/MetricCatalogTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/read/MetricAnalysisTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/MetricCatalogSearchTool.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/MetricContextResolveTool.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/MetricMemberSearchTool.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/MetricQueryValidateTool.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/MetricQueryExecuteTool.java`

- [ ] Add operation-specific constants to multi-method classes, for example `SEMANTIC_CATALOG_QUERY_NAME`, `DIMENSION_MEMBERS_QUERY_NAME`, `QUERY_VALIDATE_NAME`, and `QUERY_EXECUTE_NAME`.
- [ ] Add `NAME` to each one-operation legacy Tool class.
- [ ] Keep the two legacy-only values `metric_catalog_search` and `metric_member_search` owned by their legacy classes; do not alias them to newer annotated operations.
- [ ] Where `MetricAnalysisTools` delegates validation/execution to handler classes, reference the handler owner constants rather than duplicating the value.
- [ ] Change every `@Tool(name = ...)`, definition constructor, metric tag, persistence query, and comparison to use the owner constant.
- [ ] Keep descriptions close to their Tool method; concatenate owner constants when one description references another Tool.

## Task 4: Move management and scheduler Tool names to their implementation owners

**Files:**

- Modify:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/admin/MetricDataSourceTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/admin/MetricDatasetTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/admin/MetricSemanticDefinitionTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/admin/MetricRelationshipTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/scheduler/tool/ScheduledTaskTools.java`

- [ ] Add one constant per exposed operation using the existing wire value unchanged.
- [ ] Name constants by action (`LIST_NAME`, `GET_NAME`, `CREATE_NAME`, `UPDATE_NAME`, `DELETE_NAME`, `TRIGGER_NAME`) where unambiguous within the class.
- [ ] Update annotations and local branching to use the owner constants.
- [ ] Do not create a second central management-Tool constant class.

## Task 5: Rebuild inventories from Tool owners and remove duplicate ownership

**Files:**

- Modify:
  - `data-agent/backend/agent-capabilities/src/main/java/com/datagent/agent/capabilities/AgentToolDefinitions.java`
  - `data-agent/backend/agent-capabilities/src/main/java/com/datagent/agent/capabilities/AgentToolDefinition.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/read/MetricAnnotatedToolCatalog.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/MetricPlatformToolCatalog.java`
  - relevant production and evaluation catalog consumers
- Delete `AgentToolDefinitions` if, after migration, it has no responsibility other than duplicated names/descriptions.

- [ ] Replace name-based `switch` statements and raw equality checks with owner constants.
- [ ] Assemble any required `ALL`/`BY_NAME` inventory from definitions exported by actual Tool owners.
- [ ] Fail fast on duplicate Tool names when assembling a catalog.
- [ ] Keep `AgentToolDefinition` only if it still models a real cross-module definition; do not retain it solely as a constant container.
- [ ] Replace production-name literals in eval modules with owner constants.
- [ ] Replace production-name literals in ordinary tests with owner constants or neutral fixture names.

## Task 6: Verify identifier ownership

- [ ] Search for forbidden duplicate literals:

```powershell
rg -n '"metric_[a-z0-9_]+"|"scheduled_task_[a-z0-9_]+"' data-agent/backend --glob '*.java' --glob '!**/AgentProtocolWireNameContractTest.java'
```

- [ ] Review each match. Allow user-facing examples and deliberately dynamic data only when they are not used for lookup, comparison, branching, persistence, authorization, or cross-module communication.
- [ ] Run authorized focused tests:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -pl :agent-api,:agent-evals -am -Dtest=AgentProtocolWireNameContractTest,MetricSkillContractTest,ProductionComponentCatalogTest -Dsurefire.failIfNoSpecifiedTests=false test
```

- [ ] Run the supported backend package check:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -B -DskipTests package
```

- [ ] Inspect `git status --short --ignore-submodules=none` at the workspace root and `git -C data-agent status --short` before reporting.
- [ ] If commit authorization is granted, commit only this plan's product changes with:

```powershell
git -C data-agent add backend
git -C data-agent commit -m "refactor: assign skill and tool identifier ownership"
```
