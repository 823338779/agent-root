# 本地服务桌面中控

Python + Tkinter 一体化 Windows 桌面客户端，不需要安装第三方 Python 包，也没有独立 Web 后端。

## 启动

工作区需要 Python 3.11+（含 Tk）、JDK 21、Maven、Node/npm，以及已安装依赖的 dbt 虚拟环境。当前工作区的这些工具已存在。

在工作区根目录运行：

```powershell
.\infra\local-control\Start-LocalControl.ps1
```

也可以在 IDEA 中选择 `LocalControl` 运行配置；Python SDK 必须包含 Tk。需要查看客户端自身异常时：

```powershell
.\infra\local-control\Start-LocalControl.ps1 -Console
# 或者直接运行
python .\infra\local-control\app.py
```

客户端启动后只检查状态，不自动启动业务服务。数据库、Redis、Forgejo、Ollama 等外部依赖沿用现有工作区配置，不由此工具重建或迁移。

## 使用

| 服务 | 默认端口 | 启动方式 |
| --- | --- | --- |
| dbt-service | 8000 | 自身 `.venv/Scripts/python.exe`，根 `.run` 中的工作目录和环境变量 |
| Metric Platform | 8090 | 独立 Maven 构建生产 jar，然后使用 Java 启动 |
| Agent V2 | 8080 | 独立 Maven 构建生产 jar，然后使用 Java 启动 |
| Agent V2 前端 | 5173 | 原项目 `npm run dev`，固定端口及 strictPort |
| Metric Platform 前端 | 5174 | 原项目 `npm run dev`，固定端口及 strictPort |

- 选中服务后可启动、停止、重启、打开页面，下方显示构建和运行日志。
- **点击前端行的端口即可在默认浏览器打开对应页面**；“打开页面”按钮也使用相同地址。
- “启动全部”并行提交五个启动任务；“停止全部”只停止本客户端管理的服务；“重启已变更”只处理运行中的、确实需要重启的受管服务。
- Java 每次启动前都会重新打包生产代码，避免启动旧 jar。启动构建使用 `-Dmaven.test.skip=true`，不替代产品 README 的测试/验证命令。
- 占用端口的现有 IDE 服务显示“外部运行 / 端口占用”，不接管、不终止，也不声称确认了该进程的产品身份。请在原 IDE 停止后再用中控启动。
- 构建、启动期间可以点击“停止”。停止使用 Windows Job Object 终止本客户端拥有的进程树，包括启动包装器和子进程；属于强制停止，不执行业务排空。
- 关闭窗口会先停止所有受管进程，再退出；如果停止失败，窗口保留错误提示，方便重试。操作过程不会弹出确认框。

## 源码变更

每个服务在后台约每 3 秒扫描一次（扫描本身耗时额外计算）。监视相关源码、配置、依赖声明、IDE 启动配置；不依赖 Git，因此能识别未跟踪文件。忽略 `.git`、`node_modules`、`.venv`、`target`、`dist`、日志和缓存目录。

变更只在服务行显示，并在“变更文件”页签列出新增、修改、删除的相对路径。**不弹窗、不自动重启**。前端普通源码提示“Vite 热更新”，依赖声明或启动配置提示“建议重启”。该提示说明处理方式，不保证 Vite 的本次编译一定成功；错误请看前端日志。

成功启动且健康检查通过后，基线更新为本次启动前的源码状态。失败重启保留提醒，构建期间再次修改的代码也保留提醒。重新打开客户端会建立新的观察基线；外部 IDE 服务只检测客户端打开之后的变化。

IDE 环境变量和启动参数在每次启动时重新读取，Windows 路径和 `$PROJECT_DIR$` 宏保持原义。IDE 使用 JDK 21；中控默认通过 PATH 选择 Java/Maven，若有多版本请设置正确 PATH 或本地覆盖命令。

## 本地覆盖与日志

可选配置文件为 `tmp/local-control/settings.json`，以服务标识为键：`dbt`、`metric`、`agent`、`agent-web`、`metric-web`。默认不生成此文件。

```json
{
  "agent-web": { "port": 5273 },
  "metric-web": { "port": 5274 },
  "agent": { "startup_timeout": 180 }
}
```

支持 `port`、`health_path`、`open_path`、`cwd`、`command`、`build`、`env`、`startup_timeout`。`command` 和 `build` 必须是参数数组；`build: []` 可跳过构建，届时由开发者保证产物新鲜。`cwd` 的相对路径基于工作区。覆盖端口会同步默认启动命令和检查地址；如果同时覆盖完整命令，应在自己的命令中使用该端口。外部前后端代理依旧由产品配置管理，修改后端端口时需同步 Vite 代理。

日志位于 `tmp/local-control/logs/`，每个服务最多保留当前 2 MiB 和一份轮换文件，界面保留最近 800 行。日志可能包含产品自身输出的敏感信息；不要提交或分享未检查的日志。

## 验证

在本目录运行完整中控测试；测试创建临时 HTTP 服务和短暂的真实 Tk 窗口，不修改业务数据库：

```powershell
Set-Location .\infra\local-control
python -m unittest discover -s tests -v
python -m py_compile app.py config.py watcher.py runtime.py winjob.py
```

首次集成验证中，Metric Platform 常规打包通过，Agent V2 的生产代码打包通过。Agent V2 使用 `-DskipTests package` 时，当时工作区中的 `ConversationOrganizationPersistenceTest` 的 `setVersion`、`setTitle` 调用无法编译；本任务不修改产品测试。客户端的生产代码启动构建与产品测试结果分别报告。
