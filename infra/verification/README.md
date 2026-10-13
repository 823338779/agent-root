# 指标构建协议的部署与验收

Agent 负责项目、真实 Git 分支、保存和交付；dbt-service 只提供固定构建、部署、目录和查询能力；指标平台聚合来源与历史。会话绑定一个开发目标，同分支可由多个会话独立编辑。本期仅保证 push 后内容可恢复。

将 `metrics-branch-config.example.json` 复制到工作区外的本地受控目录，明确填写三端地址、Agent 项目、规范 repository、branchName 和previewExecution 和 productionExecution 完整快照。凭据仅通过配置所指环境变量读取，不写入清单或日志。受支持命令统一见[根 README](../../README.md)，此处不重复维护。

预检仅执行 GET：三端健康、运行中契约路径和 Agent 项目配置必须匹配；缺少配置、旧字段、未知 schema 不允许静默转换或回退旧接口。dbt-service 使用 `/builds`、`/deployments`、`/query`，平台聚合为 `/api/dbt`。生产构建读取实际合并 SHA，不能把 preview build 升为 production。

可用维度和四种查询模式均同步返回：`POST /query/available-dimensions?build_id={buildId}` 只提交 `metricResourceIds`，直接读取 `dimensions`；`POST /query?build_id={buildId}` 不接收幂等键或 offset，成功时直接返回本次 `QueryResult`，失败为非 2xx 的错误响应。服务不再提供查询身份、状态轮询、历史结果或分页。平台保留 `/api/dbt/builds/{buildId}/available-dimensions` 和 `/queries` 作为代理入口，响应采用新版字段。构建和部署继续异步执行。

Flow 验证每次 POST 返回完整有界结果，HTTP 等待预算使用 `-TimeoutSeconds`（默认 1900 秒）。平台和 Agent 的 Nginx 代理读取超时均为 1900 秒；外围网关也需覆盖实际命令执行预算。查询重试会重新执行，不复用历史结果；构建和部署的幂等键仍须保留。

预览和正式 schema 由项目配置显式提供，配置缺失时先补齐。服务使用固定 schema 及原表名，后续构建可能覆盖同名表；固定 buildId 保证源码和目录身份，不保证历史物理数据快照。测试仓库必须使用专用 schema。

Git 初始化只维护真实仓库、SSH 身份及 main 保护。显式 `DisableLegacyPublishing` 可停用本链路已识别的旧发布 Webhook，保留无关通知；不会创建新的自动发布通知。共享环境的停写、备份和正式切换窗口仍由运维明确指定。

配置与 Webhook 自检仅代表脚本行为通过。只有真实 Git、数据库事务和 dbt/MetricFlow 物理执行全部完成，才可报告端到端闭环通过；HTTP 202、fixture、Mock 或 SKIP 均不能代替。真实场景只能使用专用测试仓库及数据库，输出默认在控制台，可选系统临时目录。

dbt-service 仅支持空库初始化，不提供历史迁移或身份映射。隔离闭环通过 `init-db` 初始化专用新库。
