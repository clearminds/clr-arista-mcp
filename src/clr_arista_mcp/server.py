"""Arista EOS MCP Server — FastMCP tools for Arista switch management."""

import argparse
import logging
import logging.config
import sys
from typing import Any

from fastmcp import FastMCP

from clr_arista_mcp.config import Settings
from clr_arista_mcp.eos_client import EOSClient
from clr_arista_mcp.middleware import ToolValidationMiddleware

mcp = FastMCP("Arista")
mcp.add_middleware(ToolValidationMiddleware())

# Imported here (not at the top) on purpose: annotations.py needs ``mcp`` from
# this module, so importing it before the ``mcp = FastMCP(...)`` line above
# would be a circular import. Do not move.
from clr_arista_mcp.annotations import (  # noqa: E402
    destructive_tool,
    read_tool,
    remove_non_read_tools,
    write_tool,
)
from clr_arista_mcp._verbs import (  # noqa: E402
    require_show,
    reject_destructive,
    require_destructive,
)

_client: EOSClient | None = None


# ── System tools ─────────────────────────────────────────────────────


@read_tool
def version(host: str) -> dict[str, Any]:
    """Get EOS version, model, serial, and uptime.

    Args:
        host: Switch IP or hostname (e.g. "192.168.1.1").

    Returns:
        A dict with EOS version, model, serial number, and uptime.
    """
    return _client.eapi_run(host, "show version")


# ── Interface tools ──────────────────────────────────────────────────


@read_tool
def interfaces(host: str) -> dict[str, Any]:
    """Get interface status summary (all interfaces).

    Args:
        host: Switch IP or hostname.

    Returns:
        A dict keyed by interface name with status, speed, and type.
    """
    return _client.eapi_run(host, "show interfaces status")


@read_tool
def interface_counters(host: str) -> dict[str, Any]:
    """Get interface error counters.

    Args:
        host: Switch IP or hostname.

    Returns:
        A dict of interface counters including errors and discards.
    """
    return _client.eapi_run(host, "show interfaces counters errors")


# ── L2 tools ─────────────────────────────────────────────────────────


@read_tool
def vlans(host: str) -> dict[str, Any]:
    """List all VLANs configured on the switch.

    Args:
        host: Switch IP or hostname.

    Returns:
        A dict of VLANs with their names and assigned interfaces.
    """
    return _client.eapi_run(host, "show vlan brief")


@read_tool
def mac_table(
    host: str,
    vlan: int | None = None,
) -> dict[str, Any]:
    """Get MAC address table, optionally filtered by VLAN.

    Args:
        host: Switch IP or hostname.
        vlan: VLAN ID to filter by (omit for all).

    Returns:
        A dict containing MAC address entries.
    """
    cmd = f"show mac address-table vlan {vlan}" if vlan else "show mac address-table"
    return _client.eapi_run(host, cmd)


@read_tool
def lldp(host: str) -> dict[str, Any]:
    """Get LLDP neighbor information.

    Args:
        host: Switch IP or hostname.

    Returns:
        A dict of LLDP neighbor entries per interface.
    """
    return _client.eapi_run(host, "show lldp neighbors")


# ── L3 tools ─────────────────────────────────────────────────────────


@read_tool
def arp(
    host: str,
    vrf: str | None = None,
) -> dict[str, Any]:
    """Get ARP table, optionally filtered by VRF.

    Args:
        host: Switch IP or hostname.
        vrf: VRF name to filter by (e.g. "management").

    Returns:
        A dict containing ARP table entries.
    """
    cmd = f"show arp vrf {vrf}" if vrf else "show arp"
    return _client.eapi_run(host, cmd)


@read_tool
def ip_interfaces(host: str) -> dict[str, Any]:
    """Get IP interface brief — interface IPs and status.

    Args:
        host: Switch IP or hostname.

    Returns:
        A dict of interfaces with their IP addresses and status.
    """
    return _client.eapi_run(host, "show ip interface brief")


# ── Routing tools ────────────────────────────────────────────────────


@read_tool
def bgp_summary(host: str) -> dict[str, Any]:
    """Get BGP peer summary.

    Args:
        host: Switch IP or hostname.

    Returns:
        A dict with BGP neighbor states, prefix counts, and uptime.
    """
    return _client.eapi_run(host, "show ip bgp summary")


