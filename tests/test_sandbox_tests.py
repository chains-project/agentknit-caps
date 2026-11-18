"""Monty-native tests use the same capabilities as the code under test."""

from pathlib import Path

from agentknit_guarantees.policy import load_policy
from agentknit_guarantees.runner import Runner
from agentknit_guarantees.testing import invoke


def runner_for(path: Path) -> Runner:
    return Runner(load_policy(data={"fs": [{"host_path": str(path), "virtual_path": "/workspace", "mode": "rw"}]}))


def test_pass_fail_and_selected_file(tmp_path: Path) -> None:
    (tmp_path / "test_example.py").write_text(
        "def test_pass():\n    assert 2 + 2 == 4\n"
        "def test_fail():\n    assert 1 == 2\n"
    )
    result = runner_for(tmp_path).run(invoke())
    assert result.ok
    assert result.result["passed"] == 1
    assert result.result["failed"] == 1
    assert result.result["ok"] is False


def test_tests_cannot_exceed_caller_authority(tmp_path: Path) -> None:
    (tmp_path / "test_hostile.py").write_text(
        "from pathlib import Path\n"
        "def test_escape():\n    Path('/etc/passwd').read_text()\n"
    )
    result = runner_for(tmp_path).run(invoke(["test_hostile.py"]))
    assert result.ok
    assert result.result["failed"] == 1
    assert "FileNotFoundError" in result.result["tests"][0]["error"]


def test_tests_share_rw_workspace(tmp_path: Path) -> None:
    (tmp_path / "test_write.py").write_text(
        "from pathlib import Path\n"
        "def test_write():\n    Path('/workspace/result').write_text('yes')\n"
    )
    result = runner_for(tmp_path).run(invoke())
    assert result.result["passed"] == 1
    assert (tmp_path / "result").read_text() == "yes"
