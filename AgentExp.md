# 角色设定
你是一名精通 Python 的高级架构师与资深 AI 工程师。你需要严格遵循以下规格说明书，从零构建一个名为 `AgentExperience` 的 Python SDK 库。

# 项目目标
构建一个**非侵入式（Non-invasive）、事件驱动（Event-driven）**的 Agent 经验管理库。该库允许任何基于 LangGraph、AutoGen 或 CrewAI 构建的 Agent，通过极简代码接入，实现“工作流经验（含 DAG 结构与结果）”的**自动固化（序列化）**、**版本化存储（MVCC）**、**向量检索召回**以及**跨环境迁移**。

# 核心设计原则（必须严格遵守）
1. **存储与表示分离**：运行时内存对象使用 Python 类；磁盘存储统一使用 Protobuf 序列化为 `.bin` 二进制文件，严禁存储原始 JSON 作为持久化格式。
2. **只追加不修改（Append-Only）**：经验一旦写入磁盘，永不修改。更新通过“追加新记录 + 内存/索引指针切换”实现（MVCC 模式）。
3. **旁路监听（Sidecar）**：SDK 绝不侵入 Agent 的核心业务逻辑，仅通过装饰器（Decorator）或回调钩子（Callback）捕获数据。
4. **迁移即拷贝**：经验库的迁移被抽象为“导出（Export）”与“导入（Import）”，本质上是对底层二进制文件和索引快照的打包与解包。

---

# 项目目录结构与文件职责
请生成以下完整的 Python 项目结构：
agent_experience/
├── pyproject.toml # 项目依赖与打包配置
├── protos/
│ └── experience.proto # Protobuf 核心 Schema 定义
├── src/
│ └── agent_experience/
│ ├── init.py
│ ├── core/
│ │ ├── init.py
│ │ ├── enums.py # 枚举：ExperienceStatus, OpType
│ │ └── exceptions.py # 自定义异常
│ ├── schema/ # 由 protoc 编译生成的 Python 文件
│ │ └── experience_pb2.py
│ ├── storage/
│ │ ├── init.py
│ │ ├── binary_log.py # 二进制日志处理器 (追加写入 .bin)
│ │ ├── index_manager.py # 内存索引管理器 (存储 ID -> (offset, len, version))
│ │ ├── vector_store.py # 向量存储接口 (基于 LanceDB 或 SQLite-vec)
│ │ └── graph_store.py # 图关系存储 (基于 SQLite, 存储禁止/依赖关系)
│ ├── dag/
│ │ ├── init.py
│ │ ├── executor.py # DAG 调度执行器 (输入 proto.Input, 输出 proto.Output)
│ │ └── compiler.py # 将 LLM 轨迹或 Python 函数编译为 proto.DAG
│ ├── observer/
│ │ ├── init.py
│ │ └── decorators.py # 提供 @observe.capture() 装饰器
│ ├── integration/
│ │ ├── init.py
│ │ ├── langgraph_hook.py # LangGraph 专用拦截器
│ │ └── base_wrapper.py # 通用 Agent 包装器 (wrap_agent)
│ ├── migration/
│ │ ├── init.py
│ │ └── io.py # 导出(.exp) 与 导入 逻辑
│ └── cli/
│ └── viewer.py # 人类可读的调试查看工具 (反序列化 .bin 为表格)
└── tests/
└── test_experience_flow.py


---

# 详细模块规格说明书（AI 编写代码的唯一依据）

## 1. 底层协议定义 (protos/experience.proto)
你必须编写一个 Protobuf v3 文件，包含以下关键 message：

- **message DAGNode**: 包含 `string node_id`, `string tool_name`, `map<string, string> args`, `repeated string depends_on`, `optional string fallback_action`。
- **message ExperienceCapsule**: 核心载体。包含 `string exp_id`, `string parent_version_id` (用于回滚), `uint64 timestamp`, `DAG dag`, `float success_rate`, `repeated string trigger_keywords`。
- **message Tombstone**: 用于逻辑删除。包含 `string deprecated_exp_id`, `string new_exp_id`。
- **message ExperienceInput**: 定义输入接口，含 `string query`, `map<string, string> context`。
- **message ExperienceOutput**: 定义输出接口，含 `string result`, `ExecutionTrace trace`, `double confidence`。

