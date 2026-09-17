# Git Docker 服务

Git 与 PostgreSQL、Redis 一样由根仓库 Compose 管理。镜像使用 Alpine 3.23、Git 和 OpenSSH，提供唯一的 `/srv/git/metrics.git` 裸仓库。所有 Agent 会话共享远端 `main`；会话草稿仍由 Agent 自己隔离，卡片确认后才能推送。

## 首次部署

在根仓库用 PowerShell 执行，需要 Docker Desktop、Git 和 OpenSSH：

```powershell
.\infra\git\Initialize-GitService.ps1
```

脚本只构建和启动 `git` 服务，不重建其他容器。它会：

1. 在当前用户的 `~/.ssh/agent-metrics-git/` 生成专用密钥；重复执行保留已有密钥。
2. 将公钥复制到被 Git 忽略的 `tmp/git-service/authorized_keys`，Compose 只读挂载这份公钥。
3. 启动容器，并从本机 Docker 控制通道读取主机公钥，生成独立 `known_hosts`。
4. 在 `~/.ssh/config` 顶部添加该服务专用配置的 `Include`；原文件先备份，已有同名 Host 不会被覆盖。
5. 用真实 `git ls-remote` 验证远端 `main`，并设置当前 PowerShell 进程的 Agent Git 环境变量。

默认端口为 **127.0.0.1:2222**，Docker Desktop 分组为 **data-agent**，容器名为 **git**。初始化后可照常统一启动基础设施：

```powershell
docker compose -f .\infra\compose\compose.yml up -d
```

首次统一启动前必须先运行初始化脚本，避免公钥挂载文件不存在。改用其他端口时，运行 `Initialize-GitService.ps1 -Port 2223`；后续 Compose 命令也必须设置相同的 `GIT_SSH_PORT`（环境变量或显式指定的 `.env`）。已有信任文件出现端口或主机密钥变化时，脚本会停止，需人工核对而不会静默更新。

## 连接本机 Agent V2

若 Agent 从另一终端或 IDEA 启动，将下面两个变量配置到该启动环境，然后重启 Agent：

```powershell
$env:DATA_AGENT_GIT_ENABLED = 'true'
$env:DATA_AGENT_GIT_REMOTE_URI = 'ssh://git@agent-metrics-git/srv/git/metrics.git'
```

Agent 必须使用运行初始化脚本的同一系统账户，才能读取对应的 SSH 配置和私钥。其 Git 子进程会清理 `GIT_SSH_COMMAND` 等覆盖变量，因此连接依赖正常的 SSH Host 配置。此 Docker 服务不改变 Java 默认关闭开关，也不会重启正在运行的 Agent。

容器内的其他服务可通过 `git:22` 访问，但必须另外挂载自己的专用客户端密钥、主机信任及 SSH 配置；本机 `127.0.0.1` 配置不能直接复制到容器。

## 数据、保护和 hook

| 项目 | 存放位置 |
| --- | --- |
| 仓库对象、引用及 hooks | `agent-platform_git-data` 命名卷，容器内 `/srv/git` |
| SSH 服务端主机密钥 | `agent-platform_git-host-keys` 命名卷，容器内 `/var/lib/git-host-keys` |
| 客户端私钥及主机信任 | 当前用户 `~/.ssh/agent-metrics-git/`，不进仓库、不进镜像 |

只有不存在仓库时才创建初始空提交；重复启动保留历史。已有仓库缺少 `main` 时启动失败，需要人工检查。只允许更新 `main`，服务端拒绝强推、删除以及额外分支/标签；SSH 禁止密码、普通命令、终端和转发，远端命令只映射到固定仓库。

健康检查验证 SSH 监听和 `main` 引用。容器重建继续使用原来的数据卷和主机密钥，避免客户端信任失效。Git 两个卷保留首次部署的 `agent-platform_` 名称，并声明为外部卷，由初始化脚本创建或复用，因此 `down --volumes` 不会删除它们。备份时同时保存仓库卷、主机密钥卷和客户端配置；不要随意执行 `down --volumes`，该命令仍会删除 PostgreSQL、Redis 数据。

指标平台接点为持久卷内 `/srv/git/metrics.git/hooks/post-receive`。本次部署不配置指标平台回调地址；后续 hook 只做快速入队，独立 worker 再刷新平台。容器启动只更新内置 `pre-receive`，保留运维安装的 `post-receive`。Agent 的成功终点仍是 Git 推送被接受。

## 验证与常用操作

```powershell
# 独立测试容器与随机测试卷，不向正式指标仓库写测试提交；结束时清理测试容器与卷。
.\infra\git\Test-GitService.ps1

docker compose -f .\infra\compose\compose.yml ps git
docker compose -f .\infra\compose\compose.yml logs --tail 50 git
docker compose -f .\infra\compose\compose.yml restart git
git ls-remote ssh://git@agent-metrics-git/srv/git/metrics.git refs/heads/main
```

验收覆盖 SSH 克隆与推送、拒绝非快进/删除/额外分支/普通命令，以及重建容器后的提交和主机密钥保留。测试日志出现预期的 push rejected 属于保护验证，不是验收失败。

参考：[Docker Compose 服务配置](https://docs.docker.com/reference/compose-file/services/)、[命名卷](https://docs.docker.com/reference/compose-file/volumes/)、[Alpine 3.23 发布说明](https://www.alpinelinux.org/posts/Alpine-3.23.0-released.html)。
