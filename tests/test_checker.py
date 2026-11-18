"""Static verdict tests, including dynamic-code conservatism."""

from pathlib import Path

from agentknit_guarantees.checker import check_code
from agentknit_guarantees.policy import load_policy


def test_static_verdicts(tmp_path: Path) -> None:
    policy = load_policy(data={"fs": [{"host_path": str(tmp_path), "virtual_path": "/w", "mode": "rw"}]})
    assert check_code("open('/w/a').read()", policy).verdict == "allowed"
    assert check_code("open('/etc/passwd').read()", policy).verdict == "denied"
    assert check_code("Path('/w/a').write_text('x')", policy).verdict == "allowed"
    assert check_code("open(path).read()", policy).verdict == "indeterminate"
    assert check_code("import subprocess", policy).verdict == "denied"
    assert check_code("exec(source)", policy).verdict == "indeterminate"
    assert check_code("not valid !", policy).verdict == "denied"
