import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


APP = Path("/app")
BASE = "http://127.0.0.1:8080"


def stop_stack():
    subprocess.run(["bash", str(APP / "scripts/stop_service.sh")], check=False)


def start_stack():
    stop_stack()
    subprocess.run(["bash", str(APP / "scripts/run_service.sh")], check=True)


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


def test_readiness_and_invoice_list_after_datasource_fix():
    start_stack()
    try:
        wait_for_status("/health/ready", 200, timeout=45)
        with urllib.request.urlopen(f"{BASE}/api/invoices", timeout=5) as response:
            body = response.read().decode("utf-8")
        assert response.status == 200
        assert "inv-100,acct-1,2500" in body
    finally:
        stop_stack()
