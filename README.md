# agentknit-guarantees

An agent receives capabilities, not ambient authority. A policy defines the
resources it may use and the bounds on their use; anything not granted is denied.
The goal is that code can work directly in a workspace without inheriting the
host user's other privileges.

“Guarantee” here means an enforceable, testable security property under explicit
trust assumptions—not a proof of correctness, invulnerability or complete
CPython compatibility. The critical question is whether every effect crosses one
mediation boundary, and whether independent tests can falsify that claim.

## Install and use

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/agentknit-kimi-k3.1-guaranteed 'Fix the failing tests in /workspace'
```

Without `--policy`, the current working directory is directly writable at the
virtual path `/workspace`. This is intentionally direct: sandbox code can modify
every file beneath an `rw` mount. Use a disposable checkout or a read-only policy
when that is not acceptable.

```bash
agentknit-kimi-k3.1-guaranteed --policy policy.json 'Implement the requested change'
agentknit-kimi-k3.1-guaranteed --session SESSION_ID --policy policy.json
agentknit-guarantees --json policy --policy policy.json
agentknit-guarantees --json check --policy policy.json --code program.py
agentknit-guarantees --json run --policy policy.json --code program.py
```

`--policy` uses the same file across resumed sessions. The model cannot choose a
policy, runtime binary, import callback or resource limit. Kimi endpoint settings
and credentials come from inference-db entry `kimi-coding` on the host.

## Policy

```json
{
  "schema_version": 1,
  "fs": [{"host_path": "/absolute/project", "virtual_path": "/workspace", "mode": "rw"}],
  "env": {"EXPLICIT_NAME": "value"},
  "functions": [],
  "limits": {
    "source_bytes": 100000, "result_bytes": 100000, "output_bytes": 1000000,
    "feed_seconds": 30, "wall_seconds": 40, "memory_bytes": 256000000,
    "recursion_depth": 200, "suspensions": 1000, "write_bytes": 10000000,
    "total_calls": 100
  }
}
```

All keys are strict; unknown keys, overlapping mounts, missing host paths,
non-normalized virtual paths and unavailable host functions fail closed. `ro`
means read-only and `rw` means direct read-write. Environment grants are exact
name/value pairs. `policy --json` redacts their values. The initial host-function
registry is empty; embedding applications can explicitly register validated
functions. Network, subprocess and native-code authority are not offered.

## Tests in Monty

`agentknit_guarantees.testing.invoke(paths)` returns source defining and calling
`run_tests(paths)`. The runner discovers `test_*.py`, loads each file with
sandboxed `exec`, and calls zero-argument `test_*` functions. Test and production
code execute in the same Monty checkout and therefore have identical mounts,
environment, host functions and limits. Failures are structured data, not a host
process exit. This is a small Monty-compatible test protocol, **not pytest
compatibility**: fixtures, plugins, parametrization, arbitrary third-party
packages and CPython-only syntax are unsupported. Host pytest is used to test
this package itself and is never exposed to the agent.

## Static checker

`check` has three outcomes and exit codes: `allowed` (0), `indeterminate` (2),
and `denied` (3). Only literal, fully resolved host effects can be allowed;
dynamic paths and dynamic execution are indeterminate. A denied result identifies
a definite policy violation or syntax error. The checker is advisory and never
replaces runtime confinement.

## Guarantees and boundary

For each run, only the declared mounts, environment values and registry functions
are supplied to a fresh Monty checkout. No ambient host filesystem or environment
is supplied; socket/process modules are unavailable. Writes are confined by
Monty's capability-relative mounts. Source, output, result, memory, recursion,
suspensions, time, write bytes and total calls are bounded. A worker/session is
never reused between model calls. Execution failures return structured errors and
never fall back to CPython.

### How to establish the claim

State the claim as a total mediation property: every observable effect either is
permitted by the effective policy or is absent. Then provide four kinds of
evidence:

1. **Architecture:** enumerate every model-to-host path and show there is no
   fallback executor, ambient file tool or model-controlled callback. A single
   tool schema alone does not prove this; review dispatch and the runner too.
2. **Differential/adversarial tests:** pair every denied probe with a granted
   control, so a broken executor that rejects everything cannot appear secure.
   Include traversal, absolute paths, escaping symlinks, ambient environment,
   sockets, processes, host functions and resource boundaries.
3. **Independent oracles:** assert effects on the host (sentinel contents,
   filesystem changes, process/network observations), not merely sandbox errors
   or exit statuses. Run fuzzing and mutation tests: deliberately remove a
   mediation check and require a test to fail.
4. **Assumptions and provenance:** pin and audit Monty, exercise the exact
   production tool path, and document trusted components and residual risks.

Finite tests cannot prove universal absence of escapes. Stronger evidence would
be OS-level isolation plus a machine-checked model of the complete host boundary.
The static checker is not that proof: dynamic Python remains indeterminate and
runtime mediation is still required.

### Current evidence and limitations

This is a tested engineering confinement claim, not a formal proof or a claim
that Monty has no vulnerabilities. Trust includes the host OS/Python process,
agentknit, the pinned Monty runtime and every deliberately registered host
function. Direct `rw` writes are real host writes and may be partially completed
before an error. Allocator memory limits are not a hard process-RSS guarantee.
No network or process capability means code cannot intentionally use those
interfaces; this is not an OS-level containment claim against a Monty vulnerability.

## Development

```bash
pytest --cov=agentknit_guarantees --cov-report=term-missing
mypy agentknit_guarantees tests
ruff check .
```
