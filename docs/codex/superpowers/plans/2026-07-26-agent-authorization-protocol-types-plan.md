# Agent Authorization Protocol Types Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox checklists and must be completed in order.

**Goal:** Replace raw scope and Metric Platform capability strings with closed Java protocol types without changing authorization behavior.

**Architecture:** `MetricScope` and `MetricPlatformCapability` live in `agent-model`, the lowest shared module. Tool policy annotations, immutable Tool definitions, identity configuration, connector responses, and runtime authorization all convert to these types at their boundaries.

**Tech Stack:** Java 21, Jackson, Spring Boot configuration binding, Maven, JUnit 5, AssertJ

## Global Constraints

- Execute after the identifier-ownership plan.
- Preserve every existing scope and capability wire value exactly.
- Do not broaden any Tool's actor scopes, identity scopes, or platform capabilities.
- Parse unknown persisted or remote values strictly and produce an explicit boundary error.
- Do not alter tests or create commits until the user explicitly authorizes those actions.

## Task 1: Add the shared authorization protocol types

**Files:**

- Create:
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/MetricScope.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/MetricPlatformCapability.java`
- Modify, only after test authorization:
  - `data-agent/backend/agent-model/src/test/java/com/datagent/agent/core/runtime/MetricScopeTest.java`
  - `data-agent/backend/agent-model/src/test/java/com/datagent/agent/core/runtime/MetricPlatformCapabilityTest.java`

- [ ] Inventory current scope values from `@AgentToolPolicy`, `MetricIdentityProperties`, Skill snapshot construction, and eval fixtures.
- [ ] Define one enum constant per existing value, storing the exact external string in `wireValue`.
- [ ] Define `fromWire(String)` that rejects null, blank, and unknown values with a stable, actionable exception.
- [ ] Add Jackson `@JsonValue` and `@JsonCreator` only if these types cross JSON boundaries directly.
- [ ] Define the five existing platform capability values: `SEMANTIC_SEARCH`, `SEMANTIC_RESOLVE`, `MEMBER_SEARCH`, `VALIDATE`, and `EXECUTE`.
- [ ] Test round trips and unknown-value rejection.

The scope enum must cover this frozen inventory:

```java
METRIC_ROUTE("metric.route"),
METRIC_PREPARE("metric.prepare"),
METRIC_CATALOG_READ("metric.catalog.read"),
METRIC_MEMBER_READ("metric.member.read"),
METRIC_QUERY_VALIDATE("metric.query.validate"),
METRIC_QUERY_EXECUTE("metric.query.execute"),
METRIC_ADMIN_DATA_SOURCE_READ("metric.admin.data-source.read"),
METRIC_ADMIN_DATA_SOURCE_WRITE("metric.admin.data-source.write"),
METRIC_ADMIN_DATASET_READ("metric.admin.dataset.read"),
METRIC_ADMIN_DATASET_WRITE("metric.admin.dataset.write"),
METRIC_ADMIN_DEFINITION_READ("metric.admin.definition.read"),
METRIC_ADMIN_DEFINITION_WRITE("metric.admin.definition.write"),
METRIC_ADMIN_RELATIONSHIP_READ("metric.admin.relationship.read"),
METRIC_ADMIN_RELATIONSHIP_WRITE("metric.admin.relationship.write")
```

Both types expose the same boundary shape:

```java
String wireValue();
static MetricScope fromWire(String value);
static MetricPlatformCapability fromWire(String value);
```

## Task 2: Make Tool policy and Tool definitions typed

**Files:**

- Modify:
  - `data-agent/backend/agent-capabilities/pom.xml`
  - `data-agent/backend/agent-capabilities/src/main/java/com/datagent/agent/capabilities/AgentToolPolicy.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/ToolDefinition.java`
  - all Tool classes annotated with `@AgentToolPolicy`

- [ ] Add the one-way `agent-capabilities -> agent-model` dependency; confirm no dependency cycle.
- [ ] Change `AgentToolPolicy.scopes()` from `String[]` to `MetricScope[]`.
- [ ] Replace annotation literals with enum constants.
- [ ] Change `ToolDefinition.requiredActorScopes` and `requiredIdentityScopes` to immutable `Set<MetricScope>`.
- [ ] Change `requiredPlatformCapability` to an explicit optional typed value. Prefer `Optional<MetricPlatformCapability>` at access points while keeping the record constructor simple and non-null.
- [ ] Preserve `ToolDefinition` immutability and defensive copies.
- [ ] Compile `agent-model` and `agent-capabilities` before changing downstream modules:

The target core contract is:

```java
public record ToolDefinition(
        String name,
        String description,
        JsonSchemaDocument inputSchema,
        JsonSchemaDocument outputSchema,
        Set<MetricScope> requiredActorScopes,
        Set<MetricScope> requiredIdentityScopes,
        MetricPlatformCapability requiredPlatformCapability,
        boolean citeable) {
    public Optional<MetricPlatformCapability> platformCapability();
}
```

Use `null` only in the canonical constructor to represent “no platform capability”; callers consume
`platformCapability()`. Do not store `Optional` as a record component.

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -pl :agent-model,:agent-capabilities -am -DskipTests package
```

