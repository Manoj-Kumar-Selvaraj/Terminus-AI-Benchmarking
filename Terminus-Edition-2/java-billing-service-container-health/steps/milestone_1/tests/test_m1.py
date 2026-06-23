import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


APP = Path("/app")
BASE = "http://127.0.0.1:8080"
SAFE_JVM_OPTIONS = Path("/tmp/verifier-safe-jvm.options")


def stop_stack():
    subprocess.run(["bash", str(APP / "scripts/stop_service.sh")], check=False)


def start_stack():
    stop_stack()
    SAFE_JVM_OPTIONS.write_text("-XX:+UseContainerSupport\n-XX:MaxRAMPercentage=70.0\n")
    env = os.environ.copy()
    env["JAVA_OPTIONS_FILE"] = str(SAFE_JVM_OPTIONS)
    subprocess.run(["bash", str(APP / "scripts/run_service.sh")], check=True, env=env)


def assert_billing_jar_process():
    pid_file = APP / "run/billing.pid"
    assert pid_file.exists(), "billing.pid missing; run_service.sh did not start the JAR"
    pid = pid_file.read_text(encoding="utf-8").strip()
    deadline = time.time() + 3
    cmdline = ""
    while time.time() < deadline:
        proc_path = Path(f"/proc/{pid}/cmdline")
        if proc_path.exists():
            cmdline = proc_path.read_bytes().decode("utf-8", errors="replace").replace("\0", " ")
            if "billing-service.jar" in cmdline:
                break
        time.sleep(0.05)
    assert "billing-service.jar" in cmdline, cmdline


def read_pool_stats() -> dict[str, int]:
    with urllib.request.urlopen(f"{BASE}/internal/pool", timeout=5) as response:
        body = response.read().decode("utf-8")
    stats = {}
    for line in body.splitlines():
        key, value = line.split("=", 1)
        stats[key] = int(value)
    return stats


def wait_for_status(path: str, want: int, timeout: float = 40.0) -> str:
    deadline = time.time() + timeout
    last_error = "no response"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}{path}", timeout=2) as response:
                body = response.read().decode("utf-8")
                if response.status == want:
                    return body
                last_error = f"status={response.status} body={body}"
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8")
            if error.code == want:
                return body
            last_error = f"status={error.code} body={body}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.5)
    raise AssertionError(f"timed out waiting for {path} status {want}: {last_error}")


def test_liveness_returns_up_immediately():
    """Live health stays UP during migration; readiness fixes must not break /health/live."""
    start_stack()
    try:
        body = wait_for_status("/health/live", 200, timeout=5)
        assert "UP" in body
    finally:
        stop_stack()


def test_readiness_and_invoice_list_after_datasource_fix():
    """Readiness must reach UP and invoices must include the seeded CSV row."""
    start_stack()
    try:
        assert_billing_jar_process()
        body = wait_for_status("/health/ready", 200, timeout=45)
        assert body.strip() == "UP", f"Expected body 'UP', got '{body}'"
        with urllib.request.urlopen(f"{BASE}/api/invoices", timeout=5) as response:
            body = response.read().decode("utf-8")
        assert response.status == 200
        assert "inv-100,acct-1,2500" in body
        stats = read_pool_stats()
        assert stats["max"] == 5, stats
        assert stats["active"] == 0, stats
    finally:
        stop_stack()
