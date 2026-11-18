"""One-tool schema and CLI behavior."""

import json
from pathlib import Path
from typing import Any, cast

import agentknit
import pytest
from _pytest.capture import CaptureFixture

from agentknit_guarantees import face
from agentknit_guarantees.cli import main
from agentknit_guarantees.policy import load_policy
from agentknit_guarantees.tool import python_tool


def test_only_python_is_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agentknit, "load_specification", lambda *a, **kw: {})
    schema = face.build_schema()
    assert [x["function"]["name"] for x in schema["tool_specs"]] == ["python"]
    assert schema["tools"] == ["t_python_confined"]
    assert list(schema["tool_dispatch"]) == ["python"]
    assert set(schema["tool_specs"][0]["function"]["parameters"]["properties"]) == {"code"}


def test_tool_has_no_timeout_override() -> None:
    tool = python_tool(load_policy())
    parameters = cast("dict[str, Any]", tool.resolved_parameters)
    assert set(cast("dict[str, Any]", parameters["properties"])) == {"code"}


def test_cli_policy_check_and_run(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"env": {"SECRET": "do-not-print"}}))
    source = tmp_path / "code.py"
    source.write_text("1 + 1")
    assert main(["--json", "policy", "--policy", str(policy)]) == 0
    assert "do-not-print" not in capsys.readouterr().out
    assert main(["--json", "check", "--policy", str(policy), "--code", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "allowed"
    assert main(["--json", "run", "--policy", str(policy), "--code", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["result"] == 2
