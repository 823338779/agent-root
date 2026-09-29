# StarRocks 固定 schema 的 dbt 发布实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 电商 dbt 构建统一写入 `dbt_ecom`，每个 run 使用独立版本表；验证后切换平台活动发布，失败时旧数据可立即查询。

**Architecture:** 运行服务从受控绑定取得固定 schema，在已校验 Git 摘要的任务副本中注入表别名规则，并用 run ID 隔离物理对象。Metric Platform 继续在 PostgreSQL 事务中切换 `activeReleaseId`，只对活动版本接受新目录和查询请求；清理由运行服务根据 run 前缀回收，旧 `run_...` schema 保持兼容。

**Tech Stack:** Python 3.12、dbt-core 1.12.5、dbt-starrocks 1.12.2、MetricFlow 0.213.0、StarRocks、PostgreSQL、Java 21/Spring Boot、React/TypeScript。

**Spec:** `docs/superpowers/specs/2026-09-30-fixed-starrocks-schema-design.md`

## 全局约束

- 固定目标 schema 为 `dbt_ecom`；原始数据保持在 `ecommerce_raw`，不归 dbt 管理。
- 新 run 的物理对象名称为 `rv_<runId>_<原别名>`，其中 runId 使用无连字符的小写 UUID；不得清理其他 run 的对象。
- 构建失败不改变活动指针或旧表；历史发布保留元数据，但新目录和查询返回 410。
- 构建仅接受受控 Git `main` 的固定 SHA；HTTP 请求不能指定 schema、前缀或连接信息。
- 不修改 vendored dbt/MetricFlow 源码；不添加依赖；不创建额外 worktree。
- 当前工作区有既存改动，逐项检查并只处理本计划直接涉及的文件。
- 产品代码分别留在 `dbt-metricflow-service/` 和 `metric-platform/`；跨产品说明放在根 `docs/`。根仓规则禁止未经用户明确要求创建提交；计划执行完毕时按根仓的计划提交规则处理一次提交，不逐任务提交。

## 评审重点

- 同一个幂等键再次提交：必须复用原 run ID 和物理表前缀；见任务 2。
- 过长、非法或自定义的 dbt alias/schema：必须在写表之前拒绝；见任务 1、2。
- 构建中途失败且没有完整 manifest：清理只触及该 run 前缀；见任务 3。
- 发布切换与旧查询同时发生：已受理查询完成后才能清理旧表；见任务 5。
- 旧 `run_...` 活动版本迁移失败：旧指针和旧 schema 保持可用；见任务 3、4、7。

---

## 文件职责

- `dbt-metricflow-service/src/dbt_metricflow_service/platform_bindings.py`、`admin.py`：解析并登记服务端 `schemaName` 绑定。
- 新增 `dbt-metricflow-service/src/dbt_metricflow_service/platform_namespace.py`：run 前缀、受控宏注入、解析后物理关系校验；供本地和持久运行路径共用。
- `platform_runs.py`、`runtime.py`、`runtime_execution.py`、`platform_metricflow.py`：两条构建路径、READY 校验和双格式清理。
- `metric-platform/backend/metric-core/.../ReleaseWorkflow.java`、`PublicationGateway.java`，`metric-app/.../GitSyncProperties.java`、`ReleaseCoordinator.java`，`metric-persistence/.../PublicationStore.java`：固定 schema 配置与发布校验。
- `metric-platform/backend/metric-persistence/.../CatalogReadStore.java`、`CleanupStore.java`，`metric-app/.../QueryService.java`：只读活动版本与安全回收。
- `metric-platform/frontend/src/features/dbt/`、`metric-platform/api/openapi.yaml`、三个仓库 README/运行说明：页面、公开契约和部署说明。

### 任务 1：受控 schema 绑定与版本命名

**文件：** `dbt-metricflow-service/src/dbt_metricflow_service/platform_bindings.py`、`admin.py`；新增 `platform_namespace.py`；测试 `tests/test_platform_bindings.py`、`tests/test_runtime_api.py`、新增 `tests/test_platform_namespace.py`。

