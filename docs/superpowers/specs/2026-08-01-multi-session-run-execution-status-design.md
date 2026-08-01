# 多会话 Run 执行、恢复与状态展示设计

## 1. 背景与目标

Data Agent V2 当前在提交消息时同步创建 `running` Run，但没有真正的后台模型执行器、持续事件发布、租约恢复或终态收敛。服务重启后，数据库中的 Run 可能永久停留在 `running`，后续消息因此触发 `uq_agent_run_one_active` 唯一约束。

本设计实现以下目标：

- 不同会话可以同时执行，页面切换、SSE 断开或浏览器关闭不影响后台 Run。
- 同一用户最多同时执行 3 个 `running` Run，超出的 Run 持久化为 `queued` 并按提交时间排队。
- 单个服务实例最多同时拥有 256 个 `running` Run；该上限是服务级配置，实例满载时 queued Run 由其他有容量的实例领取或继续等待。
- 同一会话最多存在一个非终态 Run，避免上下文并发修改。
- 使用 Ollama 执行真实流式模型调用，分别处理模型明确返回的 reasoning tokens 和最终回答 tokens。
- 前端 SSE 连接与 Run owner 位于不同实例时，reasoning/answer delta 仍通过 Redis Pub/Sub 逐 chunk 实时转发。
- 使用显式 ReAct 循环编排多轮“模型决策、工具调用、工具结果回填”，每个完整 Action/Observation 都持久化为可恢复上下文。
- reasoning、回答、阶段和 checkpoint 持久化；切换会话、断线重连和服务器重启后可以恢复显示。
- 服务器重启后通过租约自动接管孤儿 Run；无法安全恢复时进入明确的失败状态并允许重试。
- 前端会话列表显示排队中、思考中、待回复、待确认、失败、取消和未读圆点。
- 未读和用户拖拽顺序跨设备持久化。
- reasoning 内容只保留 30 天，最终回答、Run 元数据和普通事件继续保留。

## 2. 已确认的产品规则

### 2.1 并发与排队

- 每个用户最多同时拥有 3 个 `running` Run。
- 每个服务实例默认最多同时拥有 256 个 `running` Run，配置项为 `data-agent.runtime.max-running-runs-per-instance`。
- `waiting_for_user` 和 `waiting_confirmation` 不占用模型执行槽。
- 第 4 个及后续 Run 创建为 `queued`，有空闲执行槽后按 `queued_at` 升序自动领取。
- `queued` 是非终态，纳入“同一会话最多一个非终态 Run”的数据库约束。
- 新会话默认排在用户会话列表顶部。

### 2.2 未读

- 未读状态按租户、用户和会话持久化，跨浏览器和设备同步。
- 前端只显示一个未读圆点，不显示未读数量。
- `done`、`failed`、`waiting_for_user`、`waiting_confirmation` 在用户未停留于该会话时产生未读。
- 普通 reasoning、answer 流式增量和阶段进度不产生未读。
- 用户进入会话时立即标记当前已知序号为已读；停留期间的新可通知事件自动推进已读游标。
- 标记已读使用显式的 `upToSequence`，不得用无条件布尔清除，以免并发到达的新事件被误清除。

### 2.3 排序

- 会话顺序由用户拖拽决定，状态和活动变化不自动重排。
- 顺序由服务端按用户持久化并跨设备同步。
- 拖拽提交使用排序版本进行乐观并发控制；冲突返回 409，前端刷新后提示重新操作。

### 2.4 reasoning 与取消

- 只有 Ollama 接口明确返回的 reasoning tokens 才原样展示；系统不生成或推断未暴露的内部推理。
- reasoning tokens 实时展示并持久化，支持切换会话和恢复。
- reasoning 保存 30 天。到期后只清空 reasoning；最终回答、Run 状态、耗时和不含 reasoning 正文的普通事件继续保留。
- `queued`、`running` 和 waiting 状态都允许取消。
- 取消后保留已经生成的 reasoning 和部分回答，并标记“已取消，回答可能不完整”。

### 2.5 ReAct 恢复语义

- 一个 Run 内可以进行多轮模型调用和工具调用；这些 ReAct 轮次始终属于同一个 Run，并持续占用同一个用户执行槽。
- 完整持久化的 `assistant tool_call` 和对应 `tool` Observation 是执行恢复边界。服务端重启后使用这些消息重建模型上下文，不恢复模型进程、KV cache 或指定 Token 位置。
- 模型流在完整 `tool_call` 或最终回答形成前中断时，旧轮次标记为 `abandoned`；新 attempt 从最后一条完整 Observation 重新调用模型。旧 partial reasoning 归档用于展示和审计；旧 partial answer 在投影切换前可以展示，但接管后不保留，也不注入新的模型上下文。
- 工具调用结果不确定时仍自动重新执行。系统采用 at-least-once 工具执行语义；即使工具不支持幂等，也接受重复副作用风险。有幂等键时必须复用原幂等键。
- ReAct Model Turn 数、工具调用数和故障恢复 attempt 分别计数，正常的多轮 ReAct 交互不消耗故障恢复预算。

### 2.6 请求幂等与执行时限

- 消息提交和手动 retry 都必须携带 `Idempotency-Key`。同一租户、会话和请求类型下，相同 key 与相同规范化 payload 重放时返回第一次创建的消息和 Run，不得重复创建；相同 key 对应不同 payload 时返回 409 `IDEMPOTENCY_KEY_REUSED`。
- 单个 Run 的 10 分钟执行时限按累计 active execution time 计算。`queued`、`waiting_for_user` 和 `waiting_confirmation` 时间不消耗预算；租约仍有效且 Run 仍为 `running` 的时间计入预算，包括 owner 崩溃后等待租约过期的时间。

## 3. 总体架构

PostgreSQL 是 Run、租约、事件、流投影、未读和排序的唯一事实来源。Redis 只承担跨实例 stream delta 转发和取消控制唤醒；排队、生命周期事件、未读和排序不依赖 Redis 通知。Redis 消息丢失不得导致任务、进度或未读状态丢失。

### 3.1 组件边界

- `agent-persistence`
  - 提供 Flyway 增量迁移、Entity、Mapper 和通用持久化 Service。
  - 不包含 Run 领取、状态转换或业务重试决策。
