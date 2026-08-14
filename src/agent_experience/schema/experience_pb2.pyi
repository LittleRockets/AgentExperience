import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from agent_experience.schema import common_pb2 as _common_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ExperienceStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXPERIENCE_STATUS_UNSPECIFIED: _ClassVar[ExperienceStatus]
    DRAFT: _ClassVar[ExperienceStatus]
    CANDIDATE: _ClassVar[ExperienceStatus]
    VALIDATED: _ClassVar[ExperienceStatus]
    ACTIVE: _ClassVar[ExperienceStatus]
    DEPRECATED: _ClassVar[ExperienceStatus]
    QUARANTINED: _ClassVar[ExperienceStatus]
    TOMBSTONED: _ClassVar[ExperienceStatus]

class ExperienceType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXPERIENCE_TYPE_UNSPECIFIED: _ClassVar[ExperienceType]
    TASK_STRATEGY: _ClassVar[ExperienceType]
    TOOL_ROUTING: _ClassVar[ExperienceType]
    PARAMETERIZATION: _ClassVar[ExperienceType]
    RECOVERY: _ClassVar[ExperienceType]
    VALIDATION: _ClassVar[ExperienceType]
    CONSTRAINT: _ClassVar[ExperienceType]

class ExperienceMode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXPERIENCE_MODE_UNSPECIFIED: _ClassVar[ExperienceMode]
    PROMPT_DELTA: _ClassVar[ExperienceMode]
    WORKFLOW: _ClassVar[ExperienceMode]
    TOOL_ROUTING_MODE: _ClassVar[ExperienceMode]
    VALIDATOR_MODE: _ClassVar[ExperienceMode]
    EXACT_CACHE_MODE: _ClassVar[ExperienceMode]
    RECOVERY_MODE: _ClassVar[ExperienceMode]

