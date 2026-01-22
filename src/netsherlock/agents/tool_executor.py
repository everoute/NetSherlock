"""Tool Executor for routing agent tool calls to actual implementations.

This module provides the bridge between Claude Agent's tool calls and
the actual L1-L4 tool implementations.
"""

from __future__ import annotations

from typing import Any

import structlog

# L1 tools
from netsherlock.tools.l1_monitoring import (
    grafana_query_metrics,
    loki_query_logs,
    query_host_latency,
    query_host_loss_rate,
    query_tcp_retransmissions,
    read_node_logs,
)

# L2 tools
from netsherlock.tools.l2_environment import (
    build_network_path,
    collect_system_network_env,
    collect_vm_network_env,
)

# L3 tools
from netsherlock.tools.l3_measurement import (
    execute_coordinated_measurement,
    measure_packet_drop,
    measure_vm_latency_breakdown,
)

# L4 tools
from netsherlock.tools.l4_analysis import (
    analyze_latency_segments,
    analyze_packet_drops,
    generate_diagnosis_report,
    identify_root_cause,
)

logger = structlog.get_logger(__name__)


class ToolNotFoundError(Exception):
    """Raised when a tool name is not recognized."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Unknown tool: {tool_name}")


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""

    def __init__(self, tool_name: str, cause: Exception):
        self.tool_name = tool_name
        self.cause = cause
        super().__init__(f"Tool {tool_name} failed: {cause}")


class ToolExecutor:
    """Routes agent tool calls to actual L1-L4 implementations.

    This class acts as a dispatcher for tool calls from the orchestrator
    agent to the actual tool implementations.

    Example:
        >>> executor = ToolExecutor()
        >>> result = await executor.execute(
        ...     "grafana_query_metrics",
        ...     {"query": "up", "start": "-1h"}
        ... )
    """

    def __init__(self):
        """Initialize tool executor with tool mappings."""
        self._sync_handlers = self._build_sync_handlers()
        self._async_handlers = self._build_async_handlers()

        self._all_tool_names = set(self._sync_handlers.keys()) | set(
            self._async_handlers.keys()
        )

    def _build_sync_handlers(self) -> dict[str, Any]:
        """Build mapping of tool names to synchronous handlers."""
        return {
            # L1 monitoring tools (synchronous)
            "grafana_query_metrics": grafana_query_metrics,
            "loki_query_logs": loki_query_logs,
            "read_node_logs": read_node_logs,
            "read_pingmesh_logs": lambda **kwargs: read_node_logs(
                host=kwargs.get("node_ip", ""),
                log_type=kwargs.get("log_type", "pingmesh"),
                lines=kwargs.get("lines", 100),
            ),
            "query_host_latency": query_host_latency,
            "query_host_loss_rate": query_host_loss_rate,
            "query_tcp_retransmissions": query_tcp_retransmissions,
            # L2 environment tools (synchronous)
            "collect_vm_network_env": collect_vm_network_env,
            "collect_system_network_env": collect_system_network_env,
            "build_network_path": build_network_path,
            # L3 measurement tools (synchronous - actual execution is sync)
            "execute_coordinated_measurement": execute_coordinated_measurement,
            "measure_vm_latency_breakdown": measure_vm_latency_breakdown,
            "measure_packet_drop": measure_packet_drop,
            # L4 analysis tools (synchronous)
            "analyze_latency_segments": analyze_latency_segments,
            "analyze_packet_drops": analyze_packet_drops,
            "generate_diagnosis_report": generate_diagnosis_report,
            "identify_root_cause": identify_root_cause,
        }

    def _build_async_handlers(self) -> dict[str, Any]:
        """Build mapping of tool names to async handlers.

        Note: Currently all tools are synchronous. This is here for
        future expansion if async tools are needed.
        """
        return {}

    def get_available_tools(self) -> list[str]:
        """Get list of all available tool names.

        Returns:
            List of tool names that can be executed
        """
        return sorted(self._all_tool_names)

    def is_tool_available(self, tool_name: str) -> bool:
        """Check if a tool is available.

        Args:
            tool_name: Name of the tool to check

        Returns:
            True if tool exists
        """
        return tool_name in self._all_tool_names

    def get_tool_layer(self, tool_name: str) -> str:
        """Get the layer (L1-L4) for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Layer string ("L1", "L2", "L3", "L4", or "unknown")
        """
        l1_tools = {
            "grafana_query_metrics",
            "loki_query_logs",
            "read_node_logs",
            "read_pingmesh_logs",
            "query_host_latency",
            "query_host_loss_rate",
            "query_tcp_retransmissions",
        }
        l2_tools = {
            "collect_vm_network_env",
            "collect_system_network_env",
            "build_network_path",
        }
        l3_tools = {
            "execute_coordinated_measurement",
            "measure_vm_latency_breakdown",
            "measure_packet_drop",
        }
        l4_tools = {
            "analyze_latency_segments",
            "analyze_packet_drops",
            "generate_diagnosis_report",
            "identify_root_cause",
        }

        if tool_name in l1_tools:
            return "L1"
        elif tool_name in l2_tools:
            return "L2"
        elif tool_name in l3_tools:
            return "L3"
        elif tool_name in l4_tools:
            return "L4"
        else:
            return "unknown"

    async def execute(self, tool_name: str, args: dict[str, Any]) -> Any:
        """Execute a tool by name with given arguments.

        Args:
            tool_name: Name of the tool to execute
            args: Arguments dict to pass to the tool

        Returns:
            Result from the tool execution

        Raises:
            ToolNotFoundError: If tool_name is not recognized
            ToolExecutionError: If tool execution fails
        """
        log = logger.bind(tool=tool_name, layer=self.get_tool_layer(tool_name))
        log.info("executing_tool", args_keys=list(args.keys()))

        # Check async handlers first
        if tool_name in self._async_handlers:
            handler = self._async_handlers[tool_name]
            try:
                result = await handler(**args)
                log.debug("tool_completed")
                return result
            except Exception as e:
                log.error("tool_execution_failed", error=str(e))
                raise ToolExecutionError(tool_name, e) from e

        # Then check sync handlers
        if tool_name in self._sync_handlers:
            handler = self._sync_handlers[tool_name]
            try:
                result = handler(**args)
                log.debug("tool_completed")
                return result
            except Exception as e:
                log.error("tool_execution_failed", error=str(e))
                raise ToolExecutionError(tool_name, e) from e

        # Tool not found
        log.warning("unknown_tool")
        raise ToolNotFoundError(tool_name)

    def execute_sync(self, tool_name: str, args: dict[str, Any]) -> Any:
        """Execute a synchronous tool by name.

        Args:
            tool_name: Name of the tool to execute
            args: Arguments dict to pass to the tool

        Returns:
            Result from the tool execution

        Raises:
            ToolNotFoundError: If tool_name is not recognized or is async-only
            ToolExecutionError: If tool execution fails
        """
        if tool_name in self._async_handlers:
            raise ToolNotFoundError(
                f"{tool_name} is async-only, use execute() instead"
            )

        if tool_name not in self._sync_handlers:
            raise ToolNotFoundError(tool_name)

        log = logger.bind(tool=tool_name, layer=self.get_tool_layer(tool_name))
        log.info("executing_tool_sync", args_keys=list(args.keys()))

        handler = self._sync_handlers[tool_name]
        try:
            result = handler(**args)
            log.debug("tool_completed")
            return result
        except Exception as e:
            log.error("tool_execution_failed", error=str(e))
            raise ToolExecutionError(tool_name, e) from e


# Singleton instance
_executor: ToolExecutor | None = None


def get_tool_executor() -> ToolExecutor:
    """Get the global ToolExecutor instance (singleton).

    Returns:
        ToolExecutor instance
    """
    global _executor
    if _executor is None:
        _executor = ToolExecutor()
    return _executor


def reset_tool_executor() -> None:
    """Reset the global ToolExecutor (for testing)."""
    global _executor
    _executor = None
