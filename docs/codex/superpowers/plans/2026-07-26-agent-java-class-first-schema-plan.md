# Agent Java Class First Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox checklists and must be completed in order.

**Goal:** Eliminate hand-built JSON Schema maps and generate model-visible schemas from Java input/output types while preserving the canonical schema contract.

**Architecture:** `ToolDefinition` carries a typed `JsonSchemaDocument`. A single `AgentJsonSchemaGenerator` adapter wraps Spring AI 2.0 `JsonSchemaGenerator` and owns generation, parsing, canonicalization, and Spring/Ollama serialization. Tool contracts come from records/classes and annotations.

**Tech Stack:** Java 21 records and sealed types, Jackson `JsonNode`, Spring AI 2.0 `JsonSchemaGenerator`, Swagger `@Schema`, Spring AI `@ToolParam`, Maven, JUnit 5, JSONAssert/Jackson

## Global Constraints

- Execute after identifier and authorization type plans.
- Preserve canonical input/output schemas unless a separately approved contract correction is required.
- Ban `Map<String, Object>` only for schema definition; retain maps for genuinely dynamic runtime/business JSON.
- Do not introduce a custom schema DSL.
- Reuse existing DTOs before creating new records.
- Do not alter tests or create commits until the user explicitly authorizes those actions.

## Task 1: Capture canonical schema compatibility

**Files:**

- Create, only after test authorization:
  - `data-agent/backend/agent-api/src/test/java/com/datagent/agent/api/ai/AgentToolSchemaCompatibilityTest.java`
  - `data-agent/backend/agent-api/src/test/resources/contracts/agent-tool-schemas.json`
- Modify, only after test authorization:
  - `data-agent/backend/agent-api/src/test/java/com/datagent/agent/api/metrictool/MetricPlatformToolContractTest.java`

- [ ] Export current input and output schemas for every Tool in deterministic Tool-name order.
- [ ] Canonicalize object-key ordering without reordering semantically ordered arrays such as `required` or enum values.
- [ ] Store a single reviewed baseline resource.
- [ ] Compare schemas structurally rather than as formatting-sensitive strings.
- [ ] Run the compatibility test before implementation and confirm the baseline represents current behavior.

## Task 2: Introduce the typed schema document and generator adapter

**Files:**

- Create:
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/JsonSchemaDocument.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/ai/AgentJsonSchemaGenerator.java`
- Modify:
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/ToolDefinition.java`
  - module POMs only where existing dependencies do not expose required Jackson/Spring AI APIs

- [ ] Implement `JsonSchemaDocument` as an immutable wrapper around a deep-copied Jackson `JsonNode`.
- [ ] Validate that the root is an object and expose deterministic JSON serialization; do not expose mutable nodes or maps.
- [ ] Provide an explicit empty/unspecified schema document for Tools that intentionally have no output contract.
- [ ] Change `ToolDefinition.inputSchema` and `outputSchema` from `Map<String, Object>` to `JsonSchemaDocument`.
- [ ] Implement `AgentJsonSchemaGenerator.forType(Type)`.
- [ ] Implement `AgentJsonSchemaGenerator.forMethodInput(Method)`.
- [ ] Implement one adapter method for already Spring-generated callback schema JSON; parsing must end in `JsonSchemaDocument`, never a map.
- [ ] Centralize canonicalization and Spring/Ollama JSON serialization in the adapter.

The target APIs are:

```java
public final class JsonSchemaDocument {
    public static JsonSchemaDocument of(JsonNode schema);
    public static JsonSchemaDocument unspecified();
    public JsonNode node();
    public String canonicalJson();
}

public final class AgentJsonSchemaGenerator {
    public JsonSchemaDocument forType(Type type);
    public JsonSchemaDocument forMethodInput(Method method);
    public JsonSchemaDocument fromGeneratedJson(String schemaJson);
    public String toModelJson(JsonSchemaDocument schema);
}
```

`node()` returns a deep copy. `unspecified()` has one documented serialization shared by every
consumer; callers must not substitute `Map.of()`.

## Task 3: Model read and analysis Tool contracts as Java types

**Files:**

