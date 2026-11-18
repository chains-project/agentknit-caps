"""Conservative three-valued static policy checker.

This is an advisory pre-check, never the runtime security boundary. ``allowed``
means every recognized host effect is a constant and granted; ``denied`` means a
constant effect definitely violates policy; all other code is ``indeterminate``.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import Literal

from .policy import Policy

Verdict = Literal["allowed", "denied", "indeterminate"]


@dataclass(frozen=True)
class CheckResult:
    verdict: Verdict
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


_READ_METHODS = {"read_text", "read_bytes", "open", "stat", "exists", "iterdir", "glob"}
_WRITE_METHODS = {"write_text", "write_bytes", "mkdir", "unlink", "rename", "replace", "rmdir"}
_DENIED_IMPORTS = {"subprocess", "socket", "ctypes", "multiprocessing", "shutil"}


def _mode(policy: Policy, path: str) -> str | None:
    target = PurePosixPath(path)
    if not target.is_absolute() or ".." in target.parts:
        return None
    matches = [m for m in policy.mounts if target == PurePosixPath(m.virtual_path)
               or PurePosixPath(m.virtual_path) in target.parents]
    return matches[0].mode if matches else None


class Checker(ast.NodeVisitor):
    def __init__(self, policy: Policy) -> None:
        self.policy = policy
        self.reasons: list[str] = []
        self.denied = False

    def unknown(self, node: ast.AST, reason: str) -> None:
        self.reasons.append(f"line {getattr(node, 'lineno', '?')}: {reason}")

    def deny(self, node: ast.AST, reason: str) -> None:
        self.denied = True
        self.unknown(node, reason)

    def visit_Import(self, node: ast.Import) -> None:
        for item in node.names:
            root = item.name.split(".")[0]
            if root in _DENIED_IMPORTS:
                self.deny(node, f"process/network/native authority is unavailable: {item.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.module.split(".")[0] in _DENIED_IMPORTS:
            self.deny(node, f"process/network/native authority is unavailable: {node.module}")
        self.generic_visit(node)

    def _path_call(self, node: ast.Call) -> tuple[str, str] | None:
        func = node.func
        if isinstance(func, ast.Name) and func.id in ("open", "Path"):
            if func.id == "Path":
                return "path", "constructor"
            mode = "r"
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                mode = str(node.args[1].value)
            return "write" if any(c in mode for c in "wax+") else "read", "open"
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call):
            owner = func.value.func
            if isinstance(owner, ast.Name) and owner.id == "Path":
                if func.attr in _WRITE_METHODS:
                    return "write", func.attr
                if func.attr in _READ_METHODS:
                    return "read", func.attr
        return None

    def visit_Call(self, node: ast.Call) -> None:
        effect = self._path_call(node)
        if effect is not None:
            operation, name = effect
            if name == "constructor":
                self.generic_visit(node)
                return
            owner = node.func
            path_node = None
            if isinstance(owner, ast.Attribute) and isinstance(owner.value, ast.Call):
                path_node = owner.value.args[0] if owner.value.args else None
            elif node.args:
                path_node = node.args[0]
            if path_node is None:
                self.unknown(node, f"dynamic {name} receiver")
            elif not isinstance(path_node, ast.Constant) or not isinstance(path_node.value, str):
                self.unknown(node, f"dynamic path passed to {name}")
            else:
                mode = _mode(self.policy, path_node.value)
                if mode is None:
                    self.deny(node, f"ungranted path: {path_node.value}")
                elif operation == "write" and mode != "rw":
                    self.deny(node, f"read-only path: {path_node.value}")
        if isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec", "compile", "__import__"):
            self.unknown(node, f"dynamic code execution: {node.func.id}")
        self.generic_visit(node)


def check_code(code: str, policy: Policy) -> CheckResult:
    """Check literal effects without executing or importing user code."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return CheckResult("denied", (f"syntax error: {exc.msg}",))
    checker = Checker(policy)
    checker.visit(tree)
    if checker.denied:
        return CheckResult("denied", tuple(checker.reasons))
    if checker.reasons:
        return CheckResult("indeterminate", tuple(checker.reasons))
    return CheckResult("allowed", ())
