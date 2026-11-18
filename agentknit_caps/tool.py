"""The sole model-facing agentknit tool."""

from __future__ import annotations

from typing import Any

from agentknit import Tool

from .policy import Policy
from .runner import Runner

PYTHON_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {"code": {"type": "string", "description": "Monty Python source to execute."}},
    "required": ["code"],
    "additionalProperties": False,
}


def python_tool(policy: Policy, runner: Runner | None = None) -> Tool:
    """Build exactly one tool; limits and policy cannot be overridden by the model."""
    active = runner or Runner(policy)
    return Tool(
        "python",
        "Execute Python in a capability-confined Monty sandbox. Only policy-granted "
        "paths, environment entries and host functions exist. Directly writes only "
        "rw mounts. No network, subprocess, CPython fallback or resource overrides.",
        active.as_tool,
        parameters=PYTHON_PARAMETERS,
    )
