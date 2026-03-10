# Diagnosis Workflow Architecture Design

## 1. 分类维度

### 1.1 网络类型 (NetworkType)
```python
class NetworkType(str, Enum):
    SYSTEM = "system"  # 主机间网络 (phy↔kernel stack↔phy)
    VM = "vm"          # 虚机间网络 (vm↔vnet↔phy↔...↔phy↔vnet↔vm)
```

### 1.2 问题类型 (ProblemType)
```python
class ProblemType(str, Enum):
    LATENCY = "latency"          # 延迟异常
    PACKET_DROP = "packet_drop"  # 丢包异常
    CONNECTIVITY = "connectivity"  # 连通性异常 (future)
    PERFORMANCE = "performance"    # 性能异常 (future: 带宽、抖动)
```

### 1.3 诊断模式 (DiagnosisMode)
```python
class DiagnosisMode(str, Enum):
    BOUNDARY = "boundary"        # 边界定界 - 最小依赖，边界点测量
    SEGMENT = "segment"          # 分段定界 - 全链路分段覆盖
    EVENT = "event"              # 事件追踪 - 数据包事件级详细追踪
    SPECIALIZED = "specialized"  # 专项分析 - 特定模块/协议/问题
```

**模式说明：**

| Mode | 中文 | 测量范围 | 典型场景 | 依赖 |
|------|------|----------|----------|------|
| boundary | 边界定界 | 边界点 (vnet↔phy, phy↔stack) | 快速定界：内部 vs 外部 | 最小 |
| segment | 分段定界 | 全链路所有主要模块 | 精确定位：全分段延迟分解 | 中等 |
| event | 事件追踪 | 所有数据包事件 | 详细追踪：丢包事件、延迟异常 | 较高 |
| specialized | 专项分析 | 特定模块/协议 | 深入分析：OVS流表、TCP重传 | 视情况 |

**详细说明：**

```
┌─────────────┬────────────────────────────────────────────────────────────────┐
│ boundary    │ 边界定界                                                        │
│             │ - 最小依赖，只在关键边界点部署探针                                │
│             │ - 快速判断问题在内部还是外部                                      │
│             │ - 例：vnet↔phy 边界，phy↔kernel stack 边界                       │
├─────────────┼────────────────────────────────────────────────────────────────┤
│ segment     │ 分段定界 (全链路)                                                │
│             │ - 覆盖路径上所有主要模块的分段测量                                │
│             │ - 分布式测量，全分段覆盖                                          │
│             │ - VM网络：8点14段测量 (需VM内部部署)                              │
│             │ - System网络：kernel全栈追踪 (phy→driver→netfilter→stack)        │
├─────────────┼────────────────────────────────────────────────────────────────┤
│ event       │ 事件追踪                                                         │
│             │ - 强调所有数据包事件的测量能力                                    │
│             │ - 追踪内部主要组件的每个数据包事件                                │
│             │ - 例：kfree_skb 追踪所有丢包事件，perf事件追踪                    │
│             │ - 产出：事件时间线、调用栈分析                                    │
├─────────────┼────────────────────────────────────────────────────────────────┤
│ specialized │ 专项分析                                                         │
│             │ - 特定模块的深入分析 (OVS datapath, virtio队列)                   │
│             │ - 特定协议的分析 (TCP重传, RDMA)                                  │
│             │ - 特定问题的分析 (中断亲和性, CPU调度)                            │
│             │ - 通常在其他模式定位后使用                                        │
└─────────────┴────────────────────────────────────────────────────────────────┘
```

## 2. 工作流矩阵

### 2.1 Boundary 模式 (边界定界)

最小依赖，仅在边界点部署探针，快速定界内部 vs 外部。

| network | problem | Measurement Skill | Analysis Skill | 状态 |
|---------|---------|-------------------|----------------|------|
| system | latency | system-network-path-tracer | system-network-latency-analysis | ✅ |
| system | packet_drop | system-network-path-tracer | system-network-drop-analysis | ✅ |
| vm | latency | vm-network-path-tracer | vm-network-latency-analysis | ✅ |
| vm | packet_drop | vm-network-path-tracer | vm-network-drop-analysis | ✅ |

