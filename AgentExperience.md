# AgentExperience 架构设计

> 状态：规划草案 v1.0  
> 目标：在编码前确定领域边界、核心协议、一致性、安全策略、评测方法与分阶段实施范围。  
> 本文只定义架构，不包含实现代码。

## 1. 项目愿景

AgentExperience 是一个面向 Agent 运行时的经验管理 SDK。它将真实运行中可验证、可复用的成功策略固化为经验，并在后续相似任务中以建议、受控重放或精确复用的方式帮助 Agent 提高成功率、降低工具调用次数和 Token 成本。

系统同时记录失败观察，但失败不会立即转化为永久禁令。所有经验都必须经过证据收集、适用性判断、验证、发布、反馈和淘汰的完整生命周期。

AgentExperience 不是：

- 原始日志归档工具；
- 单纯的向量知识库；
- 无条件重放历史工具调用的缓存；
- 替代 Agent 框架自身状态管理或持久化的运行时；
- 仅凭一次成功便自动生成永久技能的系统。

## 2. 设计目标

### 2.1 核心目标

1. **低侵入接入**：不修改业务任务逻辑，通过各框架正式扩展点采集标准化事件。
2. **可信经验形成**：从轨迹中提取候选经验，基于明确的成功证据验证后才发布。
3. **条件化召回**：同时考虑语义、结构化条件、环境兼容性、时效性、可信度和风险。
4. **安全复用**：默认仅提供建议；只有满足严格条件的经验才允许受控重放或跳过 LLM。
5. **可审计与可恢复**：以 Append-Only 事件日志作为事实来源，所有索引均可重建。
6. **可迁移**：经验包包含完整性、来源、兼容性和安全元数据，导入后重新验证。
7. **可量化评估**：通过离线基准和线上反馈证明经验带来的真实增益。

### 2.2 非目标

首期不承诺：

- 从任意 Python 堆栈自动还原语义正确的 DAG；
- 对任意 Agent 对象进行零配置、百分之百兼容的自动挂钩；
- 对有副作用的工具进行无人值守自动重放；
- 在不同工具契约、权限和环境之间做到无需验证的“拷贝即运行”；
- 提供分布式强一致、多主写入的经验数据库。

## 3. 核心原则

### 3.1 表示与存储分离

- Python 领域对象服务于运行时逻辑。
- Protobuf 是核心持久化与交换协议。
- 人类调试工具可以将 Protobuf 投影为 JSON 或表格，但 JSON 不作为核心事实存储格式。
- 向量库、SQLite 图关系库和索引快照都是可重建投影，不是事实来源。

### 3.2 事件溯源与逻辑不可变

- 所有领域变化写为不可变事件。
- 更新经验不会覆盖旧记录，而是追加新 revision 或 evaluation event。
- 当前状态由日志重放和索引投影得出。
- 允许 segment 轮转、checkpoint 和安全 compaction；Append-Only 指逻辑历史不可被静默篡改，而不是单文件无限增长。

### 3.3 低侵入不等于无适配

“低侵入”定义为不改变 Agent 的业务任务逻辑，但允许在框架规定的 middleware、callback、listener、runtime wrapper 或 decorator 扩展点注册 AgentExperience。

每个框架维护独立适配器。自动探测只是便利能力，不能成为正确性基础。

### 3.4 安全默认

- 外部经验默认隔离，不直接进入可执行状态。
- 召回默认提供建议，不自动重放。
- 有副作用、权限敏感或不可逆工具默认要求审批。
- 经验内容视为不可信输入，必须防止提示注入、Secret 泄漏和恶意迁移包。

### 3.5 证据优先

一次无异常运行不等于成功经验。经验必须保存成功判据、验证证据、适用边界、来源轨迹和复用后的反馈。

## 4. 统一术语与领域边界

### 4.1 Run

一次 Agent 从接收输入到产生最终结果或失败的完整运行实例。

### 4.2 Trace

Run 中模型、工具、节点、状态和结果事件的标准化轨迹。Trace 是事实，不等于经验。

### 4.3 Candidate Experience

从一个或多个 Trace 中提取的候选策略。未经充分验证，不允许自动执行。

### 4.4 Experience Definition

经验的不可变内容版本，包括适用条件、策略 DAG、输入输出契约、风险和成功判据。

### 4.5 Evaluation Event

对某个经验 revision 的验证或复用结果。成功率、样本量和置信度由这些事件投影计算，不直接修改经验定义。

### 4.6 Advice

提供给 Agent 规划器的经验摘要、检查项、常见风险或步骤建议，不直接执行工具。

### 4.7 Replay

在兼容性和策略校验通过后，根据经验 DAG 受控执行工具。Replay 必须产生新的 Run 和 Evaluation Event。

### 4.8 Exact Result Cache

仅对纯函数、无副作用、输入与环境指纹精确匹配且仍在有效期内的结果进行直接复用。它与一般语义经验召回分开管理。

## 5. 总体架构

```text
Agent Frameworks / Generic Python
               │
               ▼
       Framework Adapters
               │
               ▼
       Event Normalization
               │
       ┌───────┴────────┐
       ▼                ▼
 Append-only Log   Outcome Evaluator
       │                │
       └───────┬────────┘
               ▼
 Candidate Extractor / Validator
               │
               ▼
       Experience Lifecycle
               │
   ┌───────────┼────────────┐
   ▼           ▼            ▼
Active Index  Vector Index  Relation Graph
   └───────────┼────────────┘
               ▼
 Retriever + Applicability + Policy
               │
      ┌────────┼─────────┐
      ▼        ▼         ▼
    Advice   Replay   Exact Cache
      └────────┼─────────┘
               ▼
       Verification & Feedback
```

## 6. 模块划分

建议项目结构如下，最终命名可在实施计划阶段微调：

```text
agent_experience/
├── pyproject.toml
├── protos/
│   ├── common.proto
│   ├── events.proto
│   ├── experience.proto
│   └── package.proto
├── src/agent_experience/
│   ├── core/
│   │   ├── models.py
│   │   ├── enums.py
│   │   ├── policies.py
│   │   └── exceptions.py
│   ├── schema/
│   │   └── *_pb2.py
│   ├── events/
│   │   ├── envelope.py
│   │   ├── normalizer.py
│   │   └── bus.py
│   ├── storage/
│   │   ├── event_log.py
│   │   ├── segments.py
│   │   ├── recovery.py
│   │   ├── projection_manager.py
│   │   ├── snapshot_store.py
│   │   ├── vector_store.py
│   │   └── graph_store.py
│   ├── experience/
│   │   ├── extractor.py
│   │   ├── evaluator.py
│   │   ├── validator.py
│   │   ├── lifecycle.py
│   │   └── compiler.py
│   ├── retrieval/
│   │   ├── retriever.py
│   │   ├── reranker.py
│   │   └── applicability.py
│   ├── execution/
│   │   ├── executor.py
│   │   ├── tool_registry.py
│   │   ├── verifier.py
│   │   └── approval.py
│   ├── adapters/
│   │   ├── generic.py
│   │   ├── langgraph.py
│   │   ├── autogen_core.py
│   │   ├── autogen_agentchat.py
│   │   └── crewai.py
│   ├── migration/
│   │   ├── exporter.py
│   │   ├── importer.py
│   │   └── trust.py
│   ├── security/
│   │   ├── redaction.py
│   │   ├── integrity.py
│   │   └── sandbox_policy.py
│   └── cli/
│       ├── inspect.py
│       ├── verify.py
│       └── repair.py
└── tests/
    ├── unit/
    ├── integration/
    ├── recovery/
    ├── compatibility/
    └── benchmarks/
```

## 7. 领域数据模型

### 7.1 标识与版本

必须区分以下标识：

- `run_id`：一次运行的唯一标识；
- `experience_id`：逻辑经验的稳定标识；
- `revision_id`：经验不可变内容版本的标识；
- `event_id`：领域事件唯一标识；
- `repository_id`：经验库唯一标识；
- `package_id`：迁移包唯一标识。

经验版本不使用简单的 `parent_id -> child_id` 单链模型。每个 revision 至少包含：

- 一个稳定的 `experience_id`；
- 唯一 `revision_id`；
- 零个或多个 `parent_revision_ids`；
- 单调递增的 `generation`；
- `content_hash`；
- 创建主体和时间；
- 可选的 `supersedes_revision_ids`。

首期可以限制为单父版本，但协议预留多父版本，以避免未来无法表达分支合并。

### 7.2 Experience Definition

经验定义至少包含以下逻辑区域：

#### Identity

- 经验和 revision 标识；
- Schema 版本；
- 内容哈希；
- 来源仓库及发布者。

#### Applicability

- 任务类型与触发关键词；
- 结构化输入 Schema；
- 前置条件与禁用条件；
- Agent 框架与兼容版本；
- Python、OS、模型和工具能力要求；
- 权限和运行环境要求；
- TTL 及重新验证条件。

#### Strategy

- DAG 节点和依赖；
- 参数绑定；
- 节点输出绑定；
- fallback、retry、timeout；
- 最终结果聚合方式；
- 失败后的补偿动作。

#### Outcome Contract

- 成功判据；
- 输出 Schema；
- 自动验证器引用；
- 必须存在的产物或状态变化；
- 容许误差。

#### Risk and Policy

- 风险等级；
- 是否包含外部副作用；
- 是否要求人工审批；
- 允许的使用模式；
- 敏感信息标签；
- 来源信任等级。

#### Explanation

- 经验摘要；
- 关键决策及原因；
- 适用边界；
- 已知反例；
- 失败恢复建议。

### 7.3 Typed Value

工具参数不能仅使用 `map<string, string>`。协议必须支持：

- string、integer、double、boolean、bytes；
- list、map 和 null；
- 运行输入引用；
- 前序节点输出引用；
- Secret 引用；
- Artifact 引用。

Secret 只保存引用，不保存明文值。经验导出时默认不包含 Secret 内容。

### 7.4 DAG Node

每个节点至少包含：

