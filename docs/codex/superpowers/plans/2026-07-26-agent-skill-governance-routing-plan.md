# Agent Skill Governance and Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox checklists and must be completed in order.

**Goal:** Keep seven least-privilege Skills while removing duplicated governance metadata and making routing ambiguity an explicit same-Run user interaction.

**Architecture:** `SKILL.md` is the packaged Skill contract, `metric-platform-governance.md` contains only cross-Skill ReAct rules, and a startup validator reconciles resources with Java Tool/Skill owners. Routers return a typed decision. Ambiguity creates `SKILL_SELECTION`; resolving it activates one Skill in current Run state and resumes that same Run before an immutable snapshot is created.

**Tech Stack:** Java 21, Spring Boot, YAML/front-matter parsing, Spring MVC, MyBatis-Plus, Maven, JUnit 5, AssertJ

## Global Constraints

- Execute after the identifier, authorization, lifecycle, and schema plans.
- Preserve seven Skill IDs; do not merge Skills.
- Preserve one immutable Skill snapshot per Run.
- Do not add planning, automatic cross-Skill orchestration, or Skill switching inside a Run.
- Do not broaden write permissions.
- Cross-domain writes must ask the user to choose the active domain.
- Do not alter tests or create commits until the user explicitly authorizes those actions.

## Task 1: Normalize shared governance and narrow each Skill

**Files:**

- Modify:
  - `data-agent/backend/agent-capabilities/src/main/resources/agent-skills/metric-platform-governance.md`
  - `data-agent/backend/agent-capabilities/src/main/resources/agent-skills/metric-platform-analysis/SKILL.md`
  - `data-agent/backend/agent-capabilities/src/main/resources/agent-skills/metric-platform-exploration/SKILL.md`
  - `data-agent/backend/agent-capabilities/src/main/resources/agent-skills/metric-platform-data-source-management/SKILL.md`
  - `data-agent/backend/agent-capabilities/src/main/resources/agent-skills/metric-platform-dataset-management/SKILL.md`
  - `data-agent/backend/agent-capabilities/src/main/resources/agent-skills/metric-platform-semantic-definition-management/SKILL.md`
  - `data-agent/backend/agent-capabilities/src/main/resources/agent-skills/metric-platform-relationship-management/SKILL.md`
  - `data-agent/backend/agent-capabilities/src/main/resources/agent-skills/scheduled-task-management/SKILL.md`

- [ ] Move only shared ReAct governance into `metric-platform-governance.md`: obey server interactions, use Tool observations as business truth, do not invent Tool success, and stop on authorization/approval boundaries.
- [ ] Remove duplicated shared rules from the six Metric Platform Skill bodies.
- [ ] Keep each Skill's domain boundary, invariants, workflow, Tool permissions, and completion criteria local.
- [ ] Add/normalize front matter fields: `name`, `description`, `version`, `priority`, `risk-level`, `triggers`, `exclusions`, and `allowed-tools`.
- [ ] Bump Metric Platform Skill versions from `2.0.0` to `2.1.0`.
- [ ] Bump scheduled-task management from `1.0.0` to `1.1.0`.
- [ ] Keep all current `allowed-tools` values and order unless the Tool owner inventory requires deterministic canonical ordering.

## Task 2: Make `SKILL.md` metadata the registry input

**Files:**

- Modify:
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/SkillDefinition.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/ClasspathSkillRegistry.java`
- Create narrowly scoped front-matter DTO/parser classes under:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/skill`

- [ ] Parse version, priority, risk, triggers, exclusions, and allowed Tool names from each resource.
- [ ] Represent closed priority/risk values with enums, retaining exact wire values.
- [ ] Remove hardcoded per-Skill metadata tables from `ClasspathSkillRegistry`.
- [ ] Resolve Skill names through `AgentSkillConstants`.
- [ ] Resolve allowed Tool names through the actual Tool catalog.
- [ ] Derive required scopes/capabilities from resolved typed `ToolDefinition` values.
- [ ] Preserve deterministic registry ordering.

## Task 3: Add startup Skill/Tool contract validation

**Files:**

- Create:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/skill/SkillToolContractValidator.java`
- Modify:
  - application startup/configuration wiring in `data-agent/backend/agent-api`
- Modify, only after test authorization:
  - `data-agent/backend/agent-api/src/test/java/com/datagent/agent/api/ai/MetricSkillContractTest.java`

- [ ] Validate that the Skill resource directory name, front-matter `name`, and `AgentSkillConstants.ALL` entry match.
- [ ] Validate exactly seven unique packaged Skills and no unregistered constant.
- [ ] Validate every `allowed-tools` entry resolves to one actual Tool owner.
- [ ] Validate no duplicate Tool name exists across annotated and legacy catalogs.
- [ ] Validate front-matter types and semantic version format.
- [ ] Validate the effective scope/capability union equals the resolved Tool definitions; never infer it from Tool-name text.
- [ ] Fail application startup with a single diagnostic that lists all contract violations by Skill.

## Task 4: Introduce typed routing decisions

**Files:**

- Create:
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/SkillRouteDecision.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/SkillRouteDecisionType.java`
- Modify:
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/SkillRouter.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/DeterministicMetricSkillRouter.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/ScheduledTaskSkillRouter.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/CompositeSkillRouter.java`

- [ ] Model `SELECTED`, `NO_MATCH`, and `AMBIGUOUS` as a closed decision type.
- [ ] Require `SELECTED` to carry exactly one `SkillDefinition`.
- [ ] Require `AMBIGUOUS` to carry at least two unique candidates in deterministic priority/name order.
- [ ] Require `NO_MATCH` to carry no candidate.
- [ ] Preserve the current unfinished active Skill as the highest-precedence `SELECTED` result.
- [ ] Route one clearly dominant domain directly.
- [ ] Return `AMBIGUOUS` when a request contains competing cross-domain write intents; do not auto-select by arbitrary trigger order.
- [ ] Keep analysis-versus-exploration and scheduled-task precedence behavior where the objective is unambiguous.

The target router contract is:

```java
public enum SkillRouteDecisionType {
    SELECTED,
    NO_MATCH,
    AMBIGUOUS
}

