# Data Agent V2 阶段 0 契约基线实施计划

> **面向智能体执行者：** 必须使用子技能 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐项任务实施本计划。步骤使用复选框（`- [ ]`）跟踪。

**目标：** 创建 `data-agent-v2` 仓库/子模块，将 V1 的 REST、SSE、DTO、Tool、Skill 和遗留决策基线固化为由 V2 持有且可自校验的制品。

**架构：** 先初始化空远程仓库，使根工作区可以将其注册为第三个子模块。V2 在仓库根目录持有 `contracts/`；保持最小化的 `agent-server` 模块通过 JUnit 契约测试解析 OpenAPI 3.1、JSON Schema 示例和 YAML 清单，测试时不导入或读取同级 V1 仓库。

**技术栈：** Git 子模块、Java 21、Maven Wrapper、Spring Boot 4.1.0 依赖管理、JUnit 5、Jackson YAML、networknt JSON Schema Validator、OpenAPI 3.1/YAML。

## 全局约束

- 范围仅限阶段 0；不要实现认证、持久化、Redis、Ollama、前端运行时行为、Metric Platform、Tool 执行或阶段 2–13。
- V1 行为来源固定为提交 `fb9621ae`；V1 源码路径只作为提取输入，不得成为构建依赖。
- 远程仓库为 `https://github.com/823338779/data-agent-v2.git`；默认分支为 `develop`；根仓子模块路径为 `data-agent-v2`。
- 仓库布局为 `backend/agent-server`、`backend/agent-evals`、`frontend`、`contracts` 和 `docs`；根工作区不得成为 Maven reactor。
- `contracts/openapi.yaml` 是唯一权威 REST 契约。
- 契约示例无需脱敏，但不得提交真实生产凭据或企业数据。
- `assistant_delta` 和 `run_phase_changed` 是明确的 V2 阶段 1 扩展；不得误标为 V1 已产生的事件。
- 每项任务都必须保留根仓及现有子模块中无关的改动。使用 `git status --ignore-submodules=none` 检查。

## 文件结构

### 根工作区文件

- 修改：`.gitmodules` —— 注册 `data-agent-v2`、`develop` 分支及 `ignore = all`。
- 修改：`AGENTS.md` —— 添加 V2 归属和跨仓路由规则。
- 修改：`README.md` —— 记录第三个子模块和独立验证命令。

### 新 `data-agent-v2` 仓库文件

- 创建：`README.md` —— V2 仓库结构图和契约验证命令。
- 创建：`AGENTS.md` —— V2 专属归属、MyBatis-Plus、契约及阶段范围规则。
- 创建：`.gitignore`、`.gitattributes`、`.prettierignore` —— Java/Node/IDE/生成文件策略。
- 创建：`backend/pom.xml`、`backend/mvnw.cmd`、`backend/mvnw`、`backend/.mvn/wrapper/*` —— 独立的双模块 Maven 构建。
- 创建：`backend/agent-server/pom.xml` —— 契约测试宿主；暂不加入生产依赖。
- 创建：`backend/agent-evals/pom.xml` —— 可独立编译的空 JAR 模块。
- 创建：`contracts/openapi.yaml` —— REST 权威契约。
- 创建：`contracts/schemas/session-sse-event.schema.json`、`task-execution-sse-event.schema.json` —— 原始 SSE 线协议 Schema。
- 创建：`contracts/examples/rest/*.yaml`、`contracts/examples/sse/*.json` —— 有效示例。
- 创建：`contracts/inventories/source-surface.yaml`、`features.yaml`、`tools.yaml`、`skills.yaml`、`legacy-decisions.yaml` —— 完整性与归属清单。
- 创建：`backend/agent-server/src/test/java/com/datagent/agentv2/contracts/ContractPathsTest.java` —— OpenAPI 路径/方法覆盖测试。
- 创建：`backend/agent-server/src/test/java/com/datagent/agentv2/contracts/ContractExamplesTest.java` —— Schema/示例校验。
- 创建：`backend/agent-server/src/test/java/com/datagent/agentv2/contracts/InventoryConsistencyTest.java` —— Controller/Client/Tool/Skill 唯一性及交叉引用校验。
- 创建：`backend/agent-server/src/test/java/com/datagent/agentv2/contracts/ContractFiles.java` —— 供模块测试定位仓库根目录的契约制品。

