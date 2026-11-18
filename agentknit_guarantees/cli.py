"""Utilities for policy inspection, checking and one-off confined execution."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .checker import check_code
from .policy import PolicyError, load_policy
from .runner import Runner


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="agentknit-guarantees")
    result.add_argument("--json", action="store_true", help="emit machine-readable output")
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("policy", "check", "run"):
        command = sub.add_parser(name)
        command.add_argument("--policy", required=True)
        if name in ("check", "run"):
            command.add_argument("--code", required=True, help="Python source file, or - for stdin")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        policy = load_policy(args.policy)
        if args.command == "policy":
            data = policy.public_dict()
            print(json.dumps(data) if args.json else json.dumps(data, indent=2))
            return 0
        code = sys.stdin.read() if args.code == "-" else Path(args.code).read_text(encoding="utf-8")
        if args.command == "check":
            checked = check_code(code, policy).as_dict()
            print(json.dumps(checked) if args.json else json.dumps(checked, indent=2))
            verdict = checked["verdict"]
            assert isinstance(verdict, str)
            return {"allowed": 0, "indeterminate": 2, "denied": 3}[verdict]
        result = Runner(policy).as_tool(code)[1]["result"]
        assert isinstance(result, dict)
        print(json.dumps(result) if args.json else json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    except (PolicyError, OSError) as exc:
        data = {"error": str(exc), "error_type": type(exc).__name__}
        print(json.dumps(data) if args.json else json.dumps(data, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