**接口：** `ProjectBinding.schema_name: str | None`；`run_prefix(run_id: UUID) -> str` 返回 `rv_<32位hex>_`；`prepare_versioned_project(project: Path, run_id: UUID, schema: str) -> str` 返回该前缀。未配置 `schemaName` 的现有项目仍使用独立 `run_...` schema。

- [ ] 先补 `test_fixed_schema_binding`、`test_run_prefix_is_deterministic`、`test_rejects_unsafe_namespace`：断言 `schema_name == "dbt_ecom"`、`run_prefix(run_id) == "rv_" + run_id.hex + "_"`；含连字符、空值、越界名称、同名 `generate_alias_name` 宏及越界 alias 均抛 `ValueError`；HTTP 请求不能覆盖绑定 schema。
- [ ] 从 `dbt-metricflow-service/` 运行 `uv run --frozen pytest -q tests/test_platform_bindings.py tests/test_runtime_api.py tests/test_platform_namespace.py`，确认新增断言失败。
- [ ] 在服务配置读取处增加可选 `schemaName` 与 StarRocks 标识符校验；仅在任务副本中注入 `macros/generate_alias_name.sql`，保持原 Git 输入摘要。宏对 model、seed、snapshot 使用前缀，保留合法原 alias；若项目已有同名宏或命名超出 StarRocks 限制则提前拒绝。禁止受控宏被包覆盖。
- [ ] 重跑上述测试，确认全部通过；`uv run --frozen ruff check src tests` 通过。

### 任务 2：两条构建路径的预检与 READY 证明

**文件：** `dbt-metricflow-service/src/dbt_metricflow_service/platform_runs.py`、`runtime.py`、`runtime_execution.py`、`platform_namespace.py`；测试 `tests/test_platform_runs.py`、`tests/test_runtime_execution.py`、`tests/integration/test_postgres_platform_flow.py`。

**接口：** `validate_versioned_manifest(target: Path, schema: str, prefix: str) -> None` 检查全部非 ephemeral 的 model、seed、snapshot；`validate_artifacts(target, schema, *, query_probe_passed, table_prefix: str | None = None)` 兼容旧 run。

- [ ] 先补 `test_fixed_schema_run_reuses_idempotency_key`、`test_parse_rejects_unscoped_relation_before_build`、`test_ready_requires_own_prefix`：断言新 job 的 `schema_name == "dbt_ecom"`、同一幂等键 `runId` 相同；可写节点 schema 错误、无 run 前缀、relation 不匹配或同名冲突时 `dbt build` 调用次数为零；READY 只接受本 run 的 relation。
- [ ] 运行 `uv run --frozen pytest -q tests/test_platform_runs.py tests/test_runtime_execution.py tests/test_platform_namespace.py`，确认新增断言失败。
- [ ] 本地协调器与持久 worker 都在 `resolve_revision`/产物恢复后调用 `prepare_versioned_project`，执行 `dbt deps` 后、`dbt build` 前执行完整 `dbt parse` 和 `validate_versioned_manifest`，再运行原有 build、docs、探针和扩展后的 READY 校验。将 schema 与 run 前缀从持久 run ID 推导，不从请求读取；旧格式 run 沿用原流程。
- [ ] 重跑目标测试，并在已配置测试 PostgreSQL 时运行 `uv run --frozen pytest -q tests/integration/test_postgres_platform_flow.py`；验证 manifest、semantic manifest 与预览 relation 都使用 `dbt_ecom.rv_<runId>_...`。

### 任务 3：按 run 前缀清理并兼容旧 schema

**文件：** `dbt-metricflow-service/src/dbt_metricflow_service/platform_metricflow.py`、`platform_runs.py`、`runtime_execution.py`；测试 `tests/test_platform_cleanup.py`、`tests/test_runtime_execution.py`、`tests/test_runtime_storage.py`。