---

### 任务 1：初始化远程仓库和 Maven 骨架

**文件：**
- 创建：`data-agent-v2/README.md`
- 创建：`data-agent-v2/AGENTS.md`
- 创建：`data-agent-v2/.gitignore`
- 创建：`data-agent-v2/.gitattributes`
- 创建：`data-agent-v2/.prettierignore`
- 创建：`data-agent-v2/backend/pom.xml`
- 创建：`data-agent-v2/backend/agent-server/pom.xml`
- 创建：`data-agent-v2/backend/agent-evals/pom.xml`
- 创建：`data-agent-v2/backend/mvnw`、`data-agent-v2/backend/mvnw.cmd`、`data-agent-v2/backend/.mvn/wrapper/maven-wrapper.properties`

**接口：**
- 输入：空 Git 远程仓库 `https://github.com/823338779/data-agent-v2.git`。
- 输出：已推送的 `develop` 分支，Maven 坐标为 `com.datagent:data-agent-v2:0.1.0-SNAPSHOT`，包含 `agent-server`、`agent-evals` 模块。

- [ ] **步骤 1：确认远程仓库仍为空且目标路径不存在**

```powershell
git ls-remote --symref https://github.com/823338779/data-agent-v2.git HEAD
Test-Path .\data-agent-v2
```

预期：`git ls-remote` 不输出任何引用，`Test-Path` 输出 `False`。任一条件不满足时应停止并核对，不得覆盖已有工作。

- [ ] **步骤 2：克隆到已忽略的引导目录并创建 `develop`**

```powershell
git clone https://github.com/823338779/data-agent-v2.git .\tmp\data-agent-v2-bootstrap
git -C .\tmp\data-agent-v2-bootstrap switch -c develop
```

预期：Git 报告仓库为空并切换到 `develop`。

- [ ] **步骤 3：创建最小 Maven reactor 和仓库策略文件**

后端父 POM 必须包含以下精确版本属性和模块：

```xml
<parent>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-parent</artifactId>
  <version>4.1.0</version>
  <relativePath/>
</parent>
<groupId>com.datagent</groupId>
<artifactId>data-agent-v2</artifactId>
<version>0.1.0-SNAPSHOT</version>
<packaging>pom</packaging>
<modules>
  <module>agent-server</module>
  <module>agent-evals</module>
</modules>
<properties>
  <java.version>21</java.version>
  <mybatis-plus.version>3.5.16</mybatis-plus.version>
  <spring-ai.version>2.0.0</spring-ai.version>
</properties>
```

两个子 POM 均继承父 POM 并使用 `jar` 打包。向父 POM 添加 Spotless 3.6.0，并使用 AOSP Google Java Format。使用 Maven 3.9.x 生成 Maven Wrapper：

```powershell
mvn -N -f .\tmp\data-agent-v2-bootstrap\backend\pom.xml wrapper:wrapper -Dmaven=3.9.11
```

- [ ] **步骤 4：在引导克隆中验证骨架**

```powershell
.\tmp\data-agent-v2-bootstrap\backend\mvnw.cmd `
  -f .\tmp\data-agent-v2-bootstrap\backend\pom.xml -B verify
```

预期：输出 `BUILD SUCCESS`；reactor 顺序为 `data-agent-v2`、`agent-server`、`agent-evals`。

- [ ] **步骤 5：提交并推送子仓的首个提交**

```powershell
git -C .\tmp\data-agent-v2-bootstrap add --all
git -C .\tmp\data-agent-v2-bootstrap commit -m "build: initialize data agent v2 repository"
git -C .\tmp\data-agent-v2-bootstrap push -u origin develop
```

预期：`origin/develop` 已存在，且只包含仓库骨架。

### 任务 2：将 V2 注册为根仓第三个子模块

**文件：**
- 修改：`.gitmodules`
- 修改：`AGENTS.md`
- 修改：`README.md`

**接口：**
- 输入：任务 1 已推送的子仓 `develop` 分支。
- 输出：根仓中的 `data-agent-v2` Git 链接，以及工作区路由/验证文档。

- [ ] **步骤 1：将子仓添加为子模块**

```powershell
git submodule add -b develop https://github.com/823338779/data-agent-v2.git data-agent-v2
git config -f .gitmodules submodule.data-agent-v2.ignore all
```

预期 `.gitmodules` 条目：

```ini
[submodule "data-agent-v2"]
	path = data-agent-v2
	url = https://github.com/823338779/data-agent-v2.git
	branch = develop
	ignore = all
