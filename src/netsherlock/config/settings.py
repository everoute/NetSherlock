"""Configuration settings for NetSherlock.

Uses pydantic-settings for type-safe configuration loading from
environment variables and .env files.
"""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from netsherlock.schemas.config import (
    AutonomousConfig,
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
    InteractiveConfig,
)


class SSHSettings(BaseSettings):
    """SSH connection settings."""

    model_config = SettingsConfigDict(env_prefix="SSH_")

    default_user: str = Field(default="root", description="Default SSH username")
    default_port: int = Field(default=22, description="Default SSH port")
    private_key_path: Path | None = Field(
        default=None, description="Path to SSH private key"
    )
    password: SecretStr | None = Field(default=None, description="SSH password")
    connect_timeout: int = Field(default=10, description="Connection timeout in seconds")
    command_timeout: int = Field(default=60, description="Command execution timeout")
    max_connections: int = Field(default=10, description="Max concurrent connections")
    retry_attempts: int = Field(default=3, description="Connection retry attempts")
    retry_delay: float = Field(default=1.0, description="Delay between retries in seconds")


class GrafanaSettings(BaseSettings):
    """Grafana/VictoriaMetrics/Loki connection settings."""

    model_config = SettingsConfigDict(env_prefix="GRAFANA_")

    base_url: str = Field(
        default="http://192.168.79.79/grafana",
        description="Grafana base URL",
    )
    username: str = Field(default="", description="Grafana username (set via GRAFANA_USERNAME env var)")
    password: SecretStr | None = Field(
        default=None,
        description="Grafana password (required, set via GRAFANA_PASSWORD env var)",
    )
    timeout: int = Field(default=30, description="API request timeout in seconds")

    # Data source IDs (from Grafana configuration)
    victoriametrics_ds_id: int = Field(default=1, description="VictoriaMetrics datasource ID")
    clickhouse_ds_id: int = Field(default=2, description="ClickHouse datasource ID")
    loki_ds_id: int = Field(default=3, description="Loki datasource ID")
    traffic_api_ds_id: int = Field(default=8, description="Traffic API datasource ID")


class BPFToolsSettings(BaseSettings):
    """BPF measurement tools settings."""

    model_config = SettingsConfigDict(env_prefix="BPF_")

    # Local tool repository path
    local_tools_path: Path = Field(
        default=Path.home() / "workspace/troubleshooting-tools/measurement-tools",
        description="Local path to BPF measurement tools",
    )
    # Remote deployment path
    remote_tools_path: Path = Field(
        default=Path("/tmp/netsherlock-tools"),
        description="Remote path for deployed tools",
    )
    # Deployment mode: auto, scp, or pre-deployed
    deploy_mode: Literal["auto", "scp", "pre-deployed"] = Field(
        default="auto",
        description="Tool deployment mode",
    )
    # Python interpreter on remote hosts
    remote_python: str = Field(
        default="/usr/bin/python3",
        description="Python interpreter path on remote hosts",
    )


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Log level"
    )
    format: Literal["json", "console"] = Field(
        default="console", description="Log format"
    )
    file_path: Path | None = Field(default=None, description="Log file path")


class MeasurementSettings(BaseSettings):
    """Measurement execution settings."""

    model_config = SettingsConfigDict(env_prefix="MEASUREMENT_")

    default_duration: int = Field(default=30, description="Default measurement duration (sec)")
    receiver_ready_timeout: int = Field(
        default=10, description="Timeout for receiver ready signal (sec)"
    )
    receiver_startup_delay: float = Field(
        default=1.0, description="Minimum delay before starting sender (sec)"
    )
    max_concurrent_measurements: int = Field(
        default=5, description="Max concurrent measurements"
    )


class LLMSettings(BaseSettings):
    """LLM (Claude Agent SDK) configuration settings.

    Note: Agent SDK uses Claude Code's authentication. Options:
      1. Run `claude` command to login - SDK uses that auth automatically
      2. Set ANTHROPIC_API_KEY environment variable
      3. Use cloud providers via CLAUDE_CODE_USE_BEDROCK/VERTEX/FOUNDRY=1
    """

    model_config = SettingsConfigDict(env_prefix="LLM_")

    model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Claude model (claude-haiku-4-5-20251001, claude-sonnet-4-5-20250929, etc.)",
    )
    max_turns: int | None = Field(
        default=None,
        description="Maximum agent turns (None for unlimited)",
    )
    max_budget_usd: float | None = Field(
        default=None,
        description="Maximum budget in USD (None for unlimited)",
    )