## Task 3: Type identity configuration and access checks

**Files:**

- Modify:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metricidentity/MetricIdentityProperties.java`
  - identity selection/access policy classes under `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metricidentity`
  - authorized tests under `data-agent/backend/agent-api/src/test/java/com/datagent/agent/api/metricidentity`

- [ ] Bind configured scopes into `Set<MetricScope>` rather than carrying strings into business logic.
- [ ] If Spring configuration binding cannot directly report a useful unknown-value error, bind raw values in a boundary DTO and convert once in `MetricIdentityProperties`.
- [ ] Change authorization predicates to compare enum members.
- [ ] Convert typed scopes back to `wireValue()` only when calling an external API or serializing an existing wire contract.
- [ ] Verify an unknown configured scope fails startup/configuration binding rather than silently reducing or expanding access.

## Task 4: Type the Metric Platform capability boundary

**Files:**

- Modify:
  - `data-agent/backend/agent-connectors/src/main/java/com/datagent/agent/connectors/MetricPlatformClient.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/read/MetricAnnotatedToolCatalog.java`
  - legacy Tool classes under `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool`
  - authorized connector tests

- [ ] Keep the remote JSON DTO compatible with the Metric Platform API.
- [ ] Convert remote capability strings to `MetricPlatformCapability` immediately after deserialization.
- [ ] Make catalog definitions and runtime capability checks use the enum.
- [ ] Replace the capability `switch` in `MetricAnnotatedToolCatalog` with Tool-owned typed policy data.
- [ ] Ensure an unknown server capability is observable and rejected; do not treat it as authorization.

## Task 5: Remove scope inference and string conversions from business logic

**Files:**

- Modify:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/ClasspathSkillRegistry.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/MetricAgentRunContextProvider.java`
  - authorization and Tool execution classes consuming `ToolDefinition`
  - evaluation catalog/harness classes under `data-agent/backend/agent-evals`

- [ ] Derive a Skill's effective required scopes by taking the union of its actual allowed `ToolDefinition` values.
- [ ] Remove prefix/regular-expression inference of scopes from Tool names.
- [ ] Preserve the immutable Run snapshot's existing serialized scope values by writing `MetricScope.wireValue()`.
- [ ] On historical snapshot read, parse existing strings with `MetricScope.fromWire`.
- [ ] Keep authorization denial semantics unchanged.

## Task 6: Verify least privilege and compatibility

- [ ] Run authorized focused tests:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -pl :agent-model,:agent-capabilities,:agent-connectors,:agent-api -am -Dtest=MetricScopeTest,MetricPlatformCapabilityTest,MetricIdentityPropertiesTest,MetricPlatformClientTest,MetricPlatformToolContractTest -Dsurefire.failIfNoSpecifiedTests=false test
```

- [ ] Search for remaining authorization literals:

```powershell
rg -n '"metric\.[a-z0-9._-]+"|"(SEMANTIC_SEARCH|SEMANTIC_RESOLVE|MEMBER_SEARCH|VALIDATE|EXECUTE)"' data-agent/backend --glob '*.java'
```

- [ ] Review each remaining match and allow only boundary contract tests or explicit wire serialization.
- [ ] Run the supported backend package check:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -B -DskipTests package
```

- [ ] Inspect root and `data-agent` statuses independently.
- [ ] If commit authorization is granted, commit only this plan's changes:

```powershell
git -C data-agent add backend
git -C data-agent commit -m "refactor: type agent authorization protocol values"
```
