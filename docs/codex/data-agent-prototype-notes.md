# Data Agent 交互原型讨论记录

## DAT-2 工程实现重点

本工程按照 DAT-1 已确认满意的“全浅色企业工作台 + 会话内 Agent 过程”方案实现：

- 删除右侧思考/工具侧栏，只保留左侧多会话列表和中间对话区。
- 思考流放进 assistant 消息内部，用“思考了 12 秒”折叠入口承载。
- 折叠态只显示当前执行摘要和正在进行的工具活动。
- 展开态显示步骤摘要、工具名称、工具输入输出和等待确认节点。
- 用户确认框放在会话流中；点击“允许导出”或“拒绝导出”后卡片立即隐藏，并在会话内展示处理状态。
- 前端新增 `src/api/agentEvents.ts` 作为 `session/message/agent-event` 契约边界。
- 前端新增 `src/mocks/agentEventStream.ts`，用 mock 流式事件驱动体验，避免把 mock 逻辑写死在 UI 组件中。
- 前端新增 `src/api/backendAgentClient.ts`，用于请求 Spring Boot 后端 `GET/POST /api/v1/agent-sessions`、提交消息和确认动作。
- `src/domain/agentPrototype.ts` 负责把后端事件投影成消息、思考步骤、工具调用和确认状态。

## 视觉配色调整

最终视觉基准是 DAT-1 中确认的统一浅色体系：

- 使用浅中性底、浅青绿 surface 和低饱和蓝绿主色。
- 左侧会话栏、顶部、消息区、输入区都使用同一亮度体系，不出现大面积深色块。
- 选中会话用浅蓝绿底和 3px 主色线表达层次。
- 工具调用使用浅色内嵌容器和轻描边，不使用深色 terminal 块。
- 审批确认使用浅琥珀底，表达需要人工注意但不做危险警告。
- `visualPalette.test.ts` 防止深色侧栏、深色工具块和旧黑白方案回归。

## 前端事件契约

事件类型定义在 `src/api/agentEvents.ts`：

- `run.started`：开始一次 Agent run，携带 `sessionId`、`runId`、`sequence` 和目标。
- `message.created`：新增用户 / assistant / system 消息。
- `reasoning.delta`：追加或更新会话内思考摘要步骤。
- `tool.call.started`：展示工具调用开始、工具名和输入。
- `tool.call.completed`：更新工具输出并把工具步骤置为完成。
- `tool.call.failed`：把工具步骤置为等待处理并显示错误。
- `approval.requested`：在会话内生成用户确认框。
- `approval.resolved`：记录用户确认或拒绝结果。
- `run.completed`：结束 run 并追加最终回答。

当前 mock 事件在 `src/mocks/agentEventStream.ts`。真实后端接入在 `src/api/backendAgentClient.ts`，开发环境通过 Vite proxy 把 `/api` 转发到 `http://127.0.0.1:8080`。

## 外部调研结论

- OpenAI《Introducing ChatGPT agent: bridging research and action》说明 ChatGPT agent 在同一对话中工作，执行时通过 on-screen narration 让用户看到正在做什么；用户可以中断、暂停、接管或停止任务，关键动作前需要确认。来源：https://openai.com/index/introducing-chatgpt-agent/
- OpenAI《Learning to reason with LLMs》说明 reasoning 模型会花时间思考，并在示例中以“Thought for N seconds”形式表达思考时长；产品层不应把完整隐式推理作为冗长侧栏暴露，而应展示可复核摘要。来源：https://openai.com/index/learning-to-reason-with-llms/

## 页面映射

- “思考了 12 秒”对应 ChatGPT 的思考时长提示。
- “正在查询元数据目录”对应执行叙述，让用户不用展开也能知道当前进展。
- `catalog.search` 和 `spark.sql` 对应工具调用摘要，展开后才显示输入输出细节。
- 会话内“确认导出日报”对应 ChatGPT agent 的关键动作确认，确认或拒绝后从当前会话流隐藏，避免长期占屏。

## 本地运行

```powershell
Set-Location .\data-agent\frontend
npm.cmd run dev -- --port 5174
```

打开 `http://127.0.0.1:5174/` 查看原型。

后端联调时先启动 Spring Boot 服务：

```powershell
Set-Location .\data-agent
.\backend\mvnw.cmd -f .\backend\pom.xml -pl agent-api -am spring-boot:run -Dspring-boot.run.main-class=com.datagent.agent.api.DataAgentApplication
```

前端启动后会请求：

- `GET /api/v1/agent-sessions`
- `POST /api/v1/agent-sessions`（后端无会话时创建默认调试会话）
- `POST /api/v1/agent-sessions/{sessionId}/messages`
- `POST /api/v1/agent-sessions/{sessionId}/confirmations/{confirmationId}`

这些请求会被 Vite 代理到 `http://127.0.0.1:8080`，所以浏览器 Network 面板里看 `/api/...` 即可确认是否到达服务端。

## 验证命令

```bash
npm.cmd test
npm.cmd run build
```
