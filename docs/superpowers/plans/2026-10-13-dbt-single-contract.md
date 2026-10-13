# dbt 统一执行快照实施计划

设计依据：[统一执行快照契约](../specs/2026-10-13-dbt-single-contract-design.md)。执行方式：本会话顺序执行。用户后续决定已替代原计划中的版本前缀、旧数据兼容和排空门禁。

## 任务 1：服务统一契约

- [x] HTTP、CLI、构建、部署、目录、查询和版本查询收敛为无版本号接口。
- [x] 只受理完整 execution，删除旧请求/绑定注册、协议分支和历史升级入口。
- [x] schema.sql 直接定义新库；worker/查询按冻结快照执行，不回退全局 profile。
- [x] 保留幂等、generation/CAS、来源核验、物理归属与结果未知保护。
- [x] 原业务测试迁移到完整快照，增加旧字段拒绝、无版本路径和恢复回归。

验证：服务单元/API/持久化测试、Ruff、真实 PostgreSQL/dbt 四种查询。

## 任务 2：Agent 全链路配置与恢复

- [x] 项目和配置 API 保存 previewExecution、productionExecution，严格拒绝旧字段。
- [x] 预览/交付冻结完整执行快照；客户端无版本号调用并校验响应身份。
- [x] 持久会话构建解析、前端展示、OpenAPI 和契约样本同步更新。
- [x] 覆盖响应丢失后配置改变仍复用原请求的恢复场景。

验证：dbt 客户端、开发模块、Web/Server 契约测试，真实 Git 保存/预览/交付测试，前端测试和构建。

## 任务 3：Metric Platform 统一代理

- [x] Controller、HTTP Gateway、OpenAPI、前端统一 `/api/dbt`。
- [x] 构建与部署按环境 UUID 读取；唯一构建详情入口返回完整 execution。
- [x] 固定 buildId 的目录、查询和部署切换保持一致，更新浏览器测试。

验证：完整 Maven package、前端测试/构建和 Playwright 发布流程。

## 任务 4：共享验证与文档

- [x] 21 个权威样本与两端副本一致；所有相关文件名不带协议版本。
- [x] 配置校验、preflight、Flow、Regression 与隔离 runner 使用完整快照。
- [x] README、部署说明、设计和计划采用唯一契约，不要求历史数据迁移。
- [x] 完成最终真实三端隔离闭环与只读代码审查，处理必要发现。
- [x] 分别核对四个仓库差异，精确提交本计划文件，保留用户既有变更和 Git 链接。

构建命令以各仓库 README 为准。运行日志保存在本任务系统临时目录；最终验证结果在交付中说明。既有 vendor 固定提交审计失败须单独报告，不修改第三方代码或放宽检查。

## 最终验证（2026-10-14）

- 服务：433 个测试通过、4 个可选集成测试跳过；真实 PostgreSQL/dbt/MetricFlow 四种查询集成测试另行通过；Ruff 通过。唯一失败是既有 MetricFlow vendor 提交审计：仓库原 Git 链接为 `9a07d35`，测试期望 `05551f7`，本计划未修改任何 vendor 或审计断言。
- Agent：相关客户端、开发、Web/Server 测试及 Maven package 通过；真实 Git 预览与交付集成覆盖原请求恢复、配置变化不影响已受理快照。前端 100 个测试及完整构建通过。
- Metric Platform：完整 Maven package 和最终契约/HTTP 边界回归通过；前端 141 个测试、类型检查及 Vite 打包通过；8 个发布浏览器用例通过。默认前端 build 的格式门禁仍发现 51 个未修改文件的既有格式问题，本次差异与这些文件无交集。
- 三端隔离闭环通过：真实 Git 保存、预览、合并后的正式构建、目录及四种查询、非法 YAML 不改原部署、跨仓库隔离、push/merge/build 回执丢失后恢复原身份、平台离线时 Agent 继续预览、平台重启实时读取历史。真实 PostgreSQL 浏览器查询通过，旧路由 404 和旧字段 422 回归通过。
- 21 个服务权威样本与两端副本一致；共享配置自检和 Regression 自检通过。
- 只读审查发现并修复平台回执缺少源码身份校验；当前完整核验 execution、repository、branchName、requestedCommitSha、非空解析 SHA 及有效构建状态后才记录 buildId。

产品提交：dbt-service `75da1e7`、Data Agent V2 `5e5c79d`、Metric Platform `5acbf08`。各仓库仅提交本计划修改；平台预先暂存的 115 项 AD 文件保持原索引内容和工作区状态，根仓库不固定新的子模块版本。未推送。