- Modify/reuse:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/MetricToolArguments.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/MetricQuerySpec.java`
  - read/analysis argument and result DTOs under `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/read/MetricCatalogTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/read/MetricAnalysisTools.java`

- [ ] Map each current schema property to a Java record/class field.
- [ ] Use UUID and time types where the wire formatter preserves the existing string shape.
- [ ] Use enums for closed values.
- [ ] Use `@Schema`, `@ToolParam`, Jackson naming, and validation annotations to retain descriptions, required fields, bounds, formats, and enum constraints.
- [ ] Represent discriminated alternatives with sealed interfaces plus `@Schema(oneOf = ...)`.
- [ ] Use `JsonNode`/`Object` only for fields whose contract is deliberately open.
- [ ] Create typed result envelopes for stable output shapes; retain dynamic business rows/payloads as `JsonNode` or constrained map fields inside those envelopes.

## Task 4: Model management and scheduler Tool contracts as Java types

**Files:**

- Modify/reuse DTOs used by:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/admin/MetricDataSourceTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/admin/MetricDatasetTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/admin/MetricSemanticDefinitionTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/admin/MetricRelationshipTools.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/scheduler/tool/ScheduledTaskTools.java`

- [ ] Reuse connector request/response types when they already express the Tool-visible contract.
- [ ] Add narrow Tool boundary records when connector DTOs contain transport-only fields.
- [ ] Preserve nullable/required behavior exactly.
- [ ] Generate schemas from the actual Tool method inputs and declared output boundary types.
- [ ] Keep runtime conversion helpers such as `MetricToolSupport.arguments(Map, Class<T>)` and result payload maps when they process dynamic invocation data rather than define schemas.

## Task 5: Remove hand-built Tool schema maps

**Files:**

- Modify:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/MetricPlatformToolCatalog.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/metrictool/read/MetricAnnotatedToolCatalog.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/ScheduledTaskAgentRunContextProvider.java`

- [ ] Delete helpers such as `objectSchema`, `stringSchema`, nested property maps, and raw schema `TypeReference<Map<String,Object>>`.
- [ ] Build legacy catalog definitions from Java method/type schemas through `AgentJsonSchemaGenerator`.
- [ ] Wrap Spring-generated annotated callback input schema through the adapter.
- [ ] Replace `Map.of()` output schemas with the explicit unspecified document or a generated output type.
- [ ] Keep ordinary Tool arguments/results conversion independent from schema generation.

## Task 6: Generate context-summary schema from `ContextSummary`

**Files:**

- Modify:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/context/SpringAiContextSummarizer.java`
  - the file declaring `ContextSummary`, if annotations are required

- [ ] Delete all summary schema key maps.
- [ ] Generate the schema from `ContextSummary.class`.
- [ ] Add annotations to `ContextSummary` fields only where needed to preserve the existing model contract.
- [ ] Route Ollama/Spring serialization through `AgentJsonSchemaGenerator`.
- [ ] Keep summary prompt content unchanged.

## Task 7: Enforce and verify Java Class First schemas

- [ ] Add an architecture/source check, after test authorization, that rejects schema-building patterns such as maps containing `type`, `properties`, `items`, and `required`.
- [ ] Run schema compatibility:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -pl :agent-api -am -Dtest=AgentToolSchemaCompatibilityTest,MetricPlatformToolContractTest,MetricAnalysisToolContractTest,MetricReadToolContractTest,MetricAdminToolContractTest -Dsurefire.failIfNoSpecifiedTests=false test
```

- [ ] Search remaining schema maps:

```powershell
rg -n 'Map<String,\s*Object>.*Schema|Map\.of\(\s*"type"|"(properties|items|required|additionalProperties)"\s*,' data-agent/backend --glob '*.java'
```

- [ ] Review matches and confirm any remaining map is runtime/business JSON, not a schema definition.
- [ ] Run the supported backend package check:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -B -DskipTests package
```

- [ ] Inspect root and `data-agent` statuses independently.
- [ ] If commit authorization is granted:

```powershell
git -C data-agent add backend
git -C data-agent commit -m "refactor: generate agent schemas from Java types"
```