```

- [ ] **步骤 2：更新根仓归属规则和 README**

添加根仓归属规则，说明 `data-agent-v2/` 持有重建后的产品及其契约，而 `data-agent/` 在本次工作中仅供参考。添加以下独立验证命令：

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml -B verify
```

不要将 `data-agent-v2` 加入根仓 Maven 父工程。

- [ ] **步骤 3：验证全新子模块初始化语义**

```powershell
git submodule status
git -C .\data-agent-v2 branch --show-current
git status --short --ignore-submodules=none
```

预期：`data-agent-v2` 指向任务 1 在 `develop` 上的提交；根仓改动仅包含 `.gitmodules`、`AGENTS.md`、`README.md` 和新 Git 链接。

- [ ] **步骤 4：提交根仓注册改动**

```powershell
git add .gitmodules AGENTS.md README.md data-agent-v2
git commit -m "build: register data agent v2 submodule"
```

### 任务 3：添加契约测试框架

**文件：**
- 修改：`data-agent-v2/backend/agent-server/pom.xml`
- 创建：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/contracts/ContractFiles.java`
- 创建：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/contracts/ContractPathsTest.java`
- 创建：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/contracts/ContractExamplesTest.java`
- 创建：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/contracts/InventoryConsistencyTest.java`

**接口：**
- 输入：仓库根目录 `contracts/` 下的契约文件。
- 输出：`ContractFiles.openApi()`、`ContractFiles.schema(String)`、`ContractFiles.inventory(String)` 和三组聚焦的 JUnit 测试。

- [ ] **步骤 1：编写失败的仓库根目录定位测试**

```java
@Test
void resolvesContractsFromTheRepositoryRoot() {
    assertThat(ContractFiles.root()).endsWith("data-agent-v2", "contracts");
    assertThat(ContractFiles.openApi()).exists();
}
```

- [ ] **步骤 2：运行聚焦测试并观察预期失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=ContractPathsTest test
```

预期：测试失败，因为 `ContractFiles` 和 `contracts/openapi.yaml` 尚不存在。

- [ ] **步骤 3：添加测试依赖并实现 `ContractFiles`**

添加测试范围依赖 `spring-boot-starter-test`、`jackson-dataformat-yaml` 和 `com.networknt:json-schema-validator`。实现路径解析，但不得引用同级 V1 仓库：

```java
final class ContractFiles {
    private ContractFiles() {}

    static Path root() {
        Path current = Path.of("").toAbsolutePath();
        while (current != null && !Files.isDirectory(current.resolve("contracts"))) {
            current = current.getParent();
        }
        if (current == null) throw new IllegalStateException("contracts directory not found");
        return current.resolve("contracts");
    }

    static Path openApi() { return root().resolve("openapi.yaml"); }
    static Path schema(String name) { return root().resolve("schemas").resolve(name); }
    static Path inventory(String name) { return root().resolve("inventories").resolve(name); }
}
```

在 `InventoryConsistencyTest` 中使用以下具体辅助方法，使后续任务共享同一定义：

```java
private static List<String> values(JsonNode root, String array, String field) {
    return StreamSupport.stream(root.path(array).spliterator(), false)
        .map(node -> node.path(field).asText())
        .toList();
}

private static List<String> valuesFlattened(JsonNode root, String array, String field) {
    return StreamSupport.stream(root.path(array).spliterator(), false)
        .flatMap(node -> StreamSupport.stream(node.path(field).spliterator(), false))
        .map(JsonNode::asText)
        .distinct()
        .toList();
}

