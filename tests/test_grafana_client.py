"""Tests for GrafanaClient.

Tests for metrics and logs query functionality.
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

import httpx

from netsherlock.core.grafana_client import (
    GrafanaClient,
    MetricsResult,
    MetricSeries,
    MetricSample,
    LogsResult,
    LogEntry,
    query_metrics,
    query_logs,
)


class TestMetricSample:
    """Tests for MetricSample dataclass."""

    def test_create_sample(self):
        """Test creating metric sample."""
        sample = MetricSample(timestamp=1700000000.0, value=123.45)
        assert sample.timestamp == 1700000000.0
        assert sample.value == 123.45


class TestMetricSeries:
    """Tests for MetricSeries dataclass."""

    def test_create_series(self):
        """Test creating metric series."""
        series = MetricSeries(
            metric={"hostname": "node1", "job": "prometheus"},
            values=[
                MetricSample(timestamp=1700000000.0, value=100.0),
                MetricSample(timestamp=1700000060.0, value=101.0),
            ],
        )
        assert series.metric["hostname"] == "node1"
        assert len(series.values) == 2


class TestMetricsResult:
    """Tests for MetricsResult dataclass."""

    def test_create_success_result(self):
        """Test creating successful metrics result."""
        result = MetricsResult(
            status="success",
            result_type="matrix",
            series=[
                MetricSeries(metric={"hostname": "node1"}, values=[]),
            ],
        )
        assert result.status == "success"
        assert result.error is None

    def test_create_error_result(self):
        """Test creating error metrics result."""
        result = MetricsResult(
            status="error",
            result_type="",
            series=[],
            error="Query syntax error",
        )
        assert result.status == "error"
        assert result.error == "Query syntax error"


class TestLogEntry:
    """Tests for LogEntry dataclass."""

    def test_create_entry(self):
        """Test creating log entry."""
        entry = LogEntry(
            timestamp=1700000000.0,
            line="Error: connection refused",
            labels={"service": "nginx", "level": "error"},
        )
        assert entry.timestamp == 1700000000.0
        assert "Error" in entry.line
        assert entry.labels["service"] == "nginx"


class TestLogsResult:
    """Tests for LogsResult dataclass."""

    def test_create_success_result(self):
        """Test creating successful logs result."""
        result = LogsResult(
            status="success",
            entries=[
                LogEntry(timestamp=1700000000.0, line="Test log", labels={}),
            ],
        )
        assert result.status == "success"
        assert len(result.entries) == 1

    def test_create_error_result(self):
        """Test creating error logs result."""
        result = LogsResult(
            status="error",
            entries=[],
            error="Invalid query",
        )
        assert result.status == "error"


class TestGrafanaClientInit:
    """Tests for GrafanaClient initialization."""

    def test_default_init(self):
        """Test default initialization."""
        client = GrafanaClient()
        assert client.base_url == "http://192.168.79.79/grafana"
        assert client.timeout == 30
        assert client.vm_ds_id == 1
        assert client.loki_ds_id == 3
        client.close()

    def test_custom_init(self):
        """Test custom initialization."""
        client = GrafanaClient(
            base_url="http://localhost:3000/",
            username="admin",
            password="secret",
            timeout=60,
            victoriametrics_ds_id=2,
            loki_ds_id=4,
        )
        assert client.base_url == "http://localhost:3000"  # Trailing slash removed
        assert client.timeout == 60
        assert client.vm_ds_id == 2
        assert client.loki_ds_id == 4
        client.close()

    def test_auth_header_created(self):
        """Test auth header is created correctly."""
        client = GrafanaClient(username="admin", password="password")
        # Base64 of "admin:password" is "YWRtaW46cGFzc3dvcmQ="
        assert "Basic" in client._auth_header
        client.close()


class TestGrafanaClientContextManager:
    """Tests for GrafanaClient context manager."""

    def test_context_manager(self):
        """Test using client as context manager."""
        with GrafanaClient() as client:
            assert client is not None
        # After exiting, client should be closed
        assert client._client is None

    def test_close_without_client(self):
        """Test closing without initialized client."""
        client = GrafanaClient()
        # Client not yet initialized
        assert client._client is None
        client.close()  # Should not raise
        assert client._client is None


class TestGrafanaClientLazyClient:
    """Tests for lazy HTTP client initialization."""

    def test_client_property_creates_client(self):
        """Test client property creates HTTP client on first access."""
        grafana = GrafanaClient()
        assert grafana._client is None

        # Access client property
        http_client = grafana.client
        assert http_client is not None
        assert isinstance(http_client, httpx.Client)

        grafana.close()

    def test_client_reuses_existing(self):
        """Test client property reuses existing client."""
        grafana = GrafanaClient()
        client1 = grafana.client
        client2 = grafana.client
        assert client1 is client2
        grafana.close()


class TestGrafanaClientParseTime:
    """Tests for _parse_time method."""

    @pytest.fixture
    def client(self):
        """Create client fixture."""
        c = GrafanaClient()
        yield c
        c.close()

    def test_parse_float_timestamp(self, client):
        """Test parsing float timestamp."""
        ts = client._parse_time(1700000000.0)
        assert ts == 1700000000.0

    def test_parse_int_timestamp(self, client):
        """Test parsing integer timestamp."""
        ts = client._parse_time(1700000000)
        assert ts == 1700000000.0

    def test_parse_datetime(self, client):
        """Test parsing datetime object."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        ts = client._parse_time(dt)
        assert ts == dt.timestamp()

    def test_parse_now(self, client):
        """Test parsing 'now' string."""
        before = datetime.now().timestamp()
        ts = client._parse_time("now")
        after = datetime.now().timestamp()
        assert before <= ts <= after

    def test_parse_relative_seconds(self, client):
        """Test parsing relative time in seconds."""
        now = datetime.now().timestamp()
        ts = client._parse_time("-30s")
        assert abs(ts - (now - 30)) < 1

    def test_parse_relative_minutes(self, client):
        """Test parsing relative time in minutes."""
        now = datetime.now().timestamp()
        ts = client._parse_time("-5m")
        assert abs(ts - (now - 300)) < 1

    def test_parse_relative_hours(self, client):
        """Test parsing relative time in hours."""
        now = datetime.now().timestamp()
        ts = client._parse_time("-2h")
        assert abs(ts - (now - 7200)) < 1

    def test_parse_relative_days(self, client):
        """Test parsing relative time in days."""
        now = datetime.now().timestamp()
        ts = client._parse_time("-1d")
        assert abs(ts - (now - 86400)) < 1

    def test_parse_invalid_unit(self, client):
        """Test parsing invalid time unit."""
        with pytest.raises(ValueError, match="Unknown time unit"):
            client._parse_time("-5x")

    def test_parse_iso8601(self, client):
        """Test parsing ISO8601 string."""
        ts = client._parse_time("2024-01-15T10:30:00")
        expected = datetime(2024, 1, 15, 10, 30, 0).timestamp()
        assert ts == expected

    def test_parse_datetime_format(self, client):
        """Test parsing common datetime format."""
        ts = client._parse_time("2024-01-15 10:30:00")
        expected = datetime(2024, 1, 15, 10, 30, 0).timestamp()
        assert ts == expected

    def test_parse_date_format(self, client):
        """Test parsing date-only format."""
        ts = client._parse_time("2024-01-15")
        expected = datetime(2024, 1, 15, 0, 0, 0).timestamp()
        assert ts == expected

    def test_parse_invalid_string(self, client):
        """Test parsing invalid string."""
        with pytest.raises(ValueError, match="Cannot parse time"):
            client._parse_time("invalid-time-string")