## 2. 存储层 (Storage Layer) 具体要求

### A. BinaryLog 类 (src/.../storage/binary_log.py)
- **类名**: `BinaryLog`
- **初始化**: `__init__(log_path: Path)`，自动创建文件并初始化文件头（Magic Number `0xAE`）。
- **核心方法**: 
  - `append(serialized_data: bytes) -> (offset: int, length: int)`：将二进制数据追加到文件末尾，返回写入的起始偏移量和长度。
  - `read(offset: int, length: int) -> bytes`：根据偏移量读取原始二进制数据。

### B. IndexManager 类 (src/.../storage/index_manager.py)
- **功能**: 维护内存中的哈希索引和版本映射。
- **数据结构**: 
  - `active_index: dict[str, IndexEntry]`，其中 `IndexEntry` 是一个命名元组，包含 `offset, length, version, status(ACTIVE/DEPRECATED)`。
  - `version_tree: dict[str, str]` 记录 `parent_id -> child_id`。
- **核心方法**:
  - `register(exp_id: str, entry: IndexEntry)`：注册新经验。
  - `deprecate(exp_id: str, new_exp_id: str)`：标记为弃用，并指向新 ID（原子操作）。
  - `get_active(exp_id: str) -> IndexEntry`：获取当前有效指针。
  - `snapshot() -> bytes`：将当前内存索引序列化为 bytes（用于快速重启恢复）。
  - `load_snapshot(data: bytes)`：从快照恢复索引。

### C. VectorStore 类 (src/.../storage/vector_store.py)
- **集成建议**: 使用轻量级 `lance_db` 或 `sqlite-vec`。
- **Schema**: 必须包含 `id (str)`, `vector (float[])`, `metadata (json)`。
- **核心方法**:
  - `insert(exp_id: str, embedding: List[float], metadata: dict)`
  - `search(query_embedding: List[float], top_k: int = 5) -> List[Tuple[str, float]]`：返回 exp_id 和相似度分数。

### D. GraphStore 类 (src/.../storage/graph_store.py)
- **存储介质**: SQLite（本地文件）。
- **表结构**: 
  - `edges` (source_context TEXT, relation_type TEXT, target_action TEXT, ban_until TIMESTAMP)。
- **核心方法**:
  - `add_forbidden_rule(context: str, action: str)`：写入禁令。
  - `check_forbidden(context: str, action: str) -> bool`：检查是否触犯禁令。

## 3. 观察者与装饰器 (Observer Layer)

### A. observer.decorators 模块
- **装饰器**: `@observe.capture(scope: str = "function", success_threshold: float = 0.8, ttl_days: int = 30)`
- **功能逻辑**: 
  1. 拦截被装饰函数的 `args` 和 `kwargs` 作为 Input。
  2. 执行原函数，捕获 `return` 结果作为 Output，或捕获异常。
  3. 若执行成功且函数内部调用了超过 2 个工具，调用 `compiler.py` 将函数内的调用序列编译为 `DAG` 对象。
  4. 调用 `StorageEngine.save()` 写入二进制日志和向量库（异步执行，不阻塞主流程）。
- **注意**: 如果函数抛出异常，捕获异常信息，调用 `GraphStore.add_forbidden_rule()` 写入负反馈。

## 4. DAG 编译与执行器 (DAG Layer)

### A. Compiler 类 (src/.../dag/compiler.py)
- **方法**: `compile_from_trace(trace_data: dict) -> ExperienceCapsule`
- **逻辑**: 解析 Python 堆栈或 LangGraph 的 `state` 快照，提取 `node_id` 和工具参数，生成 Protobuf 的 `DAGNode`。

### B. Executor 类 (src/.../dag/executor.py)
- **方法**: `execute(capsule: ExperienceCapsule, input_data: ExperienceInput) -> ExperienceOutput`
- **逻辑**: 
  1. 解析 DAG 的依赖关系（拓扑排序）。
  2. 并行执行无依赖的节点，串行执行依赖节点。
  3. 若某节点返回错误，自动执行该节点的 `fallback_action`。
  4. 组装最终的 `ExperienceOutput`。