- `agent-web`
  - 承载会话与 Run 应用逻辑、队列调度、Ollama 适配、checkpoint、REST/SSE、未读和排序。
  - 其他模块不得直接使用 Mapper 或 MyBatis API。
- `agent-server`
  - 只负责 Spring Boot 启动、运行时装配、定时任务启用和全局 Problem Detail。
  - 不放置产品业务状态机。
- `agent-evals`
  - 通过公开 HTTP/SSE 契约评估真实运行行为。
  - 不成为任何运行时模块的依赖。

### 3.2 运行数据流

1. 用户携带 `Idempotency-Key` 提交消息。
2. 一个数据库事务写入用户消息、`queued` Run、请求幂等信息、`run_queued` 事件和空 stream 投影；命中已提交的相同幂等请求时直接读取原消息和 Run。
3. HTTP 返回 202 和已创建或已存在的 Run；模型执行不依赖原始请求继续存活。
4. 各实例调度器每 1 秒周期扫描 queued Run；有本地容量的实例尝试为对应用户领取执行槽。
5. 领取事务写入 `run_started`；执行器创建新的 Model Turn，随后调用 Ollama。每个 reasoning/answer delta 先分配 stream sequence，通过本地分发器和 Redis Pub/Sub 实时发布，再按 stream checkpoint 阈值持久化当前轮次的完整投影。
6. 模型返回完整 tool calls 时，一个事务归档当前 Model Turn、写入带结构化 tool calls 的 assistant message，并为每个 tool call 创建 `prepared` 工具执行记录。
7. 执行器按模型返回顺序执行全部工具。每个工具无论成功或失败，都在一个事务中写入对应 `tool` Observation message，并把工具执行记录更新为 `succeeded` 或 `failed`；单个工具失败不跳过同一 Model Turn 的后续工具，也不主动终止 Run。全部工具进入终态且 Observation 已持久化后，从最新持久化消息边界开始下一轮模型调用，由 LLM 决定如何继续。
8. 模型返回最终回答时，同一事务归档当前 Model Turn、把 answer 固化为 assistant message，并更新 Run、`run_completed` 事件和会话可通知序号；失败、等待或取消使用对应状态事件完成同类收敛。
9. Redis 只把短生命周期 stream delta 发布给订阅对应会话的详细 SSE 节点；取消请求另外通过 Outbox 发布 `run_control_requested`。用户级列表状态和详细生命周期事件由持有 SSE 的实例周期查询 PostgreSQL。

## 4. 数据模型

所有变更通过新的 Flyway 迁移完成，不修改已经发布的 `V1__phase_1_streaming_chat.sql`。

### 4.1 `agent_run`

新增或调整字段：

- `status`：增加 `queued`。
- `owner_user_id varchar(64) not null`：用于用户级并发控制和队列选择。
- `queued_at timestamptz`：排队时间。
- `lease_expires_at timestamptz`：当前 owner 租约截止时间。
- `heartbeat_at timestamptz`：最近成功续租时间。
- `cancellation_requested_at timestamptz`：取消请求时间。
- `retry_of_run_id varchar(64)`：手动重试创建的新 Run 指向原失败 Run。
- `recovery_attempt_count integer not null default 0`：只统计租约接管、模型断流等故障恢复，不统计首次领取或 waiting 恢复。
- `request_type varchar(32)`、`request_idempotency_key varchar(256)` 和 `request_payload_hash varchar(64)`：记录创建该 Run 的 `message_submission` 或 `run_retry` 请求及其规范化 payload 哈希。V1 遗留 Run 允许为空；新建 Run 必须三者同时非空。
- `execution_budget_ms bigint not null default 600000`：创建 Run 时固化的累计 active execution time 上限。
- `active_execution_ms bigint not null default 0`：已结算的 active execution time。
- `active_segment_started_at timestamptz`：当前 `running` 段开始计时时间；非 `running` 状态为空。

`queued` Run 的 `execution_attempt` 为 0，`owner_instance_id`、`started_at`、`hard_deadline_at`、`active_segment_started_at`、`heartbeat_at` 和 `lease_expires_at` 为空。首次领取后 `execution_attempt` 变为 1，设置 owner、执行和租约字段，并令 `active_segment_started_at = now()`、`hard_deadline_at = now() + (execution_budget_ms - active_execution_ms)`。租约接管时先把旧 active 段截至接管时刻的耗时结算进 `active_execution_ms`，再递增 attempt 并开始新的 active 段；因此 owner 崩溃后等待租约过期的 running 时间也消耗预算。Run 离开 `running` 时，在同一状态转换事务中把当前段耗时累加到 `active_execution_ms`，并清空 `active_segment_started_at` 和 `hard_deadline_at`；waiting 恢复后使用剩余预算计算新的 `hard_deadline_at`，不得重新获得完整 10 分钟。现有 `owner_instance_id` 和 `hard_deadline_at` 的非空约束必须在增量迁移中调整，并增加按状态校验字段完整性的 CHECK 约束。领取或恢复前剩余预算已耗尽时，Run 不开始新的模型或工具调用，直接以 `RUN_DEADLINE_EXCEEDED` 失败。

为新请求建立部分唯一索引：

```sql
unique (tenant_id, session_id, request_type, request_idempotency_key)
where request_idempotency_key is not null
```

`request_payload_hash` 使用服务端定义的规范化请求内容计算；`run_retry` 的哈希必须包含原 `run_id`。并发重复请求依赖该唯一索引收敛到同一个 Run，冲突事务回读原记录并比较 hash，不依赖进程内锁。

重建部分唯一索引 `uq_agent_run_one_active`，条件覆盖：

```sql
status in ('queued', 'running', 'waiting_for_user', 'waiting_confirmation')
```

### 4.2 `agent_message`

现有消息表继续作为可重建 LLM 上下文的不可变事实日志，并进行以下调整：

- `role` 增加 `tool`。
- `tool_calls jsonb not null default '[]'::jsonb`：只允许 assistant message 保存模型返回的完整结构化 tool calls。
- `tool_execution_id varchar(64)`、`tool_call_id varchar(128)` 和 `tool_name varchar(128)`：只允许 tool message 使用。`tool_execution_id` 通过租户复合外键稳定关联工具执行记录；`tool_call_id` 保留 provider 原始 ID，用于重建 LLM 上下文。
- `visibility varchar(16) not null default 'user'`：取值为 `user` 或 `internal`。ReAct assistant tool-call message 和 tool Observation 默认是 `internal`，用于模型上下文但不直接进入公开会话消息列表；最终回答和用户消息为 `user`。