- `node_id`；
- `tool_contract_id` 与兼容版本范围；
- typed 参数绑定；
- 依赖节点；
- 超时和重试策略；
- 幂等性声明；
- 风险和审批要求；
- fallback；
- 可选补偿动作；
- 输出 Schema；
- 并发与资源限制。

### 7.5 Evaluation Projection

经验质量从 Evaluation Event 投影计算，至少包括：

- 验证次数；
- 成功、失败和不确定次数；
- 最近验证时间；
- 按环境划分的成功统计；
- 置信区间；
- 近期衰减后的可信度；
- 复用带来的成本、时延和成功率增益；
- 负面影响次数。

单个 `success_rate` 只能作为查询投影，不作为不可变定义中的权威字段。

## 8. 标准化事件协议

所有事件使用统一 Event Envelope：

- `event_id`；
- `event_type`；
- `schema_version`；
- `timestamp`；
- `repository_id`；
- `run_id`；
- `sequence_number`；
- `correlation_id` 与 `causation_id`；
- `producer`；
- payload；
- payload hash；
- 可选签名。

首批事件类型建议包括：

- `RunStarted`
- `ModelCallStarted` / `ModelCallCompleted`
- `ToolCallStarted` / `ToolCallCompleted` / `ToolCallFailed`
- `NodeStarted` / `NodeCompleted` / `NodeFailed`
- `ArtifactProduced`
- `RunCompleted` / `RunFailed` / `RunCancelled`
- `OutcomeEvaluated`
- `ExperienceCandidateCreated`
- `ExperienceRevisionPublished`
- `ExperienceValidated`
- `ExperienceActivated`
- `ExperienceDeprecated`
- `ExperienceQuarantined`
- `ExperienceTombstoned`
- `ExperienceRetrieved`
- `ExperienceApplied`
- `ExperienceApplicationEvaluated`
- `ExperiencePackageImported`

事件必须具有向前兼容策略。消费者遇到未知字段时保留并忽略，遇到未知关键事件类型时不得错误更新投影。

## 9. 经验生命周期

### 9.1 状态

```text
DRAFT → CANDIDATE → VALIDATED → ACTIVE → DEPRECATED → TOMBSTONED
                       │           │
                       └────┬──────┘
                            ▼
                       QUARANTINED
```

- `DRAFT`：人工编辑或编译中的未完成定义；
- `CANDIDATE`：由轨迹提取，但证据不足；
- `VALIDATED`：通过离线验证，尚未允许常规召回；
- `ACTIVE`：允许按策略参与线上召回；
- `DEPRECATED`：保留审计，但新任务默认不使用；
- `QUARANTINED`：来源不可信、验证失败或出现安全风险；
- `TOMBSTONED`：逻辑删除，不可再激活，只保留必要审计信息。

### 9.2 晋升门槛

门槛必须可配置。初始建议：

- 单次成功只生成 `CANDIDATE`；
- 有明确业务验证器的经验可更快进入 `VALIDATED`；
- 缺乏确定性验证器时，需要多个独立样本和人工审核；
- 进入 `ACTIVE` 前必须完成风险分类、兼容性声明和最小评测；
- 外部导入经验默认进入 `QUARANTINED` 或 `CANDIDATE`；
- 工具契约、模型能力或关键环境变化时触发重新验证。

### 9.3 反馈与淘汰

- 每次经验召回、采纳、执行和验证均记录事件；
- 近期连续失败自动降权；
- 命中高风险失败时立即隔离；
- 超过 TTL 未重新验证则不允许 Replay；
- 冲突经验由适用范围、可信度、时效性和策略优先级解决；
- 不允许静默覆盖或删除历史定义。

## 10. 成功判定体系

定义统一 `OutcomeEvaluator` 接口，支持组合以下证据：

1. 调用方显式断言；
2. 输出 Schema 校验；
3. 单元测试、业务规则或验收函数；
4. 产物存在性和内容哈希；
5. 环境状态变化；
6. 用户确认；
7. Judge 模型评分；
8. 工具错误率和重试率。

工具无报错只能是弱证据。评估结果必须表达：

- `SUCCESS`
- `FAILURE`
- `PARTIAL`
- `UNKNOWN`

并保存证据引用、评估器版本和置信度。Judge 模型的结论不能覆盖确定性业务验证器。

## 11. 存储与一致性设计

### 11.1 Event Log 是唯一事实来源

Binary Event Log 保存领域事件。以下均为投影：

- Active revision index；
- version graph；
- run/trace index；
- vector index；
- relation graph；
- evaluation statistics；
- migration registry。

任何投影损坏后都可以从日志重建。

### 11.2 日志帧格式

文件头至少包含：

- 文件 Magic；
- 文件格式版本；
- repository ID；
- segment ID；
- 创建时间；
- 校验信息。

每条记录至少包含：

```text
record_magic
format_version
record_type
flags
sequence_number
payload_length
payload
checksum
```

必须限制最大 payload 长度，并在分配内存前校验长度。

### 11.3 写入流程

单库首期采用单写者模型：

1. 事件进入有界写入队列；
2. writer 按顺序写入日志；
3. 根据 durability policy 决定 flush/fsync；
4. 写入成功后发布给投影器；
5. 投影记录自身处理到的日志水位；
6. 投影失败不回滚事实日志，通过重放恢复。

持久性等级：

- `BEST_EFFORT`：允许进程崩溃时丢失未 flush 的观察事件；
- `RUN_DURABLE`：Run 结束时保证相关事件落盘；
- `STRICT_DURABLE`：关键生命周期事件写入后 fsync 才确认。

### 11.4 崩溃恢复

启动时：

1. 验证文件头；
2. 加载最近有效快照；
3. 校验 repository、segment 和 log watermark；
4. 从 watermark 继续重放；
5. 检测尾部半写记录并安全截断或隔离；
6. 快照失效时全量重建；
7. 校验向量和图投影水位。

### 11.5 并发边界

MVP 支持：

- 单进程多协程；
- 单 repository 单写者；
- 多读者；
- 受控文件锁，防止两个进程同时写同一 repository。

跨进程、多主或分布式写入不属于 MVP。未来需要引入独立协调服务或数据库后端，不能仅依赖文件追加。

### 11.6 Segment 与 Compaction

- 日志按大小或时间轮转；
- segment 封存后只读；
- 快照记录覆盖的日志水位；
- compaction 生成新的派生 segment，不静默改变历史标识；
- 删除旧 segment 前必须满足保留、审计、迁移和恢复策略。

## 12. 检索与适用性判断

召回采用多阶段流程：

1. 结构化过滤：状态、租户、权限、框架、工具版本、风险和 TTL；
2. 候选生成：关键词/BM25 与向量语义检索；
3. 重排：语义、任务类型、成功证据、时效性和历史收益；
4. 适用性检查：输入 Schema、前置条件、环境指纹和工具契约；
5. 策略检查：是否允许 Advice、Replay 或 Exact Cache；
6. 冲突与去重；
7. 生成带来源引用的结果。

不允许使用单个固定向量阈值作为执行依据。阈值必须按 embedding 模型和评测集校准。

向量条目必须记录：

- embedding provider；
- model ID 与版本；
- dimension；
- 正规化方式；
- 被嵌入文本的版本和哈希；
- experience/revision ID；
- 投影水位。

当 embedding 模型变化时允许并存多个向量空间，或进行后台重新嵌入；不能混合比较不同空间中的分数。

## 13. 三种经验使用模式

### 13.1 ADVISE

默认模式。向 Agent 提供：

- 经验摘要；
- 推荐步骤；
- 关键前置条件；
- 已知风险和反例；
- 来源和可信度。

注入内容必须明确标记为不可信参考资料，避免其中的指令覆盖系统策略。

### 13.2 REPLAY_WITH_VERIFY

只有同时满足以下条件才允许：

- revision 为 ACTIVE；
- 结构化适用性检查通过；
- 工具契约兼容；
- 风险策略允许；
- 必要审批完成；
- 输入绑定完整；
- 有可执行的结果验证器；
- 经验未过期且近期表现达标。

Replay 必须生成新 Run，节点级记录结果，并在最终验证失败时停止、补偿或回退给正常 Agent 流程。

### 13.3 EXACT_CACHE

仅在以下条件成立时跳过 LLM：

- 操作是纯函数或明确幂等且无外部副作用；
- 输入 canonical hash 完全一致；
- 环境与依赖指纹符合策略；
- 权限上下文一致；
- 缓存仍在 TTL 内；
- 输出完整性校验通过。

语义相似度无论多高，都不能单独触发 Exact Cache。

## 14. DAG 编译与执行

### 14.1 编译来源优先级

1. 框架提供的结构化节点和工具事件；
2. AgentExperience 显式 Tool Registry 事件；
3. 通用 decorator 产生的调用事件；
4. Python stack 推断仅作为实验性回退，不进入默认可靠路径。

### 14.2 编译验证

发布前必须检查：

- DAG 无环；
- 所有依赖存在；
- 输入输出类型可连接；
- Tool Contract 可解析；
- 必填输入都能绑定；
- Secret 和 Artifact 引用合法；
- 并发节点不存在已知资源冲突；
- fallback 与补偿动作可用。

### 14.3 执行语义

执行器负责：

- 拓扑调度；
- 依赖满足后的受限并发；
- 超时、重试和取消传播；
- 节点级幂等键；
- fallback；
- 对已完成副作用执行补偿；
- 结果聚合与验证；
- 完整事件记录。

Executor 不直接通过字符串查找任意 Python 函数，所有工具必须通过 Tool Registry 注册，并声明版本、Schema、风险、权限、幂等性和副作用。

## 15. 失败观察与关系规则

函数或工具失败时先记录 `FailureObservation`，内容包括：

- 上下文条件；
- action/tool contract；
- 错误类型与是否可重试；
- 环境指纹；
- 参数摘要和脱敏信息；
- 影响范围；
- 证据和重复次数。

失败观察经过聚合和归因后，才可晋升为规则：

- `INFO`
- `WARNING`
- `AVOID`
- `REQUIRES_APPROVAL`
- `FORBIDDEN`

