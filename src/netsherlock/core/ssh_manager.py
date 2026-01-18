"""SSH connection manager with connection pooling and retry support.

Adapted from troubleshooting-tools/test/automate-performance-test/src/core/ssh_manager.py
with enhancements for:
- Direct IP-based connections
- Retry logic with exponential backoff
- Structured logging
- Type safety
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import paramiko
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

if TYPE_CHECKING:
    from netsherlock.config.settings import SSHSettings

logger = structlog.get_logger(__name__)


@dataclass
class SSHConnectionInfo:
    """SSH connection information."""

    host: str
    user: str = "root"
    port: int = 22
    private_key_path: Path | None = None
    password: str | None = None


@dataclass
class CommandResult:
    """Result of a remote command execution."""

    stdout: str
    stderr: str
    exit_code: int
    success: bool = field(init=False)

    def __post_init__(self) -> None:
        self.success = self.exit_code == 0


class SSHConnectionError(Exception):
    """SSH connection error."""

    pass


class SSHCommandError(Exception):
    """SSH command execution error."""

    def __init__(self, message: str, result: CommandResult | None = None):
        super().__init__(message)
        self.result = result


class SSHManager:
    """SSH connection manager with connection pooling.

    Features:
    - Connection pooling with automatic reconnection
    - Retry logic with exponential backoff
    - Thread-safe operations
    - Context manager support

    Example:
        >>> settings = get_settings()
        >>> with SSHManager(settings.ssh) as ssh:
        ...     result = ssh.execute("192.168.1.10", "hostname")
        ...     print(result.stdout)
    """

    def __init__(
        self,
        settings: SSHSettings | None = None,
        *,
        default_user: str = "root",
        default_port: int = 22,
        private_key_path: Path | None = None,
        password: str | None = None,
        connect_timeout: int = 10,
        command_timeout: int = 60,
        max_connections: int = 10,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        keepalive_interval: int = 30,
    ):
        """Initialize SSH manager.

        Args:
            settings: SSH settings (if provided, overrides other args)
            default_user: Default SSH username
            default_port: Default SSH port
            private_key_path: Path to SSH private key
            password: SSH password
            connect_timeout: Connection timeout in seconds
            command_timeout: Command execution timeout in seconds
            max_connections: Maximum concurrent connections
            retry_attempts: Number of retry attempts
            retry_delay: Base delay between retries in seconds
            keepalive_interval: SSH keepalive interval in seconds
        """
        if settings:
            self.default_user = settings.default_user
            self.default_port = settings.default_port
            self.private_key_path = settings.private_key_path
            self.password = (
                settings.password.get_secret_value() if settings.password else None
            )
            self.connect_timeout = settings.connect_timeout
            self.command_timeout = settings.command_timeout
            self.max_connections = settings.max_connections
            self.retry_attempts = settings.retry_attempts
            self.retry_delay = settings.retry_delay
        else:
            self.default_user = default_user
            self.default_port = default_port
            self.private_key_path = private_key_path
            self.password = password
            self.connect_timeout = connect_timeout
            self.command_timeout = command_timeout
            self.max_connections = max_connections
            self.retry_attempts = retry_attempts
            self.retry_delay = retry_delay

        self.keepalive_interval = keepalive_interval

        # Connection pool: host -> SSHClient
        self._connections: dict[str, paramiko.SSHClient] = {}
        self._lock = threading.Lock()

    def _get_connection_key(
        self, host: str, user: str | None = None, port: int | None = None
    ) -> str:
        """Generate unique key for connection pool."""
        user = user or self.default_user
        port = port or self.default_port
        return f"{user}@{host}:{port}"

    def _is_connection_alive(self, client: paramiko.SSHClient) -> bool:
        """Check if SSH connection is still alive."""
        try:
            transport = client.get_transport()
            if transport is None or not transport.is_active():
                return False
            transport.send_ignore()
            return True
        except Exception:
            return False

    def _create_retry_decorator(self):
        """Create retry decorator with current settings."""
        return retry(
            retry=retry_if_exception_type((paramiko.SSHException, OSError)),
            stop=stop_after_attempt(self.retry_attempts),
            wait=wait_exponential(multiplier=self.retry_delay, min=1, max=10),
            reraise=True,
        )

    def connect(
        self,
        host: str,
        user: str | None = None,
        port: int | None = None,
        private_key_path: Path | None = None,
        password: str | None = None,
    ) -> paramiko.SSHClient:
        """Establish SSH connection with connection pooling.

        Args:
            host: Target hostname or IP address
            user: SSH username (defaults to settings)
            port: SSH port (defaults to settings)
            private_key_path: Path to private key (defaults to settings)
            password: SSH password (defaults to settings)

        Returns:
            SSH client instance

        Raises:
            SSHConnectionError: If connection fails after retries
        """
        user = user or self.default_user
        port = port or self.default_port
        private_key_path = private_key_path or self.private_key_path
        password = password or self.password

        conn_key = self._get_connection_key(host, user, port)

        with self._lock:
            # Check existing connection
            if conn_key in self._connections:
                client = self._connections[conn_key]
                if self._is_connection_alive(client):
                    logger.debug("reusing_connection", host=host, user=user)
                    return client
                else:
                    logger.warning("stale_connection", host=host, user=user)
                    try:
                        client.close()
                    except Exception:
                        pass
                    del self._connections[conn_key]

            # Check connection limit
            if len(self._connections) >= self.max_connections:
                raise SSHConnectionError(
                    f"Max connections ({self.max_connections}) reached"
                )

        # Create new connection (outside lock for better concurrency)
        @self._create_retry_decorator()
        def _connect() -> paramiko.SSHClient:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs: dict = {
                "hostname": host,
                "port": port,
                "username": user,
                "timeout": self.connect_timeout,
            }

            if private_key_path and private_key_path.exists():
                connect_kwargs["key_filename"] = str(private_key_path)
            elif password:
                connect_kwargs["password"] = password

            client.connect(**connect_kwargs)

            # Enable keepalive
            transport = client.get_transport()
            if transport:
                transport.set_keepalive(self.keepalive_interval)

            return client

        try:
            client = _connect()
            logger.info("connected", host=host, user=user, port=port)

            with self._lock:
                self._connections[conn_key] = client

            return client

        except Exception as e:
            logger.error("connection_failed", host=host, user=user, error=str(e))
            raise SSHConnectionError(f"Failed to connect to {host}: {e}") from e

    def execute(
        self,
        host: str,
        command: str,
        *,
        user: str | None = None,
        port: int | None = None,
        timeout: int | None = None,
        check: bool = False,
    ) -> CommandResult:
        """Execute command on remote host.

        Args:
            host: Target hostname or IP address
            command: Command to execute
            user: SSH username
            port: SSH port
            timeout: Command timeout (defaults to settings)
            check: Raise exception on non-zero exit code

        Returns:
            CommandResult with stdout, stderr, and exit code

        Raises:
            SSHCommandError: If check=True and command fails
        """
        timeout = timeout or self.command_timeout
        client = self.connect(host, user, port)

        log = logger.bind(host=host, command=command[:50])

        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            exit_code = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode("utf-8", errors="replace")
            stderr_data = stderr.read().decode("utf-8", errors="replace")

            result = CommandResult(
                stdout=stdout_data,
                stderr=stderr_data,
                exit_code=exit_code,
            )

            if result.success:
                log.debug("command_success", exit_code=exit_code)
            else:
                log.warning("command_failed", exit_code=exit_code, stderr=stderr_data[:200])

            if check and not result.success:
                raise SSHCommandError(
                    f"Command failed with exit code {exit_code}: {stderr_data[:200]}",
                    result=result,
                )

            return result

        except paramiko.SSHException as e:
            log.error("command_error", error=str(e))
            raise SSHCommandError(f"SSH error executing command: {e}") from e

    def execute_background(
        self,
        host: str,
        command: str,
        *,
        user: str | None = None,
        port: int | None = None,
    ) -> str:
        """Execute command in background on remote host.

        Args:
            host: Target hostname or IP address
            command: Command to execute
            user: SSH username
            port: SSH port

        Returns:
            Process ID (PID) of background process
        """
        bg_command = f"nohup {command} > /dev/null 2>&1 & echo $!"
        result = self.execute(host, bg_command, user=user, port=port)
        return result.stdout.strip()

    def copy_to_remote(
        self,
        host: str,
        local_path: Path | str,
        remote_path: Path | str,
        *,
        user: str | None = None,
        port: int | None = None,
    ) -> bool:
        """Copy file to remote host via SFTP.

        Args:
            host: Target hostname or IP address
            local_path: Local file path
            remote_path: Remote destination path
            user: SSH username
            port: SSH port

        Returns:
            True if successful
        """
        client = self.connect(host, user, port)
        local_path = Path(local_path)
        remote_path = str(remote_path)

        try:
            sftp = client.open_sftp()
            sftp.put(str(local_path), remote_path)
            sftp.close()
            logger.info(
                "file_copied_to_remote",
                host=host,
                local=str(local_path),
                remote=remote_path,
            )
            return True
        except Exception as e:
            logger.error("file_copy_failed", host=host, error=str(e))
            return False

    def copy_from_remote(
        self,
        host: str,
        remote_path: Path | str,
        local_path: Path | str,
        *,
        user: str | None = None,
        port: int | None = None,
    ) -> bool:
        """Copy file from remote host via SFTP.

        Args:
            host: Target hostname or IP address
            remote_path: Remote file path
            local_path: Local destination path
            user: SSH username
            port: SSH port

        Returns:
            True if successful
        """
        client = self.connect(host, user, port)
        remote_path = str(remote_path)
        local_path = Path(local_path)

        try:
            sftp = client.open_sftp()
            sftp.get(remote_path, str(local_path))
            sftp.close()
            logger.info(
                "file_copied_from_remote",
                host=host,
                remote=remote_path,
                local=str(local_path),
            )
            return True
        except Exception as e:
            logger.error("file_copy_failed", host=host, error=str(e))
            return False

    def check_process(self, host: str, pid: str | int) -> bool:
        """Check if process exists on remote host.

        Args:
            host: Target hostname or IP address
            pid: Process ID

        Returns:
            True if process exists
        """
        result = self.execute(host, f"ps -p {pid} >/dev/null 2>&1")
        return result.success

    def kill_process(
        self, host: str, pid: str | int, signal: str = "TERM"
    ) -> bool:
        """Kill process on remote host.

        Args:
            host: Target hostname or IP address
            pid: Process ID
            signal: Signal to send (default: TERM)

        Returns:
            True if kill command succeeded
        """
        result = self.execute(host, f"kill -{signal} {pid}")
        return result.success

    def close(self, host: str | None = None) -> None:
        """Close SSH connection(s).

        Args:
            host: Specific host to close (None = close all)
        """
        with self._lock:
            if host:
                # Close specific connection
                keys_to_remove = [k for k in self._connections if host in k]
                for key in keys_to_remove:
                    try:
                        self._connections[key].close()
                        logger.debug("connection_closed", key=key)
                    except Exception:
                        pass
                    del self._connections[key]
            else:
                # Close all connections
                for key, client in self._connections.items():
                    try:
                        client.close()
                        logger.debug("connection_closed", key=key)
                    except Exception:
                        pass
                self._connections.clear()
                logger.info("all_connections_closed")

    def __enter__(self) -> SSHManager:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# Convenience function for simple one-off commands
def ssh_execute(
    host: str,
    command: str,
    *,
    user: str = "root",
    timeout: int = 60,
) -> CommandResult:
    """Execute a single SSH command (convenience function).

    Creates a temporary SSH connection, executes command, and closes.
    For multiple commands to the same host, use SSHManager instead.

    Args:
        host: Target hostname or IP address
        command: Command to execute
        user: SSH username
        timeout: Command timeout in seconds

    Returns:
        CommandResult with stdout, stderr, and exit code
    """
    with SSHManager(default_user=user, command_timeout=timeout) as ssh:
        return ssh.execute(host, command)