`tool` message 对 `(tenant_id, tool_execution_id)` 建部分唯一约束并通过复合外键关联 `agent_tool_execution`，保证每个工具执行最多一条 Observation。模型返回 tool calls 后，必须先在一个事务中写入完整 assistant message 和对应的 `prepared` 工具执行记录，才能调用工具。每个工具执行成功或确定失败后，必须在一个事务中写入 tool message 并把工具执行记录改为对应终态；同一 Model Turn 的全部工具都进入终态且具备 Observation 后，才能开始下一轮模型调用。未形成完整 tool call 的 partial 输出不得写入 `agent_message`，也不得作为恢复上下文。

### 4.3 `agent_model_turn`

新增每次 LLM 调用一条的模型轮次表，主键为 `(tenant_id, run_id, model_turn_sequence)`：

- `execution_attempt bigint not null`。
- `input_up_to_message_sequence bigint not null`：本轮模型输入包含的最后一条持久化消息序号。
- `status varchar(32) not null`：`streaming`、`completed`、`abandoned` 或 `failed`。
- `outcome_type varchar(32)`：完成时为 `tool_calls` 或 `final_answer`；未完成时为空。
- `model_name varchar(128) not null`。
- `reasoning text`：本轮最终归档的 provider reasoning；这是该表唯一允许的大文本字段。
- `prompt_tokens bigint`、`reasoning_tokens bigint`、`completion_tokens bigint`。
- `started_at timestamptz not null`、`completed_at timestamptz`、`error_code varchar(64)`。
- `reasoning_expires_at timestamptz`。

该表不保存完整 prompt、消息上下文、工具参数、工具结果、partial answer、最终回答副本或 Ollama 原始响应。流式期间 reasoning 只写当前 stream 投影；Model Turn 完成、失败或被接管时，再把累计 reasoning 一次性归档到该表。旧 reasoning 到期后只清空正文，保留轮次状态、耗时和 Token 统计。

### 4.4 `agent_tool_execution`

新增工具执行控制表，主键为 `(tenant_id, tool_execution_id)`；`tool_execution_id varchar(64)` 是服务端生成的稳定内部标识。另建唯一约束 `(tenant_id, run_id, model_turn_sequence, tool_call_id)`，因为 provider 的 `tool_call_id` 只要求在一次 Model Turn 内唯一，不得假定其在整个 Run 内永久唯一：

- `run_id varchar(64) not null`。
- `model_turn_sequence bigint not null`。
- `tool_call_id varchar(128) not null`：保留 provider 原始 ID。
- `assistant_message_id varchar(64) not null`：指向包含该 tool call 的 assistant message。
- `tool_name varchar(128) not null`。
- `arguments_hash varchar(64) not null`：校验恢复时读取的结构化参数未发生变化。
- `idempotency_key varchar(256)`：工具支持幂等时复用；不支持时允许为空。
- `status varchar(32) not null`：`prepared`、`executing`、`succeeded` 或 `failed`。
- `result_message_id varchar(64)`：工具确定成功或失败后指向唯一的 tool Observation message。
- `error_code varchar(64)`。
- `execution_count integer not null default 0`。
- `last_execution_attempt bigint`。
- `started_at timestamptz`、`completed_at timestamptz` 和乐观锁 `version`。

`result_message_id` 使用 `(tenant_id, result_message_id)` 复合外键指向 `agent_message`，并与 message 上的 `tool_execution_id` 相互校验。工具参数只存于 assistant message 的 `tool_calls`，工具结果或确定失败 Observation 只存于 `result_message_id` 指向的 tool message，执行表不复制这些大字段。领取工具执行时以条件更新把 `prepared` 改为 `executing` 并递增 `execution_count`；租约失效时，遗留的 `executing` 记录重新变为可领取状态并自动执行。`succeeded` 和 `failed` 都是具备唯一 Observation 的终态，恢复时不得重复执行；系统明确提供 at-least-once 而非 exactly-once 语义。

### 4.5 `agent_run_stream`

继续作为当前 Model Turn 的可读取 UI 投影，字段为：

- `execution_attempt bigint not null`。
- `model_turn_sequence bigint not null`。
- `phase varchar(32) not null`。
- `stream_sequence bigint not null default 0`。
- `reasoning text not null default ''`。
- `answer text not null default ''`。
- `checkpointed_at timestamptz`。
- `reasoning_expires_at timestamptz`。
- 乐观锁 `version`。

现有 `thinking` 字段在增量迁移中重命名为 `reasoning`。`queued` Run 的空投影使用 `execution_attempt = 0`、`model_turn_sequence = 0`；开始新的 attempt 或 Model Turn 时原子替换投影并把 `stream_sequence` 重置为 0。

每个实时 delta 都在当前节点内递增 `stream_sequence`。checkpoint 保存完整累计 `reasoning`、`answer` 和最后已发布的 `stream_sequence`；`(execution_attempt, model_turn_sequence, stream_sequence)` 构成客户端去重和拼接顺序。前端发现 attempt 或 Model Turn 变化时必须用新快照替换本地 partial 内容。

### 4.6 `agent_run_attempt`

新增 attempt 审计表，主键为 `(tenant_id, run_id, execution_attempt)`，只保存：

- `owner_instance_id varchar(128) not null`。
- `status varchar(32) not null`。
- `resume_reason varchar(64)`。
- `started_at timestamptz not null`、`ended_at timestamptz`。
- `failure_code varchar(64)`。

旧 attempt 用于租约、接管和失败诊断，不复制 partial reasoning 或 partial answer。旧 Model Turn 的 reasoning 归档到 `agent_model_turn`；当前 partial UI 始终由 `agent_run_stream` 表达。

### 4.7 `agent_session`

新增：

- `last_activity_at timestamptz`：用于时间展示，不参与用户自定义排序。
- `last_notifiable_event_sequence bigint not null default 0`：最近一次应产生未读的会话事件序号。

### 4.8 用户会话状态

