# StarRocks 固定 schema 的 dbt 发布设计

## 目标与约束

- 电商语义项目的 dbt 产物固定写入 StarRocks `dbt_ecom` schema；原始表继续位于 `ecommerce_raw`，不归 dbt 管理。
- 每次构建在 `dbt_ecom` 内使用按任务隔离的物理表名，不再按发布创建 schema。相同构建任务的物理命名保持确定，重复提交同一幂等键不生成另一组表。
- 新构建失败时，旧活动版本的数据必须立即可查。历史发布仅保留发布记录，不再提供历史目录或新查询。
- 发布仍只接受受控 Git `main` 的固定提交。请求不能指定 schema、表名前缀、profile 或连接信息。

## 现状与取舍

当前 dbt 服务按 `run_<runId>` 创建独立 schema，Metric Platform 在新 run 完整验证后切换 `activeReleaseId`，清理任务随后删除旧 schema。物理隔离使失败候选不会改动旧数据，但会让 schema 数量随构建增加。

直接在 `dbt_ecom` 中反复覆盖同名表无法满足“失败后旧数据立即可查”：`dbt build` 逐模型执行，某个模型失败时其他模型可能已经更新。StarRocks 的表交换以单张表为单位，不能作为整个语义项目的原子发布。因此保留候选与活动版本的物理隔离，把隔离单位从 schema 改为固定 schema 内的任务前缀表。构建期间会暂时保留两组模型表；发布后旧组可回收。

曾评估使用 `dbt_ecom_<runId>` 候选 schema，并在发布时将旧 `dbt_ecom` 改名为备份、再将候选改名为 `dbt_ecom`。StarRocks 只提供单个 database 的 `ALTER DATABASE ... RENAME`，多条 DDL 不构成一个事务；因此两次改名之间固定名称会暂时不存在，无法实现整个项目的原子替换。候选 dbt manifest 中的物理 relation 还指向候选 schema，改名后必须同步处理这些引用和授权。这种方案仍需每次创建 schema，故不采用。固定 schema 内的版本表通过 PostgreSQL 中 `activeReleaseId` 的事务切换，让平台新查询一次选中完整的新版本；构建失败始终保留旧版本。

## 构建与受控配置

dbt 服务的项目绑定新增固定目标 schema，例如 `schemaName: dbt_ecom`。绑定来自服务端配置文件，必须符合 StarRocks 标识符规则；服务将其注入 profile 所引用的 `DBT_PLATFORM_SCHEMA`。Metric Platform 的固定项目配置也声明同一目标 schema，并在发布时校验运行快照。

服务从 Git 固定提交提取 dbt 项目并核对输入摘要后，在任务副本中提供服务控制的别名生成宏。模型、seed 和 snapshot 的物理名称使用确定的 `rv_<runId>_<原别名>` 形式；dbt 的 `ref()`、manifest、semantic manifest 与目录均指向这组物理对象。项目不能用同名宏覆盖服务控制的命名规则。执行写入前先检查解析后的可写节点均落在 `dbt_ecom`、名称均带本任务前缀，避免候选误写活动版本或原始表。

同一幂等键继续映射到同一个 run。一个新的 run 即使构建相同 Git 输入，也使用自己的前缀；未发布或过时 run 由清理流程回收。构建仍运行完整 `dbt build`、全部测试、目录生成、物理关系校验和代表性 MetricFlow 查询。只有全部通过的 run 才报告 `READY`。

## 发布与查询

Metric Platform 校验 run 的提交、输入摘要、profile、配置版本、工具链、固定 schema、物理关系和查询能力后，在 PostgreSQL 事务中导入目录并切换 `activeReleaseId`。同一 schema 可以对应多个发布记录，但每个 run 的物理表前缀必须唯一。失败候选不切换指针，旧活动 run 的表不受影响。

新的指标查询、解释、维度值和数据集预览只接受当前活动 `releaseId`；历史版本返回 410。`GET /releases` 和 `GET /releases/{releaseId}` 保留历史发布元数据。切换前已受理的查询允许完成，清理在这些查询结束后进行。现有“保留上一个成功发布版本”的清理例外随历史数据查询能力一起移除，仅活动版本与在途查询阻止回收。页面默认从活动发布进入查询；历史发布页面只展示记录与状态，不继续提供查询入口。公开 API 的错误语义与页面文案同步更新。

## 清理与迁移

新 run 的清理仅枚举并删除 `dbt_ecom` 中带该 run 前缀的对象及其本地产物；绝不执行 `DROP SCHEMA dbt_ecom`。即使构建中途失败、完整 manifest 尚未生成，清理仍依据服务持久保存的目标 schema 和任务前缀安全识别残留对象。清理操作可重复执行，且不得碰触其他 run 的表或 `ecommerce_raw`。

升级前现有活动发布及其 `run_...` schema 保持可查询。切换固定 schema 配置并提高构建配置版本后，平台发起一次新候选；只有该候选验证并发布成功，才由调整后的清理流程回收旧 run。旧格式 run 的清理继续按旧格式删除它自己的 `run_...` schema；新格式 run 按前缀删表。旧发布记录保留。任何迁移失败都保持原活动指针和旧 schema。

## 验收

1. 在真实 StarRocks 上连续构建两个不同的 dbt 提交：两次产物均位于 `dbt_ecom`，物理表前缀不同，且不会新建 `run_...` schema。
2. 第二次构建故意失败时，平台活动版本、旧表及其 `order_count` 查询结果保持可用；失败候选表可安全清理。
3. 成功发布后，新查询与解释 SQL 指向新前缀表；旧 `releaseId` 的新查询返回 410，发布记录仍可读取。
4. 清理旧 run 只删除其表；活动表、固定 schema 与 `ecommerce_raw` 不变。重复清理和服务重启恢复不会误删。
5. 从当前独立 schema 模式迁移时，首个固定 schema 构建失败仍保留旧版；成功后才切换并回收旧 schema。

## 非目标

- 不把原始电商表纳入 dbt 管理。
- 不在固定 schema 内维持不带版本前缀的稳定模型表名；手工 SQL 需使用当前发布目录中的物理 relation。
- 不提供历史发布的数据快照查询。

## 参考

- [StarRocks 对象命名限制](https://docs.starrocks.io/docs/sql-reference/System_limit/)
- [StarRocks 单表交换语义](https://docs.starrocks.io/docs/sql-reference/sql-statements/table_bucket_part_index/ALTER_TABLE/)
- [StarRocks database 改名语法及授权说明](https://docs.starrocks.io/docs/sql-reference/sql-statements/Database/ALTER_DATABASE/)
- [StarRocks 多条 DDL 不支持事务](https://github.com/StarRocks/starrocks/blob/main/contrib/starrocks-python-client/docs/usage_guide/alembic.md)
- [dbt 自定义模型别名](https://docs.getdbt.com/docs/build/custom-aliases)
