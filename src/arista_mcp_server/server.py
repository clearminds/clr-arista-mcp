"""Arista EOS MCP Server — FastMCP tools for Arista switch management."""

import argparse
import logging
import logging.config
import sys
from typing import Any

from fastmcp import FastMCP

from arista_mcp_server.config import Settings
from arista_mcp_server.eos_client import EOSClient

mcp = FastMCP("Arista")
_client: EOSClient | None = None



# ── System tools ─────────────────────────────────────────────────────


@mcp.tool
def arista_version(host: str) -> dict[str, Any]:
    """Get EOS version, model, serial, and uptime.

    Args:
        host: Switch IP or hostname (e.g. "10.20.10.218").
    """
    return _client.eapi_run(host, "show version")


# ── Interface tools ──────────────────────────────────────────────────


@mcp.tool
def arista_interfaces(host: str) -> dict[str, Any]:
    """Get interface status summary (all interfaces).

    Args:
        host: Switch IP or hostname.

    Returns dict keyed by interface name with status, speed, type.
    """
    return _client.eapi_run(host, "show interfaces status")


@mcp.tool
def arista_interface_counters(host: str) -> dict[str, Any]:
    """Get interface error counters.

    Args:
        host: Switch IP or hostname.

    Returns interface counters including errors, discards.
    """
    return _client.eapi_run(host, "show interfaces counters errors")


# ── L2 tools ─────────────────────────────────────────────────────────


@mcp.tool
def arista_vlans(host: str) -> dict[str, Any]:
    """List all VLANs configured on the switch.

    Args:
        host: Switch IP or hostname.
    """
    return _client.eapi_run(host, "show vlan brief")


@mcp.tool
def arista_mac_table(
    host: str,
    vlan: int | None = None,
) -> dict[str, Any]:
    """Get MAC address table, optionally filtered by VLAN.

    Args:
        host: Switch IP or hostname.
        vlan: VLAN ID to filter by (omit for all).
    """
    cmd = f"show mac address-table vlan {vlan}" if vlan else "show mac address-table"
    return _client.eapi_run(host, cmd)


@mcp.tool
def arista_lldp(host: str) -> dict[str, Any]:
    """Get LLDP neighbor information.

    Args:
        host: Switch IP or hostname.
    """
    return _client.eapi_run(host, "show lldp neighbors")


# ── L3 tools ─────────────────────────────────────────────────────────


@mcp.tool
def arista_arp(
    host: str,
    vrf: str | None = None,
) -> dict[str, Any]:
    """Get ARP table, optionally filtered by VRF.

    Args:
        host: Switch IP or hostname.
        vrf: VRF name to filter by (e.g. "management").
    """
    cmd = f"show arp vrf {vrf}" if vrf else "show arp"
    return _client.eapi_run(host, cmd)


@mcp.tool
def arista_ip_interfaces(host: str) -> dict[str, Any]:
    """Get IP interface brief — interface IPs and status.

    Args:
        host: Switch IP or hostname.
    """
    return _client.eapi_run(host, "show ip interface brief")


# ── Routing tools ────────────────────────────────────────────────────


@mcp.tool
def arista_bgp_summary(host: str) -> dict[str, Any]:
    """Get BGP peer summary.

    Args:
        host: Switch IP or hostname.

    Returns BGP neighbor states, prefix counts, uptime.
    """
    return _client.eapi_run(host, "show ip bgp summary")


@mcp.tool
def arista_routes(host: str) -> dict[str, Any]:
    """Get IP routing table summary.

    Args:
        host: Switch IP or hostname.
    """
    return _client.eapi_run(host, "show ip route summary")


# ── Config tools ─────────────────────────────────────────────────────


@mcp.tool
def arista_config(
    host: str,
    section: str | None = None,
) -> str:
    """Get running configuration, optionally filtered by section.

    Args:
        host: Switch IP or hostname.
        section: Config section to filter (e.g. "router bgp", "interface Ethernet1").
    """
    cmd = f"show running-config section {section}" if section else "show running-config"
    result = _client.eapi_run(host, cmd, fmt="text")
    if isinstance(result, dict):
        return result.get("output", str(result))
    return str(result)


# ── Raw tools ────────────────────────────────────────────────────────


@mcp.tool
def arista_cmd(
    host: str,
    command: str,
    fmt: str = "json",
) -> Any:
    """Execute any EOS show command via eAPI.

    Args:
        host: Switch IP or hostname.
        command: EOS CLI command (e.g. "show ip ospf neighbor").
        fmt: Output format — "json" (structured) or "text" (raw).
            Use "text" as fallback for older EOS or unsupported JSON output.

    Returns parsed result.
    """
    return _client.eapi_run(host, command, fmt)


@mcp.tool
def arista_multi(
    host: str,
    commands: list[str],
    fmt: str = "json",
) -> list[Any]:
    """Execute multiple EOS commands in a single eAPI call.

    More efficient than multiple individual calls.

    Args:
        host: Switch IP or hostname.
        commands: List of EOS CLI commands.
        fmt: Output format.

    Returns list of results (one per command).
    """
    return _client.eapi_call(host, commands, fmt)


@mcp.tool
def arista_configure(
    host: str,
    commands: list[str],
) -> str:
    """Apply configuration commands via eAPI session (atomic).

    Commands are wrapped in a configure session — all-or-nothing apply.
    Use 'arista_config' to review the running config before changes.

    Args:
        host: Switch IP or hostname.
        commands: List of config commands (e.g. ["interface Ethernet1", "description Uplink"]).

    Returns confirmation message.
    """
    _client.eapi_configure(host, commands)
    return f"Applied {len(commands)} config commands on {host}"


@mcp.tool
def arista_ssh(
    host: str,
    command: str,
) -> str:
    """Execute an EOS command via SSH.

    Fallback when eAPI is unavailable or for commands that need text output.
    Append '| json' to get JSON output from SSH.

    Args:
        host: Switch IP or hostname.
        command: EOS CLI command.

    Returns command output as text.
    """
    return _client.ssh_command(host, command)


# ── Main entry point ─────────────────────────────────────────────────


def main() -> None:
    """Main entry point for the Arista EOS MCP server."""
    global _client

    settings = Settings()

    parser = argparse.ArgumentParser(description="Arista EOS MCP Server")
    parser.add_argument(
        "--transport", type=str, choices=["stdio", "http"], default=None
    )
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    args = parser.parse_args()

    transport = args.transport or settings.arista_transport
    log_level = args.log_level or settings.arista_log_level

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "console": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "console",
                    "stream": "ext://sys.stderr",
                }
            },
            "root": {"level": log_level, "handlers": ["console"]},
        }
    )

    logger = logging.getLogger(__name__)

    if not settings.arista_password:
        logger.error("MIKROTIK_PASSWORD is required")
        sys.exit(1)

    logger.info("Starting Arista EOS MCP Server (user: %s)", settings.arista_username)
    _client = EOSClient(
        settings.arista_username,
        settings.arista_password,
        settings.arista_ssh_key,
    )

    try:
        if transport == "stdio":
            mcp.run(transport="stdio")
        else:
            mcp.run(transport="http", host=args.host, port=args.port)
    except Exception as e:
        logger.error("Failed to start MCP server: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
