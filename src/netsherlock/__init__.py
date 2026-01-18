"""NetSherlock - AI-driven network troubleshooting agent.

Built with Claude Agent SDK, integrating with internal Grafana monitoring data sources.

## Quick Start

```python
from netsherlock.agents import create_orchestrator

# Create orchestrator
orchestrator = create_orchestrator()

# Diagnose an alert
result = await orchestrator.diagnose_alert(alert_data)

# Or diagnose a manual request
result = await orchestrator.diagnose_request({
    "problem_type": "system_network_latency",
    "src_node": "192.168.1.10",
    "dst_node": "192.168.1.20",
})
```

## Run Webhook Server

```bash
python -m netsherlock.api.webhook
```

Or with uvicorn:

```bash
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080
```
"""

__version__ = "0.1.0"


def __getattr__(name: str):
    """Lazy import for agent SDK components."""
    _agent_exports = {
        "create_orchestrator",
        "create_subagent",
        "NetworkTroubleshootingOrchestrator",
        "L2EnvironmentSubagent",
        "L3MeasurementSubagent",
        "L4AnalysisSubagent",
        "DiagnosisResult",
        "ProblemType",
        "RootCauseCategory",
    }

    if name in _agent_exports:
        from . import agents
        return getattr(agents, name)

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "__version__",
    # Orchestrator
    "create_orchestrator",
    "create_subagent",
    "NetworkTroubleshootingOrchestrator",
    # Subagents
    "L2EnvironmentSubagent",
    "L3MeasurementSubagent",
    "L4AnalysisSubagent",
    # Data types
    "DiagnosisResult",
    "ProblemType",
    "RootCauseCategory",
]
