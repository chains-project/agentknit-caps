"""Tests for strict capability policy parsing."""

from pathlib import Path

import pytest

from agentknit_guarantees.policy import PolicyError, load_policy


def test_empty_policy_has_no_authority() -> None:
    policy = load_policy()
    assert policy.mounts == ()
    assert policy.env == {}
    assert policy.functions == ()


def test_workspace_policy(tmp_path: Path) -> None:
    policy = load_policy(data={"fs": [{"host_path": str(tmp_path), "virtual_path": "/w", "mode": "rw"}]})
    assert policy.mounts[0].mode == "rw"
    assert policy.public_dict()["fs"][0]["host_path"] == str(tmp_path.resolve())


@pytest.mark.parametrize("path", ["relative", "/../x", "/a/../x", "/", "", None])
def test_rejects_unsafe_virtual_paths(tmp_path: Path, path: object) -> None:
    with pytest.raises(PolicyError):
        load_policy(data={"fs": [{"host_path": str(tmp_path), "virtual_path": path, "mode": "ro"}]})


def test_rejects_unknown_keys_and_missing_host(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="unknown"):
        load_policy(data={"network": True})
    with pytest.raises(PolicyError, match="does not resolve"):
        load_policy(data={"fs": [{"host_path": str(tmp_path / "none"), "virtual_path": "/x", "mode": "ro"}]})


def test_rejects_overlap_and_bad_limits(tmp_path: Path) -> None:
    (tmp_path / "child").mkdir()
    with pytest.raises(PolicyError, match="overlapping host"):
        load_policy(data={"fs": [
            {"host_path": str(tmp_path), "virtual_path": "/a", "mode": "ro"},
            {"host_path": str(tmp_path / "child"), "virtual_path": "/b", "mode": "ro"},
        ]})
    for limits in ({"source_bytes": 0}, {"wall_seconds": 0}, {"total_calls": True}, {"typo": 1}):
        with pytest.raises(PolicyError):
            load_policy(data={"limits": limits})


def test_policy_output_redacts_env() -> None:
    policy = load_policy(data={"env": {"TOKEN": "secret"}})
    assert "secret" not in str(policy.public_dict())
    assert policy.public_dict()["env"] == {"TOKEN": "<redacted>"}
