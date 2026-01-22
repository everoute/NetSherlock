"""Grafana API client for VictoriaMetrics and Loki queries.

Provides access to monitoring data through Grafana's datasource proxy API.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MetricSample:
    """Single metric sample point."""

    timestamp: float
    value: float


@dataclass
class MetricSeries:
    """Metric series with labels and values."""

    metric: dict[str, str]
    values: list[MetricSample]


@dataclass
class MetricsResult:
    """Result of a metrics query."""

    status: Literal["success", "error"]
    result_type: str
    series: list[MetricSeries]
    error: str | None = None


@dataclass
class LogEntry:
    """Single log entry."""

    timestamp: float
    line: str
    labels: dict[str, str]


@dataclass
class LogsResult:
    """Result of a logs query."""

    status: Literal["success", "error"]
    entries: list[LogEntry]
    error: str | None = None


class GrafanaClient:
    """Client for Grafana API with VictoriaMetrics and Loki support.

    Uses Grafana's datasource proxy API to query metrics and logs with
    centralized authentication.

    Example:
        >>> client = GrafanaClient()
        >>> result = client.query_metrics("up", start="-1h", end="now")
        >>> for series in result.series:
        ...     print(series.metric, len(series.values))
    """

    def __init__(
        self,
        base_url: str = "http://192.168.79.79/grafana",
        username: str = "o11y",
        password: str = "HC!r0cks",
        timeout: int = 30,
        victoriametrics_ds_id: int = 1,
        loki_ds_id: int = 3,
    ):
        """Initialize Grafana client.

        Args:
            base_url: Grafana base URL
            username: Grafana username
            password: Grafana password
            timeout: Request timeout in seconds
            victoriametrics_ds_id: VictoriaMetrics datasource ID
            loki_ds_id: Loki datasource ID
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.vm_ds_id = victoriametrics_ds_id
        self.loki_ds_id = loki_ds_id

        # Basic auth header
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._auth_header = f"Basic {credentials}"

        # HTTP client
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Lazy-initialized HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=self.timeout,
                headers={"Authorization": self._auth_header},
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            self._client.close()
            self._client = None

    def __enter__(self) -> GrafanaClient:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object) -> None:
        self.close()

    def _parse_time(self, time_spec: str | datetime | float) -> float:
        """Parse time specification to Unix timestamp.

        Supports:
        - Unix timestamp (float/int)
        - datetime object
        - Relative time string: "now", "-1h", "-30m", "-1d"
        - ISO8601 string
        """
        if isinstance(time_spec, (int, float)):
            return float(time_spec)

        if isinstance(time_spec, datetime):
            return time_spec.timestamp()

        if isinstance(time_spec, str):
            time_spec = time_spec.strip()

            if time_spec == "now":
                return datetime.now().timestamp()

            # Relative time: -1h, -30m, -1d
            if time_spec.startswith("-"):
                unit = time_spec[-1]
                value = int(time_spec[1:-1])
                now = datetime.now()

                if unit == "s":
                    delta = timedelta(seconds=value)
                elif unit == "m":
                    delta = timedelta(minutes=value)
                elif unit == "h":
                    delta = timedelta(hours=value)
                elif unit == "d":
                    delta = timedelta(days=value)
                else:
                    raise ValueError(f"Unknown time unit: {unit}")

                return (now - delta).timestamp()

            # Try parsing as ISO8601
            try:
                return datetime.fromisoformat(time_spec).timestamp()
            except ValueError:
                pass

            # Try common formats
            for fmt in [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
            ]:
                try:
                    return datetime.strptime(time_spec, fmt).timestamp()
                except ValueError:
                    continue

        raise ValueError(f"Cannot parse time: {time_spec}")

    def _vm_api_url(self, endpoint: str) -> str:
        """Build VictoriaMetrics API URL."""
        return f"{self.base_url}/api/datasources/proxy/{self.vm_ds_id}/api/v1/{endpoint}"

    def _loki_api_url(self, endpoint: str) -> str:
        """Build Loki API URL."""
        return f"{self.base_url}/api/datasources/proxy/{self.loki_ds_id}/loki/api/v1/{endpoint}"

    def query_metrics(
        self,
        query: str,
        start: str | datetime | float = "-1h",
        end: str | datetime | float = "now",
        step: str = "1m",
    ) -> MetricsResult:
        """Execute PromQL range query against VictoriaMetrics.

        Args:
            query: PromQL query string
            start: Start time (relative like "-1h" or absolute)
            end: End time (relative like "now" or absolute)
            step: Query step interval (e.g., "1m", "30s")

        Returns:
            MetricsResult with series data
        """
        start_ts = self._parse_time(start)
        end_ts = self._parse_time(end)

        # Parse step to seconds
        step_seconds = self._parse_step(step)

        params: dict[str, str | int] = {
            "query": query,
            "start": int(start_ts),
            "end": int(end_ts),
            "step": step_seconds,
        }

        log = logger.bind(query=query[:80], start=start, end=end)

        try:
            response = self.client.get(
                self._vm_api_url("query_range"),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                error_msg = data.get("error", "Unknown error")
                log.error("metrics_query_failed", error=error_msg)
                return MetricsResult(
                    status="error",
                    result_type="",
                    series=[],
                    error=error_msg,
                )

            result_data = data.get("data", {})
            result_type = result_data.get("resultType", "matrix")
            raw_series = result_data.get("result", [])

            series = []
            for s in raw_series:
                samples = [
                    MetricSample(timestamp=float(v[0]), value=float(v[1]))
                    for v in s.get("values", [])
                    if v[1] != "NaN"
                ]
                series.append(MetricSeries(metric=s.get("metric", {}), values=samples))

            log.debug(
                "metrics_query_success",
                series_count=len(series),
                total_samples=sum(len(s.values) for s in series),
            )

            return MetricsResult(
                status="success",
                result_type=result_type,
                series=series,
            )

        except httpx.HTTPStatusError as e:
            log.error("metrics_query_http_error", status=e.response.status_code)
            return MetricsResult(
                status="error",
                result_type="",
                series=[],
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            log.error("metrics_query_error", error=str(e))
            return MetricsResult(
                status="error",
                result_type="",
                series=[],
                error=str(e),
            )

    def query_metrics_instant(self, query: str) -> MetricsResult:
        """Execute instant PromQL query.

        Args:
            query: PromQL query string

        Returns:
            MetricsResult with current values
        """
        try:
            response = self.client.get(
                self._vm_api_url("query"),
                params={"query": query},
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                return MetricsResult(
                    status="error",
                    result_type="",
                    series=[],
                    error=data.get("error", "Unknown error"),
                )

            result_data = data.get("data", {})
            result_type = result_data.get("resultType", "vector")
            raw_results = result_data.get("result", [])

            series = []
            for r in raw_results:
                value = r.get("value", [0, "0"])
                if value[1] != "NaN":
                    sample = MetricSample(timestamp=float(value[0]), value=float(value[1]))
                    series.append(MetricSeries(metric=r.get("metric", {}), values=[sample]))

            return MetricsResult(
                status="success",
                result_type=result_type,
                series=series,
            )

        except Exception as e:
            return MetricsResult(
                status="error",
                result_type="",
                series=[],
                error=str(e),
            )

    def query_logs(
        self,
        query: str,
        start: str | datetime | float = "-1h",
        end: str | datetime | float = "now",
        limit: int = 1000,
        direction: Literal["forward", "backward"] = "backward",
    ) -> LogsResult:
        """Execute LogQL query against Loki.

        Args:
            query: LogQL query string (e.g., '{service="nginx"}')
            start: Start time
            end: End time
            limit: Maximum number of entries
            direction: Query direction (backward = newest first)

        Returns:
            LogsResult with log entries
        """
        start_ts = self._parse_time(start)
        end_ts = self._parse_time(end)

        # Loki uses nanoseconds
        params = {
            "query": query,
            "start": int(start_ts * 1e9),
            "end": int(end_ts * 1e9),
            "limit": limit,
            "direction": direction,
        }

        log = logger.bind(query=query[:80], limit=limit)

        try:
            response = self.client.get(
                self._loki_api_url("query_range"),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                error_msg = data.get("error", "Unknown error")
                log.error("logs_query_failed", error=error_msg)
                return LogsResult(status="error", entries=[], error=error_msg)

            result_data = data.get("data", {})
            streams = result_data.get("result", [])

            entries = []
            for stream in streams:
                labels = stream.get("stream", {})
                for value in stream.get("values", []):
                    timestamp_ns = int(value[0])
                    line = value[1]
                    entries.append(
                        LogEntry(
                            timestamp=timestamp_ns / 1e9,
                            line=line,
                            labels=labels,
                        )
                    )

            # Sort by timestamp (direction already handled by Loki)
            log.debug("logs_query_success", entry_count=len(entries))

            return LogsResult(status="success", entries=entries)

        except httpx.HTTPStatusError as e:
            log.error("logs_query_http_error", status=e.response.status_code)
            return LogsResult(
                status="error",
                entries=[],
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            log.error("logs_query_error", error=str(e))
            return LogsResult(status="error", entries=[], error=str(e))

    def get_label_values(self, label: str) -> list[str]:
        """Get all values for a Prometheus label.

        Args:
            label: Label name (e.g., "hostname", "cluster")

        Returns:
            List of label values
        """
        try:
            response = self.client.get(
                self._vm_api_url(f"label/{label}/values"),
            )
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "success":
                result: list[str] = data.get("data", [])
                return result
            return []

        except Exception:
            return []

    def _parse_step(self, step: str) -> int:
        """Parse step string to seconds."""
        step = step.strip().lower()

        if step.endswith("s"):
            return int(step[:-1])
        elif step.endswith("m"):
            return int(step[:-1]) * 60
        elif step.endswith("h"):
            return int(step[:-1]) * 3600
        elif step.endswith("d"):
            return int(step[:-1]) * 86400
        else:
            # Assume seconds if no unit
            return int(step)


# Convenience functions for quick queries
def query_metrics(
    query: str,
    start: str = "-1h",
    end: str = "now",
    step: str = "1m",
) -> MetricsResult:
    """Quick metrics query with default settings."""
    with GrafanaClient() as client:
        return client.query_metrics(query, start, end, step)


def query_logs(
    query: str,
    start: str = "-1h",
    end: str = "now",
    limit: int = 1000,
) -> LogsResult:
    """Quick logs query with default settings."""
    with GrafanaClient() as client:
        return client.query_logs(query, start, end, limit)