新增 `agent_session_user_state`：

- 主键：`(tenant_id, user_id, session_id)`。
- `sort_order bigint not null`。
- `last_read_event_sequence bigint not null default 0`。
- 审计时间和乐观锁 `version`。

新增 `agent_conversation_preference`：

- 主键：`(tenant_id, user_id)`。
- `ordering_version bigint not null default 0`。

未读判断为：

```text
agent_session.last_notifiable_event_sequence
    > agent_session_user_state.last_read_event_sequence
```

完整重排在一个事务内锁定 `agent_conversation_preference`，验证 `ordering_version`，将提交的可见会话 ID 依次写入连续的 `sort_order`，最后递增版本。新会话通过当前最小 `sort_order - 1` 置顶；完整重排时重新压缩为连续整数，避免长期溢出。

### 4.9 reasoning 清理

每日维护任务只处理终态 Run，并清空以下位置中 `reasoning_expires_at <= now()` 的 reasoning：

- `agent_run_stream.reasoning`
- `agent_model_turn.reasoning`

事件表不得持久化原始 reasoning 正文；reasoning/answer 增量通过 stream checkpoint 和实时 SSE 表达，避免清理时遗漏副本。

## 5. Run 状态机与并发控制

### 5.1 状态转换

允许的主要转换：

```text
queued -> running
queued -> cancelled
running -> done
running -> failed
running -> cancelled
running -> waiting_for_user
running -> waiting_confirmation
waiting_for_user -> queued
waiting_confirmation -> queued
waiting_for_user -> cancelled
waiting_confirmation -> cancelled
```

自动租约接管不改变 `running` 状态，但递增 `execution_attempt` 并更换 owner。非法转换返回稳定的 409 Problem Detail。

手动重试不复活终态 Run，而是创建一个新的 `queued` Run，并通过 `retry_of_run_id` 保留审计关系。retry 请求必须使用请求级幂等键；相同请求重放返回第一次创建的新 Run。原 Run 的 partial 内容和终态保持不变。

### 5.2 用户与实例双层执行槽

调度器同时执行两层容量控制：

- 用户级上限：同一租户用户最多 3 个 `running` Run，通过 PostgreSQL 用户行锁和计数保证跨实例一致。
- 实例级上限：单个服务实例默认最多 256 个 `running` Run，通过进程内公平 Semaphore 保证同一实例的所有调度线程和恢复线程共享容量。

服务配置如下；容量和队列长度必须是正整数，时间间隔必须大于 0，修改后重启实例生效：

```yaml
data-agent:
  runtime:
    max-running-runs-per-instance: 256
    run-execution-budget: 10m
    queue-scan-interval: 1s
    control-poll-interval: 1s
  sse:
    session-event-reconciliation-interval: 1s
    activity-reconciliation-interval: 2s
    max-pending-events-per-connection: 256
```

首次领取按以下顺序执行：

1. 当前实例非阻塞获取一个本地执行许可；实例已使用 256 个许可时，本次不领取。
2. 锁定该用户的 `user_account` 行，序列化同一用户在不同节点上的领取判断。
3. 统计该用户租户内状态为 `running` 且未逻辑删除的 Run。
4. 用户数量达到 3 时结束事务并释放刚取得的本地许可。
5. 使用 `FOR UPDATE SKIP LOCKED` 选择该用户最早的 queued Run。
6. 更新 owner、attempt、started/heartbeat/lease，开始新的 active 计时段，按剩余执行预算设置 deadline，并创建 attempt 记录。
7. 提交后开始或恢复 ReAct 循环；事务失败或没有成功领取 Run 时立即释放本地许可。

租约接管也必须先取得本地许可，但不再次占用用户级槽：目标 Run 已经是 `running`，所有权转移不会增加该用户的 running 数量。接管事务只锁定目标 Run，并使用过期 lease、旧 owner 和当前 attempt 条件更新；接管失败时立即释放本地许可。

本地许可在 Run 保持 `running` 的整个 ReAct 循环期间持有。实例使用以 `run_id` 为键的本地 owner registry 包装公平 Semaphore，保证同一 Run 只获取和释放一次许可。Run 进入 `done`、`failed`、`cancelled`、`waiting_for_user` 或 `waiting_confirmation`，当前 owner 丢失租约，或执行器启动失败时，必须在 `finally` 路径释放许可并唤醒本实例调度器。实例容量是本地资源，不广播“容量可用”通知；waiting 状态重新排入 queued 后，需要重新竞争用户级和实例级执行槽。

数据库锁只覆盖短事务，不覆盖模型执行过程。本地 Semaphore 是实例资源保护，不替代 PostgreSQL 的 Run 状态和租约事实；服务指标必须暴露配置上限、已用许可、可用许可和当前 owner 的 running Run 数，以便检测许可泄漏或状态漂移。

### 5.3 租约与重启恢复

默认配置：

- 单实例 running Run 上限：256。
- 租约：60 秒。
- 心跳：每 15 秒。
- 单个 Run 累计 active execution budget：10 分钟。
- 最大故障恢复次数：3。

维护扫描器查找 `running` 且 `lease_expires_at < now()` 的 Run。接管仍需使用行锁和条件更新，确保只有一个实例成为新 owner。

恢复规则：

- Ollama 不支持从指定 Token 精确续传。流式调用中断时，把当前 Model Turn 标记为 `abandoned`，归档已经 checkpoint 的 reasoning，以新 attempt 从 `input_up_to_message_sequence` 指向的最后稳定消息边界重新生成，并重置当前 stream 投影。
- `prepared` 工具调用由新 owner 直接执行；租约失效时遗留的 `executing` 工具调用也由新 owner 自动重新执行并递增 `execution_count`。
- `succeeded` 或 `failed` 工具调用必须已经在同一事务中持久化对应 tool Observation，新 owner 读取该消息继续本轮后续工具或下一轮模型调用，不重复执行该工具。
- 工具支持幂等时复用原 `idempotency_key`；不支持幂等或结果不确定时仍自动重试，接受可能重复副作用的 at-least-once 语义。
- `recovery_attempt_count` 达到 3 后进入 `failed`。首次领取、从 waiting 状态恢复以及正常 ReAct Model Turn 递增均不增加该计数。

### 5.4 ReAct 执行循环

