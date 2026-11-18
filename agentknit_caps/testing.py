"""A small test runner implemented entirely in Monty's Python subset.

The public ``run_tests(paths=...)`` helper is ordinary sandbox source, not a
host callback. Test code therefore has precisely the caller's capabilities.
Supported tests are zero-argument functions named ``test_*`` and ``assert``.
Pytest's full API is deliberately not emulated.
"""

from __future__ import annotations

import json
from pathlib import Path

RUNNER_PATH = Path(__file__).with_name("_sandbox_tests.py")


def source() -> str:
    return RUNNER_PATH.read_text(encoding="utf-8")


def invoke(paths: list[str] | None = None) -> str:
    encoded = json.dumps(paths if paths is not None else ["."])
    code = source() + f"\nrun_tests({encoded})\n"
    return code