class RuleOperator(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RULE_OPERATOR_UNSPECIFIED: _ClassVar[RuleOperator]
    EQUALS: _ClassVar[RuleOperator]
    NOT_EQUALS: _ClassVar[RuleOperator]
    LESS_THAN_OR_EQUAL: _ClassVar[RuleOperator]
    GREATER_THAN_OR_EQUAL: _ClassVar[RuleOperator]
    CONTAINS: _ClassVar[RuleOperator]
    REQUIRES: _ClassVar[RuleOperator]
    FORBIDS: _ClassVar[RuleOperator]

EXPERIENCE_STATUS_UNSPECIFIED: ExperienceStatus
DRAFT: ExperienceStatus
CANDIDATE: ExperienceStatus
VALIDATED: ExperienceStatus
ACTIVE: ExperienceStatus
DEPRECATED: ExperienceStatus
QUARANTINED: ExperienceStatus
TOMBSTONED: ExperienceStatus
EXPERIENCE_TYPE_UNSPECIFIED: ExperienceType
TASK_STRATEGY: ExperienceType
TOOL_ROUTING: ExperienceType
PARAMETERIZATION: ExperienceType
RECOVERY: ExperienceType
VALIDATION: ExperienceType
CONSTRAINT: ExperienceType
EXPERIENCE_MODE_UNSPECIFIED: ExperienceMode
PROMPT_DELTA: ExperienceMode
WORKFLOW: ExperienceMode
TOOL_ROUTING_MODE: ExperienceMode
VALIDATOR_MODE: ExperienceMode
EXACT_CACHE_MODE: ExperienceMode
RECOVERY_MODE: ExperienceMode
RULE_OPERATOR_UNSPECIFIED: RuleOperator
EQUALS: RuleOperator
NOT_EQUALS: RuleOperator
LESS_THAN_OR_EQUAL: RuleOperator
GREATER_THAN_OR_EQUAL: RuleOperator
CONTAINS: RuleOperator
REQUIRES: RuleOperator
FORBIDS: RuleOperator

class BaselineProfile(_message.Message):
    __slots__ = (
        "baseline_id",
        "baseline_version",
        "system_prompt_hash",
        "workflow_hash",
        "toolset_hash",
        "model_id",
        "output_contract_hash",
    )
    BASELINE_ID_FIELD_NUMBER: _ClassVar[int]
    BASELINE_VERSION_FIELD_NUMBER: _ClassVar[int]
    SYSTEM_PROMPT_HASH_FIELD_NUMBER: _ClassVar[int]
    WORKFLOW_HASH_FIELD_NUMBER: _ClassVar[int]
    TOOLSET_HASH_FIELD_NUMBER: _ClassVar[int]
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_CONTRACT_HASH_FIELD_NUMBER: _ClassVar[int]
    baseline_id: str
    baseline_version: str
    system_prompt_hash: bytes
    workflow_hash: bytes
    toolset_hash: bytes
    model_id: str
    output_contract_hash: bytes
    def __init__(
        self,
        baseline_id: _Optional[str] = ...,
        baseline_version: _Optional[str] = ...,
        system_prompt_hash: _Optional[bytes] = ...,
        workflow_hash: _Optional[bytes] = ...,
        toolset_hash: _Optional[bytes] = ...,
        model_id: _Optional[str] = ...,
        output_contract_hash: _Optional[bytes] = ...,
    ) -> None: ...

class DeltaRule(_message.Message):
    __slots__ = (
        "rule_id",
        "path",
        "operator",
        "value",
        "evidence_run_ids",
        "confidence",
        "rationale",
        "priority",
        "estimated_tokens",
    )
    RULE_ID_FIELD_NUMBER: _ClassVar[int]
    PATH_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_RUN_IDS_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    RATIONALE_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    ESTIMATED_TOKENS_FIELD_NUMBER: _ClassVar[int]
    rule_id: str
    path: str
    operator: RuleOperator
    value: _common_pb2.TypedValue
    evidence_run_ids: _containers.RepeatedScalarFieldContainer[str]
    confidence: float
    rationale: str
    priority: int
    estimated_tokens: int
    def __init__(
        self,
        rule_id: _Optional[str] = ...,
        path: _Optional[str] = ...,
        operator: _Optional[_Union[RuleOperator, str]] = ...,
        value: _Optional[_Union[_common_pb2.TypedValue, _Mapping]] = ...,
        evidence_run_ids: _Optional[_Iterable[str]] = ...,
        confidence: _Optional[float] = ...,
        rationale: _Optional[str] = ...,
        priority: _Optional[int] = ...,
        estimated_tokens: _Optional[int] = ...,
    ) -> None: ...

class ExperienceDelta(_message.Message):
    __slots__ = ("baseline", "rules", "estimated_prompt_tokens", "canonical_hash")
    BASELINE_FIELD_NUMBER: _ClassVar[int]
    RULES_FIELD_NUMBER: _ClassVar[int]
    ESTIMATED_PROMPT_TOKENS_FIELD_NUMBER: _ClassVar[int]
    CANONICAL_HASH_FIELD_NUMBER: _ClassVar[int]
    baseline: BaselineProfile
    rules: _containers.RepeatedCompositeFieldContainer[DeltaRule]
    estimated_prompt_tokens: int
    canonical_hash: bytes
    def __init__(
        self,
        baseline: _Optional[_Union[BaselineProfile, _Mapping]] = ...,
        rules: _Optional[_Iterable[_Union[DeltaRule, _Mapping]]] = ...,
        estimated_prompt_tokens: _Optional[int] = ...,
        canonical_hash: _Optional[bytes] = ...,
    ) -> None: ...

class ToolContract(_message.Message):
    __slots__ = (
        "contract_id",
        "provider",
        "name",
        "version_constraint",
        "input_schema_hash",
        "output_schema_hash",
        "idempotent",
        "has_external_side_effects",
    )
    CONTRACT_ID_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    VERSION_CONSTRAINT_FIELD_NUMBER: _ClassVar[int]
    INPUT_SCHEMA_HASH_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_SCHEMA_HASH_FIELD_NUMBER: _ClassVar[int]
    IDEMPOTENT_FIELD_NUMBER: _ClassVar[int]
    HAS_EXTERNAL_SIDE_EFFECTS_FIELD_NUMBER: _ClassVar[int]
    contract_id: str
    provider: str
    name: str
    version_constraint: str
    input_schema_hash: bytes
    output_schema_hash: bytes
    idempotent: bool
    has_external_side_effects: bool
    def __init__(
        self,
        contract_id: _Optional[str] = ...,
        provider: _Optional[str] = ...,
        name: _Optional[str] = ...,
        version_constraint: _Optional[str] = ...,
        input_schema_hash: _Optional[bytes] = ...,
        output_schema_hash: _Optional[bytes] = ...,
        idempotent: _Optional[bool] = ...,
        has_external_side_effects: _Optional[bool] = ...,
    ) -> None: ...

class RetryPolicy(_message.Message):
    __slots__ = ("max_attempts", "initial_backoff_ms", "backoff_multiplier")
    MAX_ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    INITIAL_BACKOFF_MS_FIELD_NUMBER: _ClassVar[int]
    BACKOFF_MULTIPLIER_FIELD_NUMBER: _ClassVar[int]
    max_attempts: int
    initial_backoff_ms: int
    backoff_multiplier: float
    def __init__(
        self,
        max_attempts: _Optional[int] = ...,
        initial_backoff_ms: _Optional[int] = ...,
        backoff_multiplier: _Optional[float] = ...,
    ) -> None: ...

class DAGNode(_message.Message):
    __slots__ = (
        "node_id",
        "tool",
        "arguments",
        "depends_on",
        "timeout_ms",
        "retry",
        "fallback_node_id",
        "compensation_node_id",
        "requires_approval",
    )
    class ArgumentsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: _common_pb2.TypedValue
        def __init__(
            self,
            key: _Optional[str] = ...,
            value: _Optional[_Union[_common_pb2.TypedValue, _Mapping]] = ...,
        ) -> None: ...

    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    TOOL_FIELD_NUMBER: _ClassVar[int]
    ARGUMENTS_FIELD_NUMBER: _ClassVar[int]
    DEPENDS_ON_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_MS_FIELD_NUMBER: _ClassVar[int]
    RETRY_FIELD_NUMBER: _ClassVar[int]
    FALLBACK_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    COMPENSATION_NODE_ID_FIELD_NUMBER: _ClassVar[int]
    REQUIRES_APPROVAL_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    tool: ToolContract
    arguments: _containers.MessageMap[str, _common_pb2.TypedValue]
    depends_on: _containers.RepeatedScalarFieldContainer[str]
    timeout_ms: int
    retry: RetryPolicy
    fallback_node_id: str
    compensation_node_id: str
    requires_approval: bool
    def __init__(
        self,
        node_id: _Optional[str] = ...,
        tool: _Optional[_Union[ToolContract, _Mapping]] = ...,
        arguments: _Optional[_Mapping[str, _common_pb2.TypedValue]] = ...,
        depends_on: _Optional[_Iterable[str]] = ...,
        timeout_ms: _Optional[int] = ...,
        retry: _Optional[_Union[RetryPolicy, _Mapping]] = ...,
        fallback_node_id: _Optional[str] = ...,
        compensation_node_id: _Optional[str] = ...,
        requires_approval: _Optional[bool] = ...,
    ) -> None: ...

class DAG(_message.Message):
    __slots__ = ("nodes", "output_node_ids")
    NODES_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_NODE_IDS_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[DAGNode]
    output_node_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(
        self,
        nodes: _Optional[_Iterable[_Union[DAGNode, _Mapping]]] = ...,
        output_node_ids: _Optional[_Iterable[str]] = ...,
    ) -> None: ...

class Applicability(_message.Message):
    __slots__ = (
        "task_types",
        "trigger_keywords",
        "required_frameworks",
        "required_tools",
        "preconditions",
        "forbidden_conditions",
        "expires_at",
    )
    TASK_TYPES_FIELD_NUMBER: _ClassVar[int]
    TRIGGER_KEYWORDS_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_FRAMEWORKS_FIELD_NUMBER: _ClassVar[int]
    REQUIRED_TOOLS_FIELD_NUMBER: _ClassVar[int]
    PRECONDITIONS_FIELD_NUMBER: _ClassVar[int]
    FORBIDDEN_CONDITIONS_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    task_types: _containers.RepeatedScalarFieldContainer[str]
    trigger_keywords: _containers.RepeatedScalarFieldContainer[str]
    required_frameworks: _containers.RepeatedScalarFieldContainer[str]
    required_tools: _containers.RepeatedCompositeFieldContainer[ToolContract]
    preconditions: _containers.RepeatedScalarFieldContainer[str]
    forbidden_conditions: _containers.RepeatedScalarFieldContainer[str]
    expires_at: _timestamp_pb2.Timestamp
    def __init__(
        self,
        task_types: _Optional[_Iterable[str]] = ...,
        trigger_keywords: _Optional[_Iterable[str]] = ...,
        required_frameworks: _Optional[_Iterable[str]] = ...,
        required_tools: _Optional[_Iterable[_Union[ToolContract, _Mapping]]] = ...,
        preconditions: _Optional[_Iterable[str]] = ...,
        forbidden_conditions: _Optional[_Iterable[str]] = ...,
        expires_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...,
    ) -> None: ...

class ExperienceDefinition(_message.Message):
    __slots__ = (
        "experience_id",
        "revision_id",
        "parent_revision_ids",
        "generation",
        "schema_version",
        "content_hash",
        "experience_type",
        "status",
        "created_at",
        "created_by",
        "summary",
        "applicability",
        "strategy",
        "success_criteria",
        "known_counterexamples",
        "source_run_ids",
        "replay_allowed",
        "exact_cache_allowed",
        "mode",
        "delta",
        "mining_input_tokens",
        "mining_output_tokens",
        "mining_latency_ms",
    )
    EXPERIENCE_ID_FIELD_NUMBER: _ClassVar[int]
    REVISION_ID_FIELD_NUMBER: _ClassVar[int]
    PARENT_REVISION_IDS_FIELD_NUMBER: _ClassVar[int]
    GENERATION_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_VERSION_FIELD_NUMBER: _ClassVar[int]
    CONTENT_HASH_FIELD_NUMBER: _ClassVar[int]
    EXPERIENCE_TYPE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    CREATED_BY_FIELD_NUMBER: _ClassVar[int]
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    APPLICABILITY_FIELD_NUMBER: _ClassVar[int]
    STRATEGY_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_CRITERIA_FIELD_NUMBER: _ClassVar[int]
    KNOWN_COUNTEREXAMPLES_FIELD_NUMBER: _ClassVar[int]
    SOURCE_RUN_IDS_FIELD_NUMBER: _ClassVar[int]
    REPLAY_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    EXACT_CACHE_ALLOWED_FIELD_NUMBER: _ClassVar[int]
    MODE_FIELD_NUMBER: _ClassVar[int]
    DELTA_FIELD_NUMBER: _ClassVar[int]
    MINING_INPUT_TOKENS_FIELD_NUMBER: _ClassVar[int]
    MINING_OUTPUT_TOKENS_FIELD_NUMBER: _ClassVar[int]
    MINING_LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    experience_id: str
    revision_id: str
    parent_revision_ids: _containers.RepeatedScalarFieldContainer[str]
    generation: int
    schema_version: int
    content_hash: bytes
    experience_type: ExperienceType
    status: ExperienceStatus
    created_at: _timestamp_pb2.Timestamp
    created_by: str
    summary: str
    applicability: Applicability
    strategy: DAG
    success_criteria: _containers.RepeatedScalarFieldContainer[str]
    known_counterexamples: _containers.RepeatedScalarFieldContainer[str]
    source_run_ids: _containers.RepeatedScalarFieldContainer[str]
    replay_allowed: bool
    exact_cache_allowed: bool
    mode: ExperienceMode
    delta: ExperienceDelta
    mining_input_tokens: int
    mining_output_tokens: int
    mining_latency_ms: int
    def __init__(
        self,
        experience_id: _Optional[str] = ...,
        revision_id: _Optional[str] = ...,
        parent_revision_ids: _Optional[_Iterable[str]] = ...,
        generation: _Optional[int] = ...,
        schema_version: _Optional[int] = ...,
        content_hash: _Optional[bytes] = ...,
        experience_type: _Optional[_Union[ExperienceType, str]] = ...,
        status: _Optional[_Union[ExperienceStatus, str]] = ...,
        created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...,
        created_by: _Optional[str] = ...,
        summary: _Optional[str] = ...,
        applicability: _Optional[_Union[Applicability, _Mapping]] = ...,
        strategy: _Optional[_Union[DAG, _Mapping]] = ...,
        success_criteria: _Optional[_Iterable[str]] = ...,
        known_counterexamples: _Optional[_Iterable[str]] = ...,
        source_run_ids: _Optional[_Iterable[str]] = ...,
        replay_allowed: _Optional[bool] = ...,
        exact_cache_allowed: _Optional[bool] = ...,
        mode: _Optional[_Union[ExperienceMode, str]] = ...,
        delta: _Optional[_Union[ExperienceDelta, _Mapping]] = ...,
        mining_input_tokens: _Optional[int] = ...,
        mining_output_tokens: _Optional[int] = ...,
        mining_latency_ms: _Optional[int] = ...,
    ) -> None: ...

class BenefitMeasurement(_message.Message):
    __slots__ = (
        "measurement_id",
        "experience_id",
        "revision_id",
        "baseline_id",
        "run_id",
        "quality_delta",
        "success_rate_delta",
        "input_token_delta",
        "output_token_delta",
        "latency_ms_delta",
        "tool_call_delta",
        "retry_delta",
        "mining_tokens",
        "mining_latency_ms",
        "quality_weight",
        "token_cost_weight",
        "latency_cost_weight",
        "net_benefit",
        "sample_count",
        "output_truncated",
        "measured_at",
    )
    MEASUREMENT_ID_FIELD_NUMBER: _ClassVar[int]
    EXPERIENCE_ID_FIELD_NUMBER: _ClassVar[int]
    REVISION_ID_FIELD_NUMBER: _ClassVar[int]
    BASELINE_ID_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    QUALITY_DELTA_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_RATE_DELTA_FIELD_NUMBER: _ClassVar[int]
    INPUT_TOKEN_DELTA_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_TOKEN_DELTA_FIELD_NUMBER: _ClassVar[int]
    LATENCY_MS_DELTA_FIELD_NUMBER: _ClassVar[int]
    TOOL_CALL_DELTA_FIELD_NUMBER: _ClassVar[int]
    RETRY_DELTA_FIELD_NUMBER: _ClassVar[int]
    MINING_TOKENS_FIELD_NUMBER: _ClassVar[int]
    MINING_LATENCY_MS_FIELD_NUMBER: _ClassVar[int]
    QUALITY_WEIGHT_FIELD_NUMBER: _ClassVar[int]
    TOKEN_COST_WEIGHT_FIELD_NUMBER: _ClassVar[int]
    LATENCY_COST_WEIGHT_FIELD_NUMBER: _ClassVar[int]
    NET_BENEFIT_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_COUNT_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_TRUNCATED_FIELD_NUMBER: _ClassVar[int]
    MEASURED_AT_FIELD_NUMBER: _ClassVar[int]
    measurement_id: str
    experience_id: str
    revision_id: str
    baseline_id: str
    run_id: str
    quality_delta: float
    success_rate_delta: float
    input_token_delta: int
    output_token_delta: int
    latency_ms_delta: int
    tool_call_delta: int
    retry_delta: int
    mining_tokens: int
    mining_latency_ms: int
    quality_weight: float
    token_cost_weight: float
    latency_cost_weight: float
    net_benefit: float
    sample_count: int
    output_truncated: bool
    measured_at: _timestamp_pb2.Timestamp
    def __init__(
        self,
        measurement_id: _Optional[str] = ...,
        experience_id: _Optional[str] = ...,
        revision_id: _Optional[str] = ...,
        baseline_id: _Optional[str] = ...,
        run_id: _Optional[str] = ...,
        quality_delta: _Optional[float] = ...,
        success_rate_delta: _Optional[float] = ...,
        input_token_delta: _Optional[int] = ...,
        output_token_delta: _Optional[int] = ...,
        latency_ms_delta: _Optional[int] = ...,
        tool_call_delta: _Optional[int] = ...,
        retry_delta: _Optional[int] = ...,
        mining_tokens: _Optional[int] = ...,
        mining_latency_ms: _Optional[int] = ...,
        quality_weight: _Optional[float] = ...,
        token_cost_weight: _Optional[float] = ...,
        latency_cost_weight: _Optional[float] = ...,
        net_benefit: _Optional[float] = ...,
        sample_count: _Optional[int] = ...,
        output_truncated: _Optional[bool] = ...,
        measured_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...,
    ) -> None: ...

class EvaluationEvent(_message.Message):
    __slots__ = (
        "evaluation_id",
        "experience_id",
        "revision_id",
        "run_id",
        "outcome",
        "confidence",
        "evidence_references",
        "evaluator_id",
        "evaluator_version",
        "evaluated_at",
    )
    class Outcome(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        OUTCOME_UNSPECIFIED: _ClassVar[EvaluationEvent.Outcome]
        SUCCESS: _ClassVar[EvaluationEvent.Outcome]
        FAILURE: _ClassVar[EvaluationEvent.Outcome]
        PARTIAL: _ClassVar[EvaluationEvent.Outcome]
        UNKNOWN: _ClassVar[EvaluationEvent.Outcome]

    OUTCOME_UNSPECIFIED: EvaluationEvent.Outcome
    SUCCESS: EvaluationEvent.Outcome
    FAILURE: EvaluationEvent.Outcome
    PARTIAL: EvaluationEvent.Outcome
    UNKNOWN: EvaluationEvent.Outcome
    EVALUATION_ID_FIELD_NUMBER: _ClassVar[int]
    EXPERIENCE_ID_FIELD_NUMBER: _ClassVar[int]
    REVISION_ID_FIELD_NUMBER: _ClassVar[int]
    RUN_ID_FIELD_NUMBER: _ClassVar[int]
    OUTCOME_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    EVIDENCE_REFERENCES_FIELD_NUMBER: _ClassVar[int]
    EVALUATOR_ID_FIELD_NUMBER: _ClassVar[int]
    EVALUATOR_VERSION_FIELD_NUMBER: _ClassVar[int]
    EVALUATED_AT_FIELD_NUMBER: _ClassVar[int]
    evaluation_id: str
    experience_id: str
    revision_id: str
    run_id: str
    outcome: EvaluationEvent.Outcome
    confidence: float
    evidence_references: _containers.RepeatedScalarFieldContainer[str]
    evaluator_id: str
    evaluator_version: str
    evaluated_at: _timestamp_pb2.Timestamp
    def __init__(
        self,
        evaluation_id: _Optional[str] = ...,
        experience_id: _Optional[str] = ...,
        revision_id: _Optional[str] = ...,
        run_id: _Optional[str] = ...,
        outcome: _Optional[_Union[EvaluationEvent.Outcome, str]] = ...,
        confidence: _Optional[float] = ...,
        evidence_references: _Optional[_Iterable[str]] = ...,
        evaluator_id: _Optional[str] = ...,
        evaluator_version: _Optional[str] = ...,
        evaluated_at: _Optional[
            _Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]
        ] = ...,
    ) -> None: ...
