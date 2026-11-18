"""Monty execution with explicit capabilities and finite per-run budgets."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, tzinfo
from pathlib import Path
from typing import Any

from pydantic_monty import CollectString, Monty, MontyError, MountDir, OSAccess

from .policy import Policy, PolicyError

HostFunction = Callable[..., Any]


class FixedOSAccess(OSAccess):
    """Minimal environment/filesystem fallback with deterministic wall-clock values."""

    def date_today(self) -> date:
        return date(1970, 1, 1)

    def datetime_now(self, tz: tzinfo | None = None) -> datetime:
        return datetime(1970, 1, 1, tzinfo=tz)

    def time(self, caller: str = "time.time") -> float:
        return 0.0


@dataclass
class ExecutionResult:
    """Serializable result returned to the model; ``ok`` means execution completed."""

    ok: bool
    result: Any = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    error_type: str | None = None


class Registry:
    """Closed host-function registry. Functions are never imported by policy name."""

    def __init__(self) -> None:
        self._functions: dict[str, HostFunction] = {}

    def register(self, name: str, function: HostFunction) -> None:
        if not name.isidentifier() or not callable(function):
            raise ValueError("invalid host function")
        self._functions[name] = function

    def select(self, names: tuple[str, ...]) -> dict[str, HostFunction]:
        missing = set(names) - set(self._functions)
        if missing:
            raise PolicyError(f"unavailable host functions: {', '.join(sorted(missing))}")
        return {name: self._functions[name] for name in names}


DEFAULT_REGISTRY = Registry()


def monty_binary() -> Path:
    """Resolve and validate the installed runtime, never a model-controlled path."""
    import sys

    executable = Path(sys.executable).parent / "monty"
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise PolicyError(f"Monty runtime executable not found: {executable}")
    return executable.resolve(strict=True)


def _bounded_json(value: Any, limit: int) -> tuple[Any, bool]:
    try:
        encoded = json.dumps(value, ensure_ascii=False, default=repr).encode("utf-8")
    except (TypeError, ValueError):
        encoded = repr(value).encode("utf-8", errors="replace")
    if len(encoded) <= limit:
        return value, False
    return encoded[:limit].decode("utf-8", errors="replace") + "<truncated>", True


class Runner:
    """One-shot Monty runs; no worker or heap is shared between tool calls."""

    def __init__(self, policy: Policy, registry: Registry | None = None) -> None:
        self.policy = policy
        self.registry = registry or DEFAULT_REGISTRY
        self.functions = self.registry.select(policy.functions)
        self._calls = 0
        self._lock = threading.Lock()
        self._closed = False

    def close(self) -> None:
        self._closed = True

    def run(self, code: str) -> ExecutionResult:
        if not isinstance(code, str):
            return ExecutionResult(False, error="code must be a string", error_type="TypeError")
        if len(code.encode("utf-8")) > self.policy.limits.source_bytes:
            return ExecutionResult(False, error="source_bytes limit exceeded", error_type="ResourceLimit")
        with self._lock:
            if self._closed:
                return ExecutionResult(False, error="runner is closed", error_type="RuntimeError")
            self._calls += 1
            if self._calls > self.policy.limits.total_calls:
                return ExecutionResult(False, error="total_calls limit exceeded", error_type="ResourceLimit")
        limits = self.policy.limits
        collector = CollectString(max_bytes=limits.output_bytes)
        mounts = [MountDir(host_path=m.host_path, virtual_path=m.virtual_path,
                           mode="read-only" if m.mode == "ro" else "read-write",
                           write_bytes_limit=limits.write_bytes) for m in self.policy.mounts]
        resources = {
            "max_feed_duration_secs": limits.feed_seconds,
            "max_turn_duration_secs": limits.feed_seconds,
            "max_memory": limits.memory_bytes,
            "max_recursion_depth": limits.recursion_depth,
            "max_suspensions": limits.suspensions,
            "max_total_sleep_secs": 0.0,
        }
        try:
            # A pool cannot enforce a per-instance wall timeout on synchronous feeds without
            # affecting other users; create one private pool and bound its worker request.
            with (
                Monty(binary_path=monty_binary(), min_processes=1, max_processes=1,
                      request_timeout=limits.wall_seconds) as pool,
                pool.checkout(limits=resources, os_policy={  # type: ignore[arg-type]
                    "random_start": {"seed": 0}, "sleep_system_max": 0.0,
                    "datetime": "call_host",
                }) as session,
            ):
                value = session.feed_run(
                    code, mount=mounts, external_lookup=self.functions,
                    os=FixedOSAccess(environ=dict(self.policy.env), max_urandom_bytes=0, max_sleep=0),
                    print_callback=collector,
                )
            output = collector.output
            truncated = len(output.encode("utf-8")) >= limits.output_bytes
            result, result_truncated = _bounded_json(value, limits.result_bytes)
            return ExecutionResult(True, result=result, stdout=output,
                                   stderr="<output truncated>" if truncated else "",
                                   error="result truncated" if result_truncated else None)
        except (MontyError, OSError, ValueError, TypeError) as exc:
            return ExecutionResult(False, stdout=collector.output, stderr=str(exc),
                                   error=str(exc), error_type=type(exc).__name__)

    def as_tool(self, code: str) -> tuple[str, dict[str, object]]:
        """Agentknit's ``(text, metadata)`` tool result."""
        result = self.run(code)
        data = asdict(result)
        return json.dumps(data, ensure_ascii=False), {"result": data, "ok": result.ok}
