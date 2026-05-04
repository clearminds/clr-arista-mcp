"""Tests for arista verb-guard helpers."""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from clr_arista_mcp._verbs import (
    is_destructive,
    is_show,
    reject_destructive,
    require_destructive,
    require_show,
)


@pytest.mark.parametrize("cmd", [
    "show version",
    "show ip interface brief",
    "  show vlan",
    "enable show running-config",
    "SHOW VLAN",
])
def test_is_show_accepts(cmd: str) -> None:
    assert is_show(cmd)


@pytest.mark.parametrize("cmd", [
    "configure",
    "reload",
    "write erase",
    "clear counters",
])
def test_is_show_rejects(cmd: str) -> None:
    assert not is_show(cmd)


@pytest.mark.parametrize("cmd", [
    "reload",
    "write erase",
    "clear counters ethernet1",
    "delete file:foo.cfg",
])
def test_is_destructive_accepts(cmd: str) -> None:
    assert is_destructive(cmd)


@pytest.mark.parametrize("cmd", [
    "show version",
    "configure",
    "interface Ethernet1",
])
def test_is_destructive_rejects(cmd: str) -> None:
    assert not is_destructive(cmd)


def test_require_show_raises_on_non_show() -> None:
    with pytest.raises(ToolError):
        require_show("reload")


def test_reject_destructive_raises_on_destructive() -> None:
    with pytest.raises(ToolError):
        reject_destructive("reload")


def test_require_destructive_raises_on_non_destructive() -> None:
    with pytest.raises(ToolError):
        require_destructive("show version")
