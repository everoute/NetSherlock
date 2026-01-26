"""NetSherlock CLI entry point.

Provides command-line interface for network troubleshooting diagnostics.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime
from typing import Literal, cast

import click
import structlog

from netsherlock import __version__
from netsherlock.config.settings import get_settings
from netsherlock.controller.checkpoints import (
    CheckpointData,
    CheckpointResult,
    CheckpointStatus,
)
from netsherlock.controller.diagnosis_controller import (
    DiagnosisController,
    DiagnosisResult,
    DiagnosisStatus,
)
from netsherlock.schemas.alert import DiagnosisRequest
from netsherlock.schemas.config import DiagnosisMode, DiagnosisRequestSource


# Configure structlog for CLI output
def configure_logging(verbose: bool = False, json_output: bool = False) -> None:
    """Configure structured logging for CLI."""
    if json_output:
        processors = [
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = [
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            10 if verbose else 20  # DEBUG=10, INFO=20
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger(__name__)


def _determine_diagnosis_mode(
    mode: str | None,
    mode_autonomous: bool,
    mode_interactive: bool,
) -> DiagnosisMode:
    """Determine the effective diagnosis mode from CLI options.

    Priority:
    1. --mode option (explicit mode selection)
    2. --autonomous flag
    3. --interactive flag
    4. Default: interactive (safest for CLI)

    Args:
        mode: Value from --mode option
        mode_autonomous: --autonomous flag
        mode_interactive: --interactive flag

    Returns:
        DiagnosisMode enum value

    Raises:
        click.UsageError: If conflicting flags are provided
    """
    # Check for conflicting flags
    if mode_autonomous and mode_interactive:
        raise click.UsageError(
            "Cannot use both --autonomous and --interactive flags"
        )

    # --mode takes precedence
    if mode is not None:
        return DiagnosisMode(mode)

    # Flag shortcuts
    if mode_autonomous:
        return DiagnosisMode.AUTONOMOUS
    if mode_interactive:
        return DiagnosisMode.INTERACTIVE

    # Default for CLI is interactive (safe option)
    return DiagnosisMode.INTERACTIVE


async def _cli_checkpoint_callback(data: CheckpointData) -> CheckpointResult:
    """CLI callback for checkpoint interactions.

    Prompts user in terminal for confirmation at each checkpoint.

    Args:
        data: Checkpoint data to display

    Returns:
        CheckpointResult based on user input
    """
    # Display checkpoint information
    click.echo()
    click.echo("=" * 60)
    click.echo(f"CHECKPOINT: {data.checkpoint_type.value}")
    click.echo("=" * 60)
    click.echo()
    click.echo(f"Summary: {data.summary}")
    click.echo()

    if data.details:
        click.echo("Details:")
        for key, value in data.details.items():
            if isinstance(value, dict):
                click.echo(f"  {key}:")
                for k, v in value.items():
                    click.echo(f"    {k}: {v}")
            elif isinstance(value, list):
                click.echo(f"  {key}: {len(value)} items")
            else:
                click.echo(f"  {key}: {value}")
        click.echo()

    if data.recommendation:
        click.echo(f"Recommendation: {data.recommendation}")
        click.echo()

    # Display options
    if data.options:
        click.echo("Options:")
        for i, opt in enumerate(data.options, 1):
            click.echo(f"  {i}. {opt}")
        click.echo()

    # Get user input
    while True:
        choice = click.prompt(
            "Enter choice (1=Confirm, 2=Modify, 3=Cancel)",
            type=int,
            default=1,
        )

        if choice == 1:
            click.echo("Confirmed. Continuing...")
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.CONFIRMED,
            )
        elif choice == 2:
            user_input = click.prompt("Enter modifications")
            click.echo("Modified. Continuing...")
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.MODIFIED,
                user_input=user_input,
            )
        elif choice == 3:
            click.echo("Cancelled.")
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.CANCELLED,
            )
        else:
            click.echo("Invalid choice. Please enter 1, 2, or 3.")


def _format_diagnosis_result(result: DiagnosisResult, json_output: bool) -> None:
    """Format and display diagnosis result.

    Args:
        result: DiagnosisResult to display
        json_output: Whether to output JSON format
    """
    if json_output:
        output = {
            "diagnosis_id": result.diagnosis_id,
            "status": result.status.value,
            "mode": result.mode.value,
            "summary": result.summary,
            "root_cause": result.root_cause,
            "detailed_report": result.detailed_report,
            "report_path": result.report_path,
            "started_at": result.started_at.isoformat() if result.started_at else None,
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "error": result.error,
        }
        click.echo(json.dumps(output, indent=2, default=str))
    else:
        click.echo()

        # Display Markdown report if available
        if result.markdown_report:
            click.echo(result.markdown_report)
        elif result.detailed_report:
            # Fallback: display summary from detailed report
            report = result.detailed_report
            summary = report.get("summary", {})

            click.echo("=" * 70)
            click.echo("DIAGNOSIS RESULT")
            click.echo("=" * 70)
            click.echo()
            click.echo(f"Diagnosis ID: {result.diagnosis_id}")
            click.echo(f"Status: {result.status.value}")
            click.echo(f"Total RTT: {summary.get('total_rtt_us', 0):.2f} µs")
            click.echo(f"Primary Contributor: {summary.get('primary_contributor_name', 'Unknown')} ({summary.get('primary_contributor_pct', 0):.1f}%)")
        else:
            # Minimal output
            click.echo("=" * 70)
            click.echo("DIAGNOSIS RESULT")
            click.echo("=" * 70)
            click.echo()
            click.echo(f"Diagnosis ID: {result.diagnosis_id}")
            click.echo(f"Status: {result.status.value}")
            if result.summary:
                click.echo(f"Summary: {result.summary}")
            if result.root_cause:
                click.echo(f"Root Cause: {result.root_cause.get('category', 'Unknown')}")

        # Show report file path
        if result.report_path:
            click.echo()
            click.echo("-" * 70)
            click.echo(f"Report saved to: {result.report_path}")

        # Show error if any
        if result.error:
            click.echo()
            click.echo(f"Error: {result.error}", err=True)

        # Show duration
        if result.started_at and result.completed_at:
            duration = (result.completed_at - result.started_at).total_seconds()
            click.echo(f"Duration: {duration:.1f}s")


def _display_phase_progress(phase: str, verbose: bool) -> None:
    """Display progress for a diagnosis phase.

    Args:
        phase: Current phase name
        verbose: Whether verbose output is enabled
    """
    if verbose:
        click.echo(f"  [Phase] {phase}")


@click.group()
@click.version_option(version=__version__, prog_name="netsherlock")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose output")
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format")
@click.pass_context
def cli(ctx: click.Context, verbose: bool, json_output: bool) -> None:
    """NetSherlock - AI-driven network troubleshooting agent.

    Examples:

    \b
      # Single VM network diagnosis
      netsherlock diagnose --network-type vm \\
        --src-host 192.168.1.10 \\
        --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \\
        --type latency

    \b
      # VM-to-VM network diagnosis
      netsherlock diagnose --network-type vm \\
        --src-host 192.168.1.10 \\
        --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \\
        --dst-host 192.168.1.20 \\
        --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \\
        --type latency

    \b
      # Collect network environment information
      netsherlock env system --host 192.168.1.10

    \b
      # Query Grafana metrics
      netsherlock query metrics 'host_network_ping_time_ns{hostname="node1"}' -s "-1h"
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["json_output"] = json_output
    configure_logging(verbose, json_output)


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="Path to MinimalInputConfig YAML file (recommended for manual mode)",
)
@click.option(
    "--network-type",
    "-n",
    required=True,
    type=click.Choice(["vm", "system"]),
    help="Network type: vm (VM network) or system (host network)",
)
@click.option(
    "--src-host",
    required=True,
    help="Source host management IP address (required)",
)
@click.option(
    "--src-vm",
    help="Source VM UUID (required for network-type=vm)",
)
@click.option(
    "--dst-host",
    help="Destination host management IP (for inter-node diagnosis)",
)
@click.option(
    "--dst-vm",
    help="Destination VM UUID (required when --dst-host specified for vm network)",
)
@click.option(
    "--type",
    "-t",
    "diagnosis_type",
    type=click.Choice(["latency", "packet_drop", "connectivity"]),
    default="latency",
    help="Type of diagnosis to perform",
)
@click.option(
    "--duration",
    "-d",
    type=int,
    default=30,
    help="Measurement duration in seconds (default: 30)",
)
@click.option(
    "--mode",
    "-m",
    type=click.Choice(["autonomous", "interactive"]),
    default=None,
    help="Diagnosis mode (default: interactive for CLI)",
)
@click.option(
    "--autonomous",
    "mode_autonomous",
    is_flag=True,
    help="Shortcut for --mode autonomous",
)
@click.option(
    "--interactive",
    "mode_interactive",
    is_flag=True,
    help="Shortcut for --mode interactive",
)
@click.option(
    "--generate-traffic",
    "generate_traffic",
    is_flag=True,
    help="Generate ICMP test traffic from sender VM (default: use background traffic)",
)
@click.pass_context
def diagnose(
    ctx: click.Context,
    config_path: str | None,
    network_type: str,
    src_host: str,
    src_vm: str | None,
    dst_host: str | None,
    dst_vm: str | None,
    diagnosis_type: str,
    duration: int,
    mode: str | None,
    mode_autonomous: bool,
    mode_interactive: bool,
    generate_traffic: bool,
) -> None:
    """Run network diagnosis on a target host.

    This command performs end-to-end network troubleshooting:

    \b
    1. Collects network environment information (L2)
    2. Executes coordinated measurements (L3)
    3. Analyzes results and identifies root cause (L4)
    4. Generates a diagnosis report

    Modes:

    \b
      --interactive (default): Stops at checkpoints for user confirmation
      --autonomous: Runs without user intervention

    VM Network Parameters:

    \b
      --network-type vm  : VM network diagnosis
      --src-host         : Source host management IP (required)
      --src-vm           : Source VM UUID (required for vm network)
      --dst-host         : Destination host management IP (optional)
      --dst-vm           : Destination VM UUID (required if --dst-host specified)

    Examples:

    \b
      # Single VM network diagnosis
      netsherlock diagnose --network-type vm \\
        --src-host 192.168.1.10 \\
        --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \\
        --type latency

    \b
      # VM-to-VM network diagnosis (autonomous mode)
      netsherlock diagnose --network-type vm \\
        --src-host 192.168.1.10 \\
        --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \\
        --dst-host 192.168.1.20 \\
        --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \\
        --type latency --autonomous
    """
    # Determine mode from flags
    effective_mode = _determine_diagnosis_mode(mode, mode_autonomous, mode_interactive)

    # Validate parameter combinations
    if network_type == "vm":
        if not src_vm:
            raise click.UsageError("--src-vm is required for --network-type=vm")
        if dst_host and not dst_vm:
            raise click.UsageError("--dst-vm is required when --dst-host is specified")
        if dst_vm and not dst_host:
            raise click.UsageError("--dst-host is required when --dst-vm is specified")

    request_id = str(uuid.uuid4())[:8]

    request = DiagnosisRequest(
        request_id=request_id,
        request_type=cast(Literal["latency", "packet_drop", "connectivity"], diagnosis_type),
        network_type=cast(Literal["vm", "system"], network_type),
        src_host=src_host,
        src_vm=src_vm,
        dst_host=dst_host,
        dst_vm=dst_vm,
        options={
            "duration": duration,
            "mode": effective_mode.value,
            "generate_traffic": generate_traffic,
        },
    )

    log = logger.bind(
        request_id=request_id,
        network_type=network_type,
        src_host=src_host,
        type=diagnosis_type,
        mode=effective_mode.value,
    )
    log.info("diagnosis_started")

    json_output = ctx.obj.get("json_output", False)
    verbose = ctx.obj.get("verbose", False)

    try:
        # Display request info
        if not json_output:
            click.echo(f"Diagnosis Request: {request_id}")
            if config_path:
                click.echo(f"  Config: {config_path}")
            click.echo(f"  Network Type: {network_type}")
            click.echo(f"  Source Host: {src_host}")
            if src_vm:
                click.echo(f"  Source VM: {src_vm}")
            if dst_host:
                click.echo(f"  Destination Host: {dst_host}")
            if dst_vm:
                click.echo(f"  Destination VM: {dst_vm}")
            click.echo(f"  Diagnosis Type: {diagnosis_type}")
            click.echo(f"  Mode: {effective_mode.value}")
            click.echo(f"  Duration: {duration}s")
            click.echo()

        # Get diagnosis config
        settings = get_settings()
        config = settings.get_diagnosis_config()

        # Create checkpoint callback for interactive mode
        checkpoint_callback = None
        if effective_mode == DiagnosisMode.INTERACTIVE:
            checkpoint_callback = _cli_checkpoint_callback

        # Create and run controller
        controller = DiagnosisController(
            config=config,
            checkpoint_callback=checkpoint_callback,
            minimal_input_path=config_path,
            llm_model=settings.llm.model,
            llm_max_turns=settings.llm.max_turns,
            llm_max_budget_usd=settings.llm.max_budget_usd,
            bpf_local_tools_path=settings.bpf_tools.local_tools_path,
            bpf_remote_tools_path=settings.bpf_tools.remote_tools_path,
        )

        if not json_output:
            click.echo("Starting diagnosis...")
            if verbose:
                click.echo()

        # Run diagnosis asynchronously
        result = asyncio.run(
            controller.run(
                request=request,
                source=DiagnosisRequestSource.CLI,
                force_mode=effective_mode,
            )
        )

        # Display result
        _format_diagnosis_result(result, json_output)

        # Set exit code based on result status
        if result.status == DiagnosisStatus.COMPLETED:
            log.info("diagnosis_completed", status="success")
        elif result.status == DiagnosisStatus.CANCELLED:
            log.info("diagnosis_cancelled")
            sys.exit(2)
        elif result.status == DiagnosisStatus.ERROR:
            log.error("diagnosis_failed", error=result.error)
            sys.exit(1)
        elif result.status == DiagnosisStatus.INTERRUPTED:
            log.info("diagnosis_interrupted")
            sys.exit(3)

    except KeyboardInterrupt:
        click.echo("\nDiagnosis interrupted by user.", err=True)
        sys.exit(130)
    except Exception as e:
        log.error("diagnosis_failed", error=str(e))
        if json_output:
            click.echo(json.dumps({"error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.group()
def env() -> None:
    """Collect network environment information."""
    pass


@env.command("system")
@click.option("--host", "-h", required=True, help="Target host IP address")
@click.option(
    "--port-type",
    "-p",
    type=click.Choice(["mgt", "storage", "access", "vpc"]),
    help="Filter by port type",
)
@click.pass_context
def env_system(ctx: click.Context, host: str, port_type: str | None) -> None:
    """Collect system network environment.

    Gathers OVS internal ports, bridges, and physical NIC information.
    """
    from netsherlock.tools.l2_environment import collect_system_network_env

    json_output = ctx.obj.get("json_output", False)

    result = collect_system_network_env(host, port_type)

    if result.success and result.data:
        data = result.data
        if json_output:
            click.echo(json.dumps(data.model_dump(), default=str, indent=2))
        else:
            click.echo(f"System Network Environment: {host}")
            click.echo("-" * 50)
            for port in data.ports:  # type: ignore[union-attr]
                click.echo(f"  Port: {port.port_name}")
                click.echo(f"    Type: {port.port_type}")
                click.echo(f"    IP: {port.ip_address or 'N/A'}")
                click.echo(f"    Bridge: {port.ovs_bridge}")
                if port.physical_nics:
                    nics = ", ".join(n.name for n in port.physical_nics)
                    click.echo(f"    NICs: {nics}")
                click.echo()
    else:
        click.echo(f"Failed: {result.error}", err=True)
        sys.exit(1)


@env.command("vm")
@click.option("--host", "-h", required=True, help="Host (hypervisor) IP address")
@click.option("--vm-id", "-v", required=True, help="VM UUID")
@click.pass_context
def env_vm(ctx: click.Context, host: str, vm_id: str) -> None:
    """Collect VM network environment.

    Gathers VM network topology including vnet, TAP/vhost info, and OVS bridges.
    """
    from netsherlock.tools.l2_environment import collect_vm_network_env

    json_output = ctx.obj.get("json_output", False)

    result = collect_vm_network_env(vm_id, host)

    if result.success and result.data:
        if json_output:
            click.echo(json.dumps(result.data.model_dump(), default=str, indent=2))
        else:
            env = result.data
            click.echo(f"VM Network Environment: {env.vm_uuid}")  # type: ignore[union-attr]
            click.echo("-" * 50)
            click.echo(f"  Host: {env.host}")
            click.echo(f"  QEMU PID: {env.qemu_pid}")  # type: ignore[union-attr]
            click.echo(f"  NICs: {len(env.nics)}")  # type: ignore[union-attr]
            for i, nic in enumerate(env.nics, 1):  # type: ignore[union-attr]
                click.echo(f"\n  NIC {i}:")
                click.echo(f"    MAC: {nic.mac}")
                click.echo(f"    vnet: {nic.host_vnet}")
                click.echo(f"    Bridge: {nic.ovs_bridge}")
                if nic.vhost_pids:
                    pids = ", ".join(str(p.pid) for p in nic.vhost_pids)
                    click.echo(f"    vhost PIDs: {pids}")
    else:
        click.echo(f"Failed: {result.error}", err=True)
        sys.exit(1)


@cli.group()
def query() -> None:
    """Query monitoring data from Grafana."""
    pass


@query.command("metrics")
@click.argument("promql")
@click.option("--start", "-s", default="-1h", help="Start time (e.g., -1h, -30m)")
@click.option("--end", "-e", default="now", help="End time (default: now)")
@click.option("--step", default="1m", help="Query step (default: 1m)")
@click.pass_context
def query_metrics(
    ctx: click.Context, promql: str, start: str, end: str, step: str
) -> None:
    """Query VictoriaMetrics using PromQL.

    PROMQL is the Prometheus query expression.

    Examples:

    \b
      netsherlock query metrics 'up'
      netsherlock query metrics 'host_network_ping_time_ns{hostname="node1"}' -s "-30m"
    """
    from netsherlock.tools.l1_monitoring import grafana_query_metrics

    json_output = ctx.obj.get("json_output", False)

    result = grafana_query_metrics(promql, start, end, step)

    if result.status == "success":
        if json_output:
            data = {
                "status": result.status,
                "result_type": result.result_type,
                "series": [
                    {"metric": s.metric, "values": len(s.values)}
                    for s in result.series
                ],
            }
            click.echo(json.dumps(data, indent=2))
        else:
            click.echo(f"Query: {promql}")
            click.echo(f"Series: {len(result.series)}")
            for series in result.series[:10]:  # Limit output
                click.echo(f"  {series.metric}: {len(series.values)} samples")
    else:
        click.echo(f"Query failed: {result.error}", err=True)
        sys.exit(1)


@query.command("logs")
@click.argument("logql")
@click.option("--start", "-s", default="-1h", help="Start time")
@click.option("--end", "-e", default="now", help="End time")
@click.option("--limit", "-l", type=int, default=100, help="Max entries (default: 100)")
@click.pass_context
def query_logs(
    ctx: click.Context, logql: str, start: str, end: str, limit: int
) -> None:
    """Query Loki logs using LogQL.

    LOGQL is the Loki query expression.

    Examples:

    \b
      netsherlock query logs '{namespace="kube-system"}'
      netsherlock query logs '{service="nginx"} |= "error"' -l 50
    """
    from netsherlock.tools.l1_monitoring import loki_query_logs

    json_output = ctx.obj.get("json_output", False)

    result = loki_query_logs(logql, start, end, limit)

    if result.status == "success":
        if json_output:
            data = {
                "status": result.status,
                "entries": len(result.entries),
            }
            click.echo(json.dumps(data, indent=2))
        else:
            click.echo(f"Query: {logql}")
            click.echo(f"Entries: {len(result.entries)}")
            for entry in result.entries[:20]:  # Limit output
                ts = datetime.fromtimestamp(entry.timestamp).strftime("%H:%M:%S")
                line = entry.line[:80] + "..." if len(entry.line) > 80 else entry.line
                click.echo(f"  [{ts}] {line}")
    else:
        click.echo(f"Query failed: {result.error}", err=True)
        sys.exit(1)


@cli.command()
def config() -> None:
    """Show current configuration."""
    settings = get_settings()

    click.echo("NetSherlock Configuration")
    click.echo("=" * 50)
    click.echo(f"App Name: {settings.app_name}")
    click.echo(f"Debug: {settings.debug}")
    click.echo()
    click.echo("Diagnosis Settings:")
    diagnosis_config = settings.get_diagnosis_config()
    click.echo(f"  Default Mode: {diagnosis_config.default_mode.value}")
    click.echo(f"  Autonomous Enabled: {diagnosis_config.autonomous.enabled}")
    click.echo(f"  Auto-Agent Loop: {diagnosis_config.autonomous.auto_agent_loop}")
    click.echo(f"  Interactive Timeout: {diagnosis_config.interactive.timeout_seconds}s")
    click.echo()
    click.echo("SSH Settings:")
    click.echo(f"  Default User: {settings.ssh.default_user}")
    click.echo(f"  Default Port: {settings.ssh.default_port}")
    click.echo(f"  Max Connections: {settings.ssh.max_connections}")
    click.echo()
    click.echo("Grafana Settings:")
    click.echo(f"  Base URL: {settings.grafana.base_url}")
    click.echo(f"  Username: {settings.grafana.username}")
    click.echo()
    click.echo("BPF Tools Settings:")
    click.echo(f"  Local Path: {settings.bpf_tools.local_tools_path}")
    click.echo(f"  Deploy Mode: {settings.bpf_tools.deploy_mode}")


if __name__ == "__main__":
    cli()
