# Agent Skill, Protocol Identifier, and Schema Governance Design

Date: 2026-07-26  
Status: Approved in design discussion

## Context

The Data Agent packages seven progressively loaded Skills:

1. `metric-platform-exploration`
2. `metric-platform-analysis`
3. `metric-platform-data-source-management`
4. `metric-platform-dataset-management`
5. `metric-platform-semantic-definition-management`
6. `metric-platform-relationship-management`
7. `scheduled-task-management`

The Skills have legitimate read-tool overlap, but the four Metric Platform management Skills repeat the same governance workflow. Routing metadata is also duplicated between `SKILL.md`, `ClasspathSkillRegistry`, and the deterministic routers.

Stable protocol identifiers are also repeated as string literals across production code, persistence
logic, evaluations, and tests. Tool names are partly centralized in `AgentToolDefinitions` instead of
being owned by the Tool classes they identify. Skill names have a central inventory but are
redeclared by routers and consumers.

JSON Schema definitions are represented as nested `Map<String, Object>` values in
`ToolDefinition`, `MetricPlatformToolCatalog`, and `SpringAiContextSummarizer`. The repeated
`type`, `properties`, `items`, `required`, and related keys make the contracts difficult to read and
allow Java DTOs and model-visible schemas to drift independently.

Each Agent Run persists an immutable Skill snapshot containing the Skill ID, version, instruction hash, allowed tools, and required scopes. That snapshot is a security and recovery boundary and must remain limited to one Skill per Run.

The Agent uses ReAct execution. This design does not introduce a planning subsystem or automatic cross-Skill orchestration.

## Goals

In priority order:

1. Preserve least-privilege execution and immutable per-Run Skill snapshots.
2. Improve deterministic routing and make ambiguity explicit.
3. Reduce the model's instruction load and opportunity for tool misuse.
4. Give every stable protocol identifier one Java owner.
5. Replace hand-built Schema maps with schemas generated from Java classes.
6. Remove duplicated governance and routing metadata.
7. Preserve all existing wire values and the compatibility of historical runs, evaluations, and scheduled tasks.

## Non-goals

- Do not merge the management Skills.
- Do not add a super-Skill, planning tool, workflow plan, or plan persistence.
- Do not switch Skills within one Run.
- Do not expand any Skill's write-tool permissions.
- Do not change Metric Platform APIs or implementation.
- Do not migrate or rewrite historical Skill snapshots.
- Do not introduce a second hand-built JSON Schema DSL.
- Do not replace valid dynamic business JSON maps with rigid DTOs.
- Do not perform an indiscriminate conversion of user-facing text, log sentences, SQL fragments, or
  natural-language routing terms into constants.
- Do not extend this change into `metric-platform`, the Data Agent frontend, SQL migrations, or
  third-party raw JSON fixtures.

## Authority and Responsibility Layers

Rules belong to one of four layers:

| Layer | Responsibility | Authority |
| --- | --- | --- |
| Server execution policy | Authorization, scopes, confirmation state, frozen arguments, idempotency, version checks, and secret isolation | Enforced; highest |
| Global governance | Cross-Skill model behavior, interpretation of server interaction states, Tool-result fidelity, and ambiguity handling | Injected into every ReAct iteration |
| Domain Skill | Domain boundary, domain workflow, invariants, allowed tools, and completion criteria | One active Skill per Run |
| Router | Select the Skill for the current objective or report ambiguity | Selection only |

Safety properties must not depend only on model instructions when the server can enforce them.

`metric-platform-governance.md` remains globally injected by `MetricGovernanceAdvisor`. It contains cross-Skill rules only and does not describe domain fields, enums, or resource-specific procedures.

Each domain Skill owns its `allowed-tools`. Those tools continue to derive required scopes and to be captured in the immutable Run snapshot.

Tool schemas remain the source of truth for parameters, enums, and constraints. Tool observations remain the source of truth for business state.

## Stable Protocol Identifier Ownership

A stable protocol identifier is any string used for lookup, comparison, branching, persistence,
authorization, or cross-module communication.

### Skill names

Replace `AgentSkillDefinitions` with one `AgentSkillConstants` class. It owns the seven Skill name
constants and an immutable `ALL` inventory. Registries, routers, snapshots, evaluations, and tests
reference these constants and do not declare aliases such as `ANALYSIS_SKILL_ID`.

`SKILL.md` remains a standard external resource and therefore retains literal values in its directory
name, `name`, and `allowed-tools` front matter. Runtime contract validation ensures that the
directory, front matter, and `AgentSkillConstants.ALL` agree.