规则必须包含作用域、结构化条件、来源、置信度、有效期和 revision。临时网络故障不能自动变成永久禁令。

## 16. 框架适配设计

### 16.1 统一适配器职责

每个适配器只负责：

- 捕获生命周期事件；
- 将框架对象转成标准事件；
- 在允许的位置提供 Advice；
- 根据策略请求 Replay 或 Exact Cache；
- 保留 cancellation、streaming 和 error semantics；
- 不把框架专属对象泄漏到核心存储协议。

### 16.2 Generic Python

Decorator 只能可靠捕获函数边界。若希望获得工具级 DAG，被调用工具也必须经 Tool Registry 或 tracing context 记录。不能仅依靠“函数内部调用超过两个工具”这种无法通用观测的假设。

同时支持同步与异步函数，并正确传播 contextvars、异常、取消和返回类型。

### 16.3 LangGraph/LangChain

优先使用正式 middleware、model/tool call hook 和运行事件，不通过修改内部私有属性适配。需要明确支持的最低/最高版本并设置兼容测试矩阵。

### 16.4 AutoGen

AutoGen Core 与 AgentChat 分开适配。Core 以 runtime/message 生命周期为主，AgentChat 以 agent/team run 生命周期为主，不假定同一种 wrapper 可以覆盖二者。

### 16.5 CrewAI

使用公开 listener/callback/event 扩展点。首期若无法获得足够结构化工具事件，应降级为 Run/Task 级经验，而不是伪造精确 DAG。

### 16.6 `wrap_agent` 定位

可以保留统一便利入口，但内部必须返回明确的适配结果和能力声明，例如：

- 已识别框架；
- 可采集事件级别；
- 是否支持 Advice 注入；
- 是否支持 Replay；
- 不兼容原因。

未知对象不得静默 monkey patch。

## 17. 异步与运行时可靠性

核心 API 可采用 async-first，但必须承认文件和部分 SQLite/向量驱动是阻塞式的。实现可使用：

- 专用 writer task；
- 有界队列与 backpressure；
- 单写者 SQLite；
- 线程池包装阻塞 I/O；
- 批量写入；
- 明确的 `flush`、`close` 和 shutdown 生命周期。

Observer 内部错误默认不能导致 Agent 业务失败，但必须：

- 记录健康状态；
- 暴露 metrics；
- 对关键持久化失败提供可配置 fail-open/fail-closed 策略；
- 禁止无限队列；
- 在进程退出时尝试按 durability policy 清空队列。

## 18. 安全与隐私

### 18.1 数据采集

- 默认不存储 Secret、Token、Cookie 和凭据；
- 支持字段级脱敏和 allowlist；
- 原始 Prompt、模型响应和工具输出可按策略关闭或摘要化；
- Artifact 使用内容寻址和独立保留策略；
- 支持用户、项目和租户作用域。

### 18.2 提示注入防护

- 外部内容不能自动成为系统指令；
- Advice 使用固定边界和引用格式；
- 经验提取器不得把网页、文档中的指令默认当成控制策略；
- 高风险经验需要人工或策略审核；
- 记录来源链路以便追责。

### 18.3 执行安全

- Tool Registry 是执行白名单；
- 默认拒绝未知工具；
- 高风险工具需审批或沙箱；
- 文件、网络、进程和数据库权限由宿主环境控制；
- replay 不能扩大原调用方权限；
- 所有副作用节点必须声明风险和补偿能力。

### 18.4 完整性与信任

- 日志记录有 checksum；
- 迁移包有 manifest 和内容哈希；
- 支持发布者数字签名；
- 信任策略按仓库/发布者配置；
- 外部包先隔离扫描再导入；
- 导入不等于激活。

## 19. 迁移格式与流程

`.exp` 可以采用 ZIP 容器，但扩展名本身不代表可信。建议内部结构：

```text
manifest.pb
records.bin
checksums.pb
signature.bin          # 可选
artifacts/             # 可选，内容寻址
```

`manifest.pb` 至少包含：

- 包与 Schema 版本；
- package/source repository ID；
- 导出时间和发布者；
- 所含 experience/revision/event ID；
- 各文件大小和哈希；
- embedding 模型、维度和文本哈希；
- Tool Contract 依赖；
- 环境兼容范围；
- 风险、敏感度和许可元数据。

### 19.1 导出

1. 解析活动 revision 和必要历史；
2. 生成自包含记录流；
3. 默认排除 Secret；
4. 收集 Artifact 或引用；
5. 生成 manifest 与 checksum；
6. 可选签名；
7. 原子生成最终包。

### 19.2 导入

1. 在临时隔离目录中打开；
2. 防止 Zip Slip、压缩炸弹和超大文件；
3. 校验格式、大小、checksum 和签名；
4. 检查 Schema、工具和环境兼容性；
5. 处理 ID 与内容哈希冲突；
6. 将事件重新追加到本地日志；
7. 根据本地 embedding 配置重建向量；
8. 重建本地 offset 和投影；
9. 以 `QUARANTINED` 或 `CANDIDATE` 状态注册；
10. 验证通过后再激活。

因此“迁移即拷贝”只描述容器传输体验，不表示跳过校验、重索引和重新验证。

## 20. Protobuf 与构建策略

- `.proto` 是跨版本协议的权威定义；
- 发布包提交构建阶段生成的 `_pb2.py`；
- 不在最终用户安装时强依赖系统 `protoc`；
- CI 重新生成并校验生成文件无漂移；
- 生成类型存根以改善静态检查；
- 字段编号一旦发布不得复用；
- 删除字段必须 `reserved`；
- 核心 envelope 与 payload 分离，便于协议演进；
- Python package 通过正确的 `__init__.py` 组织。

## 21. 可观测性与运维

至少暴露以下指标：

- 事件队列深度与丢弃数；
- 日志写入延迟和失败数；
- 投影水位与落后量；
- 召回延迟与候选数；
- Advice/Replay/Exact Cache 使用次数；
- 经验采纳率和实际增益；
- Replay 验证失败与补偿次数；
- 隔离和安全策略命中次数；
- repository、segment 和向量索引大小。

CLI 建议支持：

- 查看 run、trace、experience 和 revision；
- 验证日志与迁移包完整性；
- 查看投影水位；
- 从日志重建投影；
- 修复尾部半写记录；
- 导出人类可读视图；
- 不允许 CLI 绕过安全策略直接激活外部经验。

## 22. 评测体系

### 22.1 离线基准

建立包含重复任务、相似任务、边界任务、冲突任务和环境变化任务的数据集，对比：

- 无经验；
- 仅关键词检索；
- 仅向量检索；
- 混合检索；
- Advice；
- Replay with verify；
- Exact Cache。

### 22.2 核心指标

- 端到端任务成功率；
- 经验命中率；
- 命中后的实际增益；
- 错误经验造成的失败率；
- Precision@K、Recall@K 和适用性判定准确率；
- Token、工具调用、成本和延迟变化；
- Replay 验证失败率；
- 安全策略漏判和误判率；
- 崩溃恢复与投影重建正确率。

### 22.3 上线门槛

建议按能力分别设置门槛：

- 采集上线：不得影响宿主业务正确性，性能开销可控；
- Advice 上线：错误建议率低于约定阈值，整体成功率不下降；
- Replay 上线：适用性与验证器覆盖达标，无未控制副作用；
- Exact Cache 上线：精确匹配与权限隔离测试全部通过。

具体数值在建立基准数据后确定，不在架构阶段凭经验写死。

## 23. 测试策略

### 23.1 单元测试

- Protobuf round-trip；
- frame encode/decode；
- DAG 校验和拓扑排序；
- 生命周期状态迁移；
- applicability 和 policy；
- typed value 与参数绑定；
- 脱敏规则。

### 23.2 属性与模糊测试

- 任意字节输入不得导致无限内存分配；
- 损坏长度、checksum 和未知版本安全失败；
- DAG 随机图检测循环；
- ZIP 路径和压缩限制；
- 重放日志必须幂等地产生相同投影。

### 23.3 崩溃恢复测试

在每个写入边界模拟崩溃：

- 文件头半写；
- payload 半写；
- checksum 半写；
- 日志已提交但投影未更新；
- 快照写入中断；
- segment 轮转中断。

### 23.4 兼容测试

- 旧日志由新版本读取；
- 未知字段保留；
- 不同 Schema 版本迁移；
- 框架支持版本矩阵；
- 不同 embedding 空间不得混检。

### 23.5 安全测试

- Secret 泄漏；
- prompt injection 固化；
- 恶意 `.exp` 包；
- 未授权工具执行；
- 租户越权；
- 签名与哈希篡改。

## 24. 分阶段实施路线

### Phase 0：协议与决策冻结

交付物：

- 术语表和领域边界；
- Architecture Decision Records；
- 核心 Protobuf 草案；
- 事件状态机；
- 日志帧和恢复规范；
- 威胁模型；
- 评测数据集草案。

退出条件：关键协议完成评审，MVP 范围无高风险歧义。

### Phase 1：可靠采集与存储

范围：

- Generic decorator；
- 一个 LangGraph/LangChain 适配器；
- 标准化 Run/Tool/Outcome 事件；
- Append-Only segmented log；
- 投影、快照和恢复；
- CLI inspect/verify；
- 手工或确定性成功标注。

明确不做：向量召回、自动 DAG replay、外部迁移自动激活。

### Phase 2：候选经验与 Advice

范围：

- Candidate extractor；
- 生命周期；
- 混合检索和 applicability；
- Advice 注入；
- Evaluation feedback；
- 离线 A/B 评测。

退出条件：Advice 对目标基准产生可重复的正向收益。

### Phase 3：受控 Replay

范围：

- Tool Registry；
- typed DAG；
- Executor；
- verifier；
- approval 与补偿；
- 仅支持幂等或低风险工具。

退出条件：安全与恢复测试通过，Replay 的错误应用率达到门槛。

### Phase 4：迁移与多框架

范围：

- 签名 `.exp` 包；
- 隔离导入与重新嵌入；
- AutoGen Core/AgentChat 适配；
- CrewAI 适配；
- 跨版本兼容矩阵。

