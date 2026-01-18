"""BPF remote executor with proper signal handling.

Specialized for BPF/BCC programs that need graceful shutdown handling
to capture final summary statistics output.

Adapted from troubleshooting-tools/test/tools/bpf_remote_executor.py
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import structlog

from netsherlock.config.settings import get_settings
from netsherlock.core.ssh_manager import SSHManager

logger = structlog.get_logger(__name__)


@dataclass
class BPFExecutionResult:
    """Result of BPF program execution."""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_actual: float = 0.0
    error: str | None = None


class BPFExecutor:
    """Execute BPF programs on remote hosts with proper signal handling.

    Features:
    - Uses expect scripts for proper Ctrl+C handling
    - Supports SCP deployment of tools
    - Captures final summary output from BPF programs
    - Automatic cleanup of processes and temp files

    Example:
        >>> executor = BPFExecutor(ssh_manager, host="192.168.1.10")
        >>> result = executor.execute(
        ...     command="python3 latency_measure.py -i eth0",
        ...     duration=30,
        ...     workspace="/tmp/bpf-tools"
        ... )
        >>> if result.success:
        ...     print(result.stdout)
    """

    def __init__(
        self,
        ssh: SSHManager,
        host: str,
        *,
        remote_tools_path: Path | str = "/tmp/netsherlock-tools",
        remote_python: str = "/usr/bin/python3",
    ):
        """Initialize BPF executor.

        Args:
            ssh: SSH manager instance
            host: Target host IP address
            remote_tools_path: Remote directory for deployed tools
            remote_python: Python interpreter path on remote host
        """
        self.ssh = ssh
        self.host = host
        self.remote_tools_path = Path(remote_tools_path)
        self.remote_python = remote_python

    def deploy_tool(self, local_path: Path | str, make_executable: bool = True) -> bool:
        """Deploy a tool to the remote host.

        Args:
            local_path: Local path to the tool
            make_executable: Whether to make the tool executable

        Returns:
            True if deployment succeeded
        """
        local_path = Path(local_path)
        if not local_path.exists():
            logger.error("tool_not_found", path=str(local_path))
            return False

        # Ensure remote directory exists
        self.ssh.execute(self.host, f"mkdir -p {self.remote_tools_path}")

        # Copy file
        remote_path = self.remote_tools_path / local_path.name
        success = self.ssh.copy_to_remote(self.host, local_path, remote_path)

        if success and make_executable:
            self.ssh.execute(self.host, f"chmod +x {remote_path}")

        logger.info(
            "tool_deployed",
            host=self.host,
            tool=local_path.name,
            remote_path=str(remote_path),
        )
        return success

    def check_tool_exists(self, tool_name: str) -> bool:
        """Check if a tool exists on the remote host.

        Args:
            tool_name: Name of the tool file

        Returns:
            True if tool exists
        """
        remote_path = self.remote_tools_path / tool_name
        result = self.ssh.execute(self.host, f"test -f {remote_path}")
        return result.success

    def execute(
        self,
        command: str,
        duration: int = 30,
        *,
        workspace: Path | str | None = None,
        use_sudo: bool = True,
        process_pattern: str | None = None,
        local_script: Path | str | None = None,
    ) -> BPFExecutionResult:
        """Execute BPF program with proper Ctrl+C handling.

        Uses expect script to send proper SIGINT for graceful shutdown,
        which is necessary to capture summary statistics from BCC/bpftrace programs.

        Args:
            command: Command to execute (relative to workspace)
            duration: Execution duration in seconds
            workspace: Working directory (defaults to remote_tools_path)
            use_sudo: Whether to use sudo
            process_pattern: Pattern for cleanup if execution is interrupted
            local_script: Local script to deploy before execution

        Returns:
            BPFExecutionResult with captured output
        """
        workspace = workspace or self.remote_tools_path
        workspace = Path(workspace)

        log = logger.bind(host=self.host, command=command[:50], duration=duration)
        log.info("bpf_execution_starting")

        start_time = time.time()

        # Deploy script if provided
        if local_script:
            if not self.deploy_tool(local_script):
                return BPFExecutionResult(
                    success=False,
                    stdout="",
                    stderr="",
                    exit_code=-1,
                    error=f"Failed to deploy script: {local_script}",
                )

        # Cleanup existing processes if pattern provided
        if process_pattern:
            self._cleanup_processes(process_pattern)

        # Generate unique output file
        output_file = f"/tmp/bpf_output_{int(time.time())}_{random.randint(1000, 9999)}.txt"
        expect_file = f"/tmp/bpf_expect_{int(time.time())}.exp"

        try:
            # Build the full command
            if use_sudo:
                full_command = f"cd {workspace} && sudo {command}"
            else:
                full_command = f"cd {workspace} && {command}"

            # Create expect script for proper signal handling
            expect_script = self._create_expect_script(
                full_command, output_file, duration
            )

            # Write expect script to remote
            result = self.ssh.execute(
                self.host,
                f"cat > {expect_file} << 'EXPECT_EOF'\n{expect_script}\nEXPECT_EOF",
            )
            if not result.success:
                return BPFExecutionResult(
                    success=False,
                    stdout="",
                    stderr=result.stderr,
                    exit_code=-1,
                    error="Failed to create expect script",
                )

            # Make expect script executable
            self.ssh.execute(self.host, f"chmod +x {expect_file}")

            log.debug("expect_script_created")

            # Execute the expect script
            exec_result = self.ssh.execute(
                self.host,
                expect_file,
                timeout=duration + 30,  # Extra time for cleanup
            )

            log.debug("expect_execution_completed", exit_code=exec_result.exit_code)

            # Retrieve output from log file
            log_result = self.ssh.execute(self.host, f"cat {output_file}")
            output_content = log_result.stdout if log_result.success else ""

            # Cleanup temp files
            self._cleanup_temp_files([output_file, expect_file])

            duration_actual = time.time() - start_time

            if output_content.strip():
                log.info(
                    "bpf_execution_completed",
                    duration=duration_actual,
                    output_lines=len(output_content.splitlines()),
                )
            else:
                log.warning("bpf_execution_no_output", duration=duration_actual)

            return BPFExecutionResult(
                success=True,
                stdout=output_content,
                stderr=exec_result.stderr,
                exit_code=exec_result.exit_code,
                duration_actual=duration_actual,
            )

        except Exception as e:
            log.error("bpf_execution_error", error=str(e))

            # Cleanup on error
            if process_pattern:
                self._cleanup_processes(process_pattern, force=True)
            self._cleanup_temp_files([output_file, expect_file])

            return BPFExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                duration_actual=time.time() - start_time,
                error=str(e),
            )

    def _create_expect_script(
        self, command: str, output_file: str, duration: int
    ) -> str:
        """Create expect script for proper Ctrl+C handling.

        The expect script:
        1. Spawns the command
        2. Waits for specified duration
        3. Sends Ctrl+C (SIGINT) for graceful shutdown
        4. Captures all output to log file
        """
        # Escape special characters for expect
        escaped_command = (
            command.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("$", "\\$")
        )

        return f'''#!/usr/bin/expect -f
set timeout {duration + 10}
log_file {output_file}
spawn bash -c "{escaped_command}"

# Timer to send Ctrl+C after duration
after [expr {duration} * 1000] {{
    send "\\003"
    expect {{
        eof {{ exit 0 }}
        timeout {{
            send "\\003"
            expect eof {{ exit 0 }}
        }}
    }}
}}

# Wait for output and handle termination
expect {{
    eof {{
        exit 0
    }}
    timeout {{
        send "\\003"
        expect {{
            eof {{ exit 0 }}
            timeout {{
                send "\\003"
                send "\\003"
                exit 1
            }}
        }}
    }}
}}
'''

    def _cleanup_processes(self, pattern: str, force: bool = False) -> None:
        """Cleanup processes matching pattern."""
        signal = "KILL" if force else "TERM"
        self.ssh.execute(
            self.host,
            f"sudo pkill -{signal} -f '{pattern}' 2>/dev/null || true",
        )
        logger.debug("processes_cleaned", pattern=pattern, signal=signal)

    def _cleanup_temp_files(self, files: list[str]) -> None:
        """Cleanup temporary files on remote host."""
        files_str = " ".join(files)
        self.ssh.execute(self.host, f"rm -f {files_str} 2>/dev/null || true")


class CoordinatedMeasurement:
    """Coordinate measurement between sender and receiver hosts.

    Implements the receiver-first timing constraint: the receiver-side
    tool must be started before the sender-side tool.

    Example:
        >>> coord = CoordinatedMeasurement(ssh)
        >>> result = coord.execute(
        ...     receiver_host="192.168.1.10",
        ...     sender_host="192.168.1.20",
        ...     receiver_command="python3 rx_latency.py",
        ...     sender_command="python3 tx_generator.py",
        ...     duration=30
        ... )
    """

    def __init__(
        self,
        ssh: SSHManager,
        *,
        receiver_ready_timeout: int = 10,
        receiver_startup_delay: float = 1.0,
    ):
        """Initialize coordinated measurement.

        Args:
            ssh: SSH manager instance
            receiver_ready_timeout: Timeout waiting for receiver ready (seconds)
            receiver_startup_delay: Minimum delay before starting sender (seconds)
        """
        self.ssh = ssh
        self.receiver_ready_timeout = receiver_ready_timeout
        self.receiver_startup_delay = receiver_startup_delay

    def execute(
        self,
        receiver_host: str,
        sender_host: str,
        receiver_command: str,
        sender_command: str,
        duration: int = 30,
        *,
        receiver_workspace: str | None = None,
        sender_workspace: str | None = None,
        deploy_mode: Literal["auto", "scp", "pre-deployed"] = "auto",
        local_tools_path: Path | str | None = None,
    ) -> tuple[BPFExecutionResult, BPFExecutionResult]:
        """Execute coordinated measurement with receiver-first timing.

        The execution order is:
        1. Check/deploy tools on both hosts
        2. Start receiver and wait for ready signal
        3. Start sender after receiver is ready
        4. Wait for duration
        5. Collect results from both

        Args:
            receiver_host: Receiver host IP
            sender_host: Sender host IP
            receiver_command: Command to run on receiver
            sender_command: Command to run on sender
            duration: Measurement duration in seconds
            receiver_workspace: Working directory on receiver
            sender_workspace: Working directory on sender
            deploy_mode: Tool deployment mode
            local_tools_path: Local path to tools for SCP deployment

        Returns:
            Tuple of (receiver_result, sender_result)
        """
        settings = get_settings()
        workspace = str(settings.bpf_tools.remote_tools_path)
        receiver_workspace = receiver_workspace or workspace
        sender_workspace = sender_workspace or workspace

        log = logger.bind(
            receiver=receiver_host,
            sender=sender_host,
            duration=duration,
        )
        log.info("coordinated_measurement_starting")

        # Create executors
        receiver_executor = BPFExecutor(
            self.ssh, receiver_host, remote_tools_path=receiver_workspace
        )
        sender_executor = BPFExecutor(
            self.ssh, sender_host, remote_tools_path=sender_workspace
        )

        # Deploy tools if needed
        if deploy_mode in ["auto", "scp"] and local_tools_path:
            local_path = Path(local_tools_path)
            # Deploy receiver tool
            receiver_tool = receiver_command.split()[0]
            if (local_path / receiver_tool).exists():
                receiver_executor.deploy_tool(local_path / receiver_tool)
            # Deploy sender tool
            sender_tool = sender_command.split()[0]
            if (local_path / sender_tool).exists():
                sender_executor.deploy_tool(local_path / sender_tool)

        # Step 1: Start receiver
        log.info("starting_receiver")
        # For now, we start receiver in background and poll for readiness
        # In a real implementation, we'd want a ready signal mechanism

        # Start receiver (it will run for duration + startup_delay)
        receiver_duration = int(duration + self.receiver_startup_delay + 5)
        receiver_result_holder: list = []

        import threading

        def run_receiver():
            result = receiver_executor.execute(
                receiver_command,
                duration=receiver_duration,
                workspace=receiver_workspace,
            )
            receiver_result_holder.append(result)

        receiver_thread = threading.Thread(target=run_receiver)
        receiver_thread.start()

        # Step 2: Wait for receiver to be ready
        log.debug("waiting_for_receiver_ready", delay=self.receiver_startup_delay)
        time.sleep(self.receiver_startup_delay)

        # Step 3: Start sender
        log.info("starting_sender")
        sender_result = sender_executor.execute(
            sender_command,
            duration=duration,
            workspace=sender_workspace,
        )

        # Step 4: Wait for receiver to complete
        receiver_thread.join(timeout=receiver_duration + 10)

        receiver_result = (
            receiver_result_holder[0]
            if receiver_result_holder
            else BPFExecutionResult(
                success=False,
                stdout="",
                stderr="",
                exit_code=-1,
                error="Receiver thread failed",
            )
        )

        log.info(
            "coordinated_measurement_completed",
            receiver_success=receiver_result.success,
            sender_success=sender_result.success,
        )

        return receiver_result, sender_result


def execute_bpf_tool(
    host: str,
    command: str,
    duration: int = 30,
    workspace: str | None = None,
) -> BPFExecutionResult:
    """Convenience function to execute a single BPF tool.

    Args:
        host: Target host IP
        command: BPF command to execute
        duration: Duration in seconds
        workspace: Working directory

    Returns:
        BPFExecutionResult
    """
    settings = get_settings()

    with SSHManager(settings.ssh) as ssh:
        executor = BPFExecutor(
            ssh,
            host,
            remote_tools_path=settings.bpf_tools.remote_tools_path,
            remote_python=settings.bpf_tools.remote_python,
        )
        return executor.execute(
            command,
            duration=duration,
            workspace=workspace or str(settings.bpf_tools.remote_tools_path),
        )