class TestGrafanaClientParseStep:
    """Tests for _parse_step method."""

    @pytest.fixture
    def client(self):
        """Create client fixture."""
        c = GrafanaClient()
        yield c
        c.close()

    def test_parse_seconds(self, client):
        """Test parsing seconds step."""
        assert client._parse_step("30s") == 30
        assert client._parse_step("60S") == 60  # Case insensitive

    def test_parse_minutes(self, client):
        """Test parsing minutes step."""
        assert client._parse_step("1m") == 60
        assert client._parse_step("5M") == 300

    def test_parse_hours(self, client):
        """Test parsing hours step."""
        assert client._parse_step("1h") == 3600
        assert client._parse_step("2H") == 7200

    def test_parse_days(self, client):
        """Test parsing days step."""
        assert client._parse_step("1d") == 86400

    def test_parse_no_unit(self, client):
        """Test parsing step without unit (assumes seconds)."""
        assert client._parse_step("60") == 60


class TestGrafanaClientApiUrls:
    """Tests for API URL building methods."""

    @pytest.fixture
    def client(self):
        """Create client fixture."""
        c = GrafanaClient(
            base_url="http://grafana:3000",
            victoriametrics_ds_id=1,
            loki_ds_id=3,
        )
        yield c
        c.close()

    def test_vm_api_url(self, client):
        """Test VictoriaMetrics API URL building."""
        url = client._vm_api_url("query_range")
        assert url == "http://grafana:3000/api/datasources/proxy/1/api/v1/query_range"

    def test_loki_api_url(self, client):
        """Test Loki API URL building."""
        url = client._loki_api_url("query_range")
        assert url == "http://grafana:3000/api/datasources/proxy/3/loki/api/v1/query_range"


class TestGrafanaClientQueryMetrics:
    """Tests for query_metrics method."""

    @pytest.fixture
    def client(self):
        """Create client fixture."""
        c = GrafanaClient()
        yield c
        c.close()

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_metrics_success(self, mock_client_prop, client):
        """Test successful metrics query."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"hostname": "node1"},
                        "values": [
                            [1700000000, "123.45"],
                            [1700000060, "124.00"],
                        ],
                    }
                ],
            },
        }
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        result = client.query_metrics("up", start="-1h", end="now", step="1m")

        assert result.status == "success"
        assert result.result_type == "matrix"
        assert len(result.series) == 1
        assert result.series[0].metric["hostname"] == "node1"
        assert len(result.series[0].values) == 2

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_metrics_filters_nan(self, mock_client_prop, client):
        """Test that NaN values are filtered out."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"hostname": "node1"},
                        "values": [
                            [1700000000, "123.45"],
                            [1700000060, "NaN"],  # Should be filtered
                            [1700000120, "125.00"],
                        ],
                    }
                ],
            },
        }
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        result = client.query_metrics("up")

        assert len(result.series[0].values) == 2  # NaN filtered out

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_metrics_api_error(self, mock_client_prop, client):
        """Test handling API error response."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "error": "Invalid query syntax",
        }
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        result = client.query_metrics("invalid{query")

        assert result.status == "error"
        assert "Invalid query syntax" in result.error

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_metrics_http_error(self, mock_client_prop, client):
        """Test handling HTTP error."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=mock_response
        )
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        result = client.query_metrics("up")

        assert result.status == "error"
        assert "HTTP 500" in result.error

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_metrics_exception(self, mock_client_prop, client):
        """Test handling general exception."""
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Connection timeout")
        mock_client_prop.return_value = mock_http

        result = client.query_metrics("up")

        assert result.status == "error"
        assert "Connection timeout" in result.error


