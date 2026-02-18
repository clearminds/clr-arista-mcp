"""eAPI and SSH clients for Arista EOS switches."""

import logging
import socket
from typing import Any

import httpx
import paramiko

logger = logging.getLogger(__name__)


class EOSClient:
    """Arista EOS eAPI (JSON-RPC) + SSH client.

    eAPI is preferred (structured JSON). SSH fallback for when eAPI
    is unavailable or for raw text output.
    """

    def __init__(self, username: str, password: str, ssh_key: str = "") -> None:
        self.username = username
        self.password = password
        self.ssh_key = ssh_key

    def _port_open(self, host: str, port: int, timeout: float = 2.0) -> bool:
        """Check if a TCP port is open."""
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except (OSError, TimeoutError):
            return False

    def _get_eapi_url(self, host: str) -> str:
        """Probe HTTPS then HTTP, return eAPI URL."""
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

        Returns list of result dicts (one per command).
        """
        url = self._get_eapi_url(host)
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
            auth=(self.username, self.password),
            verify=False,
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

        Returns result dict for the command.
        """
        results = self.eapi_call(host, [command], fmt)
        return results[0] if results else {}

    def eapi_configure(self, host: str, commands: list[str]) -> list[Any]:
        """Execute configuration commands via eAPI session.

        Wraps commands in configure session for atomic apply.

        Args:
            host: Switch IP or hostname.
            commands: List of config commands.

        Returns list of results.
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

        Returns command output as string.
        """
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs: dict[str, Any] = {
                "hostname": host,
                "port": 22,
                "username": self.username,
                "timeout": timeout,
                "allow_agent": False,
                "look_for_keys": False,
            }
            if self.ssh_key:
                connect_kwargs["key_filename"] = self.ssh_key
            else:
                connect_kwargs["password"] = self.password

            client.connect(**connect_kwargs)
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            if err:
                output += f"\n{err}"
            return output.strip()
        finally:
            client.close()
