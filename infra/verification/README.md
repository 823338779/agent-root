# 指标构建协议的部署与验收

Agent 负责项目、真实 Git 分支、保存和交付；dbt-service 只提供固定构建、部署、目录和查询能力；指标平台聚合来源与历史。会话绑定一个开发目标，同分支可由多个会话独立编辑。本期仅保证 push 后内容可恢复。

将 `metrics-branch-config.example.json` 复制到工作区外的本地受控目录，明确填写三端地址、Agent 项目、规范 repository、branchName 和两个环境的 binding/configVersion。凭据仅通过配置所指环境变量读取，不写入清单或日志。受支持命令统一见[根 README](../../README.md)，此处不重复维护。

预检仅执行 GET：三端健康、运行中契约路径和 Agent 项目配置必须匹配；缺少配置、旧字段、未知 schema 不允许静默转换或回退旧接口。dbt-service 新路径为 `/v3`，平台聚合为 `/api/v3/dbt`。生产构建读取实际合并 SHA，不能把 preview build 升为 production。

Git 初始化只维护真实仓库、SSH 身份及 main 保护。显式 `DisableLegacyPublishing` 可停用本链路已识别的旧发布 Webhook，保留无关通知；不会创建新的自动发布通知。共享环境的停写、备份和正式切换窗口仍由运维明确指定。

配置与 Webhook 自检仅代表脚本行为通过。只有真实 Git、数据库事务和 dbt/MetricFlow 物理执行全部完成，才可报告端到端闭环通过；HTTP 202、fixture、Mock 或 SKIP 均不能代替。真实场景只能使用专用测试仓库及数据库，输出默认在控制台，可选系统临时目录。

迁移必须在隔离备份副本中先 dry-run，报告每个来源冲突，再进行增量迁移并重复执行校验稳定身份。核对封存字节 hash、物理引用保护、历史查询归因，不删除未推送文件。出现问题停写后选择前向修复或匹配备份恢复，禁止把新版数据直接交给旧二进制，禁止旧新发布器并行。