执行器显式控制 ReAct 循环，不得把多轮工具调用完全隐藏在无法插入持久化边界的框架内部。每个循环按以下顺序执行：

1. 创建 `streaming` Model Turn，记录 `input_up_to_message_sequence`，把当前 stream 投影切换到新的 `model_turn_sequence`。
2. 使用截至该消息序号的不可变 `agent_message` 上下文调用 Ollama。
3. 模型返回完整 tool calls 时，一个事务归档 Model Turn reasoning、写入 assistant message，并为每个 tool call 创建 `prepared` 工具执行记录。
4. 同一 Model Turn 返回多个 tool calls 时，首版严格按 provider 返回顺序串行执行。每个工具调用无论成功或失败，都在一个事务中写入唯一 tool Observation，并更新为 `succeeded` 或 `failed`。失败 Observation 提供给 LLM，失败本身不终止 Run，也不跳过本轮尚未执行的后续工具；全部工具进入终态且都有 Observation 后才开始下一轮模型调用。
5. 模型返回最终回答时，一个事务归档 Model Turn reasoning、写入最终 assistant message，并把 Run 收敛为 `done`。

默认单 Run 最多 12 个 Model Turn、32 个 Tool Call；任一上限耗尽后最终 checkpoint 并进入 `failed`，分别使用 `REACT_MODEL_TURN_LIMIT_EXCEEDED` 和 `REACT_TOOL_CALL_LIMIT_EXCEEDED`。这些限制与 `execution_attempt`、`recovery_attempt_count` 相互独立，累计 active execution budget 仍是整个循环的最终上限。工具调用自身的成功或失败都只消耗 Tool Call 计数，不直接把 Run 转为 `failed`。

## 6. Ollama 流与 checkpoint

Ollama 适配器通过 Spring AI 的 Ollama 流式模型接口输出两类增量：

- provider 明确返回的 reasoning tokens。
- 面向用户的最终 answer tokens。

适配器不得把普通回答、日志或自行生成的摘要伪装为 reasoning。

本设计中的 checkpoint 只表示当前 Model Turn 的 UI stream 快照，不表示模型内部状态，也不决定工具是否已经执行。ReAct 的执行恢复位置由已提交的 `agent_message`、`agent_tool_execution` 和 `agent_model_turn` 推导。

每个 delta 在当前 `(execution_attempt, model_turn_sequence)` 内分配递增的 `stream_sequence`，先投递当前实例的本地 SSE dispatcher 并发布到对应 Redis 会话 channel，再由 checkpoint 累加器按以下任一阈值批量持久化：

- 距离上次 checkpoint 达到 250 毫秒。
- 新增内容达到 512 个字符。
- phase 变化、Model Turn 结束、等待、完成、失败、取消或租约即将释放。

checkpoint 原子写入完整 `reasoning`/`answer` 投影以及最后已发布的 `stream_sequence`。更新条件必须同时匹配 `run_id`、`owner_instance_id`、`execution_attempt`、`model_turn_sequence` 和 `version`，防止旧 owner 或旧 Model Turn 覆盖新投影。

节点崩溃时最多丢失尚未达到 checkpoint 阈值的实时 Token。接管者不会把旧 partial 内容重新注入模型，而是从最后完整 ReAct 消息边界重新生成；旧 partial reasoning 只归档到被标记为 `abandoned` 的 Model Turn。Run 进入任一非 running 状态前必须执行最终同步 checkpoint。Model Turn 结束时设置 `reasoning_expires_at = completed_at + 30 days`。

## 7. Redis 与 SSE

### 7.1 Redis 职责

Redis 只承担以下两类跨实例消息，不保存 Run 所有权或可恢复执行状态：

| 通信类型 | Redis | Outbox | 语义 |
| --- | --- | --- | --- |
| `STREAM_DELTA` | 会话级 Pub/Sub | 否 | 实时转发 reasoning/answer 短增量，允许丢失和重复 |
| `RUN_CONTROL_REQUESTED` | 共享控制 Pub/Sub | 是 | 唤醒当前 owner 尽快处理已持久化的取消请求 |

除这两类外，本设计不使用其他 Redis 或 Outbox 跨实例通信。

**`STREAM_DELTA`。** 执行实例把 reasoning/answer 的每个短增量发布到：

```text
agent:stream:{tenantId}:{sessionId}
```

消息字段为：

- `type`：`reasoning_delta` 或 `assistant_delta`。
- `tenantId`、`sessionId`、`runId`。
- `executionAttempt`、`modelTurnSequence`、`streamSequence`。
- `delta` 和 `occurredAt`。

delta 消息不走数据库 Outbox，不持久化到 Redis，也不包含累计 reasoning/answer、prompt、工具参数、工具结果或 Ollama 原始响应。单条 UTF-8 消息最大 16 KiB，超出时由发布端按字符边界拆分并为每段分配独立 `streamSequence`。Pub/Sub 允许丢失和重复，PostgreSQL stream checkpoint 负责最终恢复。由于 delta 可能包含敏感 reasoning/answer 片段，Redis 连接必须启用认证和传输加密，应用日志、指标和 tracing 不得记录 `delta` 正文。

**`RUN_CONTROL_REQUESTED`。** 用户取消 running Run 时，同一数据库事务写入 `cancellation_requested_at` 和 `run_control_requested` Outbox。发布器把消息发送到共享 `agent:run-control` channel：

- `notificationId`、`tenantId`、`sessionId`、`runId`。
- `ownerInstanceId`、`executionAttempt`、`controlVersion`。
- `control = cancel` 和 `occurredAt`。

所有执行实例订阅该 channel，只有数据库中仍为当前 owner 且 attempt 匹配的实例处理中止。收到消息后必须重新读取 Run 状态，不得仅凭 Redis 消息取消其他 attempt。Outbox 发布采用 at-least-once 语义，消费者按 `notificationId` 和 `controlVersion` 幂等处理。

Redis 或 Outbox 发布失败不能阻止取消事务提交。owner 在每次模型调用前、工具调用前、心跳时以及模型流存活期间每 1 秒检查 `cancellation_requested_at`，因此 Redis 消息只降低取消延迟，不是正确性来源。

