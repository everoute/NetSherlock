"""L1 Layer Tools: Base Monitoring.

MCP tools for querying Grafana metrics, Loki logs, and node local logs.
These provide the foundational monitoring data for network diagnosis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import structlog

from netsherlock.config.settings import get_settings
from netsherlock.core.grafana_client import GrafanaClient, LogsResult, MetricsResult
from netsherlock.core.ssh_manager import SSHManager

logger = structlog.get_logger(__name__)


# Tool result types
@dataclass
class NodeLogsResult:
    """Result of reading node local logs."""

    success: bool
    host: str
    log_type: str
    content: str
    lines_returned: int
    error: str | None = None


# Common network-related PromQL queries
NETWORK_QUERIES = {
    "host_ping_latency": 'host_network_ping_time_ns{{hostname="{hostname}"}}',
    "host_loss_rate": 'host_network_loss_rate{{hostname="{hostname}"}}',
    "vm_network_speed": 'elf_vm_network_{direction}_speed_bitps{{hostname="{hostname}",vm="{vm_id}"}}',
    "interface_errors": 'node_network_transmit_errs_total{{hostname="{hostname}",device="{interface}"}}',
    "tcp_retrans": 'node_netstat_Tcp_RetransSegs{{hostname="{hostname}"}}',
}

# Log type to file path mapping
NODE_LOG_FILES = {
    "pingmesh": "pingmesh",
    "l2ping": "l2ping",
    "network-high-latency": "network-high-latency",
}


def grafana_query_metrics(
    query: str,
    start: str = "-1h",
    end: str = "now",
    step: str = "1m",
) -> MetricsResult:
    """Query VictoriaMetrics via Grafana using PromQL.

    This is an L1 layer tool for retrieving time-series metrics data.

    Args:
        query: PromQL query string (e.g., 'host_network_ping_time_ns{hostname="node1"}')
        start: Start time - relative ("-1h", "-30m") or absolute ("2024-01-15 10:00:00")
        end: End time - relative ("now") or absolute
        step: Query step interval (e.g., "30s", "1m", "5m")

    Returns:
        MetricsResult containing:
        - status: "success" or "error"
        - result_type: "matrix" for range queries
        - series: List of MetricSeries with metric labels and values
        - error: Error message if status is "error"

    Example:
        >>> result = grafana_query_metrics(
        ...     'host_network_ping_time_ns{hostname="node1"}',
        ...     start="-30m",
        ...     end="now",
        ...     step="30s"
        ... )
        >>> if result.status == "success":
        ...     for series in result.series:
        ...         print(f"Metric: {series.metric}")
        ...         print(f"Samples: {len(series.values)}")
    """
    settings = get_settings()

    with GrafanaClient(
        base_url=settings.grafana.base_url,
        username=settings.grafana.username,
        password=settings.grafana.password.get_secret_value(),
        timeout=settings.grafana.timeout,
        victoriametrics_ds_id=settings.grafana.victoriametrics_ds_id,
        loki_ds_id=settings.grafana.loki_ds_id,
    ) as client:
        logger.info("querying_metrics", query=query[:80], start=start, end=end)
        return client.query_metrics(query, start, end, step)


def loki_query_logs(
    query: str,
    start: str = "-1h",
    end: str = "now",
    limit: int = 1000,
    direction: Literal["forward", "backward"] = "backward",
) -> LogsResult:
    """Query Loki logs via Grafana using LogQL.

    This is an L1 layer tool for retrieving log data.

    Args:
        query: LogQL query string (e.g., '{service="nginx"} |= "error"')
        start: Start time
        end: End time
        limit: Maximum number of log entries to return
        direction: "backward" (newest first) or "forward" (oldest first)

    Returns:
        LogsResult containing:
        - status: "success" or "error"
        - entries: List of LogEntry with timestamp, line, and labels
        - error: Error message if status is "error"

    Example:
        >>> result = loki_query_logs(
        ...     '{namespace="kube-system"} |= "error"',
        ...     start="-1h",
        ...     limit=100
        ... )
        >>> if result.status == "success":
        ...     for entry in result.entries:
        ...         print(f"[{entry.timestamp}] {entry.line[:100]}")
    """
    settings = get_settings()

    with GrafanaClient(
        base_url=settings.grafana.base_url,
        username=settings.grafana.username,
        password=settings.grafana.password.get_secret_value(),
        timeout=settings.grafana.timeout,
        victoriametrics_ds_id=settings.grafana.victoriametrics_ds_id,
        loki_ds_id=settings.grafana.loki_ds_id,
    ) as client:
        logger.info("querying_logs", query=query[:80], start=start, limit=limit)
        return client.query_logs(query, start, end, limit, direction)


def read_node_logs(
    host: str,
    log_type: Literal["pingmesh", "l2ping", "network-high-latency"],
    lines: int = 100,
    grep_pattern: str | None = None,
) -> NodeLogsResult:
    """Read local log files from a node via SSH.

    This is an L1 layer tool for accessing node-local diagnostic logs
    that are not aggregated in Loki.

    Args:
        host: Target node IP or hostname
        log_type: Type of log to read:
            - "pingmesh": Network mesh ping statistics
            - "l2ping": L2 ping probe results
            - "network-high-latency": High latency event logs
        lines: Number of lines to read from the end of the log
        grep_pattern: Optional pattern to filter log lines

    Returns:
        NodeLogsResult containing:
        - success: Whether the operation succeeded
        - host: Target host
        - log_type: Type of log read
        - content: Log content (last N lines)
        - lines_returned: Number of lines in content
        - error: Error message if unsuccessful

    Example:
        >>> result = read_node_logs(
        ...     "192.168.1.10",
        ...     "pingmesh",
        ...     lines=50
        ... )
        >>> if result.success:
        ...     print(result.content)
    """
    settings = get_settings()

    if log_type not in NODE_LOG_FILES:
        return NodeLogsResult(
            success=False,
            host=host,
            log_type=log_type,
            content="",
            lines_returned=0,
            error=f"Unknown log type: {log_type}. Valid types: {list(NODE_LOG_FILES.keys())}",
        )

    log_file = NODE_LOG_FILES[log_type]
    log_path = f"{settings.node_log_base_path}/{log_file}"

    # Build command
    if grep_pattern:
        cmd = f"grep '{grep_pattern}' {log_path} | tail -n {lines}"
    else:
        cmd = f"tail -n {lines} {log_path}"

    logger.info("reading_node_logs", host=host, log_type=log_type, lines=lines)

    try:
        with SSHManager(settings.ssh) as ssh:
            result = ssh.execute(host, cmd)

            if result.success:
                content = result.stdout
                line_count = len(content.strip().split("\n")) if content.strip() else 0

                logger.debug("node_logs_read", host=host, lines=line_count)

                return NodeLogsResult(
                    success=True,
                    host=host,
                    log_type=log_type,
                    content=content,
                    lines_returned=line_count,
                )
            else:
                error_msg = result.stderr or f"Command exited with code {result.exit_code}"
                logger.warning("node_logs_failed", host=host, error=error_msg)

                return NodeLogsResult(
                    success=False,
                    host=host,
                    log_type=log_type,
                    content="",
                    lines_returned=0,
                    error=error_msg,
                )

    except Exception as e:
        logger.error("node_logs_error", host=host, error=str(e))
        return NodeLogsResult(
            success=False,
            host=host,
            log_type=log_type,
            content="",
            lines_returned=0,
            error=str(e),
        )


# Convenience functions for common queries
def query_host_latency(hostname: str, start: str = "-1h", end: str = "now") -> MetricsResult:
    """Query ping latency for a host."""
    query = NETWORK_QUERIES["host_ping_latency"].format(hostname=hostname)
    return grafana_query_metrics(query, start, end)


def query_host_loss_rate(hostname: str, start: str = "-1h", end: str = "now") -> MetricsResult:
    """Query packet loss rate for a host."""
    query = NETWORK_QUERIES["host_loss_rate"].format(hostname=hostname)
    return grafana_query_metrics(query, start, end)


def query_tcp_retransmissions(hostname: str, start: str = "-1h", end: str = "now") -> MetricsResult:
    """Query TCP retransmission count for a host."""
    query = NETWORK_QUERIES["tcp_retrans"].format(hostname=hostname)
    return grafana_query_metrics(query, start, end)
