"""eAPI and SSH clients for Arista EOS switches."""

import logging
import socket
import ssl
import uuid
from typing import Any

import httpx
import paramiko

# A command is either a plain CLI string, or a mapping carrying multi-line
# input for commands that prompt for a body (``comment``, ``banner``):
#     {"cmd": "comment", "input": "text\n"}
EapiCommand = str | dict[str, Any]

logger = logging.getLogger(__name__)


def _make_ssl_context() -> ssl.SSLContext:
    """Create an SSL context that accepts self-signed certs and legacy ciphers.

    Older EOS versions (e.g. 4.18) only offer legacy cipher suites that
    OpenSSL 3.x rejects at the default security level.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    return ctx


class EOSClient:
    """Arista EOS eAPI (JSON-RPC) + SSH client.

    eAPI is preferred (structured JSON). SSH fallback for when eAPI
    is unavailable or for raw text output.

    Attributes:
        username: Default username for switch authentication.
        password: Default password for switch authentication.
        ssh_key: Path to SSH private key (empty string if unused).
        devices: Per-device credential overrides keyed by hostname.
    """

    def __init__(
        self,
        username: str = "",
        password: str = "",
        ssh_key: str = "",
        devices: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self.ssh_key = ssh_key
        self.devices = devices or {}

    def _get_auth(self, host: str) -> tuple[str, str]:
        """Return username and password for a specific host.

        Per-device credentials from the devices dict take precedence
        over the global defaults.

        Args:
            host: Switch IP or hostname.

        Returns:
            A tuple of (username, password).
        """
        device_creds = self.devices.get(host, {})
        username = device_creds.get("username", self.username)
        password = device_creds.get("password", self.password)
        return username, password

    def _port_open(self, host: str, port: int, timeout: float = 2.0) -> bool:
        """Check if a TCP port is open.

        Args:
            host: Target IP or hostname.
            port: TCP port number.
            timeout: Connection timeout in seconds.

        Returns:
            True if the port accepted a connection, False otherwise.
        """
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, TimeoutError):
            return False

    def _get_eapi_url(self, host: str) -> str:
        """Probe HTTPS then HTTP and return the eAPI URL.

        Args:
            host: Switch IP or hostname.

        Returns:
            The eAPI endpoint URL (HTTPS preferred, HTTP fallback).

        Raises:
            ConnectionError: If neither port 443 nor port 80 is reachable.
        """
        if self._port_open(host, 443):
            return f"https://{host}/command-api"
        if self._port_open(host, 80):
            return f"http://{host}/command-api"
        raise ConnectionError(f"Cannot connect to {host} (ports 443 and 80 closed)")

    def eapi_call(
        self,
        host: str,
        commands: list[EapiCommand],
        fmt: str = "json",
    ) -> list[Any]:
        """Execute EOS CLI commands via eAPI JSON-RPC.

        Args:
            host: Switch IP or hostname.
            commands: List of EOS CLI commands. An entry may be a dict of the
                form ``{"cmd": ..., "input": ...}`` to supply multi-line input
                to commands that prompt for a body, e.g. ``comment`` or
                ``banner``. A bare ``"!! text"`` string is NOT accepted by
                eAPI — use the ``comment`` form instead.
            fmt: Output format — "json" or "text".

        Returns:
            A list of result dicts, one per command.

        Raises:
            ConnectionError: If the switch is unreachable on ports 443/80.
            RuntimeError: If the eAPI response contains an error.
        """
        url = self._get_eapi_url(host)
        username, password = self._get_auth(host)
        payload = {
            "jsonrpc": "2.0",
            "method": "runCmds",
            "params": {
                "version": 1,
                "cmds": commands,
                "format": fmt,
            },
            "id": "mcp-1",
        }

        with httpx.Client(
            auth=(username, password),
            verify=_make_ssl_context(),
            timeout=30.0,
        ) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            err = data["error"]
            raise RuntimeError(f"eAPI error {err.get('code')}: {err.get('message')}")

        return data.get("result", [])

    def eapi_run(self, host: str, command: str, fmt: str = "json") -> Any:
        """Execute a single EOS command via eAPI.

        Args:
            host: Switch IP or hostname.
            command: Single EOS CLI command.
            fmt: Output format.

        Returns:
            The result dict for the command.
        """
        results = self.eapi_call(host, [command], fmt)
        return results[0] if results else {}

    def eapi_configure(self, host: str, commands: list[EapiCommand]) -> list[Any]:
        """Execute configuration commands via eAPI session.

        Wraps commands in configure session for atomic apply.

        The session name is unique per call. EOS retains only ONE *completed*
        session, so a fixed name meant the second call onwards collided with
        its own leftover and failed with "could not run command". The session
        is also torn down after commit so the completed slot is left free.

        Args:
            host: Switch IP or hostname.
            commands: List of config commands. Entries may be dicts carrying
                multi-line input — see :meth:`eapi_call`.

        Returns:
            A list of result dicts for each session command.
        """
        session = f"mcp-{uuid.uuid4().hex[:12]}"
        session_cmds = [f"configure session {session}", *commands, "commit"]
        try:
            return self.eapi_call(host, session_cmds)
        finally:
            # Free the single completed-session slot. Best effort: a failed
            # apply leaves nothing to clean up, and never mask the real error.
            try:
                self.eapi_call(host, [f"no configure session {session}"])
            except Exception:  # noqa: BLE001 - cleanup must not mask the caller's error
                logger.debug("Could not remove config session %s on %s", session, host)

    def eapi_sessions(self, host: str) -> dict[str, Any]:
        """List config sessions on a switch.

        Returns:
            A dict with ``sessions`` (name -> {state, description}) plus the
            ``maxOpenSessions`` / ``maxSavedSessions`` limits. EOS keeps at
            most one *completed* session and evicts the oldest automatically;
            pending sessions are the ones holding uncommitted changes.
        """
        return self.eapi_run(host, "show configuration sessions detail")

    def eapi_session_stage(
        self,
        host: str,
        session: str,
        commands: list[EapiCommand],
    ) -> list[Any]:
        """Apply commands to a named session WITHOUT committing.

        Creates the session if absent, resumes it if already pending. Changes
        stay invisible to running-config until committed, so this is the
        "propose" half of a propose/review/commit workflow.
        """
        return self.eapi_call(host, [f"configure session {session}", *commands])

    def eapi_session_diff(self, host: str, session: str) -> str:
        """Return the pending diff of a session against running-config."""
        result = self.eapi_run(
            host, f"show session-config named {session} diffs", "text"
        )
        return result.get("output", "")

    def eapi_session_commit(self, host: str, session: str) -> list[Any]:
        """Commit a pending session.

        NOTE: EOS does not detect overlapping edits. If two sessions changed
        the same object, the last commit silently wins — review the diff first.
        """
        return self.eapi_call(host, [f"configure session {session}", "commit"])

    def eapi_session_abort(self, host: str, session: str) -> list[Any]:
        """Discard a session and its uncommitted changes."""
        return self.eapi_call(host, [f"configure session {session} abort"])

    def ssh_command(self, host: str, command: str, timeout: float = 30.0) -> str:
        """Execute an EOS command via SSH.

        EOS drops into privilege 15 directly, no 'enable' needed.

        Args:
            host: Switch IP or hostname.
            command: EOS CLI command.
            timeout: SSH timeout in seconds.

        Returns:
            The command output as a string.
        """
        username, password = self._get_auth(host)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs: dict[str, Any] = {
                "hostname": host,
                "port": 22,
                "username": username,
                "timeout": timeout,
                "allow_agent": False,
                "look_for_keys": False,
            }
            if self.ssh_key:
                connect_kwargs["key_filename"] = self.ssh_key
            else:
                connect_kwargs["password"] = password

            client.connect(**connect_kwargs)
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            if err:
                output += f"\n{err}"
            return output.strip()
        finally:
            client.close()
