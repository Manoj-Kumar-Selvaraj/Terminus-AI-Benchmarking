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


def wait_for_ready(timeout: float = 45.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/health/ready", timeout=2) as response:
                if response.status == 200:
                    return
        except urllib.error.HTTPError as error:
            if error.code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError("readiness never became UP")


def post_charge(account_id: str, amount_cents: int) -> int:
    url = f"{BASE}/api/charge?account_id={account_id}&amount_cents={amount_cents}"
    request = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def read_pool_stats() -> dict[str, int]:
    with urllib.request.urlopen(f"{BASE}/internal/pool", timeout=5) as response:
        body = response.read().decode("utf-8")
    stats = {}
    for line in body.splitlines():
        key, value = line.split("=", 1)
        stats[key] = int(value)
    return stats


def test_invalid_charge_soak_does_not_exhaust_pool():
    start_stack()
    try:
        wait_for_ready()
        invalid_requests = []
        invalid_requests.extend([0] * 10)
        invalid_requests.extend([-1] * 10)
        for amount in invalid_requests:
            status = post_charge("acct-1", amount)
            assert status == 400
        for _ in range(6):
            status = post_charge("missing-acct", 100)
            assert status in {400, 404}
        stats = read_pool_stats()
        assert stats["active"] == 0, stats
        assert stats["idle"] <= stats["max"]
        with urllib.request.urlopen(f"{BASE}/api/invoices", timeout=5) as response:
            body = response.read().decode("utf-8")
        assert response.status == 200
        assert "inv-100,acct-1,2500" in body
    finally:
        stop_stack()
