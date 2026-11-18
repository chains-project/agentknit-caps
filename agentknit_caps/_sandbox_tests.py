# This file is fed to Monty, not imported on the host.
from pathlib import Path
import json


def _error(exc):
    return type(exc).__name__ + ": " + str(exc)


def run_tests(paths=["."]):
    """Discover and execute zero-argument test_* functions in the same sandbox."""
    def _sample_function():
        pass
    function_type = type(_sample_function)
    files = []
    for requested in paths:
        path = Path(requested)
        if path.is_dir():
            candidates = path.glob("test_*.py")
        else:
            candidates = [path]
        for candidate in candidates:
            if str(candidate) not in [str(f) for f in files]:
                files.append(candidate)
    results = []
    for file in files:
        namespace = {"__file__": str(file), "__name__": file.stem}
        try:
            exec(file.read_text(), namespace)
        except Exception as exc:
            results.append({"test": str(file), "ok": False, "error": _error(exc)})
            continue
        for name in sorted(namespace):
            if name.startswith("test_") and type(namespace[name]) == function_type:
                try:
                    namespace[name]()
                    results.append({"test": str(file) + "::" + name, "ok": True, "error": None})
                except Exception as exc:
                    results.append({"test": str(file) + "::" + name, "ok": False, "error": _error(exc)})
    failures = [r for r in results if not r["ok"]]
    return {"ok": len(failures) == 0, "passed": len(results) - len(failures),
            "failed": len(failures), "tests": results}
