"""Verb-guard helpers for the generic-exec arista_* tools.

The annotations metadata is static per registered tool, so we split the
generic exec entrypoint into read / write / destructive variants and use
these helpers to enforce that the command argument matches the variant.
"""

from __future__ import annotations

from fastmcp.exceptions import ToolError

# Read-only EOS commands. We accept either bare `show ...` or
# `enable show ...` (priv-exec prefix).
_SHOW_PREFIXES = ("show ", "enable show ")

# Destructive verbs. Anything starting with one of these — at the start
# of the command, after optional whitespace — is rejected by the
# write variant and required by the destructive variant.
_DESTRUCTIVE_PREFIXES = (
    "reload",
    "write erase",
    "clear ",
    "delete file:",
    "delete flash:",
)


def _normalize(cmd: str) -> str:
    return cmd.strip().lower()


def is_show(cmd: str) -> bool:
    """Return True if ``cmd`` is a read-only EOS show command."""
    n = _normalize(cmd)
    return any(n.startswith(p) for p in _SHOW_PREFIXES)


def is_destructive(cmd: str) -> bool:
    """Return True if ``cmd`` starts with a destructive EOS verb."""
    n = _normalize(cmd)
    return any(n.startswith(p) for p in _DESTRUCTIVE_PREFIXES)


def require_show(cmd: str) -> None:
    """Raise ``ToolError`` if ``cmd`` is not a read-only show command."""
    if not is_show(cmd):
        raise ToolError(
            f"Command {cmd!r} is not a 'show' command; "
            f"use arista_cmd or arista_cmd_destructive instead."
        )


def reject_destructive(cmd: str) -> None:
    """Raise ``ToolError`` if ``cmd`` is destructive."""
    if is_destructive(cmd):
        raise ToolError(
            f"Command {cmd!r} is destructive; "
            f"use arista_cmd_destructive instead."
        )


def require_destructive(cmd: str) -> None:
    """Raise ``ToolError`` if ``cmd`` is NOT destructive."""
    if not is_destructive(cmd):
        raise ToolError(
            f"Command {cmd!r} is not destructive; "
            f"use arista_cmd or arista_show instead."
        )