### 2.2 Segment 模式 (分段定界/全链路)

覆盖路径上所有主要模块，分布式测量全分段。

| network | problem | Measurement Skill | Analysis Skill | 状态 |
|---------|---------|-------------------|----------------|------|
| vm | latency | vm-latency-measurement (8点) | vm-latency-analysis | ✅ |
| vm | packet_drop | vm-drop-measurement | vm-drop-analysis | 🔜 |
| system | latency | system-segment-tracer | system-segment-analysis | 🔜 |
| system | packet_drop | system-segment-tracer | system-segment-drop-analysis | 🔜 |

### 2.3 Event 模式 (事件追踪)

追踪所有数据包事件，详细的事件时间线和调用栈分析。

| network | problem | Measurement Skill | Analysis Skill | 状态 |
|---------|---------|-------------------|----------------|------|
| * | packet_drop | kfree-skb-tracer | kernel-stack-analyzer | 部分 |
| * | latency | packet-event-tracer | event-latency-analysis | 🔜 |
| vm | * | virtio-event-tracer | virtio-event-analysis | 🔜 |

### 2.4 Specialized 模式 (专项分析)

特定模块/协议/问题的深入分析工具。

| 类别 | 工具 | 分析 | 状态 |
|------|------|------|------|
| OVS | ovs-flow-tracer | ovs-flow-analysis | 🔜 |
| TCP | tcp-retrans-tracer | tcp-retrans-analysis | 🔜 |
| 中断 | irq-affinity-collector | irq-analysis | 🔜 |
| 调度 | cpu-sched-tracer | sched-analysis | 🔜 |

## 3. Controller 架构

### 3.1 核心组件

```
┌─────────────────────────────────────────────────────────────────────┐
│                       DiagnosisController                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐  │
│  │ WorkflowRegistry│───→│ WorkflowSelector│───→│ WorkflowExecutor│  │
│  │                 │    │                 │    │                 │  │
│  │ - workflows[]   │    │ - classify()    │    │ - measure()     │  │
│  │ - register()    │    │ - select()      │    │ - analyze()     │  │
│  │ - lookup()      │    │                 │    │ - report()      │  │
│  └─────────────────┘    └─────────────────┘    └─────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Workflow 定义

```python
@dataclass
class DiagnosisWorkflow:
    """A diagnosis workflow combining measurement and analysis."""

    # Identification
    id: str  # e.g., "vm_latency_boundary"
    name: str  # e.g., "VM Latency Boundary Detection"

    # Classification
    network_type: NetworkType | None  # None = applies to all
    problem_type: ProblemType
    mode: DiagnosisMode

    # Skills
    measurement_skill: str  # e.g., "vm-network-path-tracer"
    analysis_skill: str     # e.g., "vm-network-latency-analysis"

    # Parameter builder function name
    param_builder: str  # e.g., "_build_vm_path_tracer_params"

    # Metadata
    description: str
    dependencies: list[str]  # Required capabilities (e.g., ["host_ssh", "vm_ssh"])
    priority: int = 0  # Higher = preferred when multiple match
