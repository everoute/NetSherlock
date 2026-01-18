"""
Agent prompts for the network troubleshooting system.

This module contains system prompts for the layered subagent architecture:
- Main: Orchestrator agent
- L2: Environment Awareness
- L3: Precise Measurement
- L4: Diagnostic Analysis
"""

from .main_orchestrator import (
    MAIN_ORCHESTRATOR_PROMPT,
    MAIN_ORCHESTRATOR_PROMPT_COMPACT,
    get_main_prompt,
)
from .l2_environment_awareness import (
    L2_ENVIRONMENT_AWARENESS_PROMPT,
    L2_ENVIRONMENT_AWARENESS_PROMPT_COMPACT,
    get_l2_prompt,
)
from .l3_precise_measurement import (
    L3_PRECISE_MEASUREMENT_PROMPT,
    L3_PRECISE_MEASUREMENT_PROMPT_COMPACT,
    get_l3_prompt,
)
from .l4_diagnostic_analysis import (
    L4_DIAGNOSTIC_ANALYSIS_PROMPT,
    L4_DIAGNOSTIC_ANALYSIS_PROMPT_COMPACT,
    get_l4_prompt,
)

__all__ = [
    # Main orchestrator
    "MAIN_ORCHESTRATOR_PROMPT",
    "MAIN_ORCHESTRATOR_PROMPT_COMPACT",
    "get_main_prompt",
    # L2
    "L2_ENVIRONMENT_AWARENESS_PROMPT",
    "L2_ENVIRONMENT_AWARENESS_PROMPT_COMPACT",
    "get_l2_prompt",
    # L3
    "L3_PRECISE_MEASUREMENT_PROMPT",
    "L3_PRECISE_MEASUREMENT_PROMPT_COMPACT",
    "get_l3_prompt",
    # L4
    "L4_DIAGNOSTIC_ANALYSIS_PROMPT",
    "L4_DIAGNOSTIC_ANALYSIS_PROMPT_COMPACT",
    "get_l4_prompt",
]