### Tool names

Each Tool name belongs to its implementation class:

- a one-Tool class exposes `public static final String NAME`;
- a class containing several Tool methods exposes constants such as `LIST_NAME`, `GET_NAME`,
  `CREATE_NAME`, and `UPDATE_NAME`;
- `@Tool`, runtime definitions, execution, logging, metrics, persistence queries, evaluations, and
  ordinary tests all reference the owning constant.

Descriptions that name another Tool use constant concatenation rather than embedding the wire name.
`AgentToolDefinitions` no longer owns Tool name constants or duplicate descriptions. Remaining
inventory behavior is assembled from the actual Tool classes; the class is removed if no independent
responsibility remains.

External resource files and one dedicated wire-contract test may contain literal Tool and Skill
names. Core-module tests that cannot depend on a concrete Tool module use neutral fixture names
instead of copying a production Tool name.

### Closed states and shared protocol values

Closed state sets use enums. This includes Run, Tool invocation, pending interaction, scheduler,
risk, and route-decision states. Persistence and JSON boundaries convert through explicit
`wireValue()` and strict parsing methods; business code does not compare raw strings.

Shared scopes and platform capabilities use dedicated types such as `MetricScope` and
`MetricPlatformCapability`. Tool definitions declare these types directly. Scope assignment is not
inferred from Tool-name prefixes or regular expressions.

Tool-specific result codes belong to the Tool or its domain error-code type. Cross-Tool error codes
belong to a shared domain type. Audit event names belong to `AgentAuditEventType`.

Unknown external values fail explicitly at the boundary and are never silently mapped to a default.
Existing database, HTTP, Tool, Skill, scope, capability, and audit wire values do not change.

### Values that remain ordinary strings

User-facing prompts, error explanations, log sentences, SQL text, natural-language routing terms,
and genuinely dynamic JSON keys are not protocol identifiers and are not constantized.

## Java Class First Schema

Production code must not define JSON Schema through nested `Map<String, Object>` values or through
constants for JSON Schema keywords.

### Schema document and generator

`ToolDefinition.inputSchema` and `ToolDefinition.outputSchema` use an immutable
`JsonSchemaDocument` value object rather than `Map<String, Object>`.

An `AgentJsonSchemaGenerator` adapter is the only component that calls Spring AI's
`JsonSchemaGenerator` or converts a generated schema to the JSON form required by Spring AI or
Ollama. Callers provide a Java `Type` or Tool `Method`; they do not construct schema JSON.

The project already includes Spring AI 2.0 schema generation, which supports Jackson, Swagger, and
Spring AI annotations and recursively forbids additional properties by default. No additional
schema framework or custom Schema DSL is introduced.

### Tool input and output types

Each Tool declares or reuses explicit Java input and output types:

- reuse existing argument records, request records, and response DTOs when their serialized shape
  matches the Tool contract;
- introduce Tool-specific records where the model-visible shape differs from a platform DTO;
- represent enums, UUIDs, timestamps, numeric bounds, item bounds, uniqueness, optionality, and
  descriptions through Java types and supported annotations;
- represent `oneOf` through sealed Java types and `@Schema(oneOf = {...})`;
- represent intentionally open dynamic values through `JsonNode` or `Object`.

`SpringAiContextSummarizer` generates its structured output schema from `ContextSummary.class`.
Its `summarySchema`, `stringSchema`, and `stringArraySchema` Map helpers are removed.

Dynamic Tool argument transport, `AgentToolResult.output`, platform metadata, persistence JSON, and
extension fields may remain maps because they represent runtime data rather than Schema definitions.

### Schema compatibility

Before removing the hand-built schemas, capture their canonical JSON structures. Generated schemas
must preserve properties, required fields, enums, formats, numeric and array bounds,
`additionalProperties`, descriptions, and union alternatives. JSON property order is not a
compatibility requirement.

## Skill Boundaries

### `metric-platform-exploration`

- Owns read-only catalog discovery, inventory, object details, physical source metadata, and relationship context.
- Completes when it returns the requested facts with completeness, truncation, and catalog-version limitations disclosed.
- Does not validate or execute analytical queries and does not mutate governed resources.

### `metric-platform-analysis`

- Owns semantic discovery, context and member resolution, query validation, execution, and evidence-backed interpretation.
- Completes when a valid execution result answers the business question with evidence and limitations.
- Does not create or modify governed definitions.

### `metric-platform-data-source-management`

- Owns data-source connection definitions and lifecycle transitions.
- Retains only data-source-specific invariants, including secure secret interaction and deletion impact.
- Does not create datasets.

