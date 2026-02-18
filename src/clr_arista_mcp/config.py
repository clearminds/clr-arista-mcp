"""Configuration for Arista EOS MCP Server."""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

CREDS_PATH = Path.home() / ".config" / "arista" / "credentials.json"


class Settings(BaseSettings):
    """Settings loaded from environment variables or credentials file.

    Priority order:
    1. Environment variables (ARISTA_USERNAME, ARISTA_PASSWORD, ARISTA_SSH_KEY)
    2. ~/.config/arista/credentials.json
    """

    arista_username: str = ""
    arista_password: str = ""
    arista_ssh_key: str = ""  # Path to SSH private key (optional)
    arista_transport: str = "stdio"
    arista_log_level: str = "INFO"

    model_config = {"env_prefix": ""}

    def load_credentials(self) -> dict[str, Any]:
        """Load credentials with env-first, config-file-fallback pattern.

        Returns:
            Dict with username, password, and optional ssh_key.
        """
        creds: dict[str, Any] = {}

        # 1. FIRST: Check environment variables
        if self.arista_username:
            creds["username"] = self.arista_username
        if self.arista_password:
            creds["password"] = self.arista_password
        if self.arista_ssh_key:
            creds["ssh_key"] = self.arista_ssh_key

        # If we have username and (password or ssh_key) from env, return early
        if creds.get("username") and (creds.get("password") or creds.get("ssh_key")):
            logger.info("Using Arista credentials from environment variables")
            return creds

        # 2. FALLBACK: Check credentials.json file
        if CREDS_PATH.exists():
            try:
                file_creds: dict[str, Any] = json.loads(CREDS_PATH.read_text())

                # Only use file values if NOT already set by env vars
                if "username" in file_creds and not creds.get("username"):
                    creds["username"] = file_creds["username"]
                if "password" in file_creds and not creds.get("password"):
                    creds["password"] = file_creds["password"]
                if "ssh_key" in file_creds and not creds.get("ssh_key"):
                    creds["ssh_key"] = file_creds["ssh_key"]

                logger.info(f"Loaded Arista credentials from {CREDS_PATH}")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load {CREDS_PATH}: {e}")

        if not (creds.get("username") and (creds.get("password") or creds.get("ssh_key"))):
            logger.warning(
                "No Arista credentials configured. Set ARISTA_USERNAME and "
                "(ARISTA_PASSWORD or ARISTA_SSH_KEY) env vars or create "
                f"{CREDS_PATH}"
            )

        return creds