除 `run_control_requested` 外，不为 `run_queued`、Run 状态变化、checkpoint、会话事件、未读或排序写 Outbox，也不发布对应 Redis 消息。

### 7.2 两层 SSE

用户登录后维持一条用户级状态 SSE：

```text
GET /api/v1/agent-sessions/activity-events
```

它不订阅 Redis。持有用户级 SSE 的实例默认每 2 秒按本地活跃用户批量查询 PostgreSQL，只在会话的状态、未读游标或排序版本发生变化时发送新快照。重连后前端先重新拉取会话列表；该流不永久保存通知历史。

当前打开的会话维持一条详细 SSE：

```text
GET /api/v1/agent-sessions/{sessionId}/events
Last-Event-ID: e:<session-event-sequence>;a:<execution-attempt>;t:<model-turn-sequence>;s:<stream-sequence>
```

持有 HTTP 长连接的实例维护本地 `SseConnectionRegistry`，按 `(tenantId, sessionId)` 保存已鉴权连接，并在每条连接上保留 user identity。第一个本地连接建立时订阅对应 Redis 会话 channel，最后一个连接关闭时取消订阅；没有匹配本地连接的实例不消费和转发该会话的 stream delta。访问控制在连接建立和重连时完成，Redis delta 不能绕过会话授权。

建立详细 SSE 时按以下顺序消除快照与实时订阅之间的空窗：

1. 验证当前用户对会话的访问权限，创建有界的本地发送队列。
2. 注册 Redis 会话订阅并把到达的 delta 暂存到连接缓冲区。
3. 按 `e` 重放持久化状态事件并读取当前 stream 完整快照。
4. 发送带复合 cursor 的快照，丢弃缓冲区中不大于快照 `(a,t,s)` 的消息。
5. 按序发送剩余连续 delta，然后把连接切换为实时模式。

执行实例也先把 delta 投递本地 dispatcher，再发布 Redis，使连接恰好落在 owner 实例时不依赖 Redis 往返。由于同一消息可能从本地和 Redis 两条路径到达，registry 必须按 `(executionAttempt, modelTurnSequence, streamSequence)` 去重。Redis listener 只负责校验和投递，实际 `SseEmitter.send()` 在独立 dispatcher 中执行，不阻塞 Redis 消费线程。

每条 SSE 连接使用有界队列，默认最多等待 256 个事件；队列溢出、发送超时或连续 heartbeat 失败时关闭连接，让浏览器重连并从 checkpoint 恢复。服务端默认每 15 秒发送 heartbeat。

同一 `(a,t)` 内发现 `streamSequence` 跳号时，连接进入 resync：暂存后续 delta，等待或查询 `stream_sequence` 已覆盖缺口的 PostgreSQL checkpoint，发送完整快照后再刷新连续缓冲区。缓冲区溢出或在一个租约周期内仍不能收敛时关闭 SSE。Redis 不可用期间，持有 active Run 详细连接的非 owner 实例每 1 秒轮询 stream checkpoint；Redis 恢复后停止 stream 轮询。

Run 生命周期、阶段和工具事件不通过 Redis 通知。持有详细 SSE 的实例始终每 1 秒按本地活跃 session 批量查询 `agent_run_event` 中大于各连接 `e` 的事件并按序发送；该 reconciliation 与 Redis stream delta 转发并行运行。

每个详细 SSE 消息都携带复合 cursor。快照替代断线期间不可重放的 Token delta；实时阶段只接受当前 `(a,t)` 且 `s` 更大的增量。

切换会话只关闭旧的详细 SSE 并打开新的详细 SSE，不取消后台 Run；用户级状态 SSE 始终保持。

## 8. REST 与 OpenAPI 契约

保留现有会话创建、列表、详情、消息提交和详细事件路径，并新增：

```text
POST /api/v1/agent-sessions/{sessionId}:mark-read
PUT  /api/v1/agent-sessions:reorder
POST /api/v1/agent-sessions/{sessionId}/runs/{runId}:cancel
POST /api/v1/agent-sessions/{sessionId}/runs/{runId}:retry
GET  /api/v1/agent-sessions/activity-events
```

契约调整：

- 消息提交和 `:retry` 请求要求 `Idempotency-Key` header。相同租户、会话、请求类型、key 和 payload 的重放返回第一次创建的消息和 Run；相同 key 对应不同 payload 时返回 409 `IDEMPOTENCY_KEY_REUSED`。
- `AgentRun.status` 增加 `queued`。
- Run 事件类型增加 `run_queued`；`run_started` 只表示 queued Run 已被执行器领取。
- 会话列表/详情增加 `unread`、`lastNotifiableEventSequence`、`sortOrder` 和 `orderingVersion`。
- Run stream 明确包含 `executionAttempt`、`sequence`、reasoning、answer 和 checkpoint 时间。
- Run stream 增加 `modelTurnSequence`；queued 空投影允许 `executionAttempt=0` 和 `modelTurnSequence=0`。详细 SSE 增量使用 `(executionAttempt, modelTurnSequence, streamSequence)` 去重，`Last-Event-ID` 使用包含会话事件与 stream 位置的复合 cursor。
- `reasoning_delta` 和 `assistant_delta` SSE 事件明确包含 `runId`、`executionAttempt`、`modelTurnSequence`、`streamSequence`、`delta` 和 `occurredAt`；`stream_snapshot` 事件携带完整 reasoning/answer 投影及对应复合序号。
- 公开 `AgentMessage` 仍只返回 `visibility=user` 的用户消息和最终 assistant 回答。内部 assistant tool-call message 与 tool Observation 不进入普通消息列表，其进度通过不含敏感参数和结果正文的阶段事件表达。
- ReAct 达到 Model Turn 或 Tool Call 上限时返回稳定错误码；工具采用 at-least-once 恢复语义不对外宣称 exactly-once。
- `:cancel` 返回 202 和当前 `AgentRun`。对于 `running` Run，事务只先持久化 `cancellationRequestedAt` 并可能仍返回 `status=running`；owner 完成模型中止和最终 checkpoint 后才转为 `cancelled`，客户端通过详细 SSE 或 Run 查询获得终态。`queued` 和 waiting Run 可在请求事务中直接转为 `cancelled`，重复取消幂等返回当前状态。所有取消路径都保留 partial stream。
- 重排版本冲突、活动 Run 冲突、非法状态转换使用不同的稳定 Problem Detail code。

