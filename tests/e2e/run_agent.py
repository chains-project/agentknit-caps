"""Deterministic end-to-end model/tool trace without network or credentials."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from agentknit_caps.policy import load_policy
from agentknit_caps.testing import invoke
from agentknit_caps.tool import python_tool


def run() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "test_solution.py").write_text(
            "from pathlib import Path\n"
            "def test_answer():\n"
            "    namespace = {}\n"
            "    exec(Path('solution.py').read_text(), namespace)\n"
            "    assert namespace['answer'] == 42\n"
        )
        policy = load_policy(data={"fs": [{"host_path": directory, "virtual_path": "/workspace", "mode": "rw"}]})
        tool = python_tool(policy)

        def invoke_tool(code: str) -> tuple[str, dict[str, object]]:
            result = tool.fn(code)
            assert isinstance(result, tuple)
            return result

        calls = [
            "from pathlib import Path\nPath('/workspace/solution.py').write_text('answer = 42')",
            invoke(),
            "from pathlib import Path\nPath('/etc/passwd').read_text()",
        ]
        transcript: list[dict[str, Any]] = []
        for code in calls:
            text, metadata = invoke_tool(code)
            assert isinstance(text, str)
            transcript.append({"tool": "python", "result": json.loads(text), "ok": metadata["ok"]})
        return {"tool_names": sorted({entry["tool"] for entry in transcript}),
                "edit_succeeded": (root / "solution.py").read_text() == "answer = 42",
                "tests_passed": transcript[1]["result"]["result"]["passed"] == 1,
                "outside_read_denied": not transcript[2]["ok"],
                "transcript": transcript}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", required=True)
    parser.add_argument("--json", required=True)
    args = parser.parse_args()
    data = run()
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(data, indent=2) + "\n")
    passed = data["tool_names"] == ["python"] and all(data[k] for k in ("edit_succeeded", "tests_passed", "outside_read_denied"))
    print(json.dumps({"pass": passed, "tools": data["tool_names"]}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
