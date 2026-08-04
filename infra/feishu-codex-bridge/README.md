# 飞书 Codex Bridge（Python）

该服务使用飞书官方 Python SDK 建立长连接，把白名单用户发送的文本任务交给本机 Python Codex SDK，并将结果发回飞书。

## 当前权限

当前本地配置按要求启用了：

- `sandbox = "full-access"`：Codex 可以读写工作区之外的文件并执行系统命令。
- `approval_mode = "deny_all"`：Codex 不会发起任何审批请求。
- 工作目录固定为 `E:/IdeaProjects/agent-root`，但 `full-access` 不限制 Codex 访问其他路径。
- 只有 `config.local.toml` 中 `allowed_open_ids` 列出的用户可以下发任务。

这是一个高权限远程入口。任何能够控制白名单飞书账号的人，都可能控制运行该进程的 Windows 用户有权访问的系统资源。

## 配置

实际配置位于 `config.local.toml`，其中已经写入飞书 `APP_ID`、`APP_SECRET` 和允许使用的 `OPEN_ID`。该文件已被 `.gitignore` 排除，不会出现在 Git 变更中。

可提交的字段模板位于 `config.example.toml`。修改配置后需要重启进程。

## 飞书后台

1. 创建企业自建应用并启用机器人。
2. 申请接收消息及以应用身份发送消息所需权限。
3. 在“事件与回调”中选择“使用长连接接收事件”。
4. 订阅 `im.message.receive_v1`（接收消息 v2.0）。
5. 发布应用，并把白名单用户加入应用可用范围。

## 安装与启动

```powershell
Set-Location E:\IdeaProjects\agent-root\infra\feishu-codex-bridge
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
codex login status
.\.venv\Scripts\python.exe -m feishu_codex_bridge.main
```

看到飞书 SDK 输出长连接成功信息后，即可私聊机器人；群聊中需要先加入机器人，再 `@机器人` 发送任务。

## 支持的命令

| 命令 | 作用 |
| --- | --- |
| `/new` | 清除当前飞书会话关联的 Codex 上下文 |
| `/status` | 查看当前会话是否有任务在执行 |
| `/stop` | 中止当前会话正在执行的 Codex 回合 |
| `/help` | 显示命令帮助 |

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m compileall -q feishu_codex_bridge tests
```

## 当前限制

- 只接收文本消息，不处理图片和附件。
- 重启进程后不会恢复飞书会话和 Codex Thread 的映射。
- 暂不转发 Codex 中间事件，只发送接收确认和最终结果。