```

### 3.3 WorkflowRegistry

```python
class WorkflowRegistry:
    """Registry of available diagnosis workflows."""

    def __init__(self):
        self._workflows: dict[str, DiagnosisWorkflow] = {}
        self._register_builtin_workflows()

    def _register_builtin_workflows(self):
        # ========== Boundary Mode (边界定界) ==========

        # System Network - Boundary
        self.register(DiagnosisWorkflow(
            id="system_latency_boundary",
            name="System Network Latency Boundary Detection",
            network_type=NetworkType.SYSTEM,
            problem_type=ProblemType.LATENCY,
            mode=DiagnosisMode.BOUNDARY,
            measurement_skill="system-network-path-tracer",
            analysis_skill="system-network-latency-analysis",
            param_builder="_build_system_skill_params",
            description="Detect latency at phy↔kernel stack boundary",
            dependencies=["host_ssh"],
        ))

        self.register(DiagnosisWorkflow(
            id="system_drop_boundary",
            name="System Network Drop Boundary Detection",
            network_type=NetworkType.SYSTEM,
            problem_type=ProblemType.PACKET_DROP,
            mode=DiagnosisMode.BOUNDARY,
            measurement_skill="system-network-path-tracer",
            analysis_skill="system-network-drop-analysis",
            param_builder="_build_system_skill_params",
            description="Detect packet drops at phy↔kernel stack boundary",
            dependencies=["host_ssh"],
        ))

        # VM Network - Boundary
        self.register(DiagnosisWorkflow(
            id="vm_latency_boundary",
            name="VM Network Latency Boundary Detection",
            network_type=NetworkType.VM,
            problem_type=ProblemType.LATENCY,
            mode=DiagnosisMode.BOUNDARY,
            measurement_skill="vm-network-path-tracer",
            analysis_skill="vm-network-latency-analysis",
            param_builder="_build_vm_path_tracer_params",
            description="Detect latency at vnet↔phy boundary (host-only)",
            dependencies=["host_ssh"],
        ))

        self.register(DiagnosisWorkflow(
            id="vm_drop_boundary",
            name="VM Network Drop Boundary Detection",
            network_type=NetworkType.VM,
            problem_type=ProblemType.PACKET_DROP,
            mode=DiagnosisMode.BOUNDARY,
            measurement_skill="vm-network-path-tracer",
            analysis_skill="vm-network-drop-analysis",
            param_builder="_build_vm_path_tracer_params",
            description="Detect packet drops at vnet↔phy boundary (host-only)",
            dependencies=["host_ssh"],
        ))

        # ========== Segment Mode (分段定界) ==========

        self.register(DiagnosisWorkflow(
            id="vm_latency_segment",
            name="VM Network Latency Segment Analysis",
            network_type=NetworkType.VM,
            problem_type=ProblemType.LATENCY,
            mode=DiagnosisMode.SEGMENT,
            measurement_skill="vm-latency-measurement",
            analysis_skill="vm-latency-analysis",
            param_builder="_build_skill_params",
            description="Full 8-point 14-segment latency measurement",
            dependencies=["host_ssh", "vm_ssh"],
            priority=10,  # Preferred when VM access available
        ))

        # ========== Event Mode (事件追踪) ==========

        self.register(DiagnosisWorkflow(
            id="packet_drop_event",
            name="Packet Drop Event Tracing",
            network_type=None,  # Applies to all network types
            problem_type=ProblemType.PACKET_DROP,
            mode=DiagnosisMode.EVENT,
            measurement_skill="kfree-skb-tracer",
            analysis_skill="kernel-stack-analyzer",
            param_builder="_build_event_tracer_params",
            description="Trace all kfree_skb events with kernel stack analysis",
            dependencies=["host_ssh", "root_access"],
        ))

    def register(self, workflow: DiagnosisWorkflow):
        self._workflows[workflow.id] = workflow

    def lookup(
        self,
        network_type: NetworkType | None,
        problem_type: ProblemType,
        mode: DiagnosisMode | None = None,
    ) -> list[DiagnosisWorkflow]:
        """Find matching workflows, sorted by priority."""
        matches = []
        for w in self._workflows.values():
            # Match network type (None matches all)
            if w.network_type is not None and w.network_type != network_type:
                continue
            # Match problem type
            if w.problem_type != problem_type:
                continue
            # Match mode if specified
            if mode is not None and w.mode != mode:
                continue
            matches.append(w)

        return sorted(matches, key=lambda w: -w.priority)
