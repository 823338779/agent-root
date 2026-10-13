# dbt-service 统一执行快照契约

## 已确认的边界

本设计依据用户最终决定：三端一律使用完整执行快照契约；接口和本任务相关文件名不携带协议版本号；服务尚未上线，不兼容旧协议或旧持久化数据。在当前工作区顺序实施，不创建 worktree，不推送。Data Agent 与 Metric Platform 分别调用 dbt-service，禁止直接交互。

## 公开接口与模型

dbt-service 使用 `/builds`、`/deployments`、`/query`、`/versions`；健康接口仍为 `/health/live`、`/health/ready`。Metric Platform 的代理和环境管理统一为 `/api/dbt`。Agent 自身会话 API 保持既有路径，本次仅收敛 dbt 契约。

每次构建携带 repository、branchName、可选完整 commitSha、deploymentPolicy、idempotencyKey 及完整 execution。快照包含 environmentId（UUID）、configVersion（正整数）、connection、credentialRef、catalog、schema、threads、businessTimezone。connection 只包含非敏感的类型、instanceId、host、port、path；凭据值不能进入请求、快照或日志。

构建响应必须携带完整 execution，不接受旧环境枚举或绑定字段。构建列表按 environmentId 查询，可选 repository、branchName、buildStatus。部署自然键为 repository/environmentId/branchName；分支名称不决定物理环境。

固定 buildId 的目录、资源、日志、可用维度和四种查询模式使用同一无版本号协议。查询同步返回，不产生查询任务或历史结果。保留 optionId、高精度数值、时间语义和结构化错误。

## 不可变性与恢复

构建受理原子保存完整执行快照、源码与幂等身份。同一环境同一配置版本不能提交不同快照；同一物理实例/catalog/schema 不能被不同环境占用。部署继续保留 generation、CAS、来源 head 核验和结果未知保护。

服务只从快照生成独立 profile，并通过可信实例清单核验物理目标。凭据来自受保护环境变量引用，不封存临时 profile。元数据库只提供完整新库初始化，不保留绑定注册、增量升级、历史协议判别或全局 profile 回退。

Agent 项目保存 previewExecution 和 productionExecution；操作受理时冻结所选快照。保存、推送、合并、预览、交付和响应丢失后的恢复始终复用原操作快照。项目配置更新只影响新操作。

Metric Platform 管理独立执行环境；提交前冻结环境版本及完整快照。响应丢失后的同键重试不重新读取最新环境配置。固定构建页使用 execution 展示环境，不按旧枚举推断目标。

## 验证与交付

权威样本为服务 `tests/fixtures/contract.json`，两端副本为 `contracts/dbt.json`。验证覆盖拒绝旧字段与旧入口、快照不可变性、物理隔离、两端响应校验、恢复、目录和同步查询，以及真实 Git/PostgreSQL/dbt/MetricFlow 闭环。测试失败不得通过降低断言掩盖。

按归属仓库分别提交，根仓库仅提交共享验证脚本和文档；不更新子模块指针，不夹带既有用户变更。与 dbt 契约无关的数据库迁移编号、第三方版本和 Agent 上下文协议不在本次范围内。
