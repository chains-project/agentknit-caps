"""Strict, data-only capability policy parsing."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal


class PolicyError(ValueError):
    """The policy is malformed or requests unavailable authority."""


@dataclass(frozen=True)
class Mount:
    host_path: str
    virtual_path: str
    mode: Literal["ro", "rw"]


@dataclass(frozen=True)
class Limits:
    source_bytes: int = 100_000
    result_bytes: int = 100_000
    output_bytes: int = 1_000_000
    feed_seconds: float = 30.0
    wall_seconds: float = 40.0
    memory_bytes: int = 256_000_000
    recursion_depth: int = 200
    suspensions: int = 1_000
    write_bytes: int = 10_000_000
    total_calls: int = 100


@dataclass(frozen=True)
class Policy:
    mounts: tuple[Mount, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    functions: tuple[str, ...] = ()
    limits: Limits = field(default_factory=Limits)
    version: int = 1

    def public_dict(self) -> dict[str, Any]:
        """Return the effective policy; environment values are deliberately redacted."""
        return {"schema_version": self.version, "fs": [asdict(m) for m in self.mounts],
                "env": {name: "<redacted>" for name in sorted(self.env)},
                "functions": list(self.functions), "limits": asdict(self.limits)}


def _keys(value: Any, allowed: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(k, str) for k in value):
        raise PolicyError(f"{where} must be an object")
    unknown = set(value) - allowed
    if unknown:
        raise PolicyError(f"unknown {where} keys: {', '.join(sorted(unknown))}")
    return value


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise PolicyError(f"{name} must be an integer >= {minimum}")
    return value


def load_policy(path: str | Path | None = None, data: dict[str, Any] | None = None) -> Policy:
    """Load a policy. ``None`` denotes a policy with no host authority."""
    if path is not None and data is not None:
        raise PolicyError("specify either path or data")
    if path is not None:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PolicyError(f"cannot load policy: {exc}") from exc
    if data is None:
        return Policy()
    raw = _keys(data, {"schema_version", "fs", "env", "functions", "limits"}, "policy")
    if raw.get("schema_version", 1) != 1:
        raise PolicyError("unsupported schema_version")
    mounts: list[Mount] = []
    fs = raw.get("fs", [])
    if not isinstance(fs, list):
        raise PolicyError("fs must be an array")
    for index, item in enumerate(fs):
        obj = _keys(item, {"host_path", "virtual_path", "mode"}, f"fs[{index}]")
        host = obj.get("host_path")
        virtual = obj.get("virtual_path")
        mode = obj.get("mode")
        if not isinstance(host, str) or not host:
            raise PolicyError(f"fs[{index}].host_path must be a non-empty string")
        vp = PurePosixPath(virtual) if isinstance(virtual, str) else None
        if vp is None or not vp.is_absolute() or ".." in vp.parts or str(vp) == "/":
            raise PolicyError(f"fs[{index}].virtual_path must be absolute, normalized and not /")
        if mode not in ("ro", "rw"):
            raise PolicyError(f"fs[{index}].mode must be ro or rw")
        try:
            host_path = Path(host).expanduser().resolve(strict=True)
        except OSError as exc:
            raise PolicyError(f"fs[{index}].host_path does not resolve: {exc}") from exc
        if not host_path.is_dir():
            raise PolicyError(f"fs[{index}].host_path is not a directory")
        mounts.append(Mount(str(host_path), str(vp), mode))
    for i, first in enumerate(mounts):
        a, b = PurePosixPath(first.virtual_path), None
        for second in mounts[i + 1:]:
            b = PurePosixPath(second.virtual_path)
            if a in b.parents or b in a.parents:
                raise PolicyError("overlapping virtual mounts are forbidden")
            pa, pb = Path(first.host_path), Path(second.host_path)
            if pa in pb.parents or pb in pa.parents:
                raise PolicyError("overlapping host mounts are forbidden")
    env = raw.get("env", {})
    if not isinstance(env, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in env.items()):
        raise PolicyError("env must map string names to string values")
    functions = raw.get("functions", [])
    if not isinstance(functions, list) or any(not isinstance(f, str) or not f.isidentifier() for f in functions):
        raise PolicyError("functions must be an array of identifiers")
    if len(set(functions)) != len(functions):
        raise PolicyError("functions must not contain duplicates")
    limit_data = _keys(raw.get("limits", {}), set(Limits.__dataclass_fields__), "limits")
    converted: dict[str, int | float] = {}
    for name, value in limit_data.items():
        if name in ("feed_seconds", "wall_seconds"):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise PolicyError(f"{name} must be a positive number")
            converted[name] = float(value)
        else:
            converted[name] = _integer(value, name, 1)
    return Policy(tuple(mounts), dict(env), tuple(functions), Limits(**converted))  # type: ignore[arg-type]