@read_tool
def routes(host: str) -> dict[str, Any]:
    """Get IP routing table summary.

    Args:
        host: Switch IP or hostname.

    Returns:
        A dict with route counts per protocol and total.
    """
    return _client.eapi_run(host, "show ip route summary")


# ── Config tools ─────────────────────────────────────────────────────


@read_tool
def config(
    host: str,
    section: str | None = None,
) -> str:
    """Get running configuration, optionally filtered by section.

    Args:
        host: Switch IP or hostname.
        section: Config section to filter (e.g. "router bgp", "interface Ethernet1").

    Returns:
        The running configuration as a string.
    """
    cmd = f"show running-config section {section}" if section else "show running-config"
    result = _client.eapi_run(host, cmd, fmt="text")
    if isinstance(result, dict):
        return result.get("output", str(result))
    return str(result)


# ── Raw tools ────────────────────────────────────────────────────────


@write_tool
def cmd(
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

    Returns:
        The parsed result (dict for JSON format, string for text).
    """
    reject_destructive(command)
    return _client.eapi_run(host, command, fmt)


@write_tool
def multi(
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

    Returns:
        A list of results, one per command.
    """
    for cmd in commands:
        reject_destructive(cmd)
    return _client.eapi_call(host, commands, fmt)


@destructive_tool
def configure(
    host: str,
    commands: list[str | dict[str, Any]],
) -> str:
    """Apply configuration commands via eAPI session (atomic).

    Commands are wrapped in a configure session — all-or-nothing apply.
    Use 'config' to review the running config before changes.

    Args:
        host: Switch IP or hostname.
        commands: List of config commands (e.g. ["interface Ethernet1", "description Uplink"]).
            An entry may instead be a dict {"cmd": ..., "input": ...} to supply
            multi-line input to commands that prompt for a body, such as
            ``comment`` or ``banner``. Note a bare "!! text" string is rejected
            by eAPI — use ``comment`` or the dict form.

    Returns:
        A confirmation message with the number of commands applied.
    """
    _client.eapi_configure(host, commands)
    return f"Applied {len(commands)} config commands on {host}"


@read_tool
def config_sessions(host: str) -> dict[str, Any]:
    """List configuration sessions on a switch.

    Use before configuring to see whether someone is mid-edit. A *pending*
    session holds uncommitted changes that are invisible in running-config
    until committed. Up to 5 pending sessions can coexist, so an existing
    session does NOT block you from making your own change.

    EOS retains only ONE *completed* session and evicts the oldest
    automatically, so a leftover completed session is harmless — it is only a
    problem if a new session reuses its exact name.

    Args:
        host: Switch IP or hostname.

    Returns:
        Sessions keyed by name with their state, plus the session limits.
    """
    return _client.eapi_sessions(host)


@write_tool
def session_stage(
    host: str,
    session: str,
    commands: list[str | dict[str, Any]],
) -> str:
    """Stage config in a named session WITHOUT committing it.

    The "propose" half of propose -> review -> commit. Creates the session if
    it does not exist, resumes it if already pending. Nothing reaches
    running-config until `session_commit`. Review first with
    `session_diff`, or discard with `session_abort`.

    Args:
        host: Switch IP or hostname.
        session: Session name. Pick something identifiable, not a shared name.
        commands: Config commands; entries may be dicts carrying multi-line
            input (see `configure`).

    Returns:
        A confirmation message.
    """
    _client.eapi_session_stage(host, session, commands)
    return (
        f"Staged {len(commands)} commands in session {session!r} on {host} "
        f"(not committed — review with session_diff)"
    )


@read_tool
def session_diff(host: str, session: str) -> str:
    """Show what a pending session would change, as a unified diff.

    Args:
        host: Switch IP or hostname.
        session: Session name.

    Returns:
        Diff of the session config against running-config; empty if no change.
    """
    return _client.eapi_session_diff(host, session)


@destructive_tool
def session_commit(host: str, session: str) -> str:
    """Commit a pending session, applying its changes to running-config.

    EOS does NOT detect overlapping edits: if another session changed the same
    object, the last commit silently wins with no warning. Review
    `session_diff` first. Commits are not saved to startup-config —
    follow with `write memory` if the change should survive a reload.

    Args:
        host: Switch IP or hostname.
        session: Session name.

    Returns:
        A confirmation message.
    """
    _client.eapi_session_commit(host, session)
    return f"Committed session {session!r} on {host}"


@destructive_tool
def session_abort(host: str, session: str) -> str:
    """Discard a session and all of its uncommitted changes.

    Args:
        host: Switch IP or hostname.
        session: Session name.

    Returns:
        A confirmation message.
    """
    _client.eapi_session_abort(host, session)
    return f"Aborted session {session!r} on {host}"


@destructive_tool
def comment(
    host: str,
    section: str,
    text: str,
) -> str:
    """Set a persistent ``!!`` comment on a config section.

    EOS stores the comment in running-config (and startup-config once saved),
    so this is a durable annotation — unlike a "!" line, which is stripped.
    Useful for recording provenance, e.g. the Nodus network description behind
    a VLAN whose name is limited to 32 characters.

    Only sections that support the ``comment`` sub-command work — notably
    ``interface X`` and ``vlan N``. Global level is not supported, and
    ``username`` has no sub-mode so users cannot carry a comment.

    Args:
        host: Switch IP or hostname.
        section: Config section to enter, e.g. "vlan 1142" or "interface Ethernet1".
        text: Comment body. May contain spaces and UTF-8; pass an empty string
            to remove an existing comment.

    Returns:
        A confirmation message.
    """
    if not text.strip():
        _client.eapi_configure(host, [section, "no comment"])
        return f"Removed comment on {section} on {host}"

    body = text if text.endswith("\n") else text + "\n"
    _client.eapi_configure(host, [section, {"cmd": "comment", "input": body}])
    return f"Set comment on {section} on {host}"


@destructive_tool
def ssh(
    host: str,
    command: str,
) -> str:
    """Execute an EOS command via SSH.

    Fallback when eAPI is unavailable or for commands that need text output.
    Append '| json' to get JSON output from SSH.

    Args:
        host: Switch IP or hostname.
        command: EOS CLI command.

    Returns:
        The command output as text.
    """
    return _client.ssh_command(host, command)


# ── Generic-exec splits ──────────────────────────────────────────────


@read_tool
def show(host: str, command: str, fmt: str = "json") -> Any:
    """Execute a read-only EOS 'show ...' command via eAPI.

    Refuses any command that is not a show command. Use ``cmd``
    for non-destructive non-show commands and ``cmd_destructive``
    for reload/write erase/clear/delete file.

    Args:
        host: Switch IP or hostname.
        command: EOS show command (e.g. "show ip ospf neighbor").
        fmt: Output format — "json" or "text".

    Returns:
        Parsed result.
    """
    require_show(command)
    return _client.eapi_run(host, command, fmt)


@read_tool
def show_multi(host: str, commands: list[str], fmt: str = "json") -> list[Any]:
    """Execute multiple read-only EOS show commands in a single eAPI call.

    Refuses if any command in the list is not a show command.

    Args:
        host: Switch IP or hostname.
        commands: List of EOS show commands.
        fmt: Output format — "json" or "text".

    Returns:
        A list of results, one per command.
    """
    for cmd in commands:
        require_show(cmd)
    return _client.eapi_call(host, commands, fmt)


@destructive_tool
def cmd_destructive(host: str, command: str, fmt: str = "json") -> Any:
    """Execute a destructive EOS command (reload, write erase, clear, delete file).

    Refuses anything that is not destructive — use ``cmd`` for
    write commands and ``show`` for show commands.

    Args:
        host: Switch IP or hostname.
        command: EOS destructive command.
        fmt: Output format — "json" or "text".

    Returns:
        Parsed result.
    """
    require_destructive(command)
    return _client.eapi_run(host, command, fmt)


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
    parser.add_argument(
        "--read-only",
        action="store_true",
        default=None,
        help="Run in read-only mode (hide write tools)",
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

    creds = settings.load_credentials()

    logger.info("Starting Arista EOS MCP Server (user: %s)", creds.get("username", ""))
    _client = EOSClient(
        username=creds.get("username", ""),
        password=creds.get("password", ""),
        ssh_key=creds.get("ssh_key", ""),
        devices=creds.get("devices", {}),
    )

    read_only = (
        args.read_only if args.read_only is not None else settings.arista_read_only
    )
    if read_only:
        removed = remove_non_read_tools(mcp)
        logger.info("Read-only mode: %d non-read tools removed", removed)

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