### `metric-platform-dataset-management`

- Owns physical object mapping, field selection, schema-drift detection, and field synchronization.
- Retains dataset-specific fingerprint, version, field-diff, and deletion-impact invariants.
- Does not create metric, dimension, or relationship definitions.

### `metric-platform-semantic-definition-management`

- Owns governed metric and dimension definitions.
- Retains aggregation, additivity, unit, formatting, time-granularity, semantic-type, and sensitivity invariants.
- Does not modify physical dataset fields.

### `metric-platform-relationship-management`

- Owns dataset relationships, endpoints, field pairs, cardinality, fanout behavior, and revalidation.
- Does not modify endpoint datasets.

### `scheduled-task-management`

- Owns scheduled-task definitions and execution records.
- Does not execute the task's business instruction. A fired task creates a separate Run that is routed normally.

Read tools may appear in more than one Skill when they provide required domain context. Write tools must remain owned by exactly one management Skill.

## Global Governance Content

The global governance document owns these shared rules:

- Use only runtime-supplied Tool definitions.
- Treat platform identifiers and versions as opaque.
- Read before write.
- Follow server-issued confirmation and secure-input interactions.
- Never reconstruct or alter frozen confirmed arguments.
- Treat Tool observations as authoritative.
- Do not expose credentials, tenant context, private prompts, or hidden reasoning.
- On routing ambiguity, ask the user to choose the current domain.
- Never broaden Tool access to finish a request.

Domain Skills do not repeat these rules unless a short domain statement is necessary to explain a stricter invariant.

## Skill Front Matter and Registry

Skill front matter becomes the single source of routing and operational metadata. In addition to `name`, `description`, and `allowed-tools`, it carries the existing values for:

- version
- priority
- risk level
- routing triggers
- routing exclusions

Because the instruction bodies and metadata change, the six Metric Platform Skills advance from
`2.0.0` to `2.1.0`, and `scheduled-task-management` advances from `1.0.0` to `1.1.0`. Historical
snapshots retain their original versions.

`ClasspathSkillRegistry` parses and validates this metadata. It must reject:

- a directory/name mismatch;
- a missing or invalid version;
- an empty description;
- unknown or duplicate Tool names;
- invalid risk or priority values;
- missing triggers where routing requires them.

`AgentSkillConstants.ALL` is the canonical inventory of the seven stable IDs. It does not duplicate
routing metadata.

A startup `SkillToolContractValidator` resolves every `allowed-tools` entry against the actual Tool
catalog. The Skill's effective required scopes and platform capabilities are the union of the
resolved typed Tool definitions. They are not inferred from Tool-name prefixes or regular
expressions. Unknown and duplicate names fail application startup.

## Routing

Routing remains deterministic. The priority is:

1. Explicit scheduled-task management.
2. Explicit write action and its target resource.
3. Analytical query.
4. Read-only exploration.
5. Clarification when no unique Skill can be selected.

The Router owns shared action vocabulary such as create, update, delete, synchronize, activate, and deactivate. Domain nouns and domain-specific triggers come from Skill metadata.

The current `Optional<SkillDefinition>` result cannot distinguish "no match" from "multiple write
domains matched." Replace that ambiguous contract with a typed route decision:

- `SELECTED`: exactly one Skill was selected;
- `NO_MATCH`: no supported Skill applies;
- `AMBIGUOUS`: two or more write-domain Skills match, with the candidate Skill IDs.

`AMBIGUOUS` creates a `SKILL_SELECTION` pending interaction before any Skill snapshot or business
Tool is exposed. The interaction options come only from Registry-validated candidates. Resolving the
interaction records the selected Skill in the current Run's server-owned analysis state and resumes
normal context preparation. It does not create a plan, add Tool permissions, or switch an already
snapshotted Run.

Examples:

- "在订单数据集创建销售额指标" routes to semantic-definition management.
- "修改关系使用的数据集字段" routes to dataset management.
- "查看关系依赖的数据集字段" routes to exploration.
- "查询销售额趋势" routes to analysis.
- "创建数据源并基于它创建数据集" is ambiguous across write domains and requires the user to select the current operation.

An incomplete active Skill may continue within its existing Run. A new Run never infers a new domain from a bare response such as "继续".

## Cross-domain Requests in ReAct

The Agent does not create or persist a plan.

For a request spanning multiple write domains:

1. The Agent identifies that no single least-privilege Skill owns the whole request.
2. It asks the user which domain operation to perform now.
3. The selected operation runs under one Skill and one immutable snapshot.
4. After completion, the Agent may suggest a next concrete operation but does not start it.
5. The user submits the next explicit objective, creating a new Run that is routed independently.