public record SkillRouteDecision(
        SkillRouteDecisionType type,
        Optional<SkillDefinition> selected,
        List<SkillDefinition> candidates) {
    public static SkillRouteDecision selected(SkillDefinition skill);
    public static SkillRouteDecision noMatch();
    public static SkillRouteDecision ambiguous(List<SkillDefinition> candidates);
}

public interface SkillRouter {
    SkillRouteDecision route(String objective, AnalysisState currentState);
}
```

## Task 5: Add `SKILL_SELECTION` pending interaction

**Files:**

- Modify:
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/PendingInteractionType.java`
  - `data-agent/backend/agent-model/src/main/java/com/datagent/agent/core/runtime/PendingInteraction.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/MetricAgentRunContextProvider.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/RuntimeInteractionService.java`

- [ ] Add `SKILL_SELECTION` without renaming existing interaction wire values.
- [ ] In `MetricAgentRunContextProvider.prepare`, handle `SELECTED` as today and handle `NO_MATCH` with current fallback semantics.
- [ ] For `AMBIGUOUS`, create a pending interaction before exposing Tools or persisting a Skill snapshot.
- [ ] Use candidate Skill IDs as option IDs.
- [ ] Put only safe display metadata in `InteractionOption.safeValue`; never put authorization decisions in client-controlled data.
- [ ] Move the Run to the existing waiting-for-interaction state.
- [ ] Do not create a partial Skill snapshot while selection is pending.

## Task 6: Resolve Skill selection and resume the same Run

**Files:**

- Modify:
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/PendingInteractionController.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/MetricAnalysisStateService.java`
  - `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/runtime/MetricAgentRunContextProvider.java`
  - `data-agent/backend/agent-core/src/main/java/com/datagent/agent/core/AgentSessionService.java` only if the existing resume API cannot carry the current Run unchanged

- [ ] Reuse existing tenant/session/Run ownership checks and option-membership validation.
- [ ] On `SKILL_SELECTION`, resolve the selected Skill ID from the server registry, not from `safeValue`.
- [ ] Confirm the selected Skill remains one of the interaction's persisted candidate options.
- [ ] Call `MetricAnalysisStateService.activateSkill(runId, skillId, skillVersion)` before resuming.
- [ ] Resume through `AgentSessionService.resumeWaitingRun` using the same Run ID.
- [ ] Let the next context preparation select the active unfinished Skill and create the one immutable snapshot.
- [ ] Preserve CAS/idempotency: repeated resolution with the same option returns current session state; competing options receive conflict.
- [ ] If activation/resume fails, retain the existing rollback-to-pending behavior.

## Task 7: Verify routing, security, and resource contracts

**Files:**

- Modify/create tests only after authorization:
  - `data-agent/backend/agent-api/src/test/java/com/datagent/agent/api/runtime/DeterministicMetricSkillRouterTest.java`
  - `data-agent/backend/agent-api/src/test/java/com/datagent/agent/api/ai/MetricSkillContractTest.java`
  - `data-agent/backend/agent-api/src/test/java/com/datagent/agent/api/runtime/PendingInteractionControllerTest.java`
  - `data-agent/backend/agent-api/src/test/java/com/datagent/agent/api/runtime/MetricAgentRunContextProviderTest.java`
  - `data-agent/backend/agent-evals/src/test/java/com/datagent/evals/component/ProductionComponentCatalogTest.java`

- [ ] Cover all seven direct selections.
- [ ] Cover `NO_MATCH`.
- [ ] Cover a cross-domain write request producing deterministic `AMBIGUOUS` candidates.
- [ ] Assert no Tool callbacks and no Skill snapshot exist before selection.
- [ ] Resolve an allowed option and assert the same Run resumes with exactly one snapshot.
- [ ] Reject a forged/non-candidate option.
- [ ] Cover same-option idempotency, competing-option conflict, expiry, and activation rollback.
- [ ] Assert each Skill's effective required scopes equal the union of its allowed Tool definitions.
- [ ] Run focused tests:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -pl :agent-api,:agent-evals -am -Dtest=DeterministicMetricSkillRouterTest,MetricSkillContractTest,PendingInteractionControllerTest,ProductionComponentCatalogTest -Dsurefire.failIfNoSpecifiedTests=false test
```

- [ ] Run the supported backend package check:

```powershell
.\data-agent\backend\mvnw.cmd -f .\data-agent\backend\pom.xml -B -DskipTests package
```

- [ ] Inspect root and `data-agent` statuses independently.
- [ ] If commit authorization is granted:

```powershell
git -C data-agent add backend
git -C data-agent commit -m "refactor: validate and route governed agent skills"
```
