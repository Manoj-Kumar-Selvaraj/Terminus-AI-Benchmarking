import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


APP = Path("/app")
BASE = "http://127.0.0.1:8080"
DEPLOYMENT = APP / "deploy/kube/billing-deployment.yaml"


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


def test_live_stays_up_during_migration_and_probe_manifest_is_correct():
    manifest = DEPLOYMENT.read_text(encoding="utf-8")
    assert "path: /health/live" in manifest
    assert "path: /health/ready" not in manifest.split("livenessProbe:", 1)[-1]
    assert re.search(r"(startupProbe:|initialDelaySeconds:\s*(1[2-9]|[2-9][0-9]))", manifest), manifest

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
