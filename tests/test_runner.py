"""Independent positive, negative and boundary tests for the Monty boundary."""

from pathlib import Path

import pytest

from agentknit_caps.policy import Policy, load_policy
from agentknit_caps.runner import Registry, Runner


def policy_for(path: Path, mode: str = "rw", **kwargs: object) -> Policy:
    return load_policy(data={"fs": [{"host_path": str(path), "virtual_path": "/workspace", "mode": mode}], **kwargs})


def test_granted_read_write_and_direct_workspace_effect(tmp_path: Path) -> None:
    (tmp_path / "input.txt").write_text("granted")
    result = Runner(policy_for(tmp_path)).run(
        "from pathlib import Path\n"
        "p = Path('/workspace/input.txt')\n"
        "p.write_text(p.read_text() + '-written')\n"
        "p.read_text()"
    )
    assert result.ok, result.error
    assert result.result == "granted-written"
    assert (tmp_path / "input.txt").read_text() == "granted-written"


def test_read_only_boundary(tmp_path: Path) -> None:
    result = Runner(policy_for(tmp_path, "ro")).run("from pathlib import Path\nPath('/workspace/x').write_text('no')")
    assert not result.ok
    assert not (tmp_path / "x").exists()


@pytest.mark.parametrize("code", [
    "from pathlib import Path\nPath('/etc/passwd').read_text()",
    "from pathlib import Path\nPath('/workspace/../../etc/passwd').read_text()",
    "import os\nos.environ['HOME']",
    "import socket\nsocket.socket()",
    "import subprocess\nsubprocess.run(['id'])",
    "open('/etc/passwd').read()",
])
def test_ungranted_host_authority_fails(tmp_path: Path, code: str) -> None:
    result = Runner(policy_for(tmp_path)).run(code)
    assert not result.ok, code


def test_only_explicit_environment_is_visible() -> None:
    runner = Runner(load_policy(data={"env": {"GRANTED": "yes"}}))
    result = runner.run("import os\n(os.getenv('GRANTED'), os.getenv('HOME'))")
    assert result.ok
    assert result.result == ("yes", None)


def test_closed_function_registry_and_no_implicit_callback() -> None:
    registry = Registry()
    registry.register("add", lambda a, b: a + b)
    runner = Runner(load_policy(data={"functions": ["add"]}), registry)
    result = runner.run("add(2, 3)")
    assert result.ok and result.result == 5
    assert not runner.run("unknown()").ok


def test_source_and_total_call_limits() -> None:
    runner = Runner(load_policy(data={"limits": {"source_bytes": 4, "total_calls": 2}}))
    assert not runner.run("12345").ok
    assert runner.run("1").ok
    assert runner.run("2").ok
    assert not runner.run("3").ok


def test_result_output_time_and_memory_boundaries() -> None:
    runner = Runner(load_policy(data={"limits": {"result_bytes": 8, "output_bytes": 16, "feed_seconds": 0.1, "wall_seconds": 2}}))
    result = runner.run("print('12345678901234567890')\n'x' * 100")
    assert not result.ok
    assert result.error_type == "MontyRuntimeError"
    assert result.error is not None and "16 bytes" in result.error
    result = Runner(load_policy(data={"limits": {"result_bytes": 8}})).run("'x' * 100")
    assert result.ok
    assert result.error == "result truncated"
    assert len(result.result) < 110
    result = runner.run("while True:\n    pass")
    assert not result.ok
    assert result.error_type in ("MontyRuntimeError", "MontyCrashedError")


def test_no_state_reuse_between_calls() -> None:
    runner = Runner(load_policy())
    assert runner.run("x = 41").ok
    assert not runner.run("x + 1").ok


def test_tool_result_is_structured() -> None:
    text, metadata = Runner(load_policy()).as_tool("6 * 7")
    assert '"result": 42' in text
    assert metadata["ok"] is True
