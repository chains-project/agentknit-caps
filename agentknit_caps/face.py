"""Standalone Kimi K3.1 agentknit face with one confined Python tool."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import agentknit
from agentknit import build_tool_spec
from agentknit.tool_library import TOOL_LIBRARY

from .policy import load_policy
from .runner import Runner
from .tool import python_tool

MODEL = "k3.1-pro"
INFERENCE_DB = "kimi-coding"


def default_policy() -> dict[str, Any]:
    return {"schema_version": 1, "fs": [{"host_path": os.getcwd(), "virtual_path": "/workspace", "mode": "rw"}],
            "env": {}, "functions": [], "limits": {}}


def build_schema(policy_path: str | None = None) -> dict[str, Any]:
    policy = load_policy(policy_path) if policy_path else load_policy(data=default_policy())
    schema = agentknit.load_specification(MODEL, inference_db=INFERENCE_DB)
    schema["display_name"] = "Kimi K3.1 Pro (capability guarantees)"
    schema["context_window"] = 1_048_576
    schema["compaction_trigger_tokens"] = 786_432
    runner = Runner(policy)

    def t_python_confined(code: str) -> tuple[str, dict[str, object]]:
        return runner.as_tool(code)

    tool = python_tool(policy, runner)
    tool.fn = t_python_confined
    TOOL_LIBRARY["t_python_confined"] = t_python_confined
    specs, dispatch = build_tool_spec([tool])
    schema["tool_specs"] = specs
    schema["tool_dispatch"] = dispatch
    schema["tools"] = ["t_python_confined"]
    return schema


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentknit-kimi-k3.1-guaranteed")
    parser.add_argument("task", nargs="*")
    parser.add_argument("--policy", help="policy JSON; default is cwd mounted rw at /workspace")
    parser.add_argument("--session")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--no-strict-cache-proof", action="store_true",
                        help="allow a provider whose first response has no cache-accounting field")
    args = parser.parse_args(argv)
    os.environ["AGENTKNIT_RESUME_COMMAND"] = sys.argv[0]
    schema = build_schema(args.policy)
    mounts = load_policy(args.policy).mounts if args.policy else ()
    visible = ", ".join(f"{m.virtual_path} ({m.mode})" for m in mounts) or "/workspace (rw)"
    supplement = (
        "You have exactly one tool: python(code), running in Pydantic Monty. "
        f"Granted virtual mounts: {visible}. Access no ungranted host paths. "
        "Network, subprocess and native modules are unavailable. Python executes "
        "in Monty's subset; do not attempt to escape or invoke CPython. "
        "Read and write files with pathlib. Modules from mounted directories "
        "are not importable: load their source with exec instead. Tests must "
        "use zero-argument test_* functions and assertions; read, exec and "
        "invoke those functions in the same sandbox. "
        f"Host HOME is {os.path.expanduser('~')}, but it is not accessible unless mounted."
    )
    common: dict[str, Any] = {
        "non_interactive": args.non_interactive, "session_id": args.session,
        "system_prompt_supplement": supplement, "min_cacheable_tokens": 4096,
        "cache_ttl_seconds": 300, "strict_cache_proof": not args.no_strict_cache_proof,
    }
    task = " ".join(args.task) if args.task else None
    if task is None and not sys.stdin.isatty():
        task = sys.stdin.read().strip() or None
    if task:
        agentknit.run_task(schema, task, **common)
    else:
        agentknit.run_repl(schema, **common)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