```

### 3.4 WorkflowSelector

```python
class WorkflowSelector:
    """Select appropriate workflow based on request and environment."""

    def __init__(self, registry: WorkflowRegistry):
        self.registry = registry

    def select(
        self,
        request: DiagnosisRequest,
        environment: dict[str, Any],
        preferred_mode: DiagnosisMode | None = None,
    ) -> DiagnosisWorkflow | None:
        """Select the best workflow for the request.

        Selection strategy:
        1. If mode is specified, only consider workflows of that mode
        2. Filter by available dependencies (host_ssh, vm_ssh, root_access)
        3. Return highest priority workflow that matches

        Default mode selection (when not specified):
        - If VM SSH available → prefer segment mode (more detailed)
        - Otherwise → use boundary mode (minimal dependency)
        """

        network_type = NetworkType(request.network_type)
        problem_type = ProblemType(request.request_type)

        # Check available capabilities
        capabilities = self._check_capabilities(environment)

        # Find matching workflows
        candidates = self.registry.lookup(
            network_type=network_type,
            problem_type=problem_type,
            mode=preferred_mode,
        )

        # Filter by available dependencies
        valid_candidates = []
        for workflow in candidates:
            if self._can_satisfy_dependencies(workflow, capabilities):
                valid_candidates.append(workflow)

        if not valid_candidates:
            return None

        # Return highest priority that matches
        return valid_candidates[0]

    def _check_capabilities(self, env: dict) -> set[str]:
        """Check available capabilities from environment."""
        caps = set()

        if env.get("src_host"):
            caps.add("host_ssh")

        src_env = env.get("src_env", {})
        if src_env.get("vm_uuid") or env.get("src_vm"):
            caps.add("vm_ssh")

        # root_access could be checked via a probe or config
        # For now, assume host_ssh implies potential root access
        if "host_ssh" in caps:
            caps.add("root_access")

        return caps

    def _can_satisfy_dependencies(
        self,
        workflow: DiagnosisWorkflow,
        capabilities: set[str],
    ) -> bool:
        """Check if workflow dependencies can be satisfied."""
        for dep in workflow.dependencies:
            if dep not in capabilities:
                return False
        return True
```

### 3.5 Updated Controller Flow

```python
class DiagnosisController:
    def __init__(self, ...):
        # ... existing init ...
        self._workflow_registry = WorkflowRegistry()
        self._workflow_selector = WorkflowSelector(self._workflow_registry)
        self._current_workflow: DiagnosisWorkflow | None = None

    async def _classify_and_select_workflow(
        self,
        request: DiagnosisRequest,
        environment: dict[str, Any],
    ) -> tuple[dict[str, Any], DiagnosisWorkflow | None]:
        """Classify problem and select workflow."""

        # Determine preferred mode from request options
        preferred_mode = None
        if request.options.get("mode"):
            preferred_mode = DiagnosisMode(request.options["mode"])
        elif request.options.get("segment"):
            preferred_mode = DiagnosisMode.SEGMENT
        elif request.options.get("event"):
            preferred_mode = DiagnosisMode.EVENT

        # Select workflow
        workflow = self._workflow_selector.select(
            request=request,
            environment=environment,
            preferred_mode=preferred_mode,
        )

        if not workflow:
            return {
                "type": "unsupported",
                "error": f"No workflow for {request.network_type}/{request.request_type}",
            }, None

        self._current_workflow = workflow

        classification = {
            "type": workflow.id,
            "network_type": workflow.network_type.value if workflow.network_type else "any",
            "problem_type": workflow.problem_type.value,
            "mode": workflow.mode.value,
            "workflow_name": workflow.name,
            "confidence": 0.95,
        }

        return classification, workflow

    async def _plan_measurement(
        self,
        classification: dict[str, Any],
        environment: dict[str, Any],
        request: DiagnosisRequest,
        workflow: DiagnosisWorkflow,
    ) -> dict[str, Any]:
        """Build measurement plan from selected workflow."""

        # Get parameter builder method
        param_builder = getattr(self, workflow.param_builder)
        skill_params = param_builder(environment, request)

        return {
            "mode": "skill",
            "skill": workflow.measurement_skill,
            "analysis_skill": workflow.analysis_skill,
            "parameters": skill_params,
            "duration": request.options.get("duration", 30),
            "workflow_id": workflow.id,
            "workflow_mode": workflow.mode.value,
        }

    async def _analyze_and_report(
        self,
        measurements: dict[str, Any],
        environment: dict[str, Any],
        workflow: DiagnosisWorkflow,
    ) -> dict[str, Any]:
        """Invoke analysis skill from workflow."""

        measurement_dir = self._get_measurement_dir(measurements)
        if not measurement_dir:
            return {"status": "error", "reason": "No measurement_dir found"}

        executor = self._get_skill_executor()
        result = await executor.invoke(
            skill_name=workflow.analysis_skill,
            parameters={"measurement_dir": measurement_dir},
        )

        return self._process_analysis_result(result, workflow)