所有公开行为先修改 `contracts/openapi.yaml` 和契约测试，再修改实现。

## 9. 前端设计

### 9.1 会话列表

采用紧凑单行布局：

- 左侧仅在悬停、聚焦或拖拽时突出显示拖拽手柄。
- 中间显示会话标题。
- 右侧显示一个短状态标签或未读圆点。
- 状态标签包括：`排队中`、`思考中`、`待回复`、`待确认`、`失败`、`已取消`。
- 已完成且未读时显示圆点；进入会话后圆点清除。
- 会话状态变化不改变用户顺序。

拖拽完成后乐观更新 UI 并提交完整顺序。409 时恢复服务端顺序并提示“会话顺序已在其他设备更新，请重新排序”。必须同时提供键盘可操作的上移/下移行为，不能只支持鼠标拖拽。

### 9.2 当前会话

- Header 显示 Run 状态和进度。
- reasoning 区域实时展示模型明确返回的 reasoning，可折叠但默认在运行时展开。
- answer 区域独立流式展示最终回答。
- `queued` 显示排队状态和取消入口。
- `running` 显示取消生成入口。
- `failed` 显示稳定错误摘要和重试入口。
- `cancelled` 保留 partial 内容并显示“回答可能不完整”。
- `waiting_for_user` 和 `waiting_confirmation` 显示对应操作卡片。

## 10. 错误处理

- Ollama 暂时不可用、连接超时或流异常：在最大 `recovery_attempt_count` 内退避重试；耗尽后进入 `failed`。
- LLM 流在形成完整 tool calls 或最终回答前中断：当前 Model Turn 标记为 `abandoned`，新 attempt 从其 `input_up_to_message_sequence` 重新调用模型，旧 partial 输出不进入上下文。
- 工具执行返回失败，包括参数校验、权限拒绝、超时、工具异常或确定的业务失败：工具记录改为 `failed`，写入不含敏感正文的失败 Observation，并继续执行同一 Model Turn 尚未执行的后续工具；全部工具进入终态后必须把所有成功和失败 Observation 反馈给下一轮 LLM。任何单次或多次工具失败都不得主动终止 Run；只有 Model Turn/Tool Call 上限、累计 active execution budget、用户取消或运行基础设施故障恢复耗尽等 Run 级条件可以终止 Run。
- 工具处于 `executing` 时 owner 租约失效：新 owner 无条件重新执行，复用已有幂等键并递增 `execution_count`；没有幂等键时仍重试并接受重复副作用。
- 当前实例没有可用执行许可：Run 保持 `queued`，不返回运行失败；其他实例通过 1 秒周期扫描领取该 Run。
- 累计 active execution budget 到期：中止当前模型流或阻止开始下一个模型/工具调用，结算当前 active 段并在最终 checkpoint 后进入 `failed`，错误码为 `RUN_DEADLINE_EXCEEDED`。queued 和 waiting 时间不计入预算，waiting 恢复不得重置预算。
- 租约丢失：旧 owner 立即停止写入；stream checkpoint、Model Turn 归档、工具结果提交和 Run 状态转换都带 owner、attempt、Model Turn 与 version 条件，防止僵尸实例覆盖新 owner。
- 用户取消 running Run：接口返回 202；先持久化 `cancellation_requested_at`，owner 观察到后取消 Ollama subscription，执行最终 checkpoint 并写入 `cancelled`，终态通过 SSE 或查询收敛。queued 和 waiting Run 在请求事务内直接取消。
- 消息提交或 retry 的幂等 key 重放：payload hash 相同则返回原消息和 Run，hash 不同则返回 409 `IDEMPOTENCY_KEY_REUSED`。
- 排序版本冲突：返回 409 `SESSION_ORDER_CONFLICT`。
- 同会话已有非终态 Run：返回 409 `ACTIVE_RUN_CONFLICT`。
- 非法 Run 状态转换：返回 409 `RUN_STATE_CONFLICT`。
- Redis 不可用：任务和 checkpoint 正常持久化，`run_control_requested` Outbox 保持未发布并在 Redis 恢复后重试；owner 实例上的本地 SSE 继续接收 delta，非 owner 实例上的 active Run 详细 SSE 每 1 秒轮询数据库快照并在 Redis 恢复后切回 Pub/Sub。取消仍由 owner 的 1 秒数据库检查兜底。

Problem Detail 不包含 reasoning、prompt、回答正文、数据库异常或 Ollama 原始响应。

## 11. 测试策略

### 11.1 持久化与并发

- 迁移测试验证 `queued`、按状态生效的租约和 active 计时字段 CHECK、请求幂等字段、attempt/Model Turn/工具执行/用户状态表、消息角色与 visibility 约束、外键、租户复合键和部分唯一索引。
- 并发提交相同消息或 retry 请求时，验证相同 `Idempotency-Key` 和 payload 只创建一个消息/Run 并始终返回该 Run；相同 key 配不同 payload 返回 409 `IDEMPOTENCY_KEY_REUSED`，HTTP 响应丢失后的重试不返回 `ACTIVE_RUN_CONFLICT`。
- PostgreSQL Testcontainers 并发测试同时启动两个调度实例，为同一用户插入至少 4 个 queued Run，断言最多 3 个进入 running，剩余 Run 保持 queued。
- 验证不发布 `run_queued` Redis/Outbox 消息时，其他实例仍在 1 秒扫描周期内发现并领取 queued Run。
- 单实例容量测试为至少 86 个用户创建 257 个可领取 Run，断言该实例最多拥有 256 个 running Run，第 257 个保持 queued；配置为其他正整数时按配置值生效，0 或负数启动失败。
- 双实例容量测试验证一个满载实例不会领取新 Run，另一个有容量的实例可以领取；两个实例的本地许可互不共享，PostgreSQL 租约仍保证每个 Run 只有一个 owner。
- 验证领取事务失败、执行器启动失败、waiting/终态转换和租约丢失都会恰好释放一次本地许可，重复回调不会导致许可超过配置上限。
- 验证不同用户和不同会话可以并行执行。
- 验证同一会话的 queued/running/waiting 互斥。
- 验证租约过期前不能接管，过期后只有一个新 owner 成功。
- 验证旧 owner/attempt 的 checkpoint 条件更新失败。

