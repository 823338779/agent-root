# 指标分支部署与验收

dbt-service 是唯一发布者。Agent 工作区与会话是可选关联；平台只消费固定分支和版本。执行脚本需要 PowerShell 7，各产品依照自身 README 独立构建。

## 配置预检

指标资源统一使用 `http://127.0.0.1:3000/agent-admin/metrics`。开发、测试与发布通过同一仓库的分支完成，不能按开发者或会话创建业务仓库。会话与分支通过工作区关联，彼此没有一对一绑定。

复制 `metrics-branch-config.example.json` 到 `tmp/`，按实际部署填写项目、仓库业务身份、子目录、发布开关与事件目标。JSON 只保存环境变量名，不保存 Secret。该清单是运维输入，脚本不能代替从各实际部署读取并核对配置。

```powershell
pwsh -File .\infra\verification\Test-MetricsBranchConfig.ps1 -SelfTest
pwsh -File .\infra\verification\Test-MetricsBranchConfig.ps1 -ConfigPath .\tmp\branch-config.json
```

进程环境中 `BRANCH_SERVICE_TOKEN` 与 `DATA_AGENT_DBT_BRANCH_SERVICE_TOKEN` 必须相同；`BRANCH_EVENT_SECRET` 同时用于服务验签与 Forgejo 签名。服务启用 `BRANCH_EVENTS_ENABLED=true` 和补偿扫描；开发 profile 使用 `BRANCH_PREVIEW_PROFILE_BINDING_ID`，只允许写开发库。平台后端设置 `metric.publication.mode=service-proxy`，前端使用 `VITE_PUBLICATION_MODE=service-proxy`，旧平台发布者停用。

分支 webhook 接收器按服务绑定的 `remote` 与 Forgejo payload 的 `repository.clone_url` 严格匹配。部署必须使用完全相同的受控仓库 URL；Agent 的 SSH 地址可以不同，但两者必须指向同一仓库。不要在 URL 嵌入凭据。私有 HTTP Git 认证由服务进程的受控凭据机制提供。

## 唯一事件目标

在当前 PowerShell 通过受控方式设置 `BRANCH_EVENT_SECRET` 后，显式执行：

```powershell
.\infra\git\Initialize-GitService.ps1 -BranchEventTarget http://host.docker.internal:8000/internal/git-branch-events
.\infra\git\Test-GitService.ps1
```

初始化只在指定 `BranchEventTarget` 时迁移发布通知：停用已识别的旧 dbt Webhook 和重复分支通知，保留其他用途通知。目标接收 push/delete，由服务根据登记过滤 ref；重复执行更新同一 hook。未知旧发布通知须先人工停用并纳入预检清单。测试使用随机容器、私有仓库和卷，不修改正式 Forgejo。

## 已存在分支的聚合读取与查询

先在独立测试项目完成 Agent 确认 push，等待 main/A/B 各有可用版本。把平台短期访问令牌放入当前进程 `METRIC_PLATFORM_ACCESS_TOKEN`，不要加入命令行。运行：

```powershell
.\infra\verification\Test-MetricsBranchFlow.ps1 `
  -ServiceBaseUri http://127.0.0.1:8000 `
  -PlatformBaseUri http://127.0.0.1:8090 `
  -AgentBaseUri http://127.0.0.1:8080 `
  -ProjectId ecommerce_metrics -BranchAId <UUID-A> -BranchBId <UUID-B> `
  -ExpectedProductionSha <40位SHA> -OutputDirectory .\tmp\branch-development
```

脚本通过公开 API 核对三服务分支身份、固定版本目录、服务与代理查询结果，以及同键恢复同一查询。报告仅输出断言及项目/分支/版本/SHA；错误不复制响应正文、SQL 或 Token。必要输入、可查询指标、服务响应缺失或断言失败均非零退出。单次目录限 200 个指标，超出则拒绝部分验收。

此脚本不会创建分支、编辑文件、绕过确认、合并 main 或写业务数据库；PASS 仅代表这些聚合断言，不代表完整业务验收。

## 完整验收范围

报告必须逐项记录 A01–A18：会话多分支、独立分支、共享分支同步、依赖错误、确认后远端推进、旧构建晚完成、失败保留旧版、页面过期响应、版本变化中查询恢复、main 成功/失败发布、事件补偿、push 响应丢失、同名重建、会话删除、产物引用保护、真实 SQL/YAML/测试与数据库权限、v3 历史迁移、跨上下文身份拒绝。

每项写明 PASS/FAIL/未执行和实际证据。单测、fixture 浏览器验收、PostgreSQL adapter 和真实 StarRocks 验收分别标注，禁止用任一项替代三服务真实闭环或把 SKIP 当通过。仓库迁移演练只能在独立副本执行，不能降级后重新启用旧发布者。

脚本回归不访问网络或实际仓库，覆盖真实旧平台通知 `/internal/git-sync/events` 的停用、其他用途通知保留，以及拒绝 main 冒充任一开发分支：

```powershell
pwsh -NoProfile -File .\infra\verification\Test-MetricsBranchRegression.ps1
```

真实 StarRocks 权限需分别授予数据库建表能力和表读写能力，原始库只读；依据 [StarRocks 官方 GRANT 文档](https://docs.starrocks.io/docs/sql-reference/sql-statements/account-management/GRANT/)。开发账号应实际验证无法写 raw 和生产库，不能仅检查生成 SQL。