### Phase 5：规模化演进

候选范围：

- 多进程或远程存储后端；
- 多租户治理；
- 在线实验与自动降权；
- 经验冲突分析与合并建议；
- 分布式事件日志；
- 企业级审计和保留策略。

## 25. MVP 推荐范围

为了降低首期风险，MVP 建议只实现：

1. 单机、单 repository、单写者；
2. Generic decorator 和 LangGraph/LangChain 适配；
3. Run、Tool、Outcome 标准事件；
4. Protobuf framed event log；
5. 快照、重放、完整性检查；
6. 候选经验的人工确认；
7. Advice-only 召回；
8. SQLite 元数据/BM25 加可替换向量接口；
9. CLI 查看和修复；
10. 基础脱敏与租户作用域。

MVP 不实现：

- 自动绕过 LLM；
- 高风险工具重放；
- 任意 Python 堆栈转 DAG；
- 自动信任外部经验；
- 多进程并发写；
- 自动将一次失败升级为禁令。

## 26. 关键架构决策清单

正式编码前需要逐项形成 ADR：

1. 事件日志帧具体二进制布局与 checksum 算法；
2. Protobuf message 划分和版本规则；
3. repository 和 segment 命名布局；
4. 快照格式与投影水位协议；
5. SQLite-vec、LanceDB 或可插拔后端的首选实现；
6. embedding provider 接口和默认策略；
7. OutcomeEvaluator 的组合规则；
8. Candidate 晋升门槛；
9. Advice 注入边界和 prompt injection 防护；
10. Tool Contract 与风险分类；
11. durability 默认等级；
12. `.exp` 签名和信任模型；
13. LangGraph/LangChain 首期支持版本；
14. 数据保留、脱敏和删除策略；
15. 性能预算与基准任务。

## 27. 风险评估

| 风险 | 概率 | 影响 | 主要缓解措施 |
|---|---:|---:|---|
| 将无异常误判为成功 | 高 | 高 | OutcomeEvaluator、候选状态、多证据验证 |
| 相似经验错误应用 | 高 | 高 | 结构化 applicability、Advice 默认、执行策略 |
| 自动重放产生副作用 | 中 | 极高 | Tool Registry、审批、幂等、验证和补偿 |
| 框架升级导致适配失效 | 高 | 中 | 独立适配器、版本矩阵、兼容测试 |
| 日志与投影不一致 | 中 | 高 | 日志为事实源、水位和重放 |
| 崩溃造成尾部损坏 | 中 | 中 | framed record、checksum、恢复扫描 |
| 外部经验投毒 | 中 | 极高 | 隔离导入、签名、来源信任、重新验证 |
| Secret 被固化或导出 | 中 | 极高 | allowlist、脱敏、引用化、导出扫描 |
| embedding 模型变化 | 高 | 中 | 空间标识、并存索引、重新嵌入 |
| 经验库无限增长 | 高 | 中 | segment、保留策略、checkpoint、compaction |
| 异步旁路静默丢数据 | 中 | 中 | durability 等级、队列监控、flush 生命周期 |
| 经验没有实际收益 | 中 | 高 | 离线基准、线上反馈、阶段退出门槛 |

## 28. 可行性结论

### 高可行性

- 标准化轨迹采集；
- Protobuf Append-Only 本地事件日志；
- 可重建索引和向量投影；
- Advice-only 经验召回；
- 经验版本、审计和迁移容器。

### 中等可行性

- 多框架统一表层 API；
- 从结构化框架事件编译 DAG；
- 跨环境迁移后的自动兼容性检查；
- 低风险任务的受控 Replay。

### 低可行性或不应直接承诺

- 从任意 Python 堆栈可靠推断工作流语义；
- 仅凭向量相似度直接跳过 LLM；
- 对未知 Agent 类型自动注入完整生命周期钩子；
- 不经重验实现真正的跨环境“拷贝即运行”；
- 对不可逆、高权限工具进行无人值守重放。

总体上项目可行，但应把它定义为一个“基于事件溯源的经验验证、检索与安全复用系统”，而不只是“工作流二进制存储 SDK”。优先完成可靠采集、成功验证和 Advice 闭环，再逐步开放 Replay，能够显著降低返工和安全风险。

## 29. 经验采集对象与语义边界

### 29.1 先明确“我们要获得什么经验”

AgentExperience 的核心经验不是某一次完整对话，也不是工具调用列表，而是：

> 在明确任务目标、输入类型、环境约束和风险边界下，一组经过结果验证、能够解释关键决策、并可在兼容条件下复用的策略。

一条可发布经验必须尽可能回答：

1. **任务是什么**：用户意图、任务类别和成功标准；
2. **为什么选择该路径**：关键分支、工具或 Skill 的选择依据；
3. **具体做了什么**：有因果关系的节点、调用、参数模板和依赖；
4. **获得了什么结果**：最终输出、产物和环境状态变化；
5. **为什么认为成功**：确定性验证、用户反馈或其他证据；
6. **适用于哪里**：框架、工具、模型、权限、数据和版本前提；
7. **不适用于哪里**：反例、禁用条件、失败边界和副作用；
8. **如何安全复用**：Advice、Replay 或 Exact Cache，以及验证和审批要求。

经验应按语义分为六类：

| 经验类型 | 内容 | 首期使用方式 |
|---|---|---|
| `TASK_STRATEGY` | 完成某类任务的总体规划、步骤与分支 | Advice |
| `TOOL_ROUTING` | 在什么条件下选择哪个 Tool/MCP Tool | Advice，后期受控 Replay |
| `PARAMETERIZATION` | 工具参数的生成、转换和节点间绑定规律 | Advice/Replay |
| `RECOVERY` | 错误分类、重试、fallback 和补偿策略 | Advice/Replay |
| `VALIDATION` | 如何判断结果正确、完整和安全 | Advice/自动验证 |
| `CONSTRAINT` | 应避免、需审批或禁止的行为及条件 | Policy |

可选的辅助经验包括模型路由、检索策略、上下文裁剪和并发调度；它们必须有成本或成功率证据，不能因为某次模型选择恰好成功就固化。

### 29.2 Skill、Tool、MCP 的关系

- **Tool**：一个具有输入输出契约的原子能力，是执行轨迹的主要动作单元。
- **MCP Tool**：通过 MCP Server 暴露的 Tool。经验中记录稳定身份、Schema 和调用结果摘要，不把一次连接会话当作经验。
- **MCP Resource**：供模型读取的上下文资源。它通常是证据或输入来源，不是动作；应记录 URI/模板、版本或内容哈希、读取范围和引用关系。
- **MCP Prompt**：服务端提供的提示模板。它是策略输入，需记录名称、参数和版本，但其文本不能自动获得高于系统策略的权限。
- **Skill**：比 Tool 更高层的能力包，通常包含说明、流程、模板、脚本或多个工具的协调规则。Skill 的加载、选择和使用结果应监听；经验可以形成“何时选择 Skill、如何组合 Skill 与 Tool”的策略，但默认不复制 Skill 全部内容。
- **Agent/Sub-agent**：可委派任务的执行主体。应记录委派理由、任务边界、结果和验收，而不是把子 Agent 的全部内部对话无条件固化。
- **Memory/Retriever**：提供事实或历史上下文。应记录查询、命中文档引用和对决策的贡献，不把检索到的事实直接当作可执行经验。

因此，经验的最小动作单位通常是 Tool/MCP Tool；最小策略单位是“决策 + 一个或多个动作 + 结果验证”；Skill 是可复用策略来源或执行能力，不等同于经验本身。

### 29.3 四层采集模型

所有框架事件先归入四层，避免将不同概念混成一条轨迹：

1. **Intent 层**：用户目标、任务分类、输入约束、成功标准；
2. **Decision 层**：计划、路由、分支、模型/Skill/Tool 选择和审批；
3. **Action 层**：Tool、MCP、Agent 委派、节点和环境操作；
4. **Outcome 层**：输出、Artifact、状态变化、验证、用户反馈和成本。

只有 Action 没有 Intent 和 Outcome 的记录，不足以成为经验；只有自然语言推理没有可观测决策或结果，也不应成为可靠经验。

### 29.4 原始推理数据边界

不要求也不默认保存模型私有 chain-of-thought。Decision 层只记录可审计的结构化理由，例如：

- 选择的动作或分支；
- 简短决策摘要；
- 使用的证据引用；
- 被拒绝候选的机器可读原因；
- 策略和规则命中结果。

这既降低敏感信息风险，也避免将不可验证的长篇推理误当作经验。

### 29.5 能形成经验、只能作为证据、默认不固化

| 数据 | 角色 | 是否进入经验定义 |
|---|---|---|
| 用户任务与约束摘要 | 适用条件 | 是，脱敏和抽象后 |
| 完整原始 Prompt | 原始证据 | 默认否，可按策略保留 |
| System Prompt | 环境/策略指纹 | 默认只保存版本或哈希 |
| Tool/MCP Tool Schema | 能力契约 | 是，保存稳定标识与版本 |
| Tool 参数 | 动作模板 | 是，但需脱敏、变量化 |
| Tool 原始返回 | 运行证据 | 默认摘要/哈希，必要时引用 Artifact |
| LangGraph 全量 State | 运行证据 | 默认否，只采集 allowlist/diff |
| 节点、边、路由 | 策略结构 | 是 |
| Skill 全文与脚本 | 外部能力资产 | 默认不复制，只保存引用、版本和哈希 |
| Skill 选择和结果 | 决策与证据 | 是 |
| MCP Resource 正文 | 外部事实 | 默认不固化，只保存来源与哈希 |
| MCP Prompt 展开文本 | 策略输入 | 默认不固化，保存模板身份、参数和哈希 |
| 用户审批/修改/拒绝 | 高价值反馈 | 是 |
| 最终结果与验收 | Outcome | 是，按隐私策略摘要或引用 |
| Token、延迟、重试 | 质量证据 | 进入 Evaluation，不进入策略正文 |
| Chain-of-thought | 私有推理 | 否 |
| Secret/凭据/Cookie | 敏感数据 | 禁止 |