private static Set<String> openApiOperationIds() throws IOException {
    JsonNode api = YAML.readTree(ContractFiles.openApi().toFile());
    Set<String> ids = new HashSet<>();
    api.path("paths").forEach(path -> path.forEach(operation -> {
        if (operation.hasNonNull("operationId")) ids.add(operation.path("operationId").asText());
    }));
    return ids;
}
```

创建可解析的最小 `contracts/openapi.yaml`，包含 `openapi: 3.1.0`、`info`、空 `paths` 和 `components.schemas`。

- [ ] **步骤 4：运行聚焦测试并确认通过**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=ContractPathsTest test
```

预期：测试通过。

- [ ] **步骤 5：在子仓提交测试框架**

```powershell
git -C .\data-agent-v2 add backend contracts/openapi.yaml
git -C .\data-agent-v2 commit -m "test: add contract baseline harness"
```

### 任务 4：固化 REST 路径、操作、DTO、Cookie 和 Problem Detail

**文件：**
- 修改：`data-agent-v2/contracts/openapi.yaml`
- 创建：`data-agent-v2/contracts/examples/rest/auth-login-success.yaml`
- 创建：`data-agent-v2/contracts/examples/rest/auth-login-failed.yaml`
- 创建：`data-agent-v2/contracts/examples/rest/auth-session.yaml`
- 创建：`data-agent-v2/contracts/examples/rest/session-create.yaml`
- 创建：`data-agent-v2/contracts/examples/rest/session-running.yaml`
- 创建：`data-agent-v2/contracts/examples/rest/problem-validation.yaml`
- 修改：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/contracts/ContractPathsTest.java`
- 修改：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/contracts/ContractExamplesTest.java`

**接口：**
- 输入：提交 `fb9621ae` 中 `data-agent/backend/agent-api/src/main/java/com/datagent/agent/api/**` 下的 V1 Controller，以及 `data-agent/frontend/src/api/**` 下的前端客户端。
- 输出：覆盖全部 38 个 V1 Controller 方法的 OpenAPI 操作、V1 DTO Schema，以及明确的 V2 增量 `RunStream` 字段。

- [ ] **步骤 1：添加失败的精确路径/方法覆盖测试**

使用有序 Map，确保同一路径包含多个方法时仍保持明确：

```java
private static final Map<String, Set<String>> REQUIRED = Map.ofEntries(
    entry("/api/v1/auth/login", Set.of("post")),
    entry("/api/v1/auth/session", Set.of("get")),
    entry("/api/v1/auth/logout", Set.of("post")),
    entry("/api/v1/agent-sessions", Set.of("get", "post")),
    entry("/api/v1/agent-sessions/{sessionId}", Set.of("get")),
    entry("/api/v1/agent-sessions/{sessionId}/metric-identity", Set.of("put")),
    entry("/api/v1/agent-sessions/{sessionId}/messages", Set.of("post")),
    entry("/api/v1/agent-sessions/{sessionId}/events", Set.of("get")),
    entry("/api/v1/agent-sessions/{sessionId}/confirmations/{confirmationId}", Set.of("post")),
    entry("/api/v1/agent-sessions/{sessionId}/interactions/{interactionId}:resolve", Set.of("post")),
    entry("/api/v1/agent-sessions/{sessionId}/interactions/{interactionId}:submit-secret", Set.of("post")),
    entry("/api/v1/agent-sessions/{sessionId}/audit-log", Set.of("get")),
    entry("/api/v1/metric-identities", Set.of("get", "post")),
    entry("/api/v1/metric-identities/{id}", Set.of("get")),
    entry("/api/v1/metric-identities/{id}:verify", Set.of("post")),
    entry("/api/v1/metric-identities/{id}:replace-password", Set.of("post")),
    entry("/api/v1/metric-identities/{id}:deactivate", Set.of("post")),
    entry("/api/v1/metric-identities:rotate-secrets", Set.of("post")),
    entry("/api/v1/tenants", Set.of("post")),
    entry("/api/v1/tenants/{tenantId}/members", Set.of("get", "post")),
    entry("/api/v1/artifacts/{artifactId}", Set.of("get")),
    entry("/api/v1/artifacts/{artifactId}/preview", Set.of("get")),
    entry("/api/v1/artifacts/{artifactId}:create-download", Set.of("post")),
    entry("/api/v1/artifact-downloads/{artifactId}", Set.of("get")),
    entry("/api/v1/scheduled-tasks", Set.of("get", "post")),
    entry("/api/v1/scheduled-tasks/{taskId}", Set.of("get", "put", "delete")),
    entry("/api/v1/scheduled-tasks/{taskId}/executions", Set.of("get", "post")),
    entry("/api/v1/task-executions/{executionId}", Set.of("get")),
    entry("/api/v1/task-executions/{executionId}/cancel", Set.of("post")),
    entry("/api/v1/task-executions/{executionId}/events", Set.of("get")),
    entry("/api/v1/evaluation/mutation-guard", Set.of("get")));
```

