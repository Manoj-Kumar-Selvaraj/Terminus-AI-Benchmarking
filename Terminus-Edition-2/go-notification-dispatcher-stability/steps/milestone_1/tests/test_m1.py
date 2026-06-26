import subprocess
from pathlib import Path

APP = Path("/app")
M1_CONTRACT = Path("/steps/milestone_1/tests/milestone_1_contract_test.go")

FILES = {
    "internal/dispatch/milestone_1_contract_test.go": M1_CONTRACT.read_text(encoding="utf-8"),
}


def test_go_contracts():
    for relative, content in FILES.items():
        path = APP / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    result = subprocess.run(
        ["/usr/local/go/bin/go", "test", "-race", "./internal/dispatch", "./internal/delivery", "./internal/idempotency", "-count=1"],
        cwd=APP,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
