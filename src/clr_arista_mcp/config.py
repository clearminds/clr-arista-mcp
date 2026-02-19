"""Configuration for Arista EOS MCP Server."""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

CREDS_PATH = Path.home() / ".config" / "arista" / "credentials.json"


class Settings(BaseSettings):
    """Settings loaded from credentials file or environment variables.

    Priority order:
    1. ~/.config/arista/credentials.json
    2. Environment variables (ARISTA_USERNAME, ARISTA_PASSWORD, ARISTA_SSH_KEY) - override
    """

    arista_username: str = ""
    arista_password: str = ""
    arista_ssh_key: str = ""  # Path to SSH private key (optional)
    arista_transport: str = "stdio"
    arista_log_level: str = "INFO"

    model_config = {"env_prefix": ""}

    def load_credentials(self) -> dict[str, Any]:
        """Load credentials with config-file-first, env-override pattern.

        Returns:
            Dict with username, password, and optional ssh_key.
        """
        creds: dict[str, Any] = {}

        # 1. FIRST: Load from environment variables (base/fallback)
        if self.arista_username:
            creds["username"] = self.arista_username
        if self.arista_password:
            creds["password"] = self.arista_password
        if self.arista_ssh_key:
            creds["ssh_key"] = self.arista_ssh_key

        # 2. THEN: Override with credentials.json file (takes priority)
        if CREDS_PATH.exists():
            try:
                file_creds: dict[str, Any] = json.loads(CREDS_PATH.read_text())

                if "username" in file_creds:
                    creds["username"] = file_creds["username"]
                if "password" in file_creds:
                    creds["password"] = file_creds["password"]
                if "ssh_key" in file_creds:
                    creds["ssh_key"] = file_creds["ssh_key"]
                if "devices" in file_creds:
                    creds["devices"] = file_creds["devices"]

                logger.info(f"Loaded Arista credentials from {CREDS_PATH}")
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to load {CREDS_PATH}: {e}")

        creds.setdefault("devices", {})

        if not (creds.get("username") and (creds.get("password") or creds.get("ssh_key"))):
            if not creds["devices"]:
                logger.warning(
                    "No Arista credentials configured. Set ARISTA_USERNAME and "
                    "(ARISTA_PASSWORD or ARISTA_SSH_KEY) env vars or create "
                    f"{CREDS_PATH}"
                )

        return creds