```

## 4. Request Schema 更新

```python
class DiagnosisRequest(BaseModel):
    request_type: Literal["latency", "packet_drop", "connectivity"] = Field(
        ..., description="Type of diagnosis (problem type)"
    )
    network_type: Literal["vm", "system"] = Field(
        ..., description="Network layer type"
    )
    # ... existing fields ...

    options: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional options including mode preference"
    )
    # options["mode"]: "boundary" | "segment" | "event" | "specialized"
    # options["segment"]: bool (shortcut for mode=segment)
    # options["event"]: bool (shortcut for mode=event)
```

## 5. 默认行为与降级

### 5.1 模式选择策略

```
1. 如果请求指定 mode，使用指定模式
2. 如果请求指定 segment=true，使用 segment 模式
3. 如果请求指定 event=true，使用 event 模式
4. 否则，根据可用依赖自动选择：
   - boundary 模式为默认 (最小依赖，快速定界)
   - 如果检测到有 VM SSH 可用，提示可升级到 segment 模式
```

### 5.2 降级策略

```
如果首选 workflow 依赖不满足：
1. 尝试同问题类型的更低依赖 workflow
2. 例：vm_latency_segment 不可用 (无 VM SSH) → 降级到 vm_latency_boundary
3. 记录降级原因到 classification 中：
   {
     "fallback": true,
     "original_mode": "segment",
     "fallback_mode": "boundary",
     "reason": "vm_ssh not available"
   }
```

### 5.3 模式推荐

```
根据问题场景推荐合适模式：

1. 首次排查、快速定界 → boundary
   "快速判断问题在基础设施内部还是外部"

2. 需要精确定位 → segment
   "全链路分段，找出具体哪个组件延迟高"

3. 丢包详细分析 → event
   "追踪每个丢包事件的内核调用栈"

4. 特定组件深入分析 → specialized
   "分析 OVS 流表、TCP 重传等特定问题"
```

## 6. 扩展示例

### 6.1 添加新 Boundary Workflow

```python
# 添加连通性边界检测
registry.register(DiagnosisWorkflow(
    id="system_connectivity_boundary",
    name="System Network Connectivity Check",
    network_type=NetworkType.SYSTEM,
    problem_type=ProblemType.CONNECTIVITY,
    mode=DiagnosisMode.BOUNDARY,
    measurement_skill="system-connectivity-tracer",
    analysis_skill="connectivity-analysis",
    param_builder="_build_connectivity_params",
    description="Check connectivity at phy↔stack boundary",
    dependencies=["host_ssh"],
))
```

### 6.2 添加新 Event Workflow

```python
# 添加 virtio 事件追踪
registry.register(DiagnosisWorkflow(
    id="vm_latency_virtio_event",
    name="Virtio Queue Event Tracing",
    network_type=NetworkType.VM,
    problem_type=ProblemType.LATENCY,
    mode=DiagnosisMode.EVENT,
    measurement_skill="virtio-event-tracer",
    analysis_skill="virtio-event-analysis",
    param_builder="_build_virtio_tracer_params",
    description="Trace virtio queue events for latency analysis",
    dependencies=["host_ssh", "root_access"],
))
```

### 6.3 添加 Specialized Workflow

```python
# 添加 OVS 流表专项分析
registry.register(DiagnosisWorkflow(
    id="ovs_flow_specialized",
    name="OVS Flow Table Analysis",
    network_type=NetworkType.VM,
    problem_type=ProblemType.LATENCY,
    mode=DiagnosisMode.SPECIALIZED,
    measurement_skill="ovs-flow-collector",
    analysis_skill="ovs-flow-analysis",
    param_builder="_build_ovs_flow_params",
    description="Analyze OVS flow table for slow path issues",
    dependencies=["host_ssh", "ovs_access"],
))

