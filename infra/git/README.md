# Forgejo Git 服务

根仓库 Compose 使用固定镜像 `codeberg.org/forgejo/forgejo:15.0.9-rootless` 提供带 Web 管理界面的 Git 服务。Web 只监听 `http://127.0.0.1:3000`，SSH 默认只监听 `127.0.0.1:2222`，不会向局域网或公网开放。

服务使用 SQLite，配置、数据库、仓库和 SSH 主机密钥统一保存在外部卷 `agent-platform_forgejo-data`。固定管理员为 `agent-admin`，初始化脚本创建私有仓库 `agent-admin/metrics`；服务关闭自助注册，`main` 允许正常快进推送但禁止强推和删除，普通功能分支与标签仍可使用。

## 首次部署

需要 Docker Desktop、PowerShell 7、Git 和 OpenSSH。在根仓库执行：

```powershell
.\infra\git\Initialize-GitService.ps1
```

脚本会安全提示输入 `agent-admin` 的密码。密码只存在于当前 PowerShell 进程，不写入 Compose、仓库、普通环境变量或日志。脚本随后完成以下操作：

1. 创建或复用外部卷，并只启动 Compose 的 `git` 服务（容器名为 `forgejo`）。
2. 创建或核对管理员、私有仓库、客户端 SSH Key 和 `main` 保护规则。
3. 使用短期 API Token 完成配置，并在 `finally` 中撤销 Token。
4. 从本机 Docker 控制通道读取 SSH 主机公钥，严格维护专用 `known_hosts`。
5. 在 `~/.ssh/config` 中加入 `Include agent-metrics-git/config`，最后执行真实 `git ls-remote`。

初始化可以重复运行；同名资源与预期不一致时会停止，不会静默覆盖。改用其他 SSH 端口时执行：

```powershell
.\infra\git\Initialize-GitService.ps1 -Port 2223
```

后续 Compose 命令也必须使用相同的 `GIT_SSH_PORT`。如果已有 `known_hosts` 与当前端口或主机密钥不一致，脚本会停止，需人工核对后处理。

## 连接 Data Agent V2

初始化脚本会为当前 PowerShell 进程设置：

```powershell
$env:DATA_AGENT_GIT_ENABLED = 'true'
$env:DATA_AGENT_GIT_REMOTE_URI = 'ssh://git@agent-metrics-git/agent-admin/metrics.git'
```

从另一终端或 IDEA 启动 Agent 时，需要在对应启动环境配置相同变量，并使用运行初始化脚本的同一系统账户，以便读取专用 SSH 配置和私钥。

## 数据与升级

| 项目 | 存放位置 |
| --- | --- |
| SQLite、仓库、配置、附件和 SSH 主机密钥 | 外部卷 `agent-platform_forgejo-data`，容器内 `/var/lib/gitea` |
| 客户端私钥、配置与主机信任 | 当前用户 `~/.ssh/agent-metrics-git/` |

`docker compose down --volumes` 不会删除这个外部卷。升级或迁移前应备份整个卷及客户端 SSH 目录。

旧自定义 Git 容器使用的两个外部卷不会被初始化脚本自动删除，也不会迁移到 Forgejo；确认不再需要后可由运维单独清理。

## 验证与常用操作

```powershell
# 使用随机容器、随机端口和随机卷，不向正式仓库写入测试提交。
.\infra\git\Test-GitService.ps1

docker compose -f .\infra\compose\compose.yml ps git
docker compose -f .\infra\compose\compose.yml logs --tail 50 git
docker compose -f .\infra\compose\compose.yml restart git
git ls-remote ssh://git@agent-metrics-git/agent-admin/metrics.git refs/heads/main
```

隔离测试覆盖 Web 健康、禁止注册、幂等初始化、SSH clone/push、`main` 强推与删除拒绝、功能分支以及容器重建后的数据和主机密钥持久性。测试日志中预期的 `push rejected` 是保护规则验收，不代表测试失败。
