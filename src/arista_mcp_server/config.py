"""Configuration for Arista EOS MCP Server."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings loaded from environment variables."""

    arista_username: str = ""
    arista_password: str = ""
    arista_ssh_key: str = ""  # Path to SSH private key (optional)
    arista_transport: str = "stdio"
    arista_log_level: str = "INFO"