**接口：** 程序化 `CLEANUP` 输入保留 `schema`；新格式额外传 `tablePrefix=run_prefix(parent_run_id)`。仅旧 `run_<runId>` 格式允许 `drop_schema`；新格式通过 adapter 列举 `dbt_ecom` 对象，逐个删除名称完全以本 run 前缀开头的关系。

- [ ] 先补 `test_cleanup_only_own_prefix_without_manifest`、`test_cleanup_legacy_schema`、`test_cleanup_blocks_active_query`：断言 manifest 缺失仍删除本 run 表/视图，但别的 run、无前缀对象、`ecommerce_raw` 和 `dbt_ecom` 本身保持；重复清理无副作用；旧 `run_...` 继续按旧路径清理；活跃查询与未确认外部 attempt 仍阻止清理。
- [ ] 运行 `uv run --frozen pytest -q tests/test_platform_cleanup.py tests/test_runtime_execution.py tests/test_runtime_storage.py`，确认新增断言失败。
- [ ] 在两条清理路径中从持久 run ID/原始 schema 判别新旧格式，输入受控前缀；程序化 worker 校验 schema、run ID 和前缀的一致性后使用 adapter 的关系列举与 `drop_relation`，每个对象单独幂等处理，决不对 `dbt_ecom` 调用 `drop_schema`。
- [ ] 重跑目标测试；额外验证进程中断后重试与已清理状态均返回成功。

### 任务 4：平台固定 schema 发布校验

**文件：** `metric-platform/backend/metric-core/src/main/java/com/metricplatform/publication/ReleaseWorkflow.java`、`PublicationGateway.java`；`metric-app/src/main/java/com/metricplatform/gitsync/GitSyncProperties.java`、`publication/ReleaseCoordinator.java`；`metric-persistence/src/main/java/com/metricplatform/persistence/publication/PublicationStore.java`；测试 `metric-platform/backend/metric-app/src/test/java/com/metricplatform/publication/ReleaseCoordinatorTest.java`、`PublicationFlowTest.java`。

**接口：** `ReleaseWorkflow.Config` 新增 `schemaName`；`PublicationGateway.promote(..., String expectedSchemaName)` 与实现同步。`schemaName` 由部署配置 `metric-platform.git-sync.schema-name` 提供，`dbt_ecom` 项目必须与运行服务绑定相同；空值维持旧项目规则。

- [ ] 先补 `fixedSchemaPublishesSecondRun`、`wrongSchemaKeepsActiveRelease`、`legacySchemaStillMustBeUnique`：断言两个不同 run 都用 `dbt_ecom` 时第二次指针切换成功；`run_...`、空 schema、重复物理 run 或 relation 证明不完整时指针和目录不变；旧模式仍拒绝重复独立 schema。
- [ ] 从 `metric-platform/` 运行 `mvn -B -pl backend/metric-app,backend/metric-persistence -am -Dtest=ReleaseCoordinatorTest,PublicationFlowTest -Dsurefire.failIfNoSpecifiedTests=false test`；确认新增断言失败。
- [ ] 将固定 schema 贯穿配置、workflow 和发布端口；在 `PublicationStore` 校验目标值，并仅在固定模式放宽“同 schema 不可重复发布”限制。保留原事务的候选状态、目录导入及活动指针 CAS，不能从 HTTP 请求或 Git 文件获取目标 schema。
- [ ] 重跑目标测试，并验证相同 schema 不导致不同 run 共用物理表；平台只信任运行服务在 READY 中提供的完整 relation 证明。

### 任务 5：历史版本拒绝新查询与清理时序

**文件：** `metric-platform/backend/metric-persistence/src/main/java/com/metricplatform/persistence/catalog/CatalogReadStore.java`、`store/CleanupStore.java`；`metric-app/src/main/java/com/metricplatform/query/QueryService.java`；测试 `metric-app/.../PublicationFlowTest.java`、`metric-app/.../ReleaseCleanupServiceTest.java` 与 `metric-persistence` 目录/清理测试。

**接口：** `CatalogReadStore.resolvePublished(projectId, requestedReleaseId)` 在已发布但非活动版本时抛 `ReleaseGoneException`；`GET /releases` 与 `GET /releases/{releaseId}` 保留元数据。已受理查询的 `GET` 不因指针切换中断。