## 5. 集成层 (Integration Layer) —— 开发者最关心的接口

### A. wrap_agent 函数 (src/.../integration/base_wrapper.py)
这是库的**主入口**，开发者通过此函数接入经验系统。
- **函数签名**: `def wrap_agent(agent, repo_path: str = "./exp_repo", auto_mount_external: Optional[Path] = None)`
- **参数详解**:
  - `agent`: 任意 Python 对象（支持 LangGraph 的 `StateGraph`，AutoGen 的 `ConversableAgent`）。
  - `repo_path`: 本地经验库根目录，内部自动创建 `logs/` (存放.bin), `index/` (存放快照), `vector/` (存放向量库)。
  - `auto_mount_external`: 可选导入路径（如 `"./received_skills/price_capsule.exp"`），自动解压合并迁移进来的经验。
- **返回值**: 返回被包装后的 Agent 对象（或直接修改原对象，注入 `_exp_hooks`）。
- **内部行为**: 自动探测 Agent 类型，将 `pre_hook`（前置检索）和 `post_hook`（后置记录）挂载到 Agent 的运行时生命周期中。

### B. 前置钩子逻辑 (内置于 wrap_agent)
在 Agent 接收用户 Prompt 前执行：
1. 将输入文本转为向量，查询 `VectorStore`。
2. 若召回的最高相似度 > 0.85，直接取出对应的 `ExperienceCapsule`，调用 `Executor.execute()` 返回结果，**完全阻断** LLM 调用（省 Token）。
3. 若召回了部分相关经验，将其摘要注入到原始 Prompt 的 System 消息中（作为上下文增强）。

### C. 后置钩子逻辑 (内置于 wrap_agent)
在 Agent 完成一次完整运行（无论成功或失败）后执行：
1. 提取本次完整工作流轨迹。
2. 判断成功率（基于工具报错率）。
3. 异步调用 `observer.decorators` 的存储逻辑。

## 6. 迁移模块 (Migration IO)

### A. 导出函数 (src/.../migration/io.py)
- **函数**: `export_experience(repo_path: Path, exp_ids: List[str], output_path: Path)`
- **逻辑**: 
  1. 根据 `exp_ids` 从 BinaryLog 中提取对应的二进制块。
  2. 提取 VectorStore 中对应的向量条目。
  3. 将所有数据打包成单一 `.exp` 文件（实质为 ZIP 压缩包，内部包含 `data.bin` 和 `index.json`）。

### B. 导入函数
- **函数**: `import_experience(repo_path: Path, exp_file_path: Path)`
- **逻辑**: 解压 `.exp` 文件，将 `data.bin` 追加到本地 `BinaryLog`，将向量数据合并到本地 `VectorStore`，并在 `IndexManager` 中注册新的指针。

## 7. 查看工具 (CLI Viewer)
- **命令**: `agent-exp-viewer --log path/to/experience.bin --exp-id xxxx`
- **功能**: 读取指定偏移量的二进制数据，反序列化为 JSON，并以美观的表格形式打印出 `DAG` 结构和元数据。**仅供人类调试使用，Agent 运行时禁止调用此模块。**

---

# 编程约束与技术要求
1. **异步优先**: 所有 I/O 操作（写磁盘、向量检索）必须支持 `async/await`，以防阻塞 Agent 主线程。
2. **类型注解**: 所有函数必须包含完整的 Python 类型提示（Type Hints）。
3. **Protobuf 编译**: 在 `pyproject.toml` 中配置 `setup.py` 的 `generate_proto` 钩子，确保安装时自动将 `.proto` 编译为 `_pb2.py`。
4. **依赖最小化**: 核心依赖仅包含 `protobuf>=4.0`, `sqlite-vec` 或 `lancedb`, `pydantic>=2.0`。适配 LangGraph/AutoGen 的依赖设为 `extras_require`。

---

# 第一步输出要求（请立即开始编码）
请从 **Protobuf 定义 (`experience.proto`)** 和 **BinaryLog 类** 开始生成代码，并随后给出 `wrap_agent` 函数的基础骨架。确保代码是可直接运行的，并添加详尽的 docstring 注释。