"""Tests for L1 monitoring tools.

Tests for grafana_query_metrics, loki_query_logs, read_node_logs,
and convenience functions.
"""

import pytest
from unittest.mock import MagicMock, patch

from netsherlock.tools.l1_monitoring import (
    NodeLogsResult,
    NETWORK_QUERIES,
    NODE_LOG_FILES,
    grafana_query_metrics,
    loki_query_logs,
    read_node_logs,
    query_host_latency,
    query_host_loss_rate,
    query_tcp_retransmissions,
)
from netsherlock.core.grafana_client import (
    MetricsResult,
    MetricSeries,
    MetricSample,
    LogsResult,
    LogEntry,
)


class TestNodeLogsResult:
    """Tests for NodeLogsResult dataclass."""

    def test_create_successful_result(self):
        """Test creating a successful NodeLogsResult."""
        result = NodeLogsResult(
            success=True,
            host="192.168.75.101",
            log_type="pingmesh",
            content="line1\nline2\nline3",
            lines_returned=3,
        )

        assert result.success is True
        assert result.host == "192.168.75.101"
        assert result.log_type == "pingmesh"
        assert result.lines_returned == 3
        assert result.error is None

    def test_create_failed_result(self):
        """Test creating a failed NodeLogsResult."""
        result = NodeLogsResult(
            success=False,
            host="192.168.75.101",
            log_type="l2ping",
            content="",
            lines_returned=0,
            error="Connection refused",
        )

        assert result.success is False
        assert result.error == "Connection refused"


class TestNetworkQueries:
    """Tests for NETWORK_QUERIES constant."""

    def test_host_ping_latency_query(self):
        """Test host ping latency query template."""
        query = NETWORK_QUERIES["host_ping_latency"].format(hostname="node1")
        assert 'host_network_ping_time_ns{hostname="node1"}' == query

    def test_host_loss_rate_query(self):
        """Test host loss rate query template."""
        query = NETWORK_QUERIES["host_loss_rate"].format(hostname="node2")
        assert 'host_network_loss_rate{hostname="node2"}' == query

    def test_vm_network_speed_query(self):
        """Test VM network speed query template."""
        query = NETWORK_QUERIES["vm_network_speed"].format(
            hostname="node1", direction="rx", vm_id="vm-123"
        )
        assert "elf_vm_network_rx_speed_bitps" in query
        assert 'hostname="node1"' in query
        assert 'vm="vm-123"' in query

    def test_interface_errors_query(self):
        """Test interface errors query template."""
        query = NETWORK_QUERIES["interface_errors"].format(
            hostname="node1", interface="eth0"
        )
        assert 'node_network_transmit_errs_total' in query
        assert 'device="eth0"' in query

    def test_tcp_retrans_query(self):
        """Test TCP retransmission query template."""
        query = NETWORK_QUERIES["tcp_retrans"].format(hostname="node3")
        assert 'node_netstat_Tcp_RetransSegs{hostname="node3"}' == query


class TestNodeLogFiles:
    """Tests for NODE_LOG_FILES constant."""

    def test_pingmesh_log_file(self):
        """Test pingmesh log file mapping."""
        assert NODE_LOG_FILES["pingmesh"] == "pingmesh"

    def test_l2ping_log_file(self):
        """Test l2ping log file mapping."""
        assert NODE_LOG_FILES["l2ping"] == "l2ping"

    def test_network_high_latency_log_file(self):
        """Test network-high-latency log file mapping."""
        assert NODE_LOG_FILES["network-high-latency"] == "network-high-latency"


class TestGrafanaQueryMetrics:
    """Tests for grafana_query_metrics function."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.grafana.base_url = "http://grafana:3000"
        settings.grafana.username = "admin"
        settings.grafana.password.get_secret_value.return_value = "password"
        settings.grafana.timeout = 30
        settings.grafana.victoriametrics_ds_id = 1
        settings.grafana.loki_ds_id = 3
        return settings

    @pytest.fixture
    def mock_metrics_result(self):
        """Create mock MetricsResult."""
        return MetricsResult(
            status="success",
            result_type="matrix",
            series=[
                MetricSeries(
                    metric={"hostname": "node1"},
                    values=[
                        MetricSample(timestamp=1700000000, value=1234.5),
                        MetricSample(timestamp=1700000060, value=1235.0),
                    ],
                )
            ],
        )

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.GrafanaClient")
    def test_query_metrics_success(
        self, mock_client_class, mock_get_settings, mock_settings, mock_metrics_result
    ):
        """Test successful metrics query."""
        mock_get_settings.return_value = mock_settings
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.query_metrics.return_value = mock_metrics_result
        mock_client_class.return_value = mock_client

        result = grafana_query_metrics(
            'host_network_ping_time_ns{hostname="node1"}',
            start="-30m",
            end="now",
            step="1m",
        )

        assert result.status == "success"
        assert len(result.series) == 1
        mock_client.query_metrics.assert_called_once()

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.GrafanaClient")
    def test_query_metrics_with_default_params(
        self, mock_client_class, mock_get_settings, mock_settings, mock_metrics_result
    ):
        """Test metrics query with default parameters."""
        mock_get_settings.return_value = mock_settings
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.query_metrics.return_value = mock_metrics_result
        mock_client_class.return_value = mock_client

        result = grafana_query_metrics('up{job="test"}')

        assert result.status == "success"
        mock_client.query_metrics.assert_called_once_with(
            'up{job="test"}', "-1h", "now", "1m"
        )

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.GrafanaClient")
    def test_query_metrics_error(self, mock_client_class, mock_get_settings, mock_settings):
        """Test metrics query error handling."""
        mock_get_settings.return_value = mock_settings
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.query_metrics.return_value = MetricsResult(
            status="error",
            result_type="",
            series=[],
            error="Query syntax error",
        )
        mock_client_class.return_value = mock_client

        result = grafana_query_metrics("invalid{query")

        assert result.status == "error"
        assert result.error == "Query syntax error"


class TestLokiQueryLogs:
    """Tests for loki_query_logs function."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.grafana.base_url = "http://grafana:3000"
        settings.grafana.username = "admin"
        settings.grafana.password.get_secret_value.return_value = "password"
        settings.grafana.timeout = 30
        settings.grafana.victoriametrics_ds_id = 1
        settings.grafana.loki_ds_id = 3
        return settings

    @pytest.fixture
    def mock_logs_result(self):
        """Create mock LogsResult."""
        return LogsResult(
            status="success",
            entries=[
                LogEntry(
                    timestamp=1700000000.0,
                    line="Error: connection refused",
                    labels={"service": "nginx"},
                ),
                LogEntry(
                    timestamp=1700000001.0,
                    line="Warning: high latency",
                    labels={"service": "nginx"},
                ),
            ],
        )

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.GrafanaClient")
    def test_query_logs_success(
        self, mock_client_class, mock_get_settings, mock_settings, mock_logs_result
    ):
        """Test successful logs query."""
        mock_get_settings.return_value = mock_settings
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.query_logs.return_value = mock_logs_result
        mock_client_class.return_value = mock_client

        result = loki_query_logs(
            '{service="nginx"} |= "error"',
            start="-1h",
            end="now",
            limit=100,
            direction="backward",
        )

        assert result.status == "success"
        assert len(result.entries) == 2
        mock_client.query_logs.assert_called_once()

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.GrafanaClient")
    def test_query_logs_with_default_params(
        self, mock_client_class, mock_get_settings, mock_settings, mock_logs_result
    ):
        """Test logs query with default parameters."""
        mock_get_settings.return_value = mock_settings
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.query_logs.return_value = mock_logs_result
        mock_client_class.return_value = mock_client

        result = loki_query_logs('{namespace="kube-system"}')

        assert result.status == "success"
        mock_client.query_logs.assert_called_once_with(
            '{namespace="kube-system"}', "-1h", "now", 1000, "backward"
        )

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.GrafanaClient")
    def test_query_logs_forward_direction(
        self, mock_client_class, mock_get_settings, mock_settings, mock_logs_result
    ):
        """Test logs query with forward direction."""
        mock_get_settings.return_value = mock_settings
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.query_logs.return_value = mock_logs_result
        mock_client_class.return_value = mock_client

        result = loki_query_logs('{app="test"}', direction="forward")

        assert result.status == "success"
        mock_client.query_logs.assert_called_once()
        call_args = mock_client.query_logs.call_args
        assert call_args[0][4] == "forward"

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.GrafanaClient")
    def test_query_logs_error(self, mock_client_class, mock_get_settings, mock_settings):
        """Test logs query error handling."""
        mock_get_settings.return_value = mock_settings
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.__exit__.return_value = None
        mock_client.query_logs.return_value = LogsResult(
            status="error",
            entries=[],
            error="Invalid LogQL query",
        )
        mock_client_class.return_value = mock_client

        result = loki_query_logs("invalid query")

        assert result.status == "error"
        assert result.error == "Invalid LogQL query"


class TestReadNodeLogs:
    """Tests for read_node_logs function."""

    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = MagicMock()
        settings.node_log_base_path = "/var/log/zbs"
        settings.ssh = MagicMock()
        return settings

    @pytest.fixture
    def mock_ssh_result_success(self):
        """Create successful SSH result."""
        result = MagicMock()
        result.success = True
        result.stdout = "line1\nline2\nline3"
        result.stderr = ""
        result.exit_code = 0
        return result

    @pytest.fixture
    def mock_ssh_result_failure(self):
        """Create failed SSH result."""
        result = MagicMock()
        result.success = False
        result.stdout = ""
        result.stderr = "No such file or directory"
        result.exit_code = 1
        return result

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.SSHManager")
    def test_read_pingmesh_logs_success(
        self, mock_ssh_class, mock_get_settings, mock_settings, mock_ssh_result_success
    ):
        """Test successful pingmesh log reading."""
        mock_get_settings.return_value = mock_settings
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = None
        mock_ssh.execute.return_value = mock_ssh_result_success
        mock_ssh_class.return_value = mock_ssh

        result = read_node_logs(
            host="192.168.75.101",
            log_type="pingmesh",
            lines=100,
        )

        assert result.success is True
        assert result.host == "192.168.75.101"
        assert result.log_type == "pingmesh"
        assert result.lines_returned == 3
        assert "line1" in result.content

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.SSHManager")
    def test_read_l2ping_logs_success(
        self, mock_ssh_class, mock_get_settings, mock_settings, mock_ssh_result_success
    ):
        """Test successful l2ping log reading."""
        mock_get_settings.return_value = mock_settings
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = None
        mock_ssh.execute.return_value = mock_ssh_result_success
        mock_ssh_class.return_value = mock_ssh

        result = read_node_logs(
            host="192.168.75.102",
            log_type="l2ping",
            lines=50,
        )

        assert result.success is True
        assert result.log_type == "l2ping"

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.SSHManager")
    def test_read_network_high_latency_logs(
        self, mock_ssh_class, mock_get_settings, mock_settings, mock_ssh_result_success
    ):
        """Test reading network-high-latency logs."""
        mock_get_settings.return_value = mock_settings
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = None
        mock_ssh.execute.return_value = mock_ssh_result_success
        mock_ssh_class.return_value = mock_ssh

        result = read_node_logs(
            host="192.168.75.103",
            log_type="network-high-latency",
            lines=200,
        )

        assert result.success is True
        assert result.log_type == "network-high-latency"

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.SSHManager")
    def test_read_logs_with_grep_pattern(
        self, mock_ssh_class, mock_get_settings, mock_settings, mock_ssh_result_success
    ):
        """Test reading logs with grep pattern."""
        mock_get_settings.return_value = mock_settings
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = None
        mock_ssh.execute.return_value = mock_ssh_result_success
        mock_ssh_class.return_value = mock_ssh

        result = read_node_logs(
            host="192.168.75.101",
            log_type="pingmesh",
            lines=100,
            grep_pattern="ERROR",
        )

        assert result.success is True
        # Verify grep command was used
        call_args = mock_ssh.execute.call_args
        assert "grep" in call_args[0][1]
        assert "ERROR" in call_args[0][1]

    def test_read_logs_invalid_log_type(self):
        """Test reading logs with invalid log type."""
        result = read_node_logs(
            host="192.168.75.101",
            log_type="invalid-type",  # type: ignore
            lines=100,
        )

        assert result.success is False
        assert "Unknown log type" in result.error
        assert "invalid-type" in result.error

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.SSHManager")
    def test_read_logs_ssh_failure(
        self, mock_ssh_class, mock_get_settings, mock_settings, mock_ssh_result_failure
    ):
        """Test handling SSH failure."""
        mock_get_settings.return_value = mock_settings
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = None
        mock_ssh.execute.return_value = mock_ssh_result_failure
        mock_ssh_class.return_value = mock_ssh

        result = read_node_logs(
            host="192.168.75.101",
            log_type="pingmesh",
            lines=100,
        )

        assert result.success is False
        assert "No such file" in result.error

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.SSHManager")
    def test_read_logs_ssh_exception(
        self, mock_ssh_class, mock_get_settings, mock_settings
    ):
        """Test handling SSH exception."""
        mock_get_settings.return_value = mock_settings
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = None
        mock_ssh.execute.side_effect = Exception("Connection timeout")
        mock_ssh_class.return_value = mock_ssh

        result = read_node_logs(
            host="192.168.75.101",
            log_type="pingmesh",
            lines=100,
        )

        assert result.success is False
        assert "Connection timeout" in result.error

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.SSHManager")
    def test_read_logs_empty_content(
        self, mock_ssh_class, mock_get_settings, mock_settings
    ):
        """Test reading logs with empty content."""
        mock_get_settings.return_value = mock_settings
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = None
        empty_result = MagicMock()
        empty_result.success = True
        empty_result.stdout = ""
        empty_result.stderr = ""
        empty_result.exit_code = 0
        mock_ssh.execute.return_value = empty_result
        mock_ssh_class.return_value = mock_ssh

        result = read_node_logs(
            host="192.168.75.101",
            log_type="pingmesh",
            lines=100,
        )

        assert result.success is True
        assert result.lines_returned == 0
        assert result.content == ""

    @patch("netsherlock.tools.l1_monitoring.get_settings")
    @patch("netsherlock.tools.l1_monitoring.SSHManager")
    def test_read_logs_ssh_failure_no_stderr(
        self, mock_ssh_class, mock_get_settings, mock_settings
    ):
        """Test SSH failure with no stderr but non-zero exit code."""
        mock_get_settings.return_value = mock_settings
        mock_ssh = MagicMock()
        mock_ssh.__enter__.return_value = mock_ssh
        mock_ssh.__exit__.return_value = None
        failure_result = MagicMock()
        failure_result.success = False
        failure_result.stdout = ""
        failure_result.stderr = ""  # Empty stderr
        failure_result.exit_code = 127
        mock_ssh.execute.return_value = failure_result
        mock_ssh_class.return_value = mock_ssh

        result = read_node_logs(
            host="192.168.75.101",
            log_type="pingmesh",
            lines=100,
        )

        assert result.success is False
        assert "Command exited with code 127" in result.error