### 29.6 候选经验的提取粒度

一次成功 Run 可以产生零条、一条或多条候选经验：

- 没有新颖策略或可复用价值时产生零条；
- 一个稳定的端到端模式形成 `TASK_STRATEGY`；
- 关键工具选择形成 `TOOL_ROUTING`；
- 有价值的故障恢复形成 `RECOVERY`；
- 独立验收方法形成 `VALIDATION`。

禁止机械地将每个成功 Run 整体保存为一条经验。提取器必须进行抽象、变量化、去重、边界识别和证据关联。

## 30. 统一监听事件模型

### 30.1 必须监听的核心事件

MVP 的 P0 监听集合如下：

| 类别 | 事件 | 关键字段 | 用途 |
|---|---|---|---|
| Run | start/end/error/cancel | run、parent、thread/session、输入摘要、最终状态 | 确定经验边界 |
| Agent | before/after agent | agent identity、role、输入输出 | 记录主体与任务结果 |
| Model | request/response/error | model identity、消息角色摘要、tool calls、usage | 捕获决策与成本 |
| Tool | registered/start/end/error | contract、call ID、参数、结果、时延、副作用 | 形成动作和路由经验 |
| Graph | node start/end/error | graph/node/path、input/output diff | 构建 DAG 与分支 |
| Route | branch selected | 条件摘要、候选、选中分支 | 形成决策经验 |
| Outcome | evaluated | status、evidence、verifier | 判断是否可形成经验 |
| Approval | requested/decision | action、risk、approve/edit/reject | 形成风险与人工反馈 |
| Artifact | produced/consumed | type、URI、hash、producer | 证明结果与数据流 |

如果某个适配器无法提供 Outcome，运行只能成为 Trace 或 Candidate，不得直接成为 ACTIVE 经验。

### 30.2 推荐监听的 P1 事件

- Skill discover/load/select/start/end/error；
- MCP server connect/disconnect/capability change；
- MCP tools/list、resources/list、prompts/list 的能力快照变化；
- MCP tool call、resource read/subscribe/update、prompt get；
- Retriever query、documents selected 和 citation used；
- Memory read/write；
- Sub-agent spawn/delegate/join/cancel；
- Checkpoint save/load、interrupt/resume；
- retry、fallback、compensation；
- policy/guardrail allow/block/redact；
- streaming completion 事件。

### 30.3 可选 P2 事件

- token chunk；
- 完整 state snapshot；
- 每次 prompt 模板渲染正文；
- 低层网络请求；
- Python 函数调用栈。

P2 数据成本高、噪声大或隐私风险高，默认关闭。核心经验形成不能依赖 token 级监听。

### 30.4 关联标识

为跨框架和跨协议拼接轨迹，标准事件至少需要：

- `run_id`、`parent_run_id`；
- `agent_id`、`framework`；
- `graph_id`、`node_id`、`subgraph_path`；
- `model_call_id`；
- `tool_call_id`；
- `mcp_server_id`、`mcp_session_id`；
- `skill_id`、`skill_version`；
- `thread_id`/`session_id`；
- `correlation_id`、`causation_id`；
- 单调 `sequence_number`。

并行调用不能仅依靠时间戳排序；必须使用调用 ID、父子关系和因果标识恢复 DAG。

### 30.5 监听降级等级

适配器启动时公布能力等级：

- `L0_RUN`：只能观察输入和最终输出；
- `L1_ACTION`：可观察 Tool/MCP/Agent 动作；
- `L2_GRAPH`：可观察节点、路由、并行和状态差异；
- `L3_OUTCOME`：具有可靠成功验证和反馈。

只有达到 L2 才能自动生成结构化 DAG 候选；只有达到 L3 才能自动参与经验晋升。低等级适配不得伪造缺失信息。

## 31. 主流框架与协议适配矩阵

### 31.1 优先级建议

| 优先级 | 适配目标 | 理由 | 首期目标等级 |
|---|---|---|---|
| P0 | LangChain Agent | 主流 Tool/Model agent loop，公开 middleware | L3 |
| P0 | LangGraph | 显式图、节点、状态、checkpoint、interrupt | L3 |
| P0 | Generic Python | 覆盖自研 Agent 和普通函数 | L1/L3 |
| P0 | MCP Client | 跨框架工具/资源/提示协议 | L1/L3 |
| P1 | AutoGen AgentChat | 主流多 Agent 会话和 Team | L1/L3 |
| P1 | AutoGen Core | 事件驱动 runtime 和消息路由 | L2/L3 |
| P1 | CrewAI Crew/Flow | 多 Agent、Task 和 Flow 编排 | L2/L3 |
| P1 | OpenAI Agents SDK | Agent、handoff、tool、guardrail、trace | L2/L3 |
| P2 | Semantic Kernel | function/plugin、planner/process | L1/L3 |
| P2 | LlamaIndex Workflows/Agents | workflow event、tool、retrieval | L2/L3 |
| P2 | 自定义 HTTP/消息 Agent | 通过 OpenTelemetry/标准事件接入 | 视能力而定 |

“主流”会变化，因此核心层不能依赖任何框架。适配优先级应按用户群、公开扩展点稳定性和评测需求定期调整。

### 31.2 LangChain Agent 监听点

优先使用公开 middleware：

- `before_agent`：建立 Run 边界，采集输入和上下文指纹；
- `before_model` / `wrap_model_call`：记录模型、可用工具、消息摘要和注入经验；
- `after_model`：记录结构化输出、模型选择的 tool calls 和 usage；
- `wrap_tool_call`：记录工具契约、完整调用生命周期、错误、重试和返回摘要；
- `after_agent`：记录最终输出并触发 OutcomeEvaluator。

