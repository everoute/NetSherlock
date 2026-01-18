"""Controller module for dual-mode diagnosis control.

This module implements the DiagnosisController which manages the
two operational modes:
- Autonomous: Full automated diagnosis loop
- Interactive: Human-in-the-loop with checkpoints
"""

from .checkpoints import (
    Checkpoint,
    CheckpointCallback,
    CheckpointData,
    CheckpointManager,
    CheckpointResult,
    CheckpointStatus,
)
from .diagnosis_controller import DiagnosisController

__all__ = [
    # Controller
    "DiagnosisController",
    # Checkpoints
    "Checkpoint",
    "CheckpointCallback",
    "CheckpointData",
    "CheckpointManager",
    "CheckpointResult",
    "CheckpointStatus",
]
