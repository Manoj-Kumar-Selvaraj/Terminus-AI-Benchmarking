import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


APP = Path("/app")
BASE = "http://127.0.0.1:8080"
DEPLOYMENT = APP / "deploy/kube/billing-deployment.yaml"
PROPERTIES = APP / "config/application.properties"


def stop_stack():
    subprocess.run(["bash", str(APP / "scripts/stop_service.sh")], check=False)


def start_stack():
    stop_stack()
    subprocess.run(["bash", str(APP / "scripts/run_service.sh")], check=True)


def wait_for_port(timeout: float = 20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health/live", timeout=1) as response:
                if response.status in {200, 503}:
                    return
        except urllib.error.HTTPError as error:
            if error.code in {200, 503}:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise AssertionError("billing HTTP listener never opened")


def fetch_status(path: str) -> int:
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=2) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def liveness_probe_section(manifest: str) -> str:
    match = re.search(r"livenessProbe:\s*\n(?:[ \t]+.+\n?)+", manifest)
    assert match, "livenessProbe section missing from deployment manifest"
    return match.group(0)


def probe_section(manifest: str, name: str) -> str:
    match = re.search(rf"{name}:\s*\n(?:[ \t]+.+\n?)+", manifest)
    assert match, f"{name} section missing from deployment manifest"
    return match.group(0)


def field_int(section: str, name: str, default: int = 0) -> int:
    match = re.search(rf"{name}:\s*(\d+)", section)
    return int(match.group(1)) if match else default


def property_int(name: str) -> int:
    for line in PROPERTIES.read_text(encoding="utf-8").splitlines():
        if line.startswith(name + "="):
            return int(line.split("=", 1)[1])
    raise AssertionError(f"{name} missing from application.properties")


def test_probe_manifest_is_correct():
    """Liveness probe must target /health/live with startup-safe timing."""
    manifest = DEPLOYMENT.read_text(encoding="utf-8")
    liveness = liveness_probe_section(manifest)
    readiness = probe_section(manifest, "readinessProbe")
    assert "path: /health/live" in liveness
    assert "path: /health/ready" not in liveness
    assert "path: /health/ready" in readiness
    assert re.search(
        r"(startupProbe:|initialDelaySeconds:\s*(1[2-9]|[2-9][0-9]))",
        manifest,
    ), manifest


def test_startup_probe_budget_covers_configured_migration_window():
    """Probe timing must be derived from the configured migration duration, not a lucky path swap."""
    manifest = DEPLOYMENT.read_text(encoding="utf-8")
    migration_seconds = property_int("billing.migration.seconds")
    if "startupProbe:" in manifest:
        startup = probe_section(manifest, "startupProbe")
        assert "path: /health/live" in startup
        period = field_int(startup, "periodSeconds", default=10)
        failures = field_int(startup, "failureThreshold", default=3)
        assert period * failures >= migration_seconds + 4, startup
    else:
        liveness = liveness_probe_section(manifest)
        assert field_int(liveness, "initialDelaySeconds") >= migration_seconds + 4


def test_live_stays_up_during_migration():
    """Live returns 200 while ready stays 503 during startup migration."""
    start_stack()
    try:
        wait_for_port()
        live_during_migration = fetch_status("/health/live")
        ready_during_migration = fetch_status("/health/ready")
        assert live_during_migration == 200, live_during_migration
        assert ready_during_migration == 503, ready_during_migration

        deadline = time.time() + 45
        while time.time() < deadline:
            if fetch_status("/health/ready") == 200:
                break
            time.sleep(0.5)
        else:
            raise AssertionError("readiness never became UP after migration")

        with urllib.request.urlopen(f"{BASE}/api/invoices", timeout=5) as response:
            body = response.read().decode("utf-8")
        assert "inv-100,acct-1,2500" in body
    finally:
        stop_stack()