对每个条目断言路径存在，并且只包含所需的 HTTP 方法节点。

- [ ] **步骤 2：运行覆盖测试并确认其因空 `paths` 对象而失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=ContractPathsTest test
```

预期：测试失败，缺失路径列表从 `/api/v1/auth/login` 开始。

- [ ] **步骤 3：根据固化的 V1 接口面补全 OpenAPI 操作和共享 Schema**

每个操作都必须声明 `operationId`、Cookie 安全方案、成功响应及相关 Problem Detail 响应。阶段 1 的消息操作必须保留 `202`：

```yaml
/api/v1/agent-sessions/{sessionId}/messages:
  post:
    operationId: submitAgentMessage
    security: [{ sessionCookie: [] }]
    parameters:
      - $ref: '#/components/parameters/SessionId'
    requestBody:
      required: true
      content:
        application/json:
          schema: { $ref: '#/components/schemas/SubmitMessageRequest' }
    responses:
      '202':
        description: Message persisted and Run started
        content:
          application/json:
            schema: { $ref: '#/components/schemas/AgentSession' }
      '401': { $ref: '#/components/responses/AuthenticationRequired' }
      '404': { $ref: '#/components/responses/NotFound' }
      '409': { $ref: '#/components/responses/ActiveRunConflict' }
```

定义 `AgentSession`、`AgentMessage`、`AgentRun`、`RunEvent`、`PendingInteraction`、`ProblemDetail` 及增量 `RunStream`。`AgentRun.status` 的取值为 `idle`、`running`、`waiting_for_user`、`waiting_confirmation`、`done`、`cancelled`、`failed`。`RunStream` 必须包含 `executionAttempt`、`phase`、`sequence`、`thinking`、`answer`。

- [ ] **步骤 4：在添加示例前编写示例校验测试**

```java
@ParameterizedTest
@ValueSource(strings = {
    "auth-login-failed.yaml", "auth-session.yaml", "session-create.yaml",
    "session-running.yaml", "problem-validation.yaml"
})
void restExampleIsValidYamlAndDeclaresItsSchema(String file) {
    JsonNode example = YAML.readTree(ContractFiles.root().resolve("examples/rest").resolve(file).toFile());
    assertThat(example.path("schema").asText()).isNotBlank();
    assertThat(example.path("value").isMissingNode()).isFalse();
}
```

- [ ] **步骤 5：添加完整的合成/本地示例并使测试通过**

使用 `tenant_local`、`user_admin`、`session_demo`、`run_demo` 和 `request_demo` 等稳定值。Problem Detail 示例必须采用以下结构：

```yaml
schema: ProblemDetail
value:
  type: urn:data-agent:problem:validation-failed
  title: Bad Request
  status: 400
  detail: Request validation failed
  instance: /api/v1/agent-sessions/session_demo/messages
  code: VALIDATION_FAILED
  requestId: request_demo
  errors:
    - field: content
      message: must not be blank
```

- [ ] **步骤 6：运行契约测试并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest='ContractPathsTest,ContractExamplesTest' test
git -C .\data-agent-v2 add contracts backend/agent-server
git -C .\data-agent-v2 commit -m "docs: freeze v1 rest contract"
```

### 任务 5：固化 SSE Schema、前端投影和流式扩展