This preserves ReAct behavior inside a Skill without introducing cross-Skill orchestration.

## Failure Handling

- No matching Skill: request clarification without exposing business Tools.
- Multiple write-domain matches: request a current-domain choice.
- Missing scope or platform capability: stop; do not fall back to a broader Skill.
- Stale version or changed fingerprint: re-read, recompute the domain diff, and obtain fresh confirmation.
- Retryable Tool error: retry only inside the current Skill and Run.
- Terminal Tool error: end the current operation.
- Expired or cancelled interaction: do not execute the mutation.
- Session recovery: use persisted Run state and the original Skill snapshot, not model recollection.

## Implementation Scope

The implementation is limited to `data-agent/backend` Java code and its evaluation modules.

### Stage 1: Protocol type foundations

Add the narrowly owned foundations:

- `AgentSkillConstants`;
- `JsonSchemaDocument`;
- `AgentJsonSchemaGenerator`;
- `MetricScope`;
- `MetricPlatformCapability`;
- domain-owned status, audit-event, and error-code enums;
- strict wire-value conversion helpers.

Establish the types without changing any external wire value.

### Stage 2: Tool identifier ownership

Move each Tool name and description to its implementation class. Update annotations, definitions,
execution, logging, metrics, persistence lookups, evaluations, and ordinary tests to use the owner
constant.

Remove the migrated names and duplicate descriptions from `AgentToolDefinitions`. Do not preserve
deprecated aliases, because aliases would create a second source of truth. Remove
`AgentToolDefinitions` if no independent responsibility remains.

Add startup validation between the actual Tool catalog and every `SKILL.md allowed-tools` entry.

### Stage 3: Java Class First schemas

Change `ToolDefinition` to use `JsonSchemaDocument`. Replace the hand-built schemas in
`MetricPlatformToolCatalog`, the analysis Tool handlers, annotated Metric management Tools,
scheduled-task Tools, and `SpringAiContextSummarizer` with schemas generated from Java types or Tool
methods.

Introduce or reuse explicit Tool input and output records. Keep dynamic runtime JSON maps that are
not Schema definitions.

### Stage 4: Skill governance and routing

Modify `metric-platform-governance.md`, the seven `SKILL.md` files, `ClasspathSkillRegistry`, the
deterministic routers, and the smallest required interaction-resolution wiring.

Use `AgentSkillConstants`, move Skill-specific routing metadata to front matter, retain common
write-action precedence in Router code, and surface cross-write-domain ambiguity through a typed
Skill-selection interaction. Do not add planning or cross-Skill execution.

### Stage 5: Remaining stable protocol identifiers

Migrate the remaining in-scope scope, capability, Tool invocation, Run, interaction, scheduler,
audit-event, and shared result-code strings to their domain-owned enums or constants.

Persistence entities may retain String storage fields when required by MyBatis or database
compatibility, but conversion occurs at the persistence boundary and business logic uses typed
values.

### Stage 6: Verification

Run the existing contract, routing, Runner, authorization, scheduler, and component-evaluation
checks. Verify:

- all Tool names, Skill IDs, scopes, capabilities, statuses, and audit wire values remain unchanged;
- all seven Skill IDs and allowed Tool sets remain unchanged;
- generated schemas are canonically equivalent to the previous hand-built schemas;
- governance is injected once per ReAct iteration;
- front matter and Skill/Tool ownership contracts are validated at startup;
- no scope is inferred from a Tool-name prefix;
- cross-domain requests do not silently select a write Skill;
- SQL exclusions and scheduled-task routing still work;
- each Run retains one immutable Skill snapshot;
- registered stable wire values do not reappear as literals outside owners, external resources, and
  the dedicated wire-contract test;
- the Data Agent backend package build succeeds.

New or modified test code requires explicit user authorization under the repository instructions.

## Compatibility

No migration is required for existing Skill snapshots. New Runs use the updated Skill version and
instructions. Historical Runs continue to use their persisted snapshot and are not rewritten.

Existing persisted status, scope, capability, audit, Tool, and Skill wire values remain readable.
Introducing enums or value types changes Java representation, not stored values.

Generated Tool and structured-output schemas must be canonically equivalent to the existing
model-visible contracts before the hand-built schemas are removed. Any intentional contract change
requires a separate design and version decision.

The design changes no Metric Platform contract and requires no root submodule revision update until the Data Agent product change is intentionally committed and pinned.