- [ ] 先补 `historicalReleaseRejectsNewReads`、`acceptedQueryCompletesAfterPromotion`、`cleanupWaitsForInflightQuery`：断言旧 `releaseId` 的目录、定义、血缘、指标、解释、选项、维度值和预览请求均为 410；已受理查询仍可轮询完成；`PENDING/RUNNING` 查询阻止清理，完成后可清理旧 run，不再保留“上一个成功版本”。
- [ ] 运行 `mvn -B -pl backend/metric-app,backend/metric-persistence -am -Dtest=PublicationFlowTest,ReleaseCleanupServiceTest -Dsurefire.failIfNoSpecifiedTests=false test`，确认新增断言失败。
- [ ] 用项目活动指针约束 `resolvePublished`，保留已受理任务结果路径；从 `CleanupStore.claim` 移除上一个成功版本保护，保留活动 run、在途查询及服务端认领锁。
- [ ] 重跑目标测试，确认迁移时旧活动 `run_...` 在第一次成功切换前不会被回收。

### 任务 6：页面、OpenAPI 与运行说明

**文件：** `metric-platform/frontend/src/features/dbt/DbtCatalogPage.tsx`、`DbtQueryPage.tsx` 及对应测试；`metric-platform/api/openapi.yaml`、`metric-platform/docs/dbt-publication.md`、`metric-platform/README.md`；`dbt-metricflow-service/README.md`；`metrics_store/README.md`。

- [ ] 先补 `showsHistoricalReleaseRecordWithoutQuery`、`linksToActiveRelease`：断言历史发布只显示记录与当前发布入口，`getDbtCatalog`/`submitDbtQuery` 调用次数为零；项目入口默认活动 release，旧链接收到 410 显示明确提示。核对 OpenAPI 中全部受影响端点的 410 与发布元数据行为。
- [ ] 从 `metric-platform/frontend/` 运行 `npm test -- --run DbtCatalogPage.test.tsx DbtQueryPage.test.tsx`，确认新增断言失败。
- [ ] 将历史发布的查询入口和说明改为只读记录/返回当前版本入口；同步 OpenAPI 描述与三个仓库的中文配置、迁移及权限说明。明确 `dbt_ecom` 需预建或由受控运行账号创建，`ecommerce_raw` 仅只读，配置版本升级触发新构建。
- [ ] 重跑前端目标测试和 `npm run build`；检查 OpenAPI 契约测试与页面文案一致。

### 任务 7：跨服务验收与收尾

**文件：** 仅修复本计划验证发现的问题；必要时扩展 `dbt-metricflow-service/tests/test_starrocks_e2e.py` 与现有平台端到端测试。不得把模拟原始表交给 dbt 管理。

- [ ] 在隔离的真实 StarRocks 测试环境中完成两次不同提交的完整构建与发布，检查 `SHOW DATABASES` 不新增 `run_...`，两组表暂时共存于 `dbt_ecom`，`order_count` 查询在切换前后分别读取对应 run。
- [ ] 注入一次构建失败，验证旧活动 release、旧表与查询可用；确认失败候选只清理自己的前缀。随后成功发布并验证旧 `releaseId` 新请求 410、发布元数据仍可读、在途查询完成后旧组表清理。
- [ ] 验证从现有独立 schema 活动版本迁移：首个固定 schema 构建失败保留旧版，成功后才切换并回收旧 schema。若真实测试环境不可用，记录 SKIPPED 与未验证风险，不能宣称真实库验收通过。
- [ ] 按 README 执行受影响模块的 Python、Maven、前端测试；分别检查根仓、`metric-platform/`、`dbt-metricflow-service/`、`metrics_store/` 的状态与差异，不纳入已有无关改动。
- [ ] 按根仓 `AGENTS.md` 的计划执行完成规则整理一次提交，提交信息描述固定 schema 发布；提交前确认本次修改范围与用户既存改动的归属。