**文件：**
- 创建：`data-agent-v2/contracts/schemas/session-sse-event.schema.json`
- 创建：`data-agent-v2/contracts/schemas/task-execution-sse-event.schema.json`
- 创建：`data-agent-v2/contracts/examples/sse/run-started.json`
- 创建：`data-agent-v2/contracts/examples/sse/reasoning-delta.json`
- 创建：`data-agent-v2/contracts/examples/sse/assistant-delta.json`
- 创建：`data-agent-v2/contracts/examples/sse/run-phase-changed.json`
- 创建：`data-agent-v2/contracts/examples/sse/assistant-message.json`
- 创建：`data-agent-v2/contracts/examples/sse/run-completed.json`
- 修改：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/contracts/ContractExamplesTest.java`

**接口：**
- 输入：V1 `AgentEventType`、`AgentDtos.AgentEventResponse`、`backendAgentClient.ts` 及任务执行 SSE DTO。
- 输出：生命周期、思考、回答和任务事件的 JSON Schema Draft 2020-12 信封及示例。

- [ ] **步骤 1：编写失败的事件枚举和示例校验测试**

```java
private static final Set<String> SESSION_EVENTS = Set.of(
    "run_started", "user_message", "assistant_message", "reasoning_delta",
    "assistant_delta", "run_phase_changed", "skill_activated",
    "context_compaction_started", "context_compaction_completed",
    "context_compaction_failed", "tool_call_started", "tool_call_completed",
    "tool_call_result", "tool_call_failed", "interaction_requested",
    "interaction_resolved", "user_confirmation_requested",
    "user_confirmation_resolved", "run_completed", "run_failed",
    "run_cancelled", "error");
```

加载 Schema，断言其 `type` 枚举等于该集合，然后使用 networknt 校验 `contracts/examples/sse` 中的每个 JSON 文件。

- [ ] **步骤 2：运行并确认失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=ContractExamplesTest test
```

预期：测试失败，因为 Schema 和示例尚不存在。

- [ ] **步骤 3：实现会话流式 Schema**

生命周期事件使用 `sequence`；增量事件还必须包含 `executionAttempt`、`streamSequence`、`delta` 和 `occurredAt`。`assistant_delta` 标注 `x-v2-extension: true`；`run_phase_changed.phase` 枚举为：

```json
["RECEIVED", "PREPARING_CONTEXT", "CONNECTING_MODEL", "THINKING", "ANSWERING", "PERSISTING", "COMPLETED", "FAILED"]
```

Schema 必须使用 `oneOf` 区分持久化生命周期事件和低延迟增量事件，不得通过把所有字段设为可选来区分。

- [ ] **步骤 4：添加有效示例和投影元数据**

每个增量示例使用 `session_demo`、`run_demo`、`executionAttempt: 1` 和严格递增的 `streamSequence`。添加 `x-frontend-projection` 元数据：将 `reasoning_delta` 映射到 `reasoning.delta`，将 `assistant_delta` 映射到助手草稿，将 `run_phase_changed` 映射到运行时间线。

- [ ] **步骤 5：验证并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=ContractExamplesTest test
git -C .\data-agent-v2 add contracts/schemas contracts/examples/sse backend/agent-server
git -C .\data-agent-v2 commit -m "docs: freeze sse and streaming contracts"
```

### 任务 6：构建源码面和功能完整性清单

**文件：**
- 创建：`data-agent-v2/contracts/inventories/source-surface.yaml`
- 创建：`data-agent-v2/contracts/inventories/features.yaml`
- 修改：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/contracts/InventoryConsistencyTest.java`

**接口：**
- 输入：任务 4 固化的全部 V1 Controller 方法和前端 Client 操作。
- 输出：源码到操作的一对一映射，以及包含正常、等待、失败、安全和迁移阶段字段的功能矩阵。

- [ ] **步骤 1：编写失败的清单唯一性测试**

```java
@Test
void everySourceSymbolAndOperationIdAppearsExactlyOnce() throws Exception {
    JsonNode inventory = YAML.readTree(ContractFiles.inventory("source-surface.yaml").toFile());
    List<String> symbols = values(inventory, "entries", "sourceSymbol");
    List<String> operations = values(inventory, "entries", "operationId");
    assertThat(symbols).doesNotHaveDuplicates();
    assertThat(operations).doesNotHaveDuplicates();
    assertThat(operations).containsExactlyInAnyOrderElementsOf(openApiOperationIds());
}
```

