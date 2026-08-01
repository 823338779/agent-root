# Data Agent V2 阶段 1 流式对话实施计划

> **面向智能体执行者：** 必须使用子技能 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐项任务实施本计划。步骤使用复选框（`- [ ]`）跟踪。

**目标：** 交付最小化 V2 产品：用户通过 Nginx 登录、创建对话会话并提交消息，在两个服务实例下实时看到 Ollama 的思考、回答 Token 和执行阶段。

**架构：** `agent-server` 是模块化 Spring Boot 单体；`agent-evals` 保持为空的独立 CLI 骨架。持久化用户 Message 的节点在事务提交后启动本地 Ollama 流，并且是唯一允许执行该 Run 的节点。PostgreSQL 持有认证、会话、消息、Run 生命周期、检查点和持久通知；单机 Redis Pub/Sub 将实时 Token 转发到持有浏览器 SSE 连接的副本。

**技术栈：** Java 21、Spring Boot 4.1.0、Spring MVC/Security/Actuator、Spring AI 2.0.0 Ollama `StreamingChatModel`、MyBatis-Plus 3.5.16 `ServiceImpl`、PostgreSQL/Flyway、Redis/Lettuce、React 19、TypeScript 5.8、Vite 7、Vitest 2、Nginx、Docker Compose、Testcontainers。

## 全局约束

- 本计划只实施已批准的阶段 1。不要实现 Metric Platform、Metric Identity、Tool/Skill 执行、审批、Artifact、调度、评估、长上下文摘要或阶段 2–13。
- 开始任务 1 前，必须完成阶段 0 计划及其契约测试。
- 前端迁移只将 V1 当前已跟踪的文件快照复制到 V2；不要复制 Git 历史，也不要保留对旧 `data-agent/frontend` 目录的运行时/构建依赖。迁移后旧目录仅供参考。
- `agent-server` 是唯一可部署后端；`agent-evals` 不得依赖服务端实现类。
- PostgreSQL 和单机 Redis 为必需组件。V2 服务副本不使用服务发现或直接 RPC；浏览器只访问一个 Nginx 源。
- 保存用户 Message 的节点在事务提交后执行 Ollama 流。不要轮询 Message/Run 获取任务、发布 `run.available`、让其他节点领取 Run，也不要在节点故障时自动重试模型。
- 产生 `run_phase_changed`、`reasoning_delta`、`assistant_delta`、`assistant_message`、`run_completed` 和 `run_failed`。思考与回答增量使用 `(runId, executionAttempt, streamSequence)`。
- 先持久化生命周期事件和最终消息，再发送通知。Token 增量通过 Redis 立即发布；累计思考/回答每 100ms 或每 32 个模型分块（以先到者为准）写入检查点。
- 持久化代码使用 MyBatis-Plus `ServiceImpl`、Chain Wrapper、`MetaObjectHandler`、`@TableLogic`、`@Version`、租户拦截器和乐观锁拦截器。Application/Controller 代码不得直接注入或调用 Mapper。
- 领域业务表包含 `created_at`、`updated_at`、`deleted_at`、`is_deleted`；Outbox 按保留策略硬删除。
- 使用确定性的 Ollama 协议夹具添加测试；真实 `qwen3.5:9b` 冒烟测试必须显式启用，不属于默认单元测试套件。

## 文件结构

### 后端组成与平台层

- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/AgentV2Application.java`
- 创建：`.../platform/config/{ClockConfiguration,JsonConfiguration,MybatisPlusConfiguration,RedisConfiguration}.java`
- 创建：`.../platform/context/{RequestContext,RequestContextFilter,TenantContext}.java`
- 创建：`.../platform/id/{IdGenerator,PrefixedUuidIdGenerator}.java`
- 创建：`.../platform/persistence/{AuditedEntity,TenantAuditedEntity,AuditMetaObjectHandler}.java`
- 创建：`.../platform/web/{ApiExceptionHandler,ProblemCodes}.java`

### 认证

- 创建：`.../auth/api/{AuthenticationController,LoginRequest,AuthSessionResponse}.java`
- 创建：`.../auth/application/AuthenticationService.java`
- 创建：`.../auth/persistence/{TenantEntity,UserAccountEntity,TenantMembershipEntity,LoginSessionEntity}.java`
- 创建：`.../auth/persistence/{TenantMapper,UserAccountMapper,TenantMembershipMapper,LoginSessionMapper}.java`
- 创建：`.../auth/persistence/{TenantPersistenceService,UserAccountPersistenceService,TenantMembershipPersistenceService,LoginSessionPersistenceService}.java`
- 创建：`.../auth/security/{SessionAuthenticationFilter,TenantPrincipal,SecurityConfiguration}.java`

### 对话、流式传输与模型

- 创建：`.../conversation/api/{AgentSessionController,AgentDtos,CreateSessionRequest,SubmitMessageRequest}.java`
- 创建：`.../conversation/application/{ConversationService,ConversationStreamService,RunTimeoutService}.java`
- 创建：`.../conversation/domain/{RunStatus,RunPhase,MessageRole,StreamChannel}.java`
- 为 Session、Message、Run、RunEvent、RunStream、NotificationOutbox 创建：`.../conversation/persistence/*Entity.java`、`*Mapper.java`、`*PersistenceService.java`。
- 创建：`.../conversation/cluster/{RedisStreamBridge,StreamEnvelope,LocalSseRegistry,OutboxPublisher}.java`
- 创建：`.../conversation/model/{ModelGateway,ModelRequest,OllamaStreamingModelGateway,ModelDelta}.java`
- 创建：`.../conversation/application/ConversationExecutionPort.java`

### 资源与测试

- 创建：`data-agent-v2/backend/agent-server/src/main/resources/{application.yml,application-local.yml}`
- 创建：`data-agent-v2/backend/agent-server/src/main/resources/db/migration/V1__phase_1_streaming_chat.sql`
- 在 `src/test/java/com/datagent/agentv2/**` 下创建聚焦的单元测试、MVC 测试、PostgreSQL 集成测试、Redis 双实例测试、假 Ollama 测试和可选真实 Ollama 测试。

### 前端与本地拓扑

- 创建/迁移：`data-agent-v2/frontend/{package.json,package-lock.json,index.html,tsconfig*.json,vite.config.ts,vitest.config.ts}`
- 创建/迁移：`data-agent-v2/frontend/src/{main.tsx,AuthenticatedApp.tsx,App.tsx,auth.css,styles.css}`
- 创建/迁移：`data-agent-v2/frontend/src/api/{authClient,backendAgentClient}.ts`
- 创建/迁移：`data-agent-v2/frontend/src/domain/agentPrototype.ts`
- 创建：`data-agent-v2/frontend/src/components/RunTimeline.tsx`
- 创建：`data-agent-v2/infra/compose.yml`、`data-agent-v2/infra/nginx.conf`
- 创建：`data-agent-v2/infra/Dockerfile.server`、`data-agent-v2/infra/Dockerfile.web`
- 修改：`data-agent-v2/README.md`

---

### 任务 1：启动具有稳定错误格式和请求 ID 的 Spring Boot 服务

**文件：**
- 修改：`data-agent-v2/backend/agent-server/pom.xml`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/AgentV2Application.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/id/IdGenerator.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/id/PrefixedUuidIdGenerator.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/context/RequestContext.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/context/RequestContextFilter.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/web/ApiExceptionHandler.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/resources/application.yml`
- 测试：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/platform/web/ApiExceptionHandlerTest.java`
- 测试：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/AgentV2ApplicationTest.java`

**接口：**
- 输入：阶段 0 Problem Detail 契约。
- 输出：`IdGenerator.next(String prefix)`、请求属性/MDC `requestId`、`X-Request-Id` 响应头、`/actuator/health/liveness`、`/actuator/health/readiness`。

- [ ] **步骤 1：编写失败的上下文和 Problem Detail 测试**

```java
@SpringBootTest
class AgentV2ApplicationTest {
    @Test void contextLoads() {}
}

@WebMvcTest(controllers = FailureFixtureController.class)
@Import({ApiExceptionHandler.class, RequestContextFilter.class})
class ApiExceptionHandlerTest {
    @Test void unexpectedFailureReturnsRequestIdWithoutStackTrace() throws Exception {
        mvc.perform(get("/__test/failure").header("X-Request-Id", "request_test"))
            .andExpect(status().isInternalServerError())
            .andExpect(header().string("X-Request-Id", "request_test"))
            .andExpect(jsonPath("$.code").value("INTERNAL_ERROR"))
            .andExpect(jsonPath("$.requestId").value("request_test"))
            .andExpect(jsonPath("$.trace").doesNotExist());
    }
}
```

- [ ] **步骤 2：运行并确认因应用/配置缺失而失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest='AgentV2ApplicationTest,ApiExceptionHandlerTest' test
```

- [ ] **步骤 3：添加最小依赖和实现**

添加 Web MVC、Validation、Security、Actuator、Jackson 和测试 Starter。`IdGenerator` 定义为：

```java
public interface IdGenerator {
    String next(String prefix);
}

@Component
final class PrefixedUuidIdGenerator implements IdGenerator {
    public String next(String prefix) {
        if (prefix == null || !prefix.matches("[a-z][a-z0-9_]*")) {
            throw new IllegalArgumentException("invalid id prefix");
        }
        return prefix + "_" + UUID.randomUUID().toString().replace("-", "");
    }
}
```

`RequestContextFilter` 仅在入站请求 ID 匹配 `[A-Za-z0-9._-]{1,64}` 时接受它；否则生成 `request_...`。将其写入 MDC、请求属性和响应头，并在 `finally` 中清理 MDC。

- [ ] **步骤 4：运行测试并验证健康检查端点**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest='AgentV2ApplicationTest,ApiExceptionHandlerTest' test
```

预期：测试通过。

- [ ] **步骤 5：提交**

```powershell
git -C .\data-agent-v2 add backend/agent-server
git -C .\data-agent-v2 commit -m "feat: bootstrap v2 server boundary"
```

### 任务 2：创建阶段 1 数据库迁移

**文件：**
- 修改：`data-agent-v2/backend/agent-server/pom.xml`
- 创建：`data-agent-v2/backend/agent-server/src/main/resources/db/migration/V1__phase_1_streaming_chat.sql`
- 创建：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/persistence/Phase1MigrationTest.java`

**接口：**
- 输入：已批准的 10 表基线。
- 输出：供阶段 1 全部持久化服务使用的租户安全 Schema 和约束。

- [ ] **步骤 1：编写失败的 Testcontainers 迁移测试**

```java
@Testcontainers
class Phase1MigrationTest {
    @Container static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:17-alpine");

    @Test void emptyDatabaseMigratesToExactlyTenApplicationTables() throws Exception {
        Flyway.configure().dataSource(postgres.getJdbcUrl(), postgres.getUsername(), postgres.getPassword())
            .locations("classpath:db/migration").load().migrate();
        assertThat(applicationTables(postgres)).containsExactlyInAnyOrder(
            "tenant", "user_account", "tenant_membership", "login_session",
            "agent_session", "agent_message", "agent_run", "agent_run_event",
            "agent_run_stream", "notification_outbox");
    }
}
```

测试中的 `applicationTables` 通过查询 `public` Schema 的 `information_schema.tables` 实现，并排除 `flyway_schema_history`；返回排序后的 `List<String>`，使失败信息能打印精确的意外表集合。

添加以下测试：前九张表具备审计列、带租户的复合外键、活动 Run 部分唯一性、Event/Message 序列唯一性，以及 `is_deleted/deleted_at` 一致性。

- [ ] **步骤 2：运行并确认因迁移缺失而失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=Phase1MigrationTest test
```

- [ ] **步骤 3：直接按目标结构实现迁移**

使用 `varchar(64)` 前缀 ID、`timestamptz`、受约束的状态字符串、`bigint` 序列，并使用 `text` 存储思考/回答内容。每张租户子表都具有 `unique (tenant_id, id)`，使复合外键能够强制同租户引用。活动 Run 约束为：

```sql
create unique index uq_agent_run_one_active
    on agent_run (tenant_id, session_id)
    where is_deleted = false and status in
        ('running', 'waiting_for_user', 'waiting_confirmation');
```

流表使用 `run_id` 作为兼容 `@TableId` 的单列主键，同时具有 `unique (tenant_id, run_id)`。Outbox 使用 `bigserial`/identity `id`、`notification_type`、`aggregate_type`、`aggregate_id`、`aggregate_version`、`payload jsonb`、`published_at`、`attempt_count`、`next_attempt_at` 和 `last_error`。

- [ ] **步骤 4：执行两次迁移并验证 Flyway 幂等行为**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=Phase1MigrationTest test
```

预期：第一次迁移应用版本 1；第二次迁移报告没有待执行迁移；所有约束断言均通过。

- [ ] **步骤 5：提交**

```powershell
git -C .\data-agent-v2 add backend/agent-server
git -C .\data-agent-v2 commit -m "feat: add phase one database baseline"
```

### 任务 3：配置 MyBatis-Plus 审计、租户、逻辑删除和 ServiceImpl 规范

**文件：**
- 修改：`data-agent-v2/backend/agent-server/pom.xml`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/context/TenantContext.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/persistence/AuditedEntity.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/persistence/TenantAuditedEntity.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/persistence/AuditMetaObjectHandler.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/config/MybatisPlusConfiguration.java`
- 测试：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/platform/persistence/MybatisPlusAuditIntegrationTest.java`
- 测试夹具：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/platform/persistence/{AuditFixtureEntity,AuditFixtureMapper,AuditFixtureService}.java`

**接口：**
- 输入：Schema 审计列和请求租户上下文。
- 输出：实体审计继承、自动租户写入/过滤、乐观锁，以及业务层只能通过 ServiceImpl 使用持久化的边界。

- [ ] **步骤 1：编写失败的审计和租户集成测试**

```java
@Test
void saveAndUpdateFillAuditAndTenantFields() {
    TenantContext.run("tenant_local", () -> {
        AuditFixtureEntity entity = AuditFixtureEntity.session("session_audit", "Audit");
        auditFixtureService.save(entity);
        assertThat(entity.getCreatedAt()).isEqualTo(INSTANT);
        assertThat(entity.getUpdatedAt()).isEqualTo(INSTANT);
        assertThat(entity.isDeleted()).isFalse();
        assertThat(entity.getTenantId()).isEqualTo("tenant_local");
    });
}

@Test
void tenantInterceptorHidesAnotherTenant() {
    TenantContext.run("tenant_two", () ->
        assertThat(auditFixtureService.getById("session_one")).isNull());
}
```

添加测试证明 `ServiceImpl.removeById(entity)` 同时设置 `is_deleted` 和 `deleted_at`，并添加测试证明 `updateById` 拒绝过期的 `@Version`。

测试夹具只映射阶段 1 的 `agent_session` 表，不进入生产代码：

```java
@TableName("agent_session")
final class AuditFixtureEntity extends TenantAuditedEntity {
    @TableId private String id;
    private String title;
    private String sessionType;
    private String createdBy;
    @Version private long version;

    static AuditFixtureEntity session(String id, String title) {
        AuditFixtureEntity value = new AuditFixtureEntity();
        value.id = id;
        value.title = title;
        value.sessionType = "CHAT";
        value.createdBy = "user_admin";
        return value;
    }
}

@Mapper interface AuditFixtureMapper extends BaseMapper<AuditFixtureEntity> {}
@Service final class AuditFixtureService
    extends ServiceImpl<AuditFixtureMapper, AuditFixtureEntity> {}
```

- [ ] **步骤 2：运行并确认失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=MybatisPlusAuditIntegrationTest test
```

- [ ] **步骤 3：实现共享实体和处理器**

```java
@Getter @Setter
public abstract class AuditedEntity {
    @TableField(fill = FieldFill.INSERT) private Instant createdAt;
    @TableField(fill = FieldFill.INSERT_UPDATE) private Instant updatedAt;
    @TableField(fill = FieldFill.UPDATE) private Instant deletedAt;
    @TableLogic(value = "false", delval = "true")
    @TableField(fill = FieldFill.INSERT) private boolean deleted;
}

@Getter @Setter
public abstract class TenantAuditedEntity extends AuditedEntity {
    @TableField(fill = FieldFill.INSERT) private String tenantId;
}
```

`AuditMetaObjectHandler` 使用注入的 `Clock` 填充审计字段，并从 `TenantContext.requiredTenantId()` 填充 `tenantId`。依次注册 `TenantLineInnerInterceptor`、`OptimisticLockerInnerInterceptor`、`BlockAttackInnerInterceptor`，最后注册 `PaginationInnerInterceptor(DbType.POSTGRE_SQL)`；加入 `mybatis-plus-jsqlparser` 以支持分页和租户解析。

- [ ] **步骤 4：证明业务服务使用 ServiceImpl 而不是 Mapper**

添加 ArchUnit/反射测试，确保 `*.persistence` 之外的类不存在可赋值为 `BaseMapper` 的构造字段。每个具体持久化服务都继承 `ServiceImpl<SpecificMapper, SpecificEntity>`。

- [ ] **步骤 5：运行测试并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=MybatisPlusAuditIntegrationTest test
git -C .\data-agent-v2 add backend/agent-server
git -C .\data-agent-v2 commit -m "feat: establish mybatis plus persistence conventions"
```

### 任务 4：实现最小化数据库认证

**文件：**
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/auth/api/AuthenticationController.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/auth/api/LoginRequest.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/auth/api/AuthSessionResponse.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/auth/application/AuthenticationService.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/auth/security/{SecurityConfiguration,SessionAuthenticationFilter,TenantPrincipal}.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/auth/persistence/*Entity.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/auth/persistence/*Mapper.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/auth/persistence/*PersistenceService.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/auth/application/LocalAdminInitializer.java`
- 测试：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/auth/AuthenticationHttpIntegrationTest.java`

**接口：**
- 输入：`IdGenerator`、MyBatis-Plus 服务、`Clock`、BCrypt、`DATA_AGENT_SESSION` Cookie 契约。
- 输出：`POST /api/v1/auth/login`、`GET /api/v1/auth/session`、`POST /api/v1/auth/logout` 和已认证的 `TenantPrincipal`。

- [ ] **步骤 1：编写失败的 HTTP 契约测试**

```java
@Test
void loginSessionAndLogoutUseTheSharedHttpOnlyCookie() throws Exception {
    MvcResult login = mvc.perform(post("/api/v1/auth/login")
            .contentType(APPLICATION_JSON)
            .content("""{"username":"admin","password":"admin"}"""))
        .andExpect(status().isNoContent())
        .andExpect(header().string("Set-Cookie", containsString("DATA_AGENT_SESSION=")))
        .andExpect(header().string("Set-Cookie", containsString("HttpOnly")))
        .andReturn();
    String cookie = responseCookie(login, "DATA_AGENT_SESSION");
    mvc.perform(get("/api/v1/auth/session").cookie(new Cookie("DATA_AGENT_SESSION", cookie)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.tenantId").value("tenant_local"))
        .andExpect(jsonPath("$.subject").value("admin"))
        .andExpect(jsonPath("$.roles[0]").value("ADMIN"));
}
```

添加密码错误 401 Problem Detail、Cookie 缺失 401、会话过期、会话撤销和退出幂等性测试。

- [ ] **步骤 2：运行并确认 404/Bean 缺失失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=AuthenticationHttpIntegrationTest test
```

- [ ] **步骤 3：实现持久化实体和 ServiceImpl 服务**

每个 Mapper 除 `extends BaseMapper<Entity>` 外保持为空。服务使用 `lambdaQuery()` 和 `lambdaUpdate()` 暴露意图方法：

```java
@Service
final class LoginSessionPersistenceService
        extends ServiceImpl<LoginSessionMapper, LoginSessionEntity> {
    Optional<LoginSessionEntity> activeByTokenHash(String hash, Instant now) {
        return Optional.ofNullable(lambdaQuery()
            .eq(LoginSessionEntity::getTokenHash, hash)
            .isNull(LoginSessionEntity::getRevokedAt)
            .gt(LoginSessionEntity::getExpiresAt, now)
            .one());
    }
}
```

只存储 Token 的 SHA-256 哈希；返回 256 位随机不透明 Cookie 值。密码使用 BCrypt。仅当 `data-agent.bootstrap.local-admin.enabled=true` 时初始化 `tenant_local`、`user_admin`、成员角色 `ADMIN` 和 BCrypt 加密的 `admin`。

- [ ] **步骤 4：实现安全过滤器和端点**

过滤器对 Cookie 进行哈希，加载有效会话/用户/成员关系，安装 `TenantPrincipal`，进入 `TenantContext`，继续执行过滤器链，随后清理两个上下文。Cookie 属性为 `Path=/`、`HttpOnly`、`SameSite=Lax`、可配置的 `Secure` 和最大有效期。

- [ ] **步骤 5：运行测试并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=AuthenticationHttpIntegrationTest test
git -C .\data-agent-v2 add backend/agent-server
git -C .\data-agent-v2 commit -m "feat: add minimal shared authentication"
```

### 任务 5：实现 Session、Message、Run、Event 和 Stream 持久化服务

**文件：**
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/domain/{RunStatus,RunPhase,MessageRole,StreamChannel}.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/persistence/*Entity.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/persistence/*Mapper.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/persistence/*PersistenceService.java`
- 测试：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/conversation/persistence/ConversationPersistenceIntegrationTest.java`

**接口：**
- 输入：MyBatis-Plus 规范、租户上下文和阶段 1 数据表。
- 输出：供 ConversationService 和流式任务使用的事务基础能力。

- [ ] **步骤 1：编写失败的持久化行为测试**

测试以下精确不变量：Session 列表排除已删除行；Message 序列有序；每个 Session 只有一个活动 Run；RunEvent 序列不可重复；RunStream 更新需要当前 `@Version`；一个租户不能读取另一租户的 Session；生命周期事件和 Outbox 保存必须一起回滚。

```java
@Test
void secondActiveRunForTheSameSessionIsRejected() {
    TenantContext.run("tenant_local", () -> {
        runService.save(running("run_one", "session_one"));
        assertThatThrownBy(() -> runService.save(running("run_two", "session_one")))
            .isInstanceOf(DuplicateKeyException.class);
    });
}
```

- [ ] **步骤 2：运行并确认实体/服务缺失失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=ConversationPersistenceIntegrationTest test
```

- [ ] **步骤 3：实现实体和空 BaseMapper 接口**

使用 `@TableName`、`@TableId`、`@Version`、`@EnumValue` 和审计继承。`RunStreamEntity` 字段为：

```java
@TableName("agent_run_stream")
final class RunStreamEntity extends TenantAuditedEntity {
    @TableId private String runId;
    private long executionAttempt;
    private RunPhase phase;
    private long streamSequence;
    private String thinking;
    private String answer;
    @Version private long version;
}
```

- [ ] **步骤 4：实现聚焦的 ServiceImpl 方法**

初始 Run 事件使用 `saveBatch`，历史消息使用 `lambdaQuery().orderByAsc(MessageEntity::getSequence)`，乐观锁检查点使用 `updateById`，终态转换使用 `lambdaUpdate`。任何应用服务都不得接收 Mapper。

- [ ] **步骤 5：运行测试并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=ConversationPersistenceIntegrationTest test
git -C .\data-agent-v2 add backend/agent-server
git -C .\data-agent-v2 commit -m "feat: add conversation persistence services"
```

### 任务 6：实现事务化对话 REST 边界

**文件：**
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/api/AgentSessionController.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/api/AgentDtos.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/api/CreateSessionRequest.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/api/SubmitMessageRequest.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/application/ConversationService.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/application/ConversationExecutionPort.java`
- 测试：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/conversation/api/AgentSessionHttpIntegrationTest.java`

**接口：**
- 输入：认证主体、持久化服务、`IdGenerator`、事务提交后回调。
- 输出：列表/创建/详情/消息 REST 端点，以及 `ConversationExecutionPort.startAfterCommit(tenantId, runId)`。

- [ ] **步骤 1：根据 OpenAPI 示例编写失败的 REST 测试**

```java
@Test
void createSessionThenSubmitMessageReturnsRunningSnapshot() throws Exception {
    String sessionId = createSession("分析销售", "analysis");
    mvc.perform(post("/api/v1/agent-sessions/{id}/messages", sessionId)
            .cookie(authCookie())
            .contentType(APPLICATION_JSON)
            .content("""{"content":"你好，请介绍自己"}"""))
        .andExpect(status().isAccepted())
        .andExpect(jsonPath("$.messages[0].role").value("user"))
        .andExpect(jsonPath("$.run.status").value("running"))
        .andExpect(jsonPath("$.run.stream.phase").value("RECEIVED"));
}
```

添加列表/详情、空标题/内容校验、未知 Session、跨租户不可枚举，以及第二个活动 Run 返回 409 的测试。

- [ ] **步骤 2：运行并确认端点失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=AgentSessionHttpIntegrationTest test
```

- [ ] **步骤 3：定义同节点执行接口**

```java
public interface ConversationExecutionPort {
    void startAfterCommit(String tenantId, String runId);
}
```

`submitMessage` 事务必须保存用户 Message、Run、RunStream、`user_message`、`run_started` 及对应 Outbox 行。注册 `TransactionSynchronization.afterCommit`，并在同一 Spring 实例上调用该端口；不要将 Message/Run ID 放入队列。

- [ ] **步骤 4：实现 Controller 和 DTO 投影**

返回兼容 V1 的 Session/Message/Run/Event 字段以及增量 `run.stream`。`POST /messages` 保持 202；`POST /agent-sessions` 保持 201 并携带 `Location`。阶段 1 中 Metric Identity 字段为 `null`/绑定版本 `0`。

- [ ] **步骤 5：运行测试并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=AgentSessionHttpIntegrationTest test
git -C .\data-agent-v2 add backend/agent-server
git -C .\data-agent-v2 commit -m "feat: add minimal conversation api"
```

### 任务 7：实现 Redis Token 桥接、持久 Outbox 和可重放 SSE

**文件：**
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/cluster/StreamEnvelope.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/cluster/RedisStreamBridge.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/cluster/LocalSseRegistry.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/cluster/OutboxPublisher.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/application/ConversationStreamService.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/platform/config/RedisConfiguration.java`
- 修改：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/api/AgentSessionController.java`
- 测试：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/conversation/cluster/RedisCrossInstanceSseIntegrationTest.java`

**接口：**
- 输入：已持久化的 RunEvent/RunStream/Outbox 和 Redis 主题 `data-agent-v2:stream-events`。
- 输出：`publishDelta(StreamEnvelope)`、本地会话订阅、先重放后实时的 SSE，以及持久生命周期通知。

- [ ] **步骤 1：编写失败的双应用上下文测试**

针对相同 PostgreSQL 和 Redis Testcontainers 启动两个具有不同 `data-agent.instance-id` 的上下文。将 SSE 客户端连接到 B，在 A 上调用测试发布器，并断言 B 收到：

```java
assertThat(received).satisfiesExactly(event -> {
    assertThat(event.type()).isEqualTo("assistant_delta");
    assertThat(event.runId()).isEqualTo("run_demo");
    assertThat(event.executionAttempt()).isEqualTo(1);
    assertThat(event.streamSequence()).isEqualTo(7);
    assertThat(event.delta()).isEqualTo("你好");
});
```

添加重放与实时重叠去重、序列缺口快照修复、过期执行尝试拒绝和订阅者清理测试。

- [ ] **步骤 2：运行并确认 Redis/SSE 类缺失**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=RedisCrossInstanceSseIntegrationTest test
```

- [ ] **步骤 3：实现流信封和 Redis 桥接**

```java
public record StreamEnvelope(
    String sourceInstanceId,
    String tenantId,
    String sessionId,
    String runId,
    long executionAttempt,
    long streamSequence,
    String type,
    String phase,
    String delta,
    Instant occurredAt) {}
```

将每个本地 Token 发布到 Redis 和本地订阅者。忽略来自相同 `sourceInstanceId` 的 Redis 回显。消费者拒绝更低的执行尝试，以及重复/更低的流序列。

- [ ] **步骤 4：不使用自定义领取 SQL 实现持久 Outbox 发布**

`OutboxPublisher` 使用 `NotificationOutboxPersistenceService`。查询到期候选 ID，然后通过带 `publishedAt`、`nextAttemptAt` 和版本条件的 `lambdaUpdate()` 领取每一行。发布生命周期定位载荷并标记成功；失败时增加 `attemptCount` 并进行有界退避。仅将候选扫描包装在以下调用中：

```java
InterceptorIgnoreHelper.execute(
    IgnoreStrategy.builder().tenantLine(true).build(),
    () -> outboxService.lambdaQuery()
        .isNull(NotificationOutboxEntity::getPublishedAt)
        .le(NotificationOutboxEntity::getNextAttemptAt, clock.instant())
        .page(new Page<>(1, 100, false))
        .getRecords());
```

不要为该扫描添加注解或调用自定义 Mapper 方法。

- [ ] **步骤 5：实现 SSE 先订阅后重放**

发送初始注释，订阅本地注册表，读取当前 Run 事件和 RunStream 快照，发送快照后继续实时传输。完成/错误/超时时关闭订阅。Run 进入终态后，会话 SSE 仍保持打开。

- [ ] **步骤 6：运行测试并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=RedisCrossInstanceSseIntegrationTest test
git -C .\data-agent-v2 add backend/agent-server
git -C .\data-agent-v2 commit -m "feat: stream events across v2 instances"
```

### 任务 8：在写入消息的节点流式输出 Ollama 思考和回答 Token

**文件：**
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/model/ModelGateway.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/model/ModelRequest.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/model/ModelDelta.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/model/OllamaStreamingModelGateway.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/application/ConversationExecutionService.java`
- 创建：`data-agent-v2/backend/agent-server/src/main/java/com/datagent/agentv2/conversation/application/RunTimeoutService.java`
- 创建：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/conversation/model/OllamaStreamingModelGatewayTest.java`
- 创建：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/conversation/application/ConversationExecutionIntegrationTest.java`
- 创建：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/conversation/model/RealOllamaSmokeTest.java`

**接口：**
- 输入：Spring AI `StreamingChatModel`、已存储历史、流桥接/检查点服务。
- 输出：`Flux<ModelDelta> ModelGateway.stream(ModelRequest)`、同节点执行，以及最终 Message/Run 生命周期。

- [ ] **步骤 1：编写失败的网关分通道测试**

```java
@Test
void mapsThinkingMetadataAndAnswerTextToSeparateChannels() {
    when(streamingModel.stream(any(Prompt.class))).thenReturn(Flux.just(
        response("先分析", ""),
        response("", "你好"),
        response("", "！")));
    StepVerifier.create(gateway.stream(request))
        .expectNext(new ModelDelta(StreamChannel.THINKING, "先分析"))
        .expectNext(new ModelDelta(StreamChannel.ANSWER, "你好"))
        .expectNext(new ModelDelta(StreamChannel.ANSWER, "！"))
        .verifyComplete();
}
```

测试夹具为具体实现且不调用 Ollama：

```java
private static ChatResponse response(String thinking, String text) {
    ChatResponse response = mock(ChatResponse.class, RETURNS_DEEP_STUBS);
    when(response.getResult().getMetadata().get("thinking")).thenReturn(thinking);
    when(response.getResult().getOutput().getText()).thenReturn(text);
    return response;
}
```

Spring AI Ollama 的思考内容从 `ChatResponse.getResult().getMetadata().get("thinking")` 读取；回答内容从 `getOutput().getText()` 读取。

定义不包含 Spring AI 类型的网关输入：

```java
public record ModelRequest(String model, String systemPrompt, List<ModelMessage> messages) {
    public ModelRequest {
        messages = List.copyOf(messages);
    }
    public record ModelMessage(MessageRole role, String content) {}
}
```

阶段 1 只允许 `USER` 和 `ASSISTANT` 历史，以及独立的系统提示词。

- [ ] **步骤 2：编写失败的执行集成测试**

断言精确阶段顺序为 `RECEIVED`、`PREPARING_CONTEXT`、`CONNECTING_MODEL`、`THINKING`、`ANSWERING`、`PERSISTING`、`COMPLETED`；Token 序列单调递增；检查点包含累计文本；最终助手 Message 只包含回答；Ollama 错误产生 `FAILED` 和 `run_failed`；其他实例不得执行该 Run。

- [ ] **步骤 3：运行并确认失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest='OllamaStreamingModelGatewayTest,ConversationExecutionIntegrationTest' test
```

- [ ] **步骤 4：实现模型网关**

使用已配置系统消息和有界的近期完整用户/助手 Message 构建 `Prompt`。使用 `OllamaChatOptions.builder().model(model).enableThinking().build()`。不要注册 Tool 回调。在保留提供方顺序的同时过滤空增量。

- [ ] **步骤 5：实现同节点事务提交后执行和检查点**

`ConversationExecutionService` 实现 `ConversationExecutionPort`。使用具名本地执行器/Reactor 调度器，恢复租户/请求关联，且绝不扫描数据库领取任务。每发出一个模型分块就递增 `streamSequence` 并立即发布；每 100ms 或 32 个分块写入累计文本检查点。最终持久化前确认 Run 仍为活动状态且执行尝试匹配。

- [ ] **步骤 6：实现失败和陈旧 Run 超时语义**

Ollama 错误/超时持久化 `run_failed` 和 `FAILED`。定时看门狗只能将超过已配置硬截止时间的 Run 标记为失败，绝不能调用模型。其候选扫描使用与 Outbox 相同的作用域模式 `InterceptorIgnoreHelper.execute(IgnoreStrategy.builder().tenantLine(true).build(), supplier)`，绝不全局禁用租户处理。

- [ ] **步骤 7：添加可选的真实 Ollama 冒烟测试**

使用 `@EnabledIfEnvironmentVariable(named = "RUN_REAL_OLLAMA", matches = "true")` 保护。`OLLAMA_BASE_URL` 默认为 `http://localhost:11434`，模型使用 `qwen3.5:9b`；断言至少一个非空思考增量、至少一个非空回答增量，以及非空最终回答。

- [ ] **步骤 8：运行确定性测试并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest='OllamaStreamingModelGatewayTest,ConversationExecutionIntegrationTest' test
git -C .\data-agent-v2 add backend/agent-server
git -C .\data-agent-v2 commit -m "feat: stream ollama thinking and answers"
```

### 任务 9：迁移最小化登录与流式对话前端

**文件：**
- 创建/迁移：`data-agent-v2/frontend/package.json`
- 创建/迁移：`data-agent-v2/frontend/package-lock.json`
- 创建/迁移：`data-agent-v2/frontend/index.html`
- 创建/迁移：`data-agent-v2/frontend/tsconfig.json`
- 创建/迁移：`data-agent-v2/frontend/tsconfig.node.json`
- 创建/迁移：`data-agent-v2/frontend/vite.config.ts`
- 创建/迁移：`data-agent-v2/frontend/vitest.config.ts`
- 创建/迁移：`data-agent-v2/frontend/src/main.tsx`
- 创建/迁移：`data-agent-v2/frontend/src/AuthenticatedApp.tsx`
- 创建/迁移：`data-agent-v2/frontend/src/App.tsx`
- 创建/迁移：`data-agent-v2/frontend/src/api/authClient.ts`
- 创建/迁移：`data-agent-v2/frontend/src/api/backendAgentClient.ts`
- 创建/迁移：`data-agent-v2/frontend/src/domain/agentPrototype.ts`
- 创建：`data-agent-v2/frontend/src/components/RunTimeline.tsx`
- 创建/迁移：`data-agent-v2/frontend/src/auth.css`
- 创建/迁移：`data-agent-v2/frontend/src/styles.css`
- 测试：`data-agent-v2/frontend/src/AuthenticatedApp.test.tsx`
- 测试：`data-agent-v2/frontend/src/App.streaming.test.tsx`
- 测试：`data-agent-v2/frontend/src/api/backendAgentClient.test.ts`

**接口：**
- 输入：阶段 1 认证/会话 REST 和 SSE 契约。
- 输出：登录/退出、会话列表/创建/详情、消息提交、思考时间线、回答草稿和刷新恢复界面。

- [ ] **步骤 1：仅复制已跟踪的最小前端基线**

以 V1 `develop` 为来源，但只复制包/构建配置、`main.tsx`、`AuthenticatedApp.tsx`、`authClient.ts`、`backendAgentClient.ts` 的对话子集、所需领域类型、App 对话标记和所需样式。不要复制 Metric Identity 客户端/组件、Artifact 客户端/组件、调度客户端/页面、确认/密钥交互组件或生成的 `node_modules`/`dist`。

验证迁移后的导入图：

```powershell
rg -n 'metricIdentity|scheduledTask|artifactClient|SecretInput|Confirmation' `
  .\data-agent-v2\frontend\src
```

预期：不存在运行时导入；仅在有意断言不支持能力已移除时，测试描述中才可提及这些能力。

- [ ] **步骤 2：编写失败的事件 Reducer 测试**

```ts
it('keeps thinking and answer streams separate and ordered', () => {
  let session = runningSession();
  session = applyBackendAgentEvent(session, 'session_demo', delta('reasoning_delta', 1, '先'));
  session = applyBackendAgentEvent(session, 'session_demo', delta('assistant_delta', 2, '你好'));
  expect(session.run?.stream.thinking).toBe('先');
  expect(session.run?.stream.answer).toBe('你好');
  expect(session.run?.stream.sequence).toBe(2);
});
```

添加以下测试：`run_phase_changed`、拒绝重复/更低序列、较高执行尝试重置、出现缺口后替换流快照、最终助手消息去重和认证降级。

- [ ] **步骤 3：运行并确认 Reducer/组件失败**

```powershell
npm --prefix .\data-agent-v2\frontend ci
npm --prefix .\data-agent-v2\frontend test
```

- [ ] **步骤 4：实现最小 API/领域投影**

定义：

```ts
export interface RunStream {
  executionAttempt: number;
  phase: RunPhase;
  sequence: number;
  thinking: string;
  answer: string;
}
```

监听 `run_phase_changed`、`reasoning_delta`、`assistant_delta`、`assistant_message`、`run_completed` 和 `run_failed`。Run 活动期间，回答草稿渲染在助手消息区域；思考文本和阶段列表渲染在 `RunTimeline` 中。

- [ ] **步骤 5：保留现有视觉语言，但不迁移无关页面**

复用 V1 的认证卡片、会话侧栏、对话头部、输入区、消息气泡、思考区块、间距、颜色和响应式行为。删除未使用的导航项和导入，不要留下空 UI 外壳。

- [ ] **步骤 6：运行全部前端检查并提交**

```powershell
npm --prefix .\data-agent-v2\frontend run format:check
npm --prefix .\data-agent-v2\frontend test
npm --prefix .\data-agent-v2\frontend run build
git -C .\data-agent-v2 add frontend .prettierignore
git -C .\data-agent-v2 commit -m "feat: migrate minimal streaming chat frontend"
```

### 任务 10：添加本地双实例 Nginx 拓扑

**文件：**
- 创建：`data-agent-v2/infra/compose.yml`
- 创建：`data-agent-v2/infra/nginx.conf`
- 创建：`data-agent-v2/infra/postgres-init.sql`
- 创建：`data-agent-v2/infra/Dockerfile.server`
- 创建：`data-agent-v2/infra/Dockerfile.web`
- 修改：`data-agent-v2/backend/agent-server/src/main/resources/application-local.yml`
- 修改：`data-agent-v2/frontend/vite.config.ts`
- 测试：`data-agent-v2/backend/agent-server/src/test/java/com/datagent/agentv2/acceptance/CrossInstanceConversationTest.java`

**接口：**
- 输入：服务镜像/JAR、PostgreSQL、单机 Redis、Ollama 主机端点。
- 输出：Nginx 源 `http://localhost:8080`、内部副本 `agent-v2-a:8080` 和 `agent-v2-b:8080`，以及指向 Nginx 的 Vite `/api` 代理。

- [ ] **步骤 1：编写跨实例验收测试**

测试必须明确将 SSE 连接到实例 B，向实例 A 提交 Message，在 A 上使用假 Ollama 流，并断言 B 依次转发阶段、思考、回答和完成事件。同时断言两个实例都接受同一登录 Cookie。

- [ ] **步骤 2：在拓扑/配置存在前运行并确认失败**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=CrossInstanceConversationTest test
```

- [ ] **步骤 3：为 REST 和 SSE 配置 Nginx**

```nginx
upstream data_agent_v2 {
    server agent-v2-a:8080;
    server agent-v2-b:8080;
}

location /api/ {
    proxy_pass http://data_agent_v2;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Request-Id $request_id;
}

location ~ ^/api/v1/agent-sessions/.*/events$ {
    proxy_pass http://data_agent_v2;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 30m;
}
```

不要使用 `ip_hash`、粘性 Cookie、服务注册中心或浏览器直连副本 URL。

- [ ] **步骤 4：配置 Compose 服务和就绪检查**

`Dockerfile.server` 使用 Maven Wrapper 构建 `agent-server` 并运行可执行 JAR。`Dockerfile.web` 使用 `npm ci && npm run build` 构建 `frontend/dist`，将其复制到 Nginx 并安装 `nginx.conf`。Compose 包含 PostgreSQL、Redis、`agent-v2-a`、`agent-v2-b` 和 Nginx/Web 服务。两个副本共享 DB/Redis/Ollama 配置，但具有不同的 `DATA_AGENT_INSTANCE_ID`。就绪检查包含 PostgreSQL 和 Redis；存活检查只检查进程。

- [ ] **步骤 5：让 Vite 指向 Nginx 源**

```ts
server: {
  host: '127.0.0.1',
  proxy: { '/api': 'http://127.0.0.1:8080' },
}
```

- [ ] **步骤 6：运行验收测试并提交**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml `
  -pl agent-server -Dtest=CrossInstanceConversationTest test
