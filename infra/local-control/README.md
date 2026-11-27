# 本地服务桌面中控

Python + Tkinter 一体化 Windows 桌面客户端，不需要安装第三方 Python 包，也没有独立 Web 后端。

## 启动

工作区需要 Python 3.11+（含 Tk）、PATH 中可用的 uv、JDK 21、Maven、Node/npm，以及已安装依赖的 dbt 虚拟环境。当前工作区的这些工具已存在。

在工作区根目录运行：

```powershell
.\infra\local-control\Start-LocalControl.ps1
```

使用 Git Bash 时，也可以通过脚本调用 Python：

```bash
bash ./infra/local-control/start.sh
```

或直接执行 Python 启动命令：`python ./infra/local-control/app.py`。`start.sh` 会根据自身位置定位入口，可从任意工作目录调用；请使用 Windows 原生 Python（含 Tk）。

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
| dbt-service | 8000 | `uv run <项目路径>/.venv/Scripts/python.exe -m dbt_metricflow_service.main`，通过 PATH 定位 uv，使用根 `.run` 中的工作目录和环境变量 |
| Metric Platform | 8090 | 独立 Maven 构建生产 jar，然后使用 Java 启动 |
| Data Agent | 8083 | 构建 `data-agent/backend/app` 及其 Maven 依赖，按 `.run/DataAgentApplication.run.xml` 的参数启动 jar，通过 `/actuator/health` 检查健康状态 |
| Data Agent 前端 | 5173 | 在 `data-agent/frontend` 运行 `npm run dev`，Vite 将 `/api` 和 `/actuator/health` 转发到后端的 8083 端口 |
| Metric Platform 前端 | 5174 | 原项目 `npm run dev`，固定端口及 strictPort |

首次启动 Data Agent 前，请按[产品本地运行说明](../../data-agent/README.md#本地运行)初始化 PostgreSQL 数据库 `data_agent_v3`，并在前端目录执行 `npm ci`。数据库账号和密码由[后端配置文件](../../data-agent/backend/app/src/main/resources/application.properties)提供。

- 左侧每个服务项内提供启动、停止、重启，前端服务额外提供“打开页面”。点击操作会同步选中该服务，右侧立即显示对应的构建和运行日志。
- 当前服务以深蓝底、白字和“当前”标记突出；阅读日志后仍保留选中标记。左侧支持滚动和上下方向键选择，缩小窗口后保持当前服务可见。
- 全局批量操作集中在窗口右上方；右侧“启动信息”可内联展开当前服务的工作目录与健康检查地址。
- 日志区按级别突出错误和警告，时间弱化显示；支持自动换行、复制选区或全部日志、回到底部。“专注日志”收起左侧服务目录以扩大阅读区域，点击“显示服务”还原；查看历史日志时，新输出不会把视图拉回底部。
- 构建和服务进程在后台运行，启动器为命令及其普通子进程提供隐藏控制台，不弹出命令行黑框；stdout/stderr 仍显示在中控日志中。
- **点击前端行的端口即可在默认浏览器打开对应页面**；“打开页面”按钮也使用相同地址。
- “启动全部”并行提交五个启动任务；“停止全部”停止自建和已识别的外部服务；“重启已变更”只处理运行中的、确实需要重启的可控服务。
- Java 每次启动前都会重新打包生产代码，避免启动旧 jar。启动构建使用 `-Dmaven.test.skip=true`，不替代产品 README 的测试/验证命令。
- 通过 IDEA、PyCharm 或终端启动的服务，经监听 PID、启动入口和项目路径校验后显示“运行中 · 外部”或“不健康 · 外部”，可直接停止或重启。无法确认身份的占用显示“端口占用 · 未识别”，禁用停止和重启。
- 外部服务停止前再次核对 PID、创建时间和端口归属，只终止服务及其子进程，不终止 IDE 或终端。重启后使用中控当前配置启动并接管日志，不保留原 IDE 临时调试参数。外部进程已有的 stdout/stderr 仍需在原 IDE 或终端查看。
- 构建、启动期间可以点击“停止”。停止使用 Windows Job Object 终止本客户端拥有的进程树，包括启动包装器和子进程；属于强制停止，不执行业务排空。
- 关闭窗口会先停止本客户端创建的进程，再退出；仍由外部启动的服务继续运行。如果停止失败，窗口保留错误提示，方便重试。操作过程不会弹出确认框。

## 源码变更

每个服务在后台约每 3 秒扫描一次（扫描本身耗时额外计算）。监视相关源码、配置、依赖声明、IDE 启动配置；不依赖 Git，因此能识别未跟踪文件。忽略 `.git`、`node_modules`、`.venv`、`target`、`dist`、日志和缓存目录。

变更只在服务行显示，并在“变更文件”页签列出新增、修改、删除的相对路径。**不弹窗、不自动重启**。前端普通源码提示“Vite 热更新”，依赖声明或启动配置提示“建议重启”。该提示说明处理方式，不保证 Vite 的本次编译一定成功；错误请看前端日志。

成功启动且健康检查通过后，基线更新为本次启动前的源码状态。失败重启保留提醒，构建期间再次修改的代码也保留提醒。重新打开客户端会建立新的观察基线；外部 IDE 服务只检测客户端打开之后的变化。

IDE 环境变量和启动参数在每次启动时重新读取，Windows 路径和 `$PROJECT_DIR$` 宏保持原义。IDE 使用 JDK 21；中控默认通过 PATH 选择 Java/Maven，若有多版本请设置正确 PATH 或本地覆盖命令。

## 本地覆盖与日志

可选配置文件为 `tmp/local-control/settings.json`，以服务标识为键：`dbt`、`metric`、`data-agent`、`data-agent-web`、`metric-web`。旧键 `agent` 和 `agent-web` 不再生效。

```json
{
  "data-agent-web": { "port": 5273 },
  "metric-web": { "port": 5274 },
  "data-agent": { "startup_timeout": 180 }
}
```

支持 `port`、`health_path`、`open_path`、`cwd`、`command`、`build`、`env`、`startup_timeout`。`command` 和 `build` 必须是参数数组；`build: []` 可跳过构建，届时由开发者保证产物新鲜。`cwd` 的相对路径基于工作区。覆盖端口会同步默认启动命令和检查地址；如果同时覆盖完整命令，应在自己的命令中使用该端口。外部前后端代理依旧由产品配置管理，修改后端端口时需同步 Vite 代理。

日志位于 `tmp/local-control/logs/`，每个服务最多保留当前 2 MiB 和一份轮换文件，界面保留最近 800 行。日志可能包含产品自身输出的敏感信息；不要提交或分享未检查的日志。

子进程日志优先按 UTF-8 读取，无法解码的行回退到系统本地编码（中文 Windows 通常为 GBK），兼容 Java 编译器诊断和前端工具的不同输出编码。保存的日志文件统一使用 UTF-8。升级前已被替换为 `�` 的历史内容无法恢复；重新打开中控后，新采集日志使用此规则。

## 验证

在本目录运行完整中控测试；测试创建临时 HTTP 服务和短暂的真实 Tk 窗口，不修改业务数据库：

```powershell
Set-Location .\infra\local-control
python -m unittest discover -s tests -v
python -m py_compile app.py config.py watcher.py runtime.py winjob.py external.py log_panel.py service_list.py
```