### 11.2 Ollama、checkpoint 与状态机

- 使用可控 HTTP Stub 模拟 Ollama reasoning、answer、延迟、断流和错误，不在 CI 依赖真实模型。
- 验证 reasoning 和 answer 被分离、按 checkpoint 持久化并实时发布。
- 验证每个 delta 单调递增 `stream_sequence`，checkpoint 保存完整投影及最后已发布序号。
- 验证流中断把旧 Model Turn 标记为 `abandoned`、创建新 attempt 和 Model Turn、替换实时投影，并且旧 partial 内容不进入新模型上下文。
- 验证 queued、running、waiting、done、failed、cancelled 的合法和非法转换。
- 验证取消 running Run 先返回 202、`cancellationRequestedAt` 已持久化且状态允许仍为 `running`；owner 最终 checkpoint 后才转为 `cancelled`，期间保留 partial 内容。验证 queued/waiting 取消可在请求事务内直接终态化，重复取消保持幂等。
- 验证 `execution_attempt`、`recovery_attempt_count`、Model Turn、Tool Call 和累计 active execution time 分别计数；queued/waiting 不消耗执行预算，running 租约过期等待时间消耗预算，waiting 恢复只使用剩余预算且不消耗故障恢复次数，各上限返回稳定错误码。

### 11.3 ReAct 与工具恢复

- 使用可控模型和工具 Stub 构造至少三轮 ReAct 工具调用，在“Model Turn 开始、assistant tool calls 已提交、工具 executing、tool Observation 已提交、最终回答提交”各边界注入崩溃。
- 验证未完成 Model Turn 从 `input_up_to_message_sequence` 对应的最后完整 Observation 重新生成。
- 验证 `prepared` 工具直接执行，租约失效的 `executing` 工具自动重复执行并递增 `execution_count`。
- 验证不同 Model Turn 可以使用相同 provider `tool_call_id`，内部 `tool_execution_id` 仍唯一，Observation 通过该内部 ID 关联到正确执行记录。
- 验证 `succeeded` 和 `failed` 工具都读取 `result_message_id` 指向的 Observation，不重复执行。
- 验证工具成功或失败状态与对应 tool Observation 同事务提交，不存在终态但缺少结果消息的状态。
- 验证参数校验、权限拒绝、超时、工具异常和业务失败都会形成失败 Observation；单个或多个工具失败后继续执行本轮后续工具，并把全部 Observation 交给下一轮 LLM，不主动终止 Run。
- 验证新 owner 接管后旧 owner 不能提交工具结果、归档 Model Turn 或写 stream checkpoint。
- 验证恢复后重建的 LLM 消息序列与崩溃前最后完整 ReAct 边界一致，internal 消息不出现在公开普通消息列表。
- 验证无幂等键的 `executing` 副作用工具也会自动重试，明确覆盖可能执行两次的 at-least-once 行为。

### 11.4 SSE、未读与排序

- 两实例测试让浏览器详细 SSE 固定连接实例 A、Run 固定由实例 B 执行，验证 A 通过 Redis 按序实时收到并转发 reasoning/answer delta。
- 验证详细 SSE 先建立 Redis 缓冲订阅、再重放和发送 stream 快照、最后刷新连续缓冲区，连接建立空窗期间不丢 delta。
- 验证同一 delta 同时经 owner 本地 dispatcher 和 Redis 到达时只发送一次；没有对应本地连接的实例不订阅或转发该会话 channel。
- 验证 attempt 或 Model Turn 变化时前端替换 partial 投影，同一轮只接受更大的 `streamSequence`。
- 验证 Redis delta 丢失、重复和乱序时进入 resync，待 PostgreSQL checkpoint 覆盖缺口后发送完整快照并继续实时增量。
- 验证 Redis 不可用时 owner 本地连接继续实时接收，非 owner 连接降级为 1 秒 checkpoint 轮询，Redis 恢复后停止轮询且不重复内容。
- 验证第一个本地连接订阅会话 channel、最后一个连接关闭后取消订阅；慢客户端队列溢出时只关闭该连接并允许其重连恢复。
- 验证详细 SSE 每 1 秒批量补查持久化生命周期事件，用户级 SSE 每 2 秒批量补查状态、未读和排序；没有对应 Redis/Outbox 消息时仍能收敛。
- 验证 running Run 的取消事务只为 `run_control_requested` 写 Outbox；queued/waiting 直接取消以及排队、终态、会话事件、未读和排序变化均不写通信 Outbox。
- 验证 owner 收到 `run_control_requested` 后重新检查数据库并快速取消；Redis 消息丢失时 1 秒数据库检查仍能取消，重复 Outbox 消息不会重复终态转换。
- 验证后台会话进入 done/failed/waiting 后产生未读，reasoning/answer delta 不产生未读。
- 验证 `upToSequence` 不会清除并发到达的新通知。
- 验证拖拽顺序跨设备读取一致，冲突返回 409。
- 验证新会话默认置顶且完整重排会压缩 sort order。

### 11.5 保留策略与前端

- 使用可控 Clock 验证只清空终态且超过 30 天的 reasoning。
- 验证 `agent_model_turn.reasoning` 和当前 stream reasoning 到期清空，而最终回答、ReAct 消息上下文、工具结果、Run、普通事件和未到期 reasoning 不受影响。
- React 测试覆盖紧凑状态、未读圆点、会话切换、用户级与详细 SSE、拖拽/键盘排序、取消、失败重试和 partial 回答提示。
- 完整服务验收使用 PostgreSQL、Redis Testcontainers 和 Ollama HTTP Stub。

## 12. 非目标

- 首版不同时支持其他模型供应商；只实现 Ollama。
- 不展示或推断 Ollama 未显式返回的内部推理。
- 不使用 Redis 作为任务或事件的唯一事实来源。
- 不允许同一会话同时执行多个非终态 Run。
- 不承诺跨任意外部工具的 exactly-once 副作用；工具恢复语义明确为 at-least-once。
- 不在本次工作中迁移旧 `data-agent` 的全部工具、技能和 Metric Platform 能力；只实现显式 ReAct 编排边界、工具执行协议和当前 V2 会话能力所需的最小工具集合。