git -C .\data-agent-v2 add infra backend/agent-server frontend/vite.config.ts
git -C .\data-agent-v2 commit -m "feat: add local multi-instance topology"
```

### 任务 11：验证完整的阶段 1 垂直切片

**文件：**
- 修改：`data-agent-v2/README.md`
- 创建：`data-agent-v2/docs/phase-1-verification.md`

**接口：**
- 输入：阶段 1 的全部后端、前端、契约和拓扑任务。
- 输出：可复现的自动验证和真实 Ollama 手工检查清单。

- [ ] **步骤 1：记录精确的启动和验证命令**

```powershell
docker compose -f .\infra\compose.yml up -d postgres redis agent-v2-a agent-v2-b nginx
npm --prefix .\frontend ci
npm --prefix .\frontend run dev
```

记录本地登录账号 `admin/admin`、Nginx 源、Ollama 端点/模型覆盖方式，以及如何按 `requestId`、`sessionId`、`runId` 和 `instanceId` 检查两个实例的日志。

- [ ] **步骤 2：运行后端聚焦验证和聚合验证**

```powershell
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml -B `
  -pl agent-server -Dtest='*Contract*Test,*MigrationTest,*Authentication*Test,*Conversation*Test,*Redis*Test' test
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml -B verify
```

