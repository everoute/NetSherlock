"""L3 Layer Tools: Precise Measurement.

MCP tools for executing BPF-based measurements with proper timing coordination.
The key constraint enforced here is receiver-first timing for coordinated measurements.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import structlog

from netsherlock.config.settings import get_settings
from netsherlock.core.bpf_executor import BPFExecutor, CoordinatedMeasurement
from netsherlock.core.ssh_manager import SSHManager
from netsherlock.schemas.environment import VMNetworkEnv
from netsherlock.schemas.measurement import (
    CoordinatedMeasurementResult,
    DropPoint,
    LatencyBreakdown,
    LatencySegment,
    MeasurementMetadata,
    MeasurementResult,
    MeasurementStatus,
    MeasurementType,
    PacketDropResult,
)

logger = structlog.get_logger(__name__)


# Tool paths relative to tools directory
LATENCY_TOOLS = {
    "vm_network": "performance/vm_network_latency_summary.py",
    "system_network": "performance/system_network_latency_summary.py",
    "vhost_tun": "kvm-virt-network/kvm_vhost_tun_latency_summary.py",
}

DROP_TOOLS = {
    "kernel_drop": "linux-network-stack/packet-drop/kernel_drop_stack_stats_summary.py",
    "icmp_drop": "linux-network-stack/packet-drop/icmp_drop_detector.py",
}


def execute_coordinated_measurement(
    receiver_host: str,
    sender_host: str,
    receiver_tool: str,
    sender_tool: str,
    receiver_args: dict | None = None,
    sender_args: dict | None = None,
    duration: int = 30,
    deploy_mode: Literal["auto", "scp", "pre-deployed"] = "auto",
) -> CoordinatedMeasurementResult:
    """Execute coordinated measurement with receiver-first timing.

    This is the core L3 tool that enforces the receiver-first timing constraint.
    The receiver-side BPF tool is guaranteed to start before the sender-side tool.

    The execution order is:
    1. Check/deploy receiver tool
    2. Start receiver and wait for ready signal (min 1 second)
    3. Check/deploy sender tool
    4. Start sender
    5. Wait for duration
    6. Collect and return results from both

    Args:
        receiver_host: Receiver host IP address
        sender_host: Sender host IP address
        receiver_tool: BPF tool name for receiver (e.g., "vm_network_latency_summary.py")
        sender_tool: BPF tool name for sender (e.g., "ping_generator.py")
        receiver_args: Arguments dict for receiver tool
        sender_args: Arguments dict for sender tool
        duration: Measurement duration in seconds
        deploy_mode: Tool deployment mode
            - "auto": Check if exists, SCP if not
            - "scp": Always SCP tools
            - "pre-deployed": Assume tools are pre-deployed

    Returns:
        CoordinatedMeasurementResult with measurements from both sides

    Example:
        >>> result = execute_coordinated_measurement(
        ...     receiver_host="192.168.1.10",
        ...     sender_host="192.168.1.20",
        ...     receiver_tool="vm_network_latency_summary.py",
        ...     sender_tool="ping_generator.py",
        ...     receiver_args={"interface": "eth0"},
        ...     sender_args={"target": "192.168.1.10", "count": 100},
        ...     duration=30
        ... )
        >>> if result.receiver_result.status == "success":
        ...     print(result.receiver_result.latency_data)
    """
    settings = get_settings()
    measurement_id = str(uuid.uuid4())[:8]

    log = logger.bind(
        measurement_id=measurement_id,
        receiver=receiver_host,
        sender=sender_host,
        duration=duration,
    )
    log.info("coordinated_measurement_starting")

    # Build command strings
    receiver_args = receiver_args or {}
    sender_args = sender_args or {}

    receiver_cmd = _build_command(receiver_tool, receiver_args)
    sender_cmd = _build_command(sender_tool, sender_args)

    try:
        with SSHManager(settings.ssh) as ssh:
            coord = CoordinatedMeasurement(
                ssh,
                receiver_ready_timeout=settings.measurement.receiver_ready_timeout,
                receiver_startup_delay=settings.measurement.receiver_startup_delay,
            )

            receiver_result, sender_result = coord.execute(
                receiver_host=receiver_host,
                sender_host=sender_host,
                receiver_command=receiver_cmd,
                sender_command=sender_cmd,
                duration=duration,
                deploy_mode=deploy_mode,
                local_tools_path=settings.bpf_tools.local_tools_path,
            )

            # Parse results
            receiver_parsed = _parse_measurement_result(
                raw_result=receiver_result,
                measurement_type=MeasurementType.LATENCY,
                host=receiver_host,
                tool_name=receiver_tool,
            )

            sender_parsed = _parse_measurement_result(
                raw_result=sender_result,
                measurement_type=MeasurementType.LATENCY,
                host=sender_host,
                tool_name=sender_tool,
            )

            log.info(
                "coordinated_measurement_completed",
                receiver_status=receiver_parsed.status,
                sender_status=sender_parsed.status,
            )

            return CoordinatedMeasurementResult(
                measurement_id=measurement_id,
                receiver_result=receiver_parsed,
                sender_result=sender_parsed,
            )

    except Exception as e:
        log.error("coordinated_measurement_failed", error=str(e))

        # Return failed results
        now = datetime.now()
        failed_metadata = MeasurementMetadata(
            tool_name="",
            host="",
            duration_sec=0,
            start_time=now,
        )

        return CoordinatedMeasurementResult(
            measurement_id=measurement_id,
            receiver_result=MeasurementResult(
                measurement_id=f"{measurement_id}-rx",
                measurement_type=MeasurementType.LATENCY,
                status=MeasurementStatus.FAILED,
                error=str(e),
                metadata=failed_metadata,
            ),
            sender_result=MeasurementResult(
                measurement_id=f"{measurement_id}-tx",
                measurement_type=MeasurementType.LATENCY,
                status=MeasurementStatus.FAILED,
                error=str(e),
                metadata=failed_metadata,
            ),
        )


def measure_vm_latency_breakdown(
    vm_id: str,
    host: str,
    env: VMNetworkEnv | None = None,
    duration: int = 30,
) -> MeasurementResult:
    """Measure VM network stack latency breakdown.

    Uses BPF tools to measure latency at each segment of the VM network path:
    - virtio TX/RX
    - vhost-net processing
    - TAP device
    - OVS flow processing

    Args:
        vm_id: VM UUID
        host: Host (hypervisor) IP address
        env: Pre-collected VMNetworkEnv (optional, will collect if not provided)
        duration: Measurement duration in seconds

    Returns:
        MeasurementResult with LatencyBreakdown data

    Example:
        >>> result = measure_vm_latency_breakdown(
        ...     vm_id="ae6aa164-604c-4cb0-84b8-2dea034307f1",
        ...     host="192.168.1.10",
        ...     duration=30
        ... )
        >>> if result.status == "success":
        ...     for seg in result.latency_data.segments:
        ...         print(f"{seg.name}: avg={seg.avg_us}us p99={seg.p99_us}us")
    """
    settings = get_settings()
    measurement_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()

    log = logger.bind(measurement_id=measurement_id, vm_id=vm_id, host=host)
    log.info("vm_latency_measurement_starting")

    try:
        # Collect environment if not provided
        if env is None:
            from netsherlock.tools.l2_environment import collect_vm_network_env

            env_result = collect_vm_network_env(vm_id, host)
            if not env_result.success or not isinstance(env_result.data, VMNetworkEnv):
                return MeasurementResult(
                    measurement_id=measurement_id,
                    measurement_type=MeasurementType.LATENCY,
                    status=MeasurementStatus.FAILED,
                    error=f"Failed to collect VM environment: {env_result.error}",
                    metadata=MeasurementMetadata(
                        tool_name="vm_network_latency_summary.py",
                        host=host,
                        duration_sec=0,
                        start_time=start_time,
                    ),
                )
            env = env_result.data

        # Build tool command with VM-specific args
        nic = env.nics[0] if env.nics else None
        if not nic:
            return MeasurementResult(
                measurement_id=measurement_id,
                measurement_type=MeasurementType.LATENCY,
                status=MeasurementStatus.FAILED,
                error="No NICs found for VM",
                metadata=MeasurementMetadata(
                    tool_name="vm_network_latency_summary.py",
                    host=host,
                    duration_sec=0,
                    start_time=start_time,
                ),
            )

        tool_args = {
            "vnet": nic.host_vnet,
            "qemu_pid": env.qemu_pid,
        }
        if nic.vhost_pids:
            tool_args["vhost_pid"] = nic.vhost_pids[0].pid

        cmd = _build_command(LATENCY_TOOLS["vm_network"], tool_args)

        with SSHManager(settings.ssh) as ssh:
            executor = BPFExecutor(
                ssh,
                host,
                remote_tools_path=settings.bpf_tools.remote_tools_path,
            )

            raw_result = executor.execute(cmd, duration=duration)

            result = _parse_measurement_result(
                raw_result=raw_result,
                measurement_type=MeasurementType.LATENCY,
                host=host,
                tool_name="vm_network_latency_summary.py",
            )

            log.info(
                "vm_latency_measurement_completed",
                status=result.status,
                segments=len(result.latency_data.segments) if result.latency_data else 0,
            )

            return result

    except Exception as e:
        log.error("vm_latency_measurement_failed", error=str(e))
        return MeasurementResult(
            measurement_id=measurement_id,
            measurement_type=MeasurementType.LATENCY,
            status=MeasurementStatus.FAILED,
            error=str(e),
            metadata=MeasurementMetadata(
                tool_name="vm_network_latency_summary.py",
                host=host,
                duration_sec=0,
                start_time=start_time,
            ),
        )


def measure_packet_drop(
    host: str,
    interface: str | None = None,
    duration: int = 30,
) -> MeasurementResult:
    """Monitor kernel packet drops using kfree_skb tracing.

    Args:
        host: Target host IP address
        interface: Optional interface to filter (default: all interfaces)
        duration: Monitoring duration in seconds

    Returns:
        MeasurementResult with PacketDropResult data
    """
    settings = get_settings()
    measurement_id = str(uuid.uuid4())[:8]
    start_time = datetime.now()

    log = logger.bind(measurement_id=measurement_id, host=host, duration=duration)
    log.info("packet_drop_measurement_starting")

    try:
        tool_args = {}
        if interface:
            tool_args["interface"] = interface

        cmd = _build_command(DROP_TOOLS["kernel_drop"], tool_args)

        with SSHManager(settings.ssh) as ssh:
            executor = BPFExecutor(
                ssh,
                host,
                remote_tools_path=settings.bpf_tools.remote_tools_path,
            )

            raw_result = executor.execute(cmd, duration=duration)

            result = _parse_measurement_result(
                raw_result=raw_result,
                measurement_type=MeasurementType.PACKET_DROP,
                host=host,
                tool_name="kernel_drop_stack_stats_summary.py",
            )

            log.info(
                "packet_drop_measurement_completed",
                status=result.status,
                total_drops=result.drop_data.total_drops if result.drop_data else 0,
            )

            return result

    except Exception as e:
        log.error("packet_drop_measurement_failed", error=str(e))
        return MeasurementResult(
            measurement_id=measurement_id,
            measurement_type=MeasurementType.PACKET_DROP,
            status=MeasurementStatus.FAILED,
            error=str(e),
            metadata=MeasurementMetadata(
                tool_name="kernel_drop_stack_stats_summary.py",
                host=host,
                duration_sec=0,
                start_time=start_time,
            ),
        )


def _build_command(tool_name: str, args: dict) -> str:
    """Build command string from tool name and arguments."""
    settings = get_settings()

    # Build args string
    args_str = " ".join(f"--{k} {v}" for k, v in args.items() if v is not None)

    # Determine if tool is Python script
    if tool_name.endswith(".py"):
        cmd = f"{settings.bpf_tools.remote_python} {tool_name}"
    else:
        cmd = tool_name

    if args_str:
        cmd = f"{cmd} {args_str}"

    return cmd


def _parse_measurement_result(
    raw_result,
    measurement_type: MeasurementType,
    host: str,
    tool_name: str,
) -> MeasurementResult:
    """Parse BPF execution result into structured MeasurementResult."""
    measurement_id = str(uuid.uuid4())[:8]
    now = datetime.now()

    metadata = MeasurementMetadata(
        tool_name=tool_name,
        host=host,
        duration_sec=raw_result.duration_actual,
        start_time=now,
        end_time=now,
    )

    if not raw_result.success:
        return MeasurementResult(
            measurement_id=measurement_id,
            measurement_type=measurement_type,
            status=MeasurementStatus.FAILED,
            error=raw_result.error or "Execution failed",
            metadata=metadata,
            raw_output=raw_result.stdout,
        )

    output = raw_result.stdout

    if measurement_type == MeasurementType.LATENCY:
        latency_data = _parse_latency_output(output)
        status = MeasurementStatus.SUCCESS if latency_data.segments else MeasurementStatus.PARTIAL

        return MeasurementResult(
            measurement_id=measurement_id,
            measurement_type=measurement_type,
            status=status,
            latency_data=latency_data,
            metadata=metadata,
            raw_output=output,
        )

    elif measurement_type == MeasurementType.PACKET_DROP:
        drop_data = _parse_drop_output(output)
        status = MeasurementStatus.SUCCESS

        return MeasurementResult(
            measurement_id=measurement_id,
            measurement_type=measurement_type,
            status=status,
            drop_data=drop_data,
            metadata=metadata,
            raw_output=output,
        )

    else:
        return MeasurementResult(
            measurement_id=measurement_id,
            measurement_type=measurement_type,
            status=MeasurementStatus.PARTIAL,
            metadata=metadata,
            raw_output=output,
        )


def _parse_latency_output(output: str) -> LatencyBreakdown:
    """Parse latency measurement output into LatencyBreakdown."""
    segments = []

    # Look for histogram summaries
    # Pattern: "segment_name: avg=100.5us p50=80.0us p99=500.0us"
    pattern = r"(\w+):\s*avg=(\d+\.?\d*)us.*?p99=(\d+\.?\d*)us"

    for match in re.finditer(pattern, output, re.IGNORECASE):
        name = match.group(1)
        avg = float(match.group(2))
        p99 = float(match.group(3))

        segments.append(
            LatencySegment(
                name=name,
                avg_us=avg,
                p99_us=p99,
            )
        )

    # Calculate totals
    total_avg = sum(s.avg_us for s in segments)
    total_p99 = sum(s.p99_us for s in segments)

    return LatencyBreakdown(
        segments=segments,
        total_avg_us=total_avg,
        total_p99_us=total_p99,
    )


def _parse_drop_output(output: str) -> PacketDropResult:
    """Parse packet drop output into PacketDropResult."""
    drop_points = []
    total_drops = 0

    # Look for drop locations
    # Pattern: "function_name: 123 drops"
    pattern = r"(\w+):\s*(\d+)\s*drops?"

    for match in re.finditer(pattern, output, re.IGNORECASE):
        location = match.group(1)
        count = int(match.group(2))
        total_drops += count

        drop_points.append(
            DropPoint(
                location=location,
                count=count,
            )
        )

    return PacketDropResult(
        drop_points=drop_points,
        total_drops=total_drops,
    )
