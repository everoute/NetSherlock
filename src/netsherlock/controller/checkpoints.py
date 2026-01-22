"""Checkpoint management for interactive mode.

Checkpoints are points in the diagnosis flow where the system
pauses to wait for human confirmation or input.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from netsherlock.schemas.config import CheckpointType


class CheckpointStatus(str, Enum):
    """Status of a checkpoint."""

    PENDING = "pending"
    WAITING = "waiting"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class CheckpointData:
    """Data presented at a checkpoint.

    Attributes:
        checkpoint_type: Type of checkpoint
        summary: Human-readable summary of current state
        details: Detailed data for review
        options: Available options for user
        recommendation: Agent's recommended action
    """

    checkpoint_type: CheckpointType
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    options: list[str] = field(default_factory=list)
    recommendation: str | None = None


@dataclass
class CheckpointResult:
    """Result of a checkpoint interaction.

    Attributes:
        checkpoint_type: Type of checkpoint
        status: How the checkpoint was resolved
        user_input: Any input provided by user
        selected_option: Which option was selected (if applicable)
        timestamp: When the checkpoint was resolved
    """

    checkpoint_type: CheckpointType
    status: CheckpointStatus
    user_input: str | None = None
    selected_option: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def is_confirmed(self) -> bool:
        """Check if checkpoint was confirmed (proceed)."""
        return self.status in (CheckpointStatus.CONFIRMED, CheckpointStatus.MODIFIED)

    @property
    def is_cancelled(self) -> bool:
        """Check if checkpoint was cancelled."""
        return self.status == CheckpointStatus.CANCELLED


# Type for checkpoint callback functions
CheckpointCallback = Callable[
    [CheckpointData],
    Coroutine[Any, Any, CheckpointResult]
]


class Checkpoint:
    """A single checkpoint in the diagnosis flow.

    Manages the state and interaction for one checkpoint.
    """

    def __init__(
        self,
        checkpoint_type: CheckpointType,
        timeout_seconds: int = 300,
        auto_confirm_on_timeout: bool = False,
    ):
        """Initialize checkpoint.

        Args:
            checkpoint_type: Type of this checkpoint
            timeout_seconds: Timeout for user response
            auto_confirm_on_timeout: Whether to auto-confirm on timeout
        """
        self.checkpoint_type = checkpoint_type
        self.timeout_seconds = timeout_seconds
        self.auto_confirm_on_timeout = auto_confirm_on_timeout
        self._event = asyncio.Event()
        self._result: CheckpointResult | None = None
        self._data: CheckpointData | None = None

    async def wait(self, data: CheckpointData) -> CheckpointResult:
        """Wait for checkpoint resolution.

        Args:
            data: Data to present at checkpoint

        Returns:
            Result of checkpoint interaction
        """
        self._data = data
        self._event.clear()

        try:
            await asyncio.wait_for(
                self._event.wait(),
                timeout=self.timeout_seconds,
            )
            if self._result is None:
                raise RuntimeError("Checkpoint resolved without result")
            return self._result
        except asyncio.TimeoutError:
            if self.auto_confirm_on_timeout:
                return CheckpointResult(
                    checkpoint_type=self.checkpoint_type,
                    status=CheckpointStatus.CONFIRMED,
                )
            return CheckpointResult(
                checkpoint_type=self.checkpoint_type,
                status=CheckpointStatus.TIMEOUT,
            )

    def confirm(self, user_input: str | None = None) -> None:
        """Confirm the checkpoint and continue.

        Args:
            user_input: Optional input from user
        """
        self._result = CheckpointResult(
            checkpoint_type=self.checkpoint_type,
            status=CheckpointStatus.CONFIRMED,
            user_input=user_input,
        )
        self._event.set()

    def modify(self, user_input: str) -> None:
        """Modify and continue with user's changes.

        Args:
            user_input: User's modified input
        """
        self._result = CheckpointResult(
            checkpoint_type=self.checkpoint_type,
            status=CheckpointStatus.MODIFIED,
            user_input=user_input,
        )
        self._event.set()

    def cancel(self) -> None:
        """Cancel at this checkpoint."""
        self._result = CheckpointResult(
            checkpoint_type=self.checkpoint_type,
            status=CheckpointStatus.CANCELLED,
        )
        self._event.set()

    @property
    def is_waiting(self) -> bool:
        """Check if checkpoint is waiting for response."""
        return self._data is not None and not self._event.is_set()

    @property
    def current_data(self) -> CheckpointData | None:
        """Get current checkpoint data."""
        return self._data


class CheckpointManager:
    """Manages checkpoints for a diagnosis session.

    Coordinates multiple checkpoints and provides a unified
    interface for the controller.
    """

    def __init__(
        self,
        enabled_checkpoints: list[CheckpointType],
        timeout_seconds: int = 300,
        auto_confirm_on_timeout: bool = False,
        callback: CheckpointCallback | None = None,
    ):
        """Initialize checkpoint manager.

        Args:
            enabled_checkpoints: Which checkpoints are enabled
            timeout_seconds: Default timeout for checkpoints
            auto_confirm_on_timeout: Auto-confirm on timeout
            callback: Optional callback for checkpoint interactions
        """
        self.enabled_checkpoints = set(enabled_checkpoints)
        self.timeout_seconds = timeout_seconds
        self.auto_confirm_on_timeout = auto_confirm_on_timeout
        self.callback = callback

        self._checkpoints: dict[CheckpointType, Checkpoint] = {}
        self._history: list[CheckpointResult] = []

    def is_enabled(self, checkpoint_type: CheckpointType) -> bool:
        """Check if a checkpoint type is enabled.

        Args:
            checkpoint_type: Type to check

        Returns:
            True if checkpoint is enabled
        """
        return checkpoint_type in self.enabled_checkpoints

    async def wait_at(self, data: CheckpointData) -> CheckpointResult:
        """Wait at a checkpoint.

        Args:
            data: Data to present at checkpoint

        Returns:
            Result of checkpoint interaction

        Note:
            If checkpoint is not enabled, returns confirmed immediately.
        """
        if not self.is_enabled(data.checkpoint_type):
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.CONFIRMED,
            )

        # Use callback if available
        if self.callback is not None:
            result = await self.callback(data)
            self._history.append(result)
            return result

        # Otherwise use internal checkpoint
        checkpoint = Checkpoint(
            checkpoint_type=data.checkpoint_type,
            timeout_seconds=self.timeout_seconds,
            auto_confirm_on_timeout=self.auto_confirm_on_timeout,
        )
        self._checkpoints[data.checkpoint_type] = checkpoint

        result = await checkpoint.wait(data)
        self._history.append(result)
        return result

    def get_checkpoint(self, checkpoint_type: CheckpointType) -> Checkpoint | None:
        """Get a checkpoint by type.

        Args:
            checkpoint_type: Type of checkpoint

        Returns:
            Checkpoint if exists, None otherwise
        """
        return self._checkpoints.get(checkpoint_type)

    def confirm_checkpoint(
        self,
        checkpoint_type: CheckpointType,
        user_input: str | None = None,
    ) -> bool:
        """Confirm a waiting checkpoint.

        Args:
            checkpoint_type: Type of checkpoint to confirm
            user_input: Optional user input

        Returns:
            True if checkpoint was confirmed, False if not found/waiting
        """
        checkpoint = self._checkpoints.get(checkpoint_type)
        if checkpoint is not None and checkpoint.is_waiting:
            checkpoint.confirm(user_input)
            return True
        return False

    def cancel_checkpoint(self, checkpoint_type: CheckpointType) -> bool:
        """Cancel a waiting checkpoint.

        Args:
            checkpoint_type: Type of checkpoint to cancel

        Returns:
            True if checkpoint was cancelled, False if not found/waiting
        """
        checkpoint = self._checkpoints.get(checkpoint_type)
        if checkpoint is not None and checkpoint.is_waiting:
            checkpoint.cancel()
            return True
        return False

    @property
    def history(self) -> list[CheckpointResult]:
        """Get checkpoint history for this session."""
        return self._history.copy()

    @property
    def waiting_checkpoint(self) -> Checkpoint | None:
        """Get currently waiting checkpoint, if any."""
        for checkpoint in self._checkpoints.values():
            if checkpoint.is_waiting:
                return checkpoint
        return None
