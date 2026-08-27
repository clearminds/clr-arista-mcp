"""Tests for config-session handling and multi-line eAPI input."""

from __future__ import annotations

from typing import Any

import pytest

from clr_arista_mcp.eos_client import EOSClient


class _RecordingClient(EOSClient):
    """EOSClient that records eapi_call batches instead of talking to a switch."""

    def __init__(self) -> None:  # noqa: D107 - test double, skip base __init__
        self.batches: list[list[Any]] = []

    def eapi_call(  # type: ignore[override]
        self,
        host: str,
        commands: list[Any],
        fmt: str = "json",
    ) -> list[Any]:
        self.batches.append(list(commands))
        return [{} for _ in commands]


@pytest.fixture
def client() -> _RecordingClient:
    return _RecordingClient()


def test_configure_wraps_in_session_and_commits(client: _RecordingClient) -> None:
    client.eapi_configure("sw1", ["vlan 10", "name test"])

    apply_batch = client.batches[0]
    assert apply_batch[0].startswith("configure session ")
    assert apply_batch[1:-1] == ["vlan 10", "name test"]
    assert apply_batch[-1] == "commit"


def test_session_name_is_unique_per_call(client: _RecordingClient) -> None:
    """EOS keeps only ONE completed session, so a fixed name collides with its
    own leftover and every call after the first fails."""
    client.eapi_configure("sw1", ["vlan 10"])
    client.eapi_configure("sw1", ["vlan 11"])

    first = client.batches[0][0]
    second = client.batches[2][0]
    assert first != second
    assert "mcp-config" not in (first, second)


def test_session_is_torn_down_after_commit(client: _RecordingClient) -> None:
    client.eapi_configure("sw1", ["vlan 10"])

    session = client.batches[0][0].removeprefix("configure session ")
    assert client.batches[1] == [f"no configure session {session}"]


def test_cleanup_failure_does_not_mask_apply_error() -> None:
    class _Failing(_RecordingClient):
        def eapi_call(
            self, host: str, commands: list[Any], fmt: str = "json"
        ) -> list[Any]:
            self.batches.append(list(commands))
            if commands[-1] == "commit":
                raise RuntimeError("eAPI error 1002: invalid command")
            raise RuntimeError("cleanup also failed")

    failing = _Failing()
    with pytest.raises(RuntimeError, match="invalid command"):
        failing.eapi_configure("sw1", ["bogus"])


def test_structured_command_with_input_is_passed_through(
    client: _RecordingClient,
) -> None:
    """Multi-line input rides in a dict; a bare '!! text' string is rejected by eAPI."""
    comment = {"cmd": "comment", "input": "nodus-owned nn-136\n"}
    client.eapi_configure("sw1", ["vlan 1142", comment])

    assert client.batches[0][2] == comment


def test_stage_does_not_commit(client: _RecordingClient) -> None:
    """Staging is the 'propose' step — a commit here would defeat the point."""
    client.eapi_session_stage("sw1", "review-me", ["vlan 10", "name test"])

    batch = client.batches[0]
    assert batch[0] == "configure session review-me"
    assert "commit" not in batch


def test_stage_resumes_existing_session_by_name(client: _RecordingClient) -> None:
    client.eapi_session_stage("sw1", "review-me", ["vlan 10"])
    client.eapi_session_stage("sw1", "review-me", ["vlan 11"])

    assert client.batches[0][0] == client.batches[1][0] == "configure session review-me"


def test_commit_and_abort_target_the_named_session(client: _RecordingClient) -> None:
    client.eapi_session_commit("sw1", "review-me")
    client.eapi_session_abort("sw1", "review-me")

    assert client.batches[0] == ["configure session review-me", "commit"]
    assert client.batches[1] == ["configure session review-me abort"]


def test_stage_accepts_structured_commands(client: _RecordingClient) -> None:
    comment = {"cmd": "comment", "input": "why this exists\n"}
    client.eapi_session_stage("sw1", "review-me", ["vlan 1142", comment])

    assert client.batches[0][2] == comment
