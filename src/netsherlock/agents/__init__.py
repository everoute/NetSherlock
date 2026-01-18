"""
Network troubleshooting agents built with Claude Agent SDK.

This module implements a four-layer diagnostic architecture:
- Main Agent: Orchestrates the diagnostic workflow
- L2 Subagent: Environment awareness and topology collection
- L3 Subagent: Precise measurement execution (BCC/eBPF tools)
- L4 Subagent: Diagnostic analysis and report generation

Note: Agent classes (orchestrator, subagents) require claude_code_sdk to be installed.
Prompts and base types can be imported without the SDK.
"""

# These can always be imported (no external SDK dependency)
from .prompts import (
    MAIN_ORCHESTRATOR_PROMPT,
    L2_ENVIRONMENT_AWARENESS_PROMPT,
    L3_PRECISE_MEASUREMENT_PROMPT,
    L4_DIAGNOSTIC_ANALYSIS_PROMPT,
    get_main_prompt,
    get_l2_prompt,
    get_l3_prompt,
    get_l4_prompt,
)
from .base import (
    ProblemType,
    RootCauseCategory,
    AlertContext,
    VMInfo,
    NetworkInfo,
    NodeEnvironment,
    NetworkPath,
    FlowInfo,
    NetworkEnvironment,
    LatencyHistogram,
    LatencySegment,
    MeasurementResult,
    RootCause,
    Recommendation,
    DiagnosisResult,
)
from .tool_executor import (
    ToolExecutor,
    ToolNotFoundError,
    ToolExecutionError,
    get_tool_executor,
    reset_tool_executor,
)


# Lazy imports for SDK-dependent classes
def __getattr__(name: str):
    """Lazy import for Claude SDK dependent components."""
    _subagent_exports = {
        "L2EnvironmentSubagent",
        "L3MeasurementSubagent",
        "L4AnalysisSubagent",
        "create_subagent",
    }
    _orchestrator_exports = {
        "NetworkTroubleshootingOrchestrator",
        "create_orchestrator",
    }

    if name in _subagent_exports:
        from . import subagents
        return getattr(subagents, name)

    if name in _orchestrator_exports:
        from . import orchestrator
        return getattr(orchestrator, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Prompts
    "MAIN_ORCHESTRATOR_PROMPT",
    "L2_ENVIRONMENT_AWARENESS_PROMPT",
    "L3_PRECISE_MEASUREMENT_PROMPT",
    "L4_DIAGNOSTIC_ANALYSIS_PROMPT",
    "get_main_prompt",
    "get_l2_prompt",
    "get_l3_prompt",
    "get_l4_prompt",
    # Data types
    "ProblemType",
    "RootCauseCategory",
    "AlertContext",
    "VMInfo",
    "NetworkInfo",
    "NodeEnvironment",
    "NetworkPath",
    "FlowInfo",
    "NetworkEnvironment",
    "LatencyHistogram",
    "LatencySegment",
    "MeasurementResult",
    "RootCause",
    "Recommendation",
    "DiagnosisResult",
    # Tool executor
    "ToolExecutor",
    "ToolNotFoundError",
    "ToolExecutionError",
    "get_tool_executor",
    "reset_tool_executor",
    # Subagents (lazy loaded)
    "L2EnvironmentSubagent",
    "L3MeasurementSubagent",
    "L4AnalysisSubagent",
    "create_subagent",
    # Orchestrator (lazy loaded)
    "NetworkTroubleshootingOrchestrator",
    "create_orchestrator",
]
