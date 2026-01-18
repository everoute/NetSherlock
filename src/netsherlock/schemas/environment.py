"""Environment-related Pydantic models for L2 layer.

These schemas define the network environment information collected
from hosts and VMs for diagnostic purposes.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class NetworkType(str, Enum):
    """Type of network being diagnosed."""

    VM = "vm"
    SYSTEM = "system"


class PhysicalNIC(BaseModel):
    """Physical network interface card information."""

    name: str = Field(..., description="NIC name (e.g., eth0, ens3f0)")
    speed: str = Field(default="unknown", description="Link speed (e.g., 25000Mb/s)")
    is_bond: bool = Field(default=False, description="Whether this is a bond interface")
    bond_type: str = Field(default="", description="Bond type: 'ovs' or 'linux'")
    bond_members: list[str] = Field(default_factory=list, description="Bond member interfaces")
    member_speeds: dict[str, str] = Field(
        default_factory=dict, description="Speed of each bond member"
    )


class VhostInfo(BaseModel):
    """Vhost thread/process information."""

    pid: int = Field(..., description="Vhost process/thread ID")
    name: str = Field(default="", description="Process name")


class VMNicInfo(BaseModel):
    """Single VM network interface information."""

    mac: str = Field(..., description="MAC address")
    vm_nic_name: str = Field(default="", description="NIC name inside VM (e.g., eth0, ens4)")
    vm_ip: str = Field(default="", description="IP address inside VM")
    host_vnet: str = Field(default="", description="vnet interface on host")
    tap_fds: list[int] = Field(default_factory=list, description="TAP file descriptors")
    vhost_fds: list[int] = Field(default_factory=list, description="vhost file descriptors")
    vhost_pids: list[VhostInfo] = Field(
        default_factory=list, description="vhost thread/process info"
    )
    ovs_bridge: str = Field(default="", description="OVS bridge name")
    uplink_bridge: str = Field(default="", description="Uplink OVS bridge (for patch ports)")
    physical_nics: list[PhysicalNIC] = Field(
        default_factory=list, description="Physical NICs on the path"
    )


class VMNetworkEnv(BaseModel):
    """VM network environment information.

    This is the output of collect_vm_network_env tool.
    """

    vm_uuid: str = Field(..., description="VM UUID")
    vm_name: str = Field(default="", description="VM domain name")
    host: str = Field(..., description="Host (hypervisor) IP")
    qemu_pid: int = Field(default=0, description="qemu-kvm process PID")
    nics: list[VMNicInfo] = Field(default_factory=list, description="All VM network interfaces")


class SystemNetworkInfo(BaseModel):
    """System network (OVS internal port) information."""

    port_name: str = Field(..., description="OVS port name (e.g., port-mgt)")
    port_type: str = Field(..., description="Port type: mgt, storage, access, vpc")
    ip_address: str = Field(default="", description="IP address on this port")
    ovs_bridge: str = Field(default="", description="OVS bridge name")
    uplink_bridge: str = Field(default="", description="Uplink bridge for patch port case")
    physical_nics: list[PhysicalNIC] = Field(
        default_factory=list, description="Physical NICs on uplink"
    )


class SystemNetworkEnv(BaseModel):
    """System network environment information.

    This is the output of collect_system_network_env tool.
    """

    host: str = Field(..., description="Host IP address")
    ports: list[SystemNetworkInfo] = Field(
        default_factory=list, description="All OVS internal ports"
    )


class NetworkEndpoint(BaseModel):
    """Network endpoint for path analysis."""

    host: str = Field(..., description="Host IP address")
    vm_id: str | None = Field(default=None, description="VM UUID if applicable")
    vnet: str | None = Field(default=None, description="vnet interface name")
    bridge: str | None = Field(default=None, description="OVS bridge name")
    vhost_pid: int | None = Field(default=None, description="vhost process ID")
    physical_nic: str | None = Field(default=None, description="Physical NIC name")


class PathSegment(BaseModel):
    """Single segment in the network path."""

    name: str = Field(..., description="Segment name (e.g., 'virtio_tx', 'ovs_flow')")
    from_point: str = Field(..., description="Start point description")
    to_point: str = Field(..., description="End point description")
    description: str = Field(default="", description="Segment description")


class NetworkPath(BaseModel):
    """Network path information for measurement planning.

    This is the L2→L3 interface containing environment information
    needed to set up measurements.
    """

    network_type: NetworkType = Field(..., description="VM or system network")
    source: NetworkEndpoint = Field(..., description="Source endpoint")
    target: NetworkEndpoint | None = Field(default=None, description="Target endpoint")
    path_segments: list[PathSegment] = Field(
        default_factory=list, description="Path segments for measurement"
    )
    raw_env: VMNetworkEnv | SystemNetworkEnv | None = Field(
        default=None, description="Raw environment data"
    )

    model_config = {"extra": "allow"}


class FlowInfo(BaseModel):
    """Flow characteristics for measurement targeting.

    Describes the network flow to be measured or diagnosed.
    """

    src_ip: str = Field(..., description="Source IP address")
    dst_ip: str = Field(..., description="Destination IP address")
    protocol: str = Field(default="icmp", description="Protocol (icmp, tcp, udp)")
    src_port: int = Field(default=0, description="Source port (0 for ICMP)")
    dst_port: int = Field(default=0, description="Destination port (0 for ICMP)")
