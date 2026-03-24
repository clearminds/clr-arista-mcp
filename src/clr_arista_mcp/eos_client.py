"""eAPI and SSH clients for Arista EOS switches."""

import logging
import socket
import ssl
from typing import Any

import httpx
import paramiko

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
        commands: list[str],
        fmt: str = "json",
    ) -> list[Any]:
        """Execute EOS CLI commands via eAPI JSON-RPC.

        Args:
            host: Switch IP or hostname.
            commands: List of EOS CLI commands.
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

    def eapi_configure(self, host: str, commands: list[str]) -> list[Any]:
        """Execute configuration commands via eAPI session.

        Wraps commands in configure session for atomic apply.

        Args:
            host: Switch IP or hostname.
            commands: List of config commands.

        Returns:
            A list of result dicts for each session command.
        """
        session_cmds = ["configure session mcp-config"] + commands + ["commit"]
        return self.eapi_call(host, session_cmds)

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