添加第二个测试，要求每个功能都具有非空的 `entry`、`success`、`failure`、`security` 字段和整数 `phase` 字段。

- [ ] **步骤 2：运行并确认因文件缺失而失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=InventoryConsistencyTest test
```

- [ ] **步骤 3：填充精确的源码接口面**

每个条目使用以下具体结构：

```yaml
entries:
  - sourceKind: controller
    sourcePath: backend/agent-api/src/main/java/com/datagent/agent/api/SessionAuthenticationController.java
    sourceSymbol: SessionAuthenticationController#login
    frontendPath: frontend/src/api/authClient.ts
    frontendSymbol: authClient.login
    operationId: login
    status: effective
```

包含任务 4 列出的每个 Controller 方法。不存在前端客户端时，省略 `frontendPath` 并设置 `consumer: operations-or-evals`；不得虚构前端调用方。

- [ ] **步骤 4：填充功能矩阵**

分别为认证、会话 CRUD、消息/运行、会话 SSE、Metric Identity、租户控制面、Artifact、定时任务、任务执行、变更防护、待处理交互和密钥输入建立条目。阶段 1 条目必须明确包含多实例 Redis 通知、无服务发现、同入口节点执行 Ollama、思考流、回答流、刷新恢复、活动 Run 冲突、Ollama 失败和陈旧 Run 超时。

- [ ] **步骤 5：验证并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=InventoryConsistencyTest test
git -C .\data-agent-v2 add contracts/inventories backend/agent-server
git -C .\data-agent-v2 commit -m "docs: freeze source and feature inventories"
```

### 任务 7：固化 Tool、Skill 和遗留决策清单

**文件：**
- 创建：`data-agent-v2/contracts/inventories/tools.yaml`
- 创建：`data-agent-v2/contracts/inventories/skills.yaml`
- 创建：`data-agent-v2/contracts/inventories/legacy-decisions.yaml`
- 修改：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/contracts/InventoryConsistencyTest.java`

**接口：**
- 输入：设计文档第 14 节中的 56 个名称，以及 V1 中发现的 8 个 Skill/治理资源。
- 输出：恰好 56 个唯一 Tool 条目、8 个唯一 Skill 条目，以及针对 `assistant_delta` 和 `QUERY_SCOPE` 的明确决策。

- [ ] **步骤 1：编写失败的数量、唯一性和引用测试**

```java
@Test
void toolsAndSkillsAreCompleteAndCrossReferenced() throws Exception {
    JsonNode tools = YAML.readTree(ContractFiles.inventory("tools.yaml").toFile());
    JsonNode skills = YAML.readTree(ContractFiles.inventory("skills.yaml").toFile());
    assertThat(tools.path("tools")).hasSize(56);
    assertThat(skills.path("skills")).hasSize(8);
    assertThat(values(tools, "tools", "name")).doesNotHaveDuplicates();
    assertThat(values(skills, "skills", "name")).doesNotHaveDuplicates();
    assertThat(values(skills, "skills", "name"))
        .containsAll(valuesFlattened(tools, "tools", "allowedSkills"));
}
```

要求每个 Tool 都具有 `name`、非空 `description`、对象类型 `inputSchema`、`risk`、布尔值 `idempotent`、`requiredScopes`、`allowedSkills`、`interactionMode`、`resultCodes` 和整数 `phase`。

- [ ] **步骤 2：运行并确认失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=InventoryConsistencyTest test
```

- [ ] **步骤 3：按六个已批准分组填充全部 56 个 Tool 条目**

使用设计文档第 14.1–14.6 节中的精确名称：7 个指标分析/目录 Tool、10 个数据源 Tool、13 个数据集 Tool、11 个指标/维度定义 Tool、7 个关系 Tool、8 个调度/任务执行 Tool。不要创建可执行 Tool 代码。使用 JSON Schema 对象，不要使用文字参数列表。

- [ ] **步骤 4：填充 8 个 Skill/治理条目**