class TestQueryHostLatency:
    """Tests for query_host_latency convenience function."""

    @patch("netsherlock.tools.l1_monitoring.grafana_query_metrics")
    def test_query_host_latency(self, mock_query):
        """Test query_host_latency function."""
        mock_query.return_value = MetricsResult(
            status="success",
            result_type="matrix",
            series=[],
        )

        result = query_host_latency("node1", start="-30m", end="now")

        assert result.status == "success"
        mock_query.assert_called_once()
        call_args = mock_query.call_args
        assert 'host_network_ping_time_ns{hostname="node1"}' in call_args[0][0]
        assert call_args[0][1] == "-30m"
        assert call_args[0][2] == "now"

    @patch("netsherlock.tools.l1_monitoring.grafana_query_metrics")
    def test_query_host_latency_default_params(self, mock_query):
        """Test query_host_latency with default parameters."""
        mock_query.return_value = MetricsResult(
            status="success",
            result_type="matrix",
            series=[],
        )

        result = query_host_latency("node2")

        mock_query.assert_called_once()
        call_args = mock_query.call_args
        assert call_args[0][1] == "-1h"  # Default start
        assert call_args[0][2] == "now"  # Default end


class TestQueryHostLossRate:
    """Tests for query_host_loss_rate convenience function."""

    @patch("netsherlock.tools.l1_monitoring.grafana_query_metrics")
    def test_query_host_loss_rate(self, mock_query):
        """Test query_host_loss_rate function."""
        mock_query.return_value = MetricsResult(
            status="success",
            result_type="matrix",
            series=[],
        )

        result = query_host_loss_rate("node1", start="-2h", end="now")

        assert result.status == "success"
        mock_query.assert_called_once()
        call_args = mock_query.call_args
        assert 'host_network_loss_rate{hostname="node1"}' in call_args[0][0]

    @patch("netsherlock.tools.l1_monitoring.grafana_query_metrics")
    def test_query_host_loss_rate_default_params(self, mock_query):
        """Test query_host_loss_rate with default parameters."""
        mock_query.return_value = MetricsResult(
            status="success",
            result_type="matrix",
            series=[],
        )

        result = query_host_loss_rate("node3")

        mock_query.assert_called_once()


class TestQueryTcpRetransmissions:
    """Tests for query_tcp_retransmissions convenience function."""

    @patch("netsherlock.tools.l1_monitoring.grafana_query_metrics")
    def test_query_tcp_retransmissions(self, mock_query):
        """Test query_tcp_retransmissions function."""
        mock_query.return_value = MetricsResult(
            status="success",
            result_type="matrix",
            series=[],
        )

        result = query_tcp_retransmissions("node1", start="-1h", end="now")

        assert result.status == "success"
        mock_query.assert_called_once()
        call_args = mock_query.call_args
        assert 'node_netstat_Tcp_RetransSegs{hostname="node1"}' in call_args[0][0]

    @patch("netsherlock.tools.l1_monitoring.grafana_query_metrics")
    def test_query_tcp_retransmissions_default_params(self, mock_query):
        """Test query_tcp_retransmissions with default parameters."""
        mock_query.return_value = MetricsResult(
            status="success",
            result_type="matrix",
            series=[],
        )

        result = query_tcp_retransmissions("node2")

        mock_query.assert_called_once()
        call_args = mock_query.call_args
        assert call_args[0][1] == "-1h"
        assert call_args[0][2] == "now"