# 添加 TCP 重传专项分析
registry.register(DiagnosisWorkflow(
    id="tcp_retrans_specialized",
    name="TCP Retransmission Analysis",
    network_type=None,  # Applies to both
    problem_type=ProblemType.PACKET_DROP,
    mode=DiagnosisMode.SPECIALIZED,
    measurement_skill="tcp-retrans-tracer",
    analysis_skill="tcp-retrans-analysis",
    param_builder="_build_tcp_retrans_params",
    description="Analyze TCP retransmissions and their causes",
    dependencies=["host_ssh"],
))
```

### 6.4 添加新问题类型

```python
# 添加性能问题类型
class ProblemType(str, Enum):
    LATENCY = "latency"
    PACKET_DROP = "packet_drop"
    CONNECTIVITY = "connectivity"
    PERFORMANCE = "performance"  # 新增：带宽、抖动、队列深度

# 注册性能工作流
registry.register(DiagnosisWorkflow(
    id="vm_performance_boundary",
    name="VM Network Performance Boundary",
    network_type=NetworkType.VM,
    problem_type=ProblemType.PERFORMANCE,
    mode=DiagnosisMode.BOUNDARY,
    measurement_skill="vm-network-perf-tracer",
    analysis_skill="vm-network-perf-analysis",
    param_builder="_build_perf_tracer_params",
    description="Measure bandwidth, jitter at vnet↔phy boundary",
    dependencies=["host_ssh"],
))
```

## 7. 实现路线图

### Phase 1: 基础架构
- [x] 定义分类枚举 (NetworkType, ProblemType, DiagnosisMode)
- [ ] 实现 DiagnosisWorkflow 数据类
- [ ] 实现 WorkflowRegistry
- [ ] 实现 WorkflowSelector
- [ ] 重构 Controller 使用 Workflow 模式

### Phase 2: Boundary Mode (边界定界)
- [x] system_latency_boundary (已有)
- [ ] system_drop_boundary
- [ ] vm_latency_boundary
- [ ] vm_drop_boundary

### Phase 3: Segment Mode (分段定界)
- [x] vm_latency_segment (已有，原 vm_latency_full_path)
- [ ] vm_drop_segment
- [ ] system_latency_segment
- [ ] system_drop_segment

### Phase 4: Event Mode (事件追踪)
- [x] packet_drop_event (部分，kernel-stack-analyzer)
- [ ] latency_event (packet-event-tracer)
- [ ] virtio_event (VM 特定)

### Phase 5: Specialized Mode (专项分析)
- [ ] ovs_flow_specialized
- [ ] tcp_retrans_specialized
- [ ] irq_affinity_specialized
- [ ] cpu_sched_specialized

## 8. 诊断流程图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            诊断请求入口                                       │
│  request: { network_type, problem_type, options: { mode?, ... } }           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WorkflowSelector                                     │
│  1. 解析请求: network_type + problem_type + mode                             │
│  2. 查找匹配 workflows: Registry.lookup()                                    │
│  3. 检查依赖: host_ssh? vm_ssh? root_access?                                 │
│  4. 选择最高优先级 workflow                                                   │
│  5. 如需降级，记录原因                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Selected Workflow                                    │
│  { id, measurement_skill, analysis_skill, param_builder, ... }              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
        ┌───────────────────┐           ┌───────────────────┐
        │  L3 Measurement   │           │   L4 Analysis     │
        │  workflow.        │    ───►   │  workflow.        │
        │  measurement_skill│           │  analysis_skill   │
        └───────────────────┘           └───────────────────┘
                                                │
                                                ▼
                                    ┌───────────────────┐
                                    │   Diagnosis       │
                                    │   Report          │
                                    └───────────────────┘
```
