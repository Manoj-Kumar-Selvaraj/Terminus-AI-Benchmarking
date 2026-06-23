import re
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


APP = Path("/app")
JVM_OPTIONS = APP / "config/jvm.options"
PROPERTIES = APP / "config/application.properties"
CONTAINER_MEMORY_MB = 256


def stop_stack():
    subprocess.run(["bash", str(APP / "scripts/stop_service.sh")], check=False)


def start_stack():
    stop_stack()
    subprocess.run(["bash", str(APP / "scripts/run_service.sh")], check=True)


def wait_for_ready(timeout: float = 45.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8080/health/ready", timeout=2) as response:
                if response.status == 200:
                    return
        except urllib.error.HTTPError as error:
            if error.code == 200:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError("readiness never became UP")


def test_jvm_options_respect_container_memory_limit():
    """JVM flags must be container-aware, drop fixed heaps, and keep a safe MaxRAMPercentage."""
    text = JVM_OPTIONS.read_text(encoding="utf-8")
    assert "-XX:+UseContainerSupport" in text
    match = re.search(r"-XX:MaxRAMPercentage=(\d+(?:\.\d+)?)", text)
    assert match, text
    percentage = float(match.group(1))
    assert 25 <= percentage <= 75, f"MaxRAMPercentage={percentage} unsafe for 256Mi"
    lowered = text.lower()
    assert not re.search(r"(?m)^\s*-xmx\S+", lowered), text
    assert not re.search(r"(?m)^\s*-xms\S+", lowered), text
    props = PROPERTIES.read_text(encoding="utf-8")
    assert "billing.container.memory.mb=256" in props
    effective_heap_mb = CONTAINER_MEMORY_MB * (percentage / 100.0)
    assert effective_heap_mb <= CONTAINER_MEMORY_MB * 0.75, effective_heap_mb


def test_prior_milestones_remain_functional():
    """M1 datasource readiness and M2 pool-release behavior must survive JVM tuning.

    Starts the stack with the tuned jvm.options, waits for readiness, then posts
    a zero-cent charge. The handler must reject it with HTTP 400 without leaving
    borrowed JDBC connections active (pool leak regression from milestone 2).
    """
    start_stack()
    try:
        wait_for_ready()
        request = urllib.request.Request(
            "http://127.0.0.1:8080/api/charge?account_id=acct-1&amount_cents=0",
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            assert error.code == 400
        with urllib.request.urlopen("http://127.0.0.1:8080/internal/pool", timeout=5) as response:
            body = response.read().decode("utf-8")
        stats = {}
        for line in body.splitlines():
            key, value = line.split("=", 1)
            stats[key] = int(value)
        assert stats["active"] == 0, stats
    finally:
        stop_stack()
