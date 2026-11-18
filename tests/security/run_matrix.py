"""Executable adversarial matrix; host checks effects independently of sandbox output."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from agentknit_caps.policy import load_policy
from agentknit_caps.runner import Runner


def run() -> list[dict[str, object]]:
    cases = [
        ("read-outside", "from pathlib import Path\nPath('/etc/passwd').read_text()", False),
        ("traversal", "open('/workspace/../../etc/passwd').read()", False),
        ("absolute-open", "open('/etc/passwd').read()", False),
        ("socket", "import socket\nsocket.socket()", False),
        ("subprocess", "import subprocess", False),
        ("ctypes", "import ctypes", False),
        ("ambient-env", "import os\nos.environ['HOME']", False),
        ("granted-control", "from pathlib import Path\nPath('/workspace/control').write_text('ok')", True),
    ]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        policy = load_policy(data={"fs": [{"host_path": directory, "virtual_path": "/workspace", "mode": "rw"}]})
        results = []
        for name, code, expected in cases:
            result = Runner(policy).run(code)
            host_effect = (root / "control").read_text() == "ok" if name == "granted-control" else False
            passed = result.ok == expected and host_effect == expected
            results.append({"case": name, "expected_ok": expected, "actual_ok": result.ok,
                            "host_effect": host_effect, "pass": passed, "error_type": result.error_type})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", required=True)
    args = parser.parse_args()
    results = run()
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({"total": len(results), "passed": sum(bool(r["pass"]) for r in results)}))
    return 0 if all(r["pass"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
