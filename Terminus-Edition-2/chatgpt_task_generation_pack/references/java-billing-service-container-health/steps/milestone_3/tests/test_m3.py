import re
import subprocess
from pathlib import Path


APP = Path("/app")
JVM_OPTIONS = APP / "config/jvm.options"
PROPERTIES = APP / "config/application.properties"


def test_jvm_options_respect_container_memory_limit():
    text = JVM_OPTIONS.read_text(encoding="utf-8")
    assert "-XX:+UseContainerSupport" in text
    assert re.search(r"-XX:MaxRAMPercentage=\d+", text), text
    assert "-Xmx512m" not in text.lower()
    props = PROPERTIES.read_text(encoding="utf-8")
    assert "billing.container.memory.mb=256" in props


def test_prior_milestones_remain_functional():
    subprocess.run(["bash", str(APP / "scripts/stop_service.sh")], check=False)
    subprocess.run(["bash", str(APP / "scripts/run_service.sh")], check=True)
    try:
        import time
        import urllib.error
        import urllib.request

        deadline = time.time() + 45
        while time.time() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8080/health/ready", timeout=2) as response:
                    if response.status == 200:
                        break
            except urllib.error.HTTPError as error:
                if error.code == 200:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            raise AssertionError("readiness never became UP")
        request = urllib.request.Request(
            "http://127.0.0.1:8080/api/charge?account_id=acct-1&amount_cents=0",
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            assert error.code == 400
    finally:
        subprocess.run(["bash", str(APP / "scripts/stop_service.sh")], check=False)