LangChain 的 tool call ID 应作为模型决策与 ToolMessage 结果之间的主要关联键。模型流式 chunk 只用于观测，不作为最终动作；必须在聚合出完整 tool call 后记录动作事件。公开 middleware 已覆盖 agent、model 和 tool 生命周期，适合成为主要接入路径。[LangChain Middleware](https://docs.langchain.com/oss/python/langchain/middleware/custom)、[LangChain Tools](https://docs.langchain.com/oss/python/langchain/tools)

### 31.3 LangGraph 监听点

监听：

- graph invocation start/end/error/cancel；
- node/task start/end/error；
- state update diff，默认不存全量 state；
- conditional edge/route 结果；
- subgraph path 与父子关系；
- checkpoint save/load；
- interrupt 和 resume；
- `Command` 导致的 update/goto/resume；
- ToolNode 内的 tool calls；
- streaming 的 `updates`、`tasks`、`checkpoints`、`subgraphs` 等结构化事件。

LangGraph interrupt 恢复时可能重新开始节点，经验记录必须以幂等键识别重复副作用，不能把恢复后的重复执行误判为两个独立策略。官方也明确要求 interrupt 前的副作用具备幂等性。[LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)、[LangGraph Event Streaming](https://docs.langchain.com/oss/python/langgraph/event-streaming)

### 31.4 MCP 监听点

MCP 适配器位于 Client 侧或网关侧，监听协议语义而不是特定 Agent 框架：

- server identity、transport、协议版本和初始化能力；
- tools/resources/prompts 能力列表及变化通知；
- tool `call` 请求、参数、结果、错误和取消；
- resource `read`、模板参数、内容哈希、订阅和更新；
- prompt `get`、参数和模板版本/哈希；
- progress、logging 和 cancellation；
- elicitation/approval 等用户交互（如果实现支持）；
- server disconnect/reconnect 和 capability drift。

MCP Tool 的稳定身份不能只用 tool name，建议使用：

```text
server_trust_domain + server_identity + tool_name + schema_hash
```

URI、文件内容、网页正文等 MCP Resource 默认只作为来源证据；经验保存其引用和内容哈希，除非数据治理策略明确允许复制。MCP Tool 调用可以成为 Action，但是否形成经验取决于任务结果验证。

### 31.5 Skill 监听点

由于 Skill 并非所有框架共有的统一协议，核心定义一个通用 Skill Event：

- discover：发现了哪些 Skill；
- eligible：哪些 Skill 满足触发条件；
- selected/rejected：选择结果和结构化原因；
- loaded：名称、版本、来源、内容哈希和依赖；
- started/completed/failed：执行范围、内部动作引用和结果；
- artifact used：模板、脚本或参考资产；
- feedback：该 Skill 对成功率、成本和时延的影响。

Skill 内容由其拥有者管理。AgentExperience 默认只保存 manifest、版本、哈希和调用引用；只有获得明确授权才把 Skill 资产打入迁移包。

### 31.6 多 Agent 与委派监听点

对 AutoGen、CrewAI、OpenAI Agents SDK 等多 Agent 系统，统一监听：

- agent/team/crew 创建和角色能力摘要；
- message send/receive 与因果关联；
- handoff/delegation 的来源、目标、任务契约和理由；
- sub-agent start/end/error/cancel；
- shared context 或 memory 的读写引用；
- 汇聚、投票、仲裁或终止条件；
- 每个子任务的 Outcome 和总任务 Outcome。

高价值经验是“什么任务应委派给什么能力的 Agent、如何定义子任务和验收”，而不是聊天消息的简单顺序。

### 31.7 Retriever、Memory 与 RAG 监听点

监听：

- query 及其规范化/改写摘要；
- retriever/index identity 和版本；
- filter、top-k 和 score；
- 返回文档 ID、版本、URI、hash；
- 哪些文档实际被最终回答引用；
- memory read/write 类型、scope 和 TTL；
- 基于检索的最终 Outcome。

由此形成的是“检索和证据选择经验”，不是复制事实内容。易变化的事实必须保持来源引用和新鲜度检查。

### 31.8 Provider 原生 Tool 与代码执行

模型供应商的原生搜索、文件检索、代码执行、计算机操作等能力必须归一化为 Tool Action，并额外记录：

- provider 与能力版本；
- 沙箱/权限范围；
- 输入和产物引用；
- 是否访问网络或外部状态；
- 副作用与审批；
- provider 返回的 call ID。

计算机操作、Shell、文件写入、数据库写入和消息发送属于高风险动作，默认不能通过语义经验自动 Replay。

### 31.9 OpenTelemetry 互操作

建议将标准事件同时映射为 OpenTelemetry trace/span：

- Run/Agent/Graph Node/Model/Tool 为 span；
- correlation、token、cost、framework、tool contract 为 attributes；
- Artifact、Outcome、Approval 为 span event 或关联对象。

OpenTelemetry 用于跨组件观测与接入，不替代 AgentExperience 的领域事件日志。敏感参数不得无差别写入 span attribute。

## 32. 经验价值筛选与固化规则

### 32.1 值得固化的经验

候选经验至少满足以下多数条件：

- 有明确且已验证的 Outcome；
- 包含至少一个可解释的决策或非平凡动作组合；
- 对未来任务存在可描述的适用范围；
- 相比基线减少错误、成本、时延或步骤；
- 能抽象为参数和条件，而非绑定单个具体输入；
- Tool/Skill/MCP 契约稳定且可识别；
- 不依赖不可迁移的隐式状态；
- 敏感信息可以安全移除；
- 与已有经验不完全重复。

### 32.2 不应固化为经验

- 闲聊或一次性内容生成，除非存在稳定工作流；
- 仅有模型回答、无成功验证；
- 纯粹重复已有经验；
- 依赖临时 Token、Cookie 或会话隐式状态；
- 主要价值是易变化事实，而非解决策略；
- 无法区分成功来自策略还是偶然环境；
- 含无法脱敏的个人或机密数据；
- 高风险副作用且没有审批、验证和补偿；
- 失败原因尚未归因的单次异常。

### 32.3 经验抽象规则

提取时应：

1. 将具体值变量化，例如具体城市变为 `location`；
2. 保留决定分支的关键特征，不保存无关上下文；
3. 将固定工具名称绑定为 Tool Contract，而非自然语言字符串；
4. 将节点间数据流表示为 typed binding；
5. 将输出正确性表示为 verifier；
6. 保存反例和禁用条件；
7. 关联原始 Run 作为证据，但不把完整 Trace 塞入经验正文；
8. 对相似候选聚类、去重，并保留不同适用边界；
9. 不能证明因果时标注为相关性经验并降低自动化等级。

### 32.4 经验质量评分

建议使用多维评分而不是一个总成功率：

- `outcome_confidence`：结果是否真的成功；
- `applicability_confidence`：适用边界是否可靠；
- `reproducibility`：跨样本复现程度；
- `novelty`：相对已有经验的新信息；
- `utility_gain`：成功率、成本或时延增益；
- `freshness`：依赖和事实的新鲜度；
- `safety_confidence`：风险与副作用是否被控制；
- `portability`：跨环境复用能力。

不同经验类型使用不同权重。质量评分决定检索排序和允许的使用模式，但不能越过硬性安全策略。

### 32.5 MVP 监听范围最终建议

首个可执行版本应冻结为：

1. LangChain Agent middleware；
2. LangGraph graph/node/route/interrupt/ToolNode；
3. Generic Python decorator + Tool Registry；
4. MCP Client 的 tools/resources/prompts 和生命周期；
5. Run、Model、Tool、Graph、Outcome、Approval、Artifact 七类 P0 事件；
6. Skill 只做 identity/select/result 监听，不解析或复制全部内容；
7. Retriever/Memory 首期记录引用和贡献，不固化文档正文；
8. 只生成 TASK_STRATEGY、TOOL_ROUTING、RECOVERY、VALIDATION 四类 Candidate；
9. 只开放 Advice 使用；
10. Outcome 缺失时只存 Trace，不自动形成可发布经验。

AutoGen、CrewAI、OpenAI Agents SDK 放入下一适配批次。在核心标准事件稳定后接入，可以避免每个框架各自产生不兼容的经验格式。

## 33. PyPI 开源库与发行工程规范

### 33.1 项目产品形态

AgentExperience 明确定位为：

- 发布到 PyPI 的开源 Python SDK；
- 安装发行名暂定为 `agent-experience`；
- Python 导入包名为 `agent_experience`；
- 采用语义化版本和稳定的公共 API；
- 核心包默认保持轻量，框架适配器和存储后端使用 optional extras；
- 首期尽量发布跨平台纯 Python wheel，避免强制绑定特定平台原生扩展。

在首次发布前必须查询并确认 PyPI 项目名可用。发行名一经公开不轻易变更。

### 33.2 推荐仓库与源码布局

采用标准 `src` layout：

```text
AgentExperience/
├── pyproject.toml
├── setup.py
├── MANIFEST.in
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
├── SECURITY.md
├── NOTICE                         # 存在第三方声明时
├── protos/                        # 协议源文件，进入 sdist
│   ├── common.proto
│   ├── events.proto
│   ├── experience.proto
│   └── package.proto
├── src/
│   └── agent_experience/
│       ├── __init__.py
│       ├── py.typed
│       ├── _version.py
│       ├── schema/                # 已生成的 pb2/pyi，进入 wheel
│       ├── core/
│       ├── events/
│       ├── storage/
│       ├── experience/
│       ├── retrieval/
│       ├── execution/
│       ├── adapters/
│       ├── migration/
│       ├── security/
│       └── cli/
├── tests/                         # 进入 sdist，默认不进入 wheel
├── docs/                          # 进入 sdist，默认不进入 wheel
├── examples/                      # 精选示例进入 sdist，不进入 wheel
├── benchmarks/                    # 仓库保留，默认不进入发行包
├── scripts/                       # 开发/发布脚本，按需进入 sdist
└── .github/workflows/
```

所有 Python package 目录使用 `__init__.py`，不能写成 `init.py`。

### 33.3 `pyproject.toml` 是唯一元数据事实来源

现代 Python 包以 `pyproject.toml` 为构建和项目元数据的权威来源：

- `[build-system]` 声明 setuptools build backend 和构建期依赖；
- `[project]` 声明名称、版本、描述、README、许可证、Python 版本、依赖、classifiers 和 URL；
- `[project.optional-dependencies]` 声明 extras；
- `[project.scripts]` 声明 CLI 入口；
- `[tool.setuptools]` 声明 `src` layout、包发现和 package data；
- lint、test、type check 和 coverage 工具配置也可以放入对应 `[tool.*]` 区域。

PyPA 推荐新项目使用 `pyproject.toml` 的 `[project]` 表；`setup.py` 可以保留，但不应成为第二套元数据来源。[PyPA pyproject.toml 指南](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)

### 33.4 必须保留但保持最小化的 `setup.py`

项目根目录必须提供 `setup.py`，用于仍会探测该文件的兼容工具。设计约束：

- 文件保持最小，只调用 setuptools 的 setup 入口；
- 不重复定义 name、version、dependencies、extras 或 entry points；
- 不从网络下载依赖；
- 不在 import 阶段编译 Protobuf 或执行其他副作用；
- 不使用 `setup_requires`；
- 不把 `setup.py` 作为安装、构建或上传命令入口。

官方建议也允许现代 setuptools 项目保留最小 `setup.py`，同时让 `pyproject.toml` 承担配置。[PyPA 现代化 setup.py 指南](https://packaging.python.org/en/latest/guides/modernize-setup-py-project/)

正式工作流禁止：

- `python setup.py install`
- `python setup.py develop`
- `python setup.py sdist`
- `python setup.py bdist_wheel`
- `python setup.py upload`

对应使用 `pip install .`、`pip install -e .`、`python -m build` 和 PyPI Trusted Publishing/Twine。

### 33.5 版本与 Python 支持策略

- 使用 PEP 440 兼容版本；
- 公共发行遵循 SemVer：破坏性 API 变更提升 major；
- `0.x` 阶段仍需通过 changelog 明确破坏性变更；
- 版本单一来源，推荐由 Git tag 通过 `setuptools-scm` 产生，或由单一 `_version.py` 提供；
- 不在 `__init__.py` 复制硬编码版本；
- MVP 建议最低支持 Python 3.10；正式发布前根据框架兼容矩阵冻结；
- 支持的 Python 版本必须在 CI 中逐一测试，并与 `requires-python` 和 classifiers 一致；
- 停止支持某个 Python 版本需要在 changelog 中提前说明。

### 33.6 依赖分层与 extras

核心依赖必须仅包含所有安装场景都需要的库。建议分组：

| Extra | 内容范围 |
|---|---|
| 默认 core | Protobuf、核心模型和本地基础能力 |
| `langchain` | LangChain Agent 适配依赖 |
| `langgraph` | LangGraph 适配依赖 |
| `mcp` | MCP Client/协议适配依赖 |
| `autogen` | AutoGen AgentChat/Core 适配依赖 |
| `crewai` | CrewAI 适配依赖 |
| `openai-agents` | OpenAI Agents SDK 适配依赖 |
| `lancedb` | LanceDB 向量后端 |
| `sqlite-vec` | sqlite-vec 向量后端 |
| `cli` | Rich 等增强 CLI 依赖 |
| `all-frameworks` | 所有稳定框架适配器，不含开发工具 |
| `dev` | test、lint、type、build 工具，仅开发使用 |
| `docs` | 文档构建依赖 |

规范要求：

- optional adapter 模块不得在顶层无条件 import 对应框架；
- 缺少 extra 时抛出明确异常，并给出准确安装提示；
- 不强制用户同时安装互相冲突的主流框架；
- 核心接口不能暴露 optional dependency 的类型作为必需运行时对象；
- 依赖使用兼容范围，不随意无上限锁死，也不对库项目提交应用式全量依赖锁作为用户安装依据；
- 对存在原生二进制的后端提供纯 Python 或标准库降级路径。

### 33.7 Protobuf 源文件与生成文件

为了让 PyPI 安装不依赖本机 `protoc`：

- `.proto` 源文件保留在仓库，并包含在 sdist；
- 生成的 `_pb2.py` 和类型存根包含在 `src/agent_experience/schema/`，同时进入 sdist 和 wheel；
- 普通用户安装 wheel/sdist 时不自动重新生成 Protobuf；
- 开发命令显式执行生成；
- CI 重新生成并检查工作树无差异；
- 构建流程验证生成代码与运行时 protobuf 版本兼容；
- 生成文件顶部明确标注自动生成，不接受手工修改。

只有未来确实需要自定义 build command 时，才允许在 `setup.py` 或独立 build backend hook 中加入生成逻辑；即使如此，构建依赖也必须由 `[build-system]` 完整声明，且发布 wheel 仍包含生成结果。首期不采用“用户安装时运行 protoc”。

### 33.8 Wheel、sdist 与仓库内容边界

#### Wheel 必须包含

- `src/agent_experience/**/*.py`；
- 所有 `__init__.py`；
- 生成的 `_pb2.py` 和 `.pyi`；
- `py.typed`；
- 包运行时真正需要的小型静态 Schema、默认配置或模板；
- 许可证元数据和由构建系统生成的 dist-info；
- CLI entry point 元数据。

#### Wheel 默认不包含

- tests；
- docs 源文件；
- examples；
- benchmarks；
- GitHub workflow；
- 开发脚本；
- 原始运行日志、经验库、`.bin`、`.exp`、SQLite/向量数据库；
- 本地配置、凭据、`.env`、缓存；
- 未使用的 `.proto` 源文件（运行时若需要 schema descriptor，则应明确放入包内的数据目录）。

#### sdist 必须包含

- 构建 wheel 所需的全部源码和配置；
- `pyproject.toml`、`setup.py`、`MANIFEST.in`；
- README、LICENSE、CHANGELOG；
- `.proto` 源文件和生成文件；
- tests；
- 必要的构建/生成脚本；
- 精选 docs 和 examples；
- 第三方许可证/NOTICE。

#### sdist 默认不包含

- `.git`、IDE 配置和本地缓存；
- coverage、测试报告和构建产物；
- benchmark 大数据集；
- 用户经验库和运行记录；
- Secret、Token、私有证书；
- 临时文件和下载缓存；
- 未经授权的第三方模型、Skill 或数据资产。

包数据必须使用显式 allowlist，不使用宽泛模式把任意 `.bin`、`.json`、`.db` 打入 wheel。Setuptools 支持在 `pyproject.toml` 中按 package 声明 package data，应优先采用精确模式。[Setuptools Package Data](https://setuptools.pypa.io/en/stable/userguide/datafiles.html)

### 33.9 `MANIFEST.in` 的职责

`MANIFEST.in` 只管理 sdist 中需要、但不由 package discovery 自动覆盖的文件，例如：

- `.proto`；
- tests；
- README、LICENSE、CHANGELOG；
- 构建所需脚本；
- 必要 docs/examples。

不能用递归全包含后再依靠大量排除项兜底。每次发布都必须解包检查 sdist 和 wheel 的实际清单。

### 33.10 公共 API 与类型规范

- 顶层 `agent_experience` 只导出经过承诺的稳定 API；
- 内部模块和符号使用前导下划线或明确 internal 文档；
- 所有公共函数、类和异常有完整类型注解与 docstring；
- 发布 `py.typed`，遵循 PEP 561；
- 公共 API 的新增、弃用和删除写入 changelog；
- 弃用至少经过一个明确周期，并产生 `DeprecationWarning`；
- import 核心包不得启动线程、创建目录、访问网络、探测框架或读取用户配置；
- optional adapter 使用延迟导入；
- Protobuf 类型尽量不直接成为全部用户 API，外层提供稳定领域接口，降低 Schema 演进对调用方的冲击。

### 33.11 CLI 与用户数据目录

CLI 通过 `[project.scripts]` 声明，不打包独立脚本文件作为主要入口。命令名称暂定：

- `agent-exp`：统一命令入口；
- 子命令包含 inspect、verify、repair、export、import。

运行时数据绝不写入 Python 安装目录或 package resources。repository 路径由用户显式传入，或遵循平台标准用户数据目录；默认行为必须可预测并记录。只读 package data 通过 `importlib.resources` 访问。

### 33.12 开源治理文件

首次公开前必须具备：

- `LICENSE`：选择明确 SPDX 许可证，建议在治理决策中比较 Apache-2.0 与 MIT；
- `README.md`：安装、最小示例、支持矩阵、安全警告和项目状态；
- `CHANGELOG.md`：版本变化；
- `CONTRIBUTING.md`：开发环境、测试和提交规范；
- `CODE_OF_CONDUCT.md`；
- `SECURITY.md`：私下报告漏洞的方式和支持版本；
- 第三方依赖与 vendored 资产的许可证声明；
- 项目主页、源码、Issues、文档和 changelog URL。

许可证标识、许可证文件及 PyPI metadata 必须一致。PyPA 建议使用 SPDX license expression 并包含完整许可证文本。[PyPA Licensing Guide](https://packaging.python.org/en/latest/guides/licensing-examples-and-user-scenarios/)

### 33.13 代码质量门槛

所有合并和发布至少运行：

- 格式与 lint；
- 静态类型检查；
- 支持 Python 版本的单元测试；
- 关键框架适配集成测试；
- Protobuf 生成漂移检查；
- sdist/wheel 构建；
- metadata 校验；
- 从 wheel 在干净环境安装和 import；
- 各 extra 的最小安装测试；
- 包内容与大小检查；
- 依赖和源码安全扫描；
- 许可证合规检查。

测试不得依赖开发源码路径掩盖漏打包问题，必须至少有一组测试从构建后的 wheel 安装运行。

### 33.14 构建与发布流程

标准流程：

1. 从干净 Git checkout 构建；
2. 执行完整质量门槛；
3. 使用 `python -m build` 生成 sdist 和 wheel；
4. 校验 metadata 与包内容；
5. 在隔离环境分别安装 wheel 和 sdist；
6. 在 TestPyPI 验证首发或重大构建变更；
7. 创建签名 Git tag 和 GitHub Release；
8. 通过 PyPI Trusted Publishing 发布；
9. 验证 PyPI 安装、CLI、extras 和 provenance；
10. 保存构建证明和发布日志。

不在开发者本机长期保存 PyPI API Token。优先使用 CI 的 Trusted Publishing。PyPA 推荐使用 `build` 构建发行物，并推荐受支持 CI 使用 Trusted Publishing。[PyPA Tool Recommendations](https://packaging.python.org/en/latest/guides/tool-recommendations/)

### 33.15 平台与 wheel 策略

- 核心 wheel 保持 `py3-none-any` 的目标；
- sqlite-vec、LanceDB 等可能带原生组件的能力作为 extras，由其上游发行物负责平台 wheel；
- 核心包不得因为某个可选后端在特定平台不可用而无法安装；
- CI 至少覆盖 Linux、Windows、macOS 的核心安装和 smoke test；
- 若未来加入自有原生扩展，需要独立 ADR、cibuildwheel 矩阵、sdist 源码和 ABI 策略。

### 33.16 发行安全与供应链

- 构建依赖使用合理下限并接受依赖安全审计；
- GitHub Actions 固定第三方 action 到可信版本或 commit；
- 发布工作流使用最小权限和受保护 environment；
- 不允许构建脚本从未校验 URL 下载并执行代码；
- 生成文件和迁移 Schema 在 CI 中可复现；
- 发布包扫描 Secret；
- 记录 SBOM/provenance 的生成方案；
- 对恶意安装包名近似、依赖混淆和发布者账户安全制定措施。

### 33.17 PyPI 发布前验收清单

- [ ] PyPI 名称已确认；
- [ ] LICENSE 与依赖许可证已评审；
- [ ] `pyproject.toml` 是唯一元数据来源；
- [ ] 最小 `setup.py` 存在；
- [ ] sdist 和 wheel 内容符合 allowlist；
- [ ] `_pb2.py`、`.pyi`、`py.typed` 已包含；
- [ ] wheel 干净安装通过；
- [ ] sdist 构建 wheel 通过；
- [ ] 默认安装不引入主流框架依赖；
- [ ] 每个稳定 extra 有安装测试；
- [ ] README 的安装命令和 API 可运行；
- [ ] CLI entry point 可运行；
- [ ] 支持矩阵和安全边界已公开；
- [ ] TestPyPI 验证通过；
- [ ] Trusted Publishing 已配置；
- [ ] 版本 tag、changelog 和发行物一致。

## 34. 实施状态（2026-08-13）

当前仓库已经完成可在单机开源 Python 包内验收的 Phase 0–4 闭环：可靠采集与事件存储、
候选经验提取、证据驱动生命周期、结构化检索与 Advice、受控 DAG Replay、`.exp` 安全迁移、
LangChain/LangGraph/MCP 观察适配，以及 AutoGen/CrewAI 的显式能力识别与降级声明。

以下能力属于 Phase 5，当前只冻结扩展协议，不宣称已有生产实现：多进程 sequence 协调、远程或
分布式日志、多租户授权与隔离、企业保留策略、在线自动实验与跨节点一致性。外部导入永远不会自动
激活；Replay 永远不会由语义相似度单独触发。

### 34.1 经验语义修订：从长文本总结到最小策略增量

真实 A/B 表明，将多个完整输出再次交给强模型总结、再把整段总结注入 Prompt，会同时增加提炼
成本、输入 Token、输出截断风险和延迟。因此默认经验语义修订为：

> 经验是在明确 Baseline 下，经过独立证据验证、能够改变后续决策且具有正净收益的最小策略增量。

核心新增：

- `BaselineProfile`：标识 system prompt、workflow、toolset、model 和 output contract 版本；
- `ExperienceDelta` / `DeltaRule`：只保存 Baseline 尚未包含的结构化规则；
- `ExperienceMode`：区分 Prompt Delta、Workflow、Tool Routing、Validator、Cache 和 Recovery；
- `DeterministicMiner`：优先从结构化 Run features 提取交集，不调用 LLM；
- `RuleSelector` / `TokenBudget`：规则级选择、Baseline 去重和上下文预算拒用；
- `BenefitMeasurement` / `BenefitLedger`：记录质量、成功率、Token、延迟、工具调用、重试、
  提炼成本摊销与净收益；
- `BreakEvenPolicy`：只有独立留出测量达到预先冻结的收益策略，Validated 才能进入 Active；
- 负收益、输出截断或成本超限会阻止激活或使 Active revision 进入 Quarantined。

该机制不包含旅行、天气、代码等领域规则。领域适配器只负责将自己的确定性验证结果映射为通用
feature/constraint path。旧版自然语言 `summary` 继续可读，用于兼容和解释，但不再是默认高效经验载荷。
核心库不维护领域词表或为某个 benchmark 设置专用阈值。

### 34.2 通用扩展边界与稳健评测

- `FeatureExtractor` 由框架适配器或应用实现，把任意运行记录转换为 `RunFeatures`；
- `BaselineResolver` 由应用解析系统提示、工作流、工具集、输出契约和模型版本的基线指纹；
- `TokenEstimator` 可注入模型原生 tokenizer，默认实现只是无依赖的 UTF-8 保守估算；
- LangChain、LangGraph、MCP 等适配层只监听并规范化事件，不向核心注入领域规则；
- 示例与 benchmark 可覆盖旅行、代码生成、客服路由等场景，但其中的规则不得进入发行包核心。

收益决策必须聚合同一 experience revision 的多次测量，按 `sample_count` 加权，并限制评测窗口。
策略具有稳定的 `policy_id` 和 `policy_version`；判定返回机器可读原因，包括样本不足、质量或成功率
回退、Token 超限、净收益不足及输出截断。单次 A/B 胜出不构成激活依据。

## 35. 下一步规划会议建议

下一轮不应直接编码，建议按以下顺序形成实施决策：

1. 确认 MVP 是否接受 Advice-only；
2. 选择首个框架适配目标及支持版本；
3. 确认首批 OutcomeEvaluator；
4. 冻结核心事件列表和 Experience Definition；
5. 冻结日志帧、durability 和恢复语义；
6. 选择首期检索后端与 embedding 策略；
7. 确定脱敏、租户和数据保留边界；
8. 定义基准任务和阶段验收指标；
9. 冻结 P0/P1 监听事件和适配能力等级；
10. 冻结首批经验类型、固化条件和禁止固化的数据；
11. 明确 MCP Tool/Resource/Prompt 与 Skill 的身份、版本和信任规则；
12. 冻结 PyPI 发行名、Python 支持范围和开源许可证；
13. 冻结 core 与 optional extras 的依赖边界；
14. 冻结 wheel/sdist 文件清单和 Protobuf 构建策略；
15. 冻结版本、CI、TestPyPI 和 Trusted Publishing 流程；
16. 将 Phase 0 拆解为可执行任务，再进入代码实现。

## 36. Architecture v2：Decorator Runtime，而不是服务拼装

### 36.1 当前架构为何不合格

当前公共示例要求应用直接组合 `Repository`、`ToolRegistry`、`ToolSpec`、`capture`、
`CandidateService`、`LifecycleManager`、Miner 和 Selector。这些对象本应是 Runtime 内部组件，
却被暴露为普通用户的必备步骤，造成以下问题：

- 存储路径、tool name、contract ID、producer 和经验 path 被重复配置；
- 用户代码量远大于被监听函数；
- 资源关闭、ContextVar、因果 ID 和候选提炼顺序由应用承担；
- LangChain、LangGraph、MCP 与普通 Python 使用完全不同的接入心智；
- 为了简化示例而默认“无异常就是正确”会破坏经验可信性；
- 在调用热路径同步执行提炼、检索或生命周期逻辑会增加不可预测延迟。

因此 v2 不是给旧 API 增加 facade，而是重新划分公共边界。

### 36.2 唯一推荐公共 API

应用只创建一个 Runtime，并且只通过装饰器声明监听边界：

```python
from agent_experience import agent_experience

experience = agent_experience("./experience-data")

@experience.tool
def get_weather(city: str):
    return weather_client.get(city)

@experience.run(verify=lambda result: result.get("fresh") is True)
def weather_agent(city: str):
    return get_weather(city)
```

约束如下：

- 存储根路径在 `agent_experience(...)` 中最多指定一次；
- `@experience.tool` 不接受 path、name、contract ID 或 producer；
- `@experience.run` 是唯一允许配置任务级 verifier 的位置；
- 所有装饰器支持同步和异步函数，并保持原返回值、异常和签名；
- Runtime 自动延迟打开存储、flush 并在进程退出时关闭；
- 高级配置集中放入一次性的 Runtime policy/config，不散落在每个函数上。

普通 Python 无法在不使用全局 profiler 或 monkey patch 的情况下可靠判断任意嵌套函数是否为
“tool”，因此原生 Python tool 必须使用无参数 `@experience.tool`。LangChain/LangGraph/MCP 已经
具有显式 tool/node/protocol 身份，框架插件应直接读取其公共元数据，不要求用户再次标记。

### 36.3 自动身份和 path

用户不创建任何经验 path。`IdentityResolver` 自动生成稳定身份：

- Runtime：规范化存储根和 repository UUID；
- Run boundary：Python module + qualname + distribution/version + code/config fingerprint；
- Tool：框架 contract（优先）或 module + qualname + signature + version fingerprint；
- Framework node：graph namespace + node ID + graph fingerprint；
- MCP：trust domain + server identity + capability name/version；
- Rule path：由 `ExperienceCompiler` 从规范化 schema field 生成。

展示名称可以随代码重命名而变化；持久身份必须有 fingerprint 和 alias/migration 机制。任何自动
身份冲突都应拒绝写入而不是静默覆盖。

### 36.4 单一 Runtime 内核

`ExperienceRuntime` 是唯一协调者，内部包含但不向普通用户暴露：

```text
Decorators / Framework plugins
              │
              ▼
      Instrumentation Gateway
              │ normalized signals
              ▼
          Event Pipeline ───────────────► Store
              │                            │
              │ run completed              │ replay/projection
              ▼                            ▼
        Evidence Policy             Experience Compiler
              │                            │
              └──────────────► Candidate / Revision
                                           │
                              Selection + Benefit Policy
                                           │
                                           ▼
                                    Application Plan
```

Runtime 的职责：

1. 管理一个 storage root 和 Repository 生命周期；
2. 维护 ContextVar run scope 和 causation；
3. 通过统一 Gateway 接受 Python/framework/MCP 信号；
4. 自动脱敏、计时、token/cost 统计和错误归一化；
5. 在 run 完成后提交 consolidation job，而不是让 tool 调用直接提炼经验；
6. 自动去重、生成内部 rule path 和 immutable Candidate；
7. 仅在证据、收益、预算和安全策略通过后生成 ApplicationPlan；
8. 提供 `flush()`、`close()` 和诊断，不要求应用手动串联内部服务。

### 36.5 Evidence 分层

低代码不能以牺牲语义为代价。Runtime 自动记录两种不同证据：

- `ExecutionEvidence`：函数返回、没有异常、tool 协议成功；自动产生；
- `QualityEvidence`：业务 verifier、测试、约束检查或外部评测证明结果正确；仅在 run 边界产生。

没有 verifier 的 run 可以形成低置信 `CANDIDATE`，用于保存路径和运行事实，但永远不能仅凭
ExecutionEvidence 进入 `VALIDATED/ACTIVE`。Tool 不单独配置业务 verifier；任务级 verifier 在
最外层运行一次并覆盖整个因果树。

### 36.6 Consolidation 不在调用热路径

每次调用只执行有界操作：事件构造、脱敏、append 和必要 durability。以下工作由 run 结束后的
consolidation queue 执行，并可配置为 inline、thread、external worker 或 manual：

- trace 重建；
- feature extraction；
- baseline 比较；
- candidate mining/deduplication；
- benefit aggregation；
- projection 更新和 retention。

默认本地模式可在 `flush()` 或进程退出前完成队列；生产插件可以把 job 发送到外部后端。

### 36.7 Framework Plugin 统一协议

所有适配器实现同一内部 `InstrumentationPlugin`：

```python
class InstrumentationPlugin(Protocol):
    framework: str
    def detect(self, target: object) -> bool: ...
    def bind(self, target: object, gateway: InstrumentationGateway) -> object: ...
    def capabilities(self) -> AdapterCapabilities: ...
```

- LangChain：读取公开 agent/model/tool middleware 信号；
- LangGraph：读取 task/update/checkpoint/interrupt stream；
- MCP：读取 session/server/capability/call 信号；
- 普通 Python：只处理显式 `run/tool` 装饰器；
- 插件不得直接写 Repository、生成 Candidate 或决定 Active；全部通过 Gateway/Runtime。

这样框架适配器只负责“翻译信号”，核心 Runtime 负责统一语义。

### 36.8 公共层级与兼容策略

v2 包结构分为：

- `agent_experience`：仅导出 `agent_experience`、Runtime 类型、策略和只读结果；
- `agent_experience.integrations`：框架插件和可选依赖；
- `agent_experience.low_level`：Repository、Protobuf、Registry、EventLog、Replay 等高级 API；
- `agent_experience.schema`：持久数据契约。

旧 root exports 在一个开发周期内保留并发出 deprecation warning；文档和示例立即只使用 Runtime
API。v2 进入 PyPI 前必须完成兼容测试，不能仅用 facade 调用旧服务来宣称架构完成。

### 36.9 v2 验收标准

- 最简单 tool 示例除业务函数外不超过 3 行集成代码；
- storage path 全应用只出现一次；
- 用户不写 tool name、contract ID、producer、rule path 或 CandidateService；
- 同步、异步、嵌套、异常和并发 context 测试全部通过；
- 无 verifier 的经验无法激活；
- tool verifier 不重复配置，run verifier 覆盖完整因果树；
- framework plugins 不直接依赖 Repository；
- observation 热路径不执行 LLM mining；
- Runtime 能解释自动身份、监听事件、候选来源、选择结果和拒绝原因；
- README 主示例与底层实现完全一致。