class TestGrafanaClientQueryMetricsInstant:
    """Tests for query_metrics_instant method."""

    @pytest.fixture
    def client(self):
        """Create client fixture."""
        c = GrafanaClient()
        yield c
        c.close()

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_instant_success(self, mock_client_prop, client):
        """Test successful instant query."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"hostname": "node1"},
                        "value": [1700000000, "123.45"],
                    }
                ],
            },
        }
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        result = client.query_metrics_instant("up")

        assert result.status == "success"
        assert result.result_type == "vector"
        assert len(result.series) == 1

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_instant_filters_nan(self, mock_client_prop, client):
        """Test that NaN values are filtered in instant query."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {
                        "metric": {"hostname": "node1"},
                        "value": [1700000000, "NaN"],
                    },
                    {
                        "metric": {"hostname": "node2"},
                        "value": [1700000000, "100.0"],
                    },
                ],
            },
        }
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        result = client.query_metrics_instant("up")

        assert len(result.series) == 1  # NaN filtered

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_instant_api_error(self, mock_client_prop, client):
        """Test instant query API error."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "error": "Query error",
        }
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        result = client.query_metrics_instant("invalid")

        assert result.status == "error"

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_instant_exception(self, mock_client_prop, client):
        """Test instant query exception handling."""
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Network error")
        mock_client_prop.return_value = mock_http

        result = client.query_metrics_instant("up")

        assert result.status == "error"
        assert "Network error" in result.error


class TestGrafanaClientQueryLogs:
    """Tests for query_logs method."""

    @pytest.fixture
    def client(self):
        """Create client fixture."""
        c = GrafanaClient()
        yield c
        c.close()

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_logs_success(self, mock_client_prop, client):
        """Test successful logs query."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "stream": {"service": "nginx"},
                        "values": [
                            ["1700000000000000000", "Error: connection refused"],
                            ["1700000001000000000", "Warning: high latency"],
                        ],
                    }
                ],
            },
        }
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        result = client.query_logs(
            '{service="nginx"}',
            start="-1h",
            end="now",
            limit=100,
            direction="backward",
        )

        assert result.status == "success"
        assert len(result.entries) == 2
        assert result.entries[0].labels["service"] == "nginx"

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_logs_api_error(self, mock_client_prop, client):
        """Test logs query API error."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
            "error": "Invalid LogQL query",
        }
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        result = client.query_logs("invalid")

        assert result.status == "error"
        assert "Invalid LogQL query" in result.error

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_logs_http_error(self, mock_client_prop, client):
        """Test logs query HTTP error."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=mock_response
        )
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        result = client.query_logs('{app="test"}')

        assert result.status == "error"
        assert "HTTP 503" in result.error

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_query_logs_exception(self, mock_client_prop, client):
        """Test logs query exception handling."""
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Timeout")
        mock_client_prop.return_value = mock_http

        result = client.query_logs('{app="test"}')

        assert result.status == "error"
        assert "Timeout" in result.error


class TestGrafanaClientGetLabelValues:
    """Tests for get_label_values method."""

    @pytest.fixture
    def client(self):
        """Create client fixture."""
        c = GrafanaClient()
        yield c
        c.close()

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_get_label_values_success(self, mock_client_prop, client):
        """Test successful label values query."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "data": ["node1", "node2", "node3"],
        }
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        values = client.get_label_values("hostname")

        assert values == ["node1", "node2", "node3"]

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_get_label_values_error(self, mock_client_prop, client):
        """Test label values query error."""
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "error",
        }
        mock_http.get.return_value = mock_response
        mock_client_prop.return_value = mock_http

        values = client.get_label_values("invalid")

        assert values == []

    @patch.object(GrafanaClient, "client", new_callable=PropertyMock)
    def test_get_label_values_exception(self, mock_client_prop, client):
        """Test label values query exception."""
        mock_http = MagicMock()
        mock_http.get.side_effect = Exception("Network error")
        mock_client_prop.return_value = mock_http

        values = client.get_label_values("hostname")

        assert values == []


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @patch("netsherlock.core.grafana_client.GrafanaClient")
    def test_query_metrics_function(self, mock_client_class):
        """Test query_metrics convenience function."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.query_metrics.return_value = MetricsResult(
            status="success", result_type="matrix", series=[]
        )
        mock_client_class.return_value = mock_client

        result = query_metrics("up", start="-30m", end="now", step="30s")

        assert result.status == "success"
        mock_client.query_metrics.assert_called_once_with("up", "-30m", "now", "30s")

    @patch("netsherlock.core.grafana_client.GrafanaClient")
    def test_query_logs_function(self, mock_client_class):
        """Test query_logs convenience function."""
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.query_logs.return_value = LogsResult(
            status="success", entries=[]
        )
        mock_client_class.return_value = mock_client

        result = query_logs('{app="test"}', start="-2h", end="now", limit=500)

        assert result.status == "success"
        mock_client.query_logs.assert_called_once_with('{app="test"}', "-2h", "now", 500)
