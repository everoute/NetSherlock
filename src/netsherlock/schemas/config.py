"""Diagnosis configuration schemas.

Defines configuration models for dual-mode diagnosis control:
- Autonomous mode: Full automated diagnosis loop
- Interactive mode: Human-in-the-loop with checkpoints
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class DiagnosisMode(str, Enum):
    """Diagnosis execution mode."""

    AUTONOMOUS = "autonomous"
    INTERACTIVE = "interactive"


class CheckpointType(str, Enum):
    """Types of human checkpoints in interactive mode."""

    PROBLEM_CLASSIFICATION = "problem_classification"
    MEASUREMENT_PLAN = "measurement_plan"
    FURTHER_DIAGNOSIS = "further_diagnosis"


class AutonomousConfig(BaseModel):
    """Configuration for autonomous mode."""

    enabled: bool = Field(
        default=True,
        description="Whether autonomous mode is allowed",
    )
    auto_agent_loop: bool = Field(
        default=False,
        description="Auto-start agent loop on alert (requires enabled=True)",
    )
    interrupt_enabled: bool = Field(
        default=True,
        description="Allow interrupting autonomous execution",
    )
    known_alert_types: list[str] = Field(
        default_factory=lambda: ["VMNetworkLatency", "HostNetworkLatency"],
        description="Alert types that can trigger autonomous mode",
    )


class InteractiveConfig(BaseModel):
    """Configuration for interactive mode."""

    checkpoints: list[CheckpointType] = Field(
        default_factory=lambda: [
            CheckpointType.PROBLEM_CLASSIFICATION,
            CheckpointType.MEASUREMENT_PLAN,
        ],
        description="Checkpoints requiring user confirmation",
    )
    timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Timeout for user input at checkpoints (30-3600 seconds)",
    )
    auto_confirm_on_timeout: bool = Field(
        default=False,
        description="Auto-confirm and continue if user times out",
    )


class DiagnosisConfig(BaseModel):
    """Main diagnosis configuration.

    Controls the dual-mode diagnosis behavior:
    - default_mode: Which mode to use by default
    - autonomous: Settings for autonomous mode
    - interactive: Settings for interactive mode

    Example:
        >>> config = DiagnosisConfig(
        ...     default_mode=DiagnosisMode.INTERACTIVE,
        ...     autonomous=AutonomousConfig(auto_agent_loop=True),
        ... )
        >>> config.default_mode
        <DiagnosisMode.INTERACTIVE: 'interactive'>
    """

    default_mode: DiagnosisMode = Field(
        default=DiagnosisMode.INTERACTIVE,
        description="Default diagnosis mode",
    )
    autonomous: AutonomousConfig = Field(
        default_factory=AutonomousConfig,
        description="Autonomous mode configuration",
    )
    interactive: InteractiveConfig = Field(
        default_factory=InteractiveConfig,
        description="Interactive mode configuration",
    )

    def is_autonomous_allowed(self, alert_type: str | None = None) -> bool:
        """Check if autonomous mode is allowed for given alert type.

        Args:
            alert_type: The alert type to check (e.g., "VMNetworkLatency")

        Returns:
            True if autonomous mode can be used

        Note:
            Requires a known alert_type for safety. Unknown or missing
            alert types will not trigger autonomous mode automatically.
        """
        if not self.autonomous.enabled:
            return False
        if not self.autonomous.auto_agent_loop:
            return False
        # Require a known alert type for autonomous mode
        if not alert_type or alert_type not in self.autonomous.known_alert_types:
            return False
        return True

    def determine_mode(
        self,
        source: Literal["cli", "webhook", "api"],
        alert_type: str | None = None,
        force_mode: DiagnosisMode | None = None,
    ) -> DiagnosisMode:
        """Determine which mode to use based on context.

        Args:
            source: Where the request originated from
            alert_type: Alert type if triggered by alert
            force_mode: Explicitly requested mode (overrides logic)

        Returns:
            The diagnosis mode to use

        Mode selection rules:
        1. If force_mode specified, use it
        2. CLI default: interactive
        3. Webhook with auto_agent_loop + known alert: autonomous
        4. Otherwise: default_mode
        """
        # Rule 1: Explicit override
        if force_mode is not None:
            return force_mode

        # Rule 2: CLI defaults to interactive
        if source == "cli":
            return DiagnosisMode.INTERACTIVE

        # Rule 3: Webhook can trigger autonomous
        if source == "webhook" and self.is_autonomous_allowed(alert_type):
            return DiagnosisMode.AUTONOMOUS

        # Rule 4: Use default
        return self.default_mode


class DiagnosisRequestSource(str, Enum):
    """Source of diagnosis request."""

    CLI = "cli"
    WEBHOOK = "webhook"
    API = "api"