使用 `data-agent/backend/agent-capabilities/src/main/resources` 下发现的真实 V1 资源名称；记录 `sourcePath`、SHA-256 内容哈希、职责、允许的 Tool 分组和迁移阶段。提取并计算 `fb9621ae` 精确内容的哈希：

```powershell
$skillExtract = Join-Path (Resolve-Path .\tmp) 'v1-skill-hash'
New-Item -ItemType Directory -Force -Path $skillExtract | Out-Null
git -C .\data-agent archive fb9621ae backend/agent-capabilities/src/main/resources `
  | tar -xf - -C $skillExtract
$skillFiles = Get-ChildItem `
  (Join-Path $skillExtract 'backend\agent-capabilities\src\main\resources') -Recurse -File
$skillFiles | Get-FileHash -Algorithm SHA256 | Select-Object Path,Hash
```

断言 `$skillFiles.Count -eq 8`；在 `skills.yaml` 中记录这八个具体相对路径及其哈希。

- [ ] **步骤 5：记录明确的遗留决策**

```yaml
decisions:
  - id: assistant-delta
    v1Status: compatibility-input-only
    v2Status: phase-1-production-event
    rationale: Required for answer-token streaming in the approved V2 UI.
  - id: query-scope-interaction
    v1Status: incomplete-production-chain
    v2Status: do-not-migrate-until-a-producing-path-is-proven
    rationale: An enum without a complete creation and resolution flow is not effective behavior.
```

- [ ] **步骤 6：验证并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=InventoryConsistencyTest test
git -C .\data-agent-v2 add contracts/inventories backend/agent-server
git -C .\data-agent-v2 commit -m "docs: freeze tool skill and legacy inventories"
```

### 任务 8：通过独立验证完成阶段 0

**文件：**
- 修改：`data-agent-v2/README.md`
- 创建：`data-agent-v2/docs/contracts.md`

**接口：**
- 输入：阶段 0 的全部契约制品和测试。
- 输出：在不存在 `data-agent/` 的全新克隆中可复现的阶段 0 验证。

- [ ] **步骤 1：记录归属和验证方式**

`docs/contracts.md` 必须说明：OpenAPI 是 REST 权威契约；JSON Schema 是 SSE 权威契约；清单负责完整性；源码提交为 `fb9621ae`；V1 不是运行时/测试依赖。添加以下命令：

```powershell
.\backend\mvnw.cmd -f .\backend\pom.xml -B -pl agent-server test
.\backend\mvnw.cmd -f .\backend\pom.xml -B verify
```

- [ ] **步骤 2：在子仓运行聚焦验证和聚合验证**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml -B `
  -pl agent-server -Dtest='ContractPathsTest,ContractExamplesTest,InventoryConsistencyTest' test
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml -B verify
```

预期：两个命令均输出 `BUILD SUCCESS`。

- [ ] **步骤 3：提交验证文档并推送阶段 0**

```powershell
git -C .\data-agent-v2 add README.md docs
git -C .\data-agent-v2 commit -m "docs: document contract baseline verification"
git -C .\data-agent-v2 push origin develop
```

- [ ] **步骤 4：证明已推送远程仓库不依赖同级仓库**

在 `agent-root` 外的临时目录中仅克隆 V2 并验证：

```powershell
git clone --branch develop https://github.com/823338779/data-agent-v2.git .\tmp\data-agent-v2-clean
.\tmp\data-agent-v2-clean\backend\mvnw.cmd `
  -f .\tmp\data-agent-v2-clean\backend\pom.xml -B verify
```

预期：输出 `BUILD SUCCESS`；不存在引用 `../data-agent` 的路径查找。

- [ ] **步骤 5：更新根仓 Git 链接**

```powershell
git add data-agent-v2
git commit -m "build: advance data agent v2 contract baseline"
```

- [ ] **步骤 6：分别检查两个仓库**

```powershell
git -C .\data-agent-v2 status --short
git status --short --ignore-submodules=none
git -C .\data-agent-v2 log -5 --oneline
git diff HEAD^ --submodule=log
```

预期：V2 工作区干净；完成有意的根仓提交后，根仓只显示用户原有的无关改动。