class DiagnosisSettings(BaseSettings):
    """Diagnosis mode settings.

    Wraps DiagnosisConfig for environment-based configuration.
    Supports dual-mode operation (autonomous vs interactive).
    """

    model_config = SettingsConfigDict(env_prefix="DIAGNOSIS_")

    default_mode: DiagnosisMode = Field(
        default=DiagnosisMode.INTERACTIVE,
        description="Default diagnosis mode (autonomous or interactive)",
    )

    # Autonomous mode settings
    autonomous_enabled: bool = Field(
        default=False,
        description="Enable autonomous mode",
    )
    autonomous_auto_agent_loop: bool = Field(
        default=False,
        description="Auto-start agent loop on alert",
    )
    autonomous_interrupt_enabled: bool = Field(
        default=True,
        description="Allow interrupting autonomous execution",
    )
    autonomous_known_alert_types: list[str] = Field(
        default_factory=lambda: [
            # Production alert types
            "VMNetworkLatency",
            "VMNetworkLatencyHigh",
            "VMNetworkLatencyCritical",
            "VMNetworkPacketLoss",
            "HostNetworkLatency",
            # Test/Dev alert types
            "NetSherlockHostLatencyDevTest",
            "HostNetworkPacketLossDevTest",
        ],
        description="Alert types that can trigger autonomous mode",
    )

    # Interactive mode settings
    interactive_checkpoints: list[CheckpointType] = Field(
        default_factory=lambda: [
            CheckpointType.PROBLEM_CLASSIFICATION,
            CheckpointType.MEASUREMENT_PLAN,
        ],
        description="Checkpoints requiring user confirmation",
    )
    interactive_timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Timeout for user input at checkpoints",
    )
    interactive_auto_confirm_on_timeout: bool = Field(
        default=False,
        description="Auto-confirm and continue if user times out",
    )

    def to_diagnosis_config(self) -> DiagnosisConfig:
        """Convert settings to DiagnosisConfig instance.

        Returns:
            DiagnosisConfig with values from settings
        """
        return DiagnosisConfig(
            default_mode=self.default_mode,
            autonomous=AutonomousConfig(
                enabled=self.autonomous_enabled,
                auto_agent_loop=self.autonomous_auto_agent_loop,
                interrupt_enabled=self.autonomous_interrupt_enabled,
                known_alert_types=self.autonomous_known_alert_types,
            ),
            interactive=InteractiveConfig(
                checkpoints=self.interactive_checkpoints,
                timeout_seconds=self.interactive_timeout_seconds,
                auto_confirm_on_timeout=self.interactive_auto_confirm_on_timeout,
            ),
        )


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    # Application info
    app_name: str = Field(default="netsherlock", description="Application name")
    debug: bool = Field(default=False, description="Debug mode")

    # Nested settings
    ssh: SSHSettings = Field(default_factory=SSHSettings)
    grafana: GrafanaSettings = Field(default_factory=GrafanaSettings)
    bpf_tools: BPFToolsSettings = Field(default_factory=BPFToolsSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    measurement: MeasurementSettings = Field(default_factory=MeasurementSettings)
    diagnosis: DiagnosisSettings = Field(default_factory=DiagnosisSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)

    # Node local log paths
    node_log_base_path: Path = Field(
        default=Path("/var/log/zbs"),
        description="Base path for node local logs",
    )

    # Engine selection
    diagnosis_engine: Literal["controller", "orchestrator"] = Field(
        default="controller",
        description="Diagnosis engine type (DIAGNOSIS_ENGINE env var)",
    )

    # Path configuration
    global_inventory_path: Path | None = Field(
        default=None,
        description="Path to global inventory YAML (GLOBAL_INVENTORY_PATH env var)",
    )
    project_path: Path | None = Field(
        default=None,
        description="Path to netsherlock project root (PROJECT_PATH env var)",
    )

    # Webhook API security
    webhook_api_key: SecretStr | None = Field(
        default=None,
        description="API key for webhook authentication (set via WEBHOOK_API_KEY env var)",
    )
    webhook_allow_insecure: bool = Field(
        default=False,
        description="Allow unauthenticated webhook access (development only, set via WEBHOOK_ALLOW_INSECURE env var)",
    )

    def get_diagnosis_config(self) -> DiagnosisConfig:
        """Get DiagnosisConfig from settings.

        Returns:
            DiagnosisConfig instance built from diagnosis settings
        """
        return self.diagnosis.to_diagnosis_config()


# Global settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get application settings (singleton)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Reset settings (for testing)."""
    global _settings
    _settings = None