预期：全部确定性测试和两个模块均通过。

- [ ] **步骤 3：运行全部前端检查**

```powershell
npm --prefix .\data-agent-v2\frontend ci
npm --prefix .\data-agent-v2\frontend run format:check
npm --prefix .\data-agent-v2\frontend test
npm --prefix .\data-agent-v2\frontend run build
```

预期：每个命令均以退出码 0 结束。

- [ ] **步骤 4：运行显式真实 Ollama 冒烟测试**

```powershell
$env:RUN_REAL_OLLAMA='true'
$env:OLLAMA_BASE_URL='http://localhost:11434'
$env:OLLAMA_MODEL='qwen3.5:9b'
.\data-agent-v2\backend\mvnw.cmd -f .\data-agent-v2\backend\pom.xml -B `
  -pl agent-server -Dtest=RealOllamaSmokeTest test
```

预期：测试观察到非空思考流、非空回答流和非空最终回答。

- [ ] **步骤 5：通过 Nginx 执行浏览器验收路径**

验证：登录；创建 Session；发送两轮消息；看到阶段转换；增量看到思考；增量看到回答；Run 执行期间刷新并从检查点恢复；完成后刷新且保留历史；短暂停止 Redis 并观察基于检查点的降级更新/最终恢复；停止执行副本并观察 Run 超时失败，且模型不被其他节点接管。

- [ ] **步骤 6：提交、推送子仓并更新根仓 Git 链接**

```powershell
git -C .\data-agent-v2 add README.md docs/phase-1-verification.md
git -C .\data-agent-v2 commit -m "docs: record phase one verification"
git -C .\data-agent-v2 push origin develop
git add data-agent-v2
git commit -m "build: advance data agent v2 phase one"
```

- [ ] **步骤 7：分别检查根仓和子仓**

```powershell
git -C .\data-agent-v2 status --short
git status --short --ignore-submodules=none
git -C .\data-agent-v2 log --oneline --decorate -12
git diff HEAD^ --submodule=log
```

预期：子仓工作区干净；根仓不包含意外的 V1 或 Metric Platform 改动。
