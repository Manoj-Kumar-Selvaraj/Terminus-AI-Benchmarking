import json
import os
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
TOOL = APP / "tools" / "compose_api_recovery.py"


def call(state):
    td = Path(tempfile.mkdtemp())
    sp = td / "s.json"
    out = td / "out"
    sp.write_text(json.dumps(state))
    cp = subprocess.run(
        ["python3", str(TOOL), "up", "--state", str(sp), "--out", str(out)],
        text=True,
        capture_output=True,
    )
    return cp, out, sp


class TestMilestone1:
    def test_api_blocks_until_db_and_cache_healthy(self):
        """API must not report ready when cache is only created, not healthy."""
        cp, out, sp = call(
            {
                "services": {"db": "healthy", "cache": "created", "api": "stopped"},
                "db": {},
                "cache": {},
                "outbox": [],
            }
        )
        r = json.loads((out / "result.json").read_text())
        assert cp.returncode != 0
        assert r["status"] == "BLOCKED"
        assert json.loads(sp.read_text())["services"]["api"] == "blocked"

    def test_api_ready_when_dependencies_healthy(self):
        """Healthy DB and cache allow API readiness."""
        cp, out, sp = call(
            {
                "services": {"db": "healthy", "cache": "healthy", "api": "stopped"},
                "db": {},
                "cache": {},
                "outbox": [],
            }
        )
        r = json.loads((out / "result.json").read_text())
        assert r["status"] == "UP"
        assert cp.returncode == 0
        assert json.loads(sp.read_text())["services"]["api"] == "healthy"

    def test_blocked_output_contains_operator_reason(self):
        """Dependency failures should produce structured operator evidence."""
        cp, out, sp = call(
            {
                "services": {"db": "created", "cache": "healthy", "api": "stopped"},
                "db": {},
                "cache": {},
                "outbox": [],
            }
        )
        r = json.loads((out / "result.json").read_text())
        assert r["status"] == "BLOCKED"
        assert "dependency" in r["reason"]

    def test_api_blocks_when_both_dependencies_unhealthy(self):
        """API must block when every dependency is unhealthy."""
        cp, out, sp = call(
            {
                "services": {"db": "stopped", "cache": "stopped", "api": "stopped"},
                "db": {},
                "cache": {},
                "outbox": [],
            }
        )
        r = json.loads((out / "result.json").read_text())
        assert cp.returncode != 0
        assert r["status"] == "BLOCKED"
        assert json.loads(sp.read_text())["services"]["api"] == "blocked"

    def test_malformed_state_fails_closed(self):
        """Malformed services shape must fail closed with structured output."""
        td = Path(tempfile.mkdtemp())
        sp = td / "s.json"
        out = td / "out"
        before = '{"services": "not_a_dict"}'
        sp.write_text(before)
        cp = subprocess.run(
            ["python3", str(TOOL), "up", "--state", str(sp), "--out", str(out)],
            text=True,
            capture_output=True,
        )
        assert sp.read_text() == before, "state mutated on malformed input"
        assert cp.returncode != 0
        assert json.loads((out / "result.json").read_text())["status"] == "FAILED_CLOSED"

    def test_missing_services_key_fails_closed(self):
        """State missing required services object must fail closed."""
        td = Path(tempfile.mkdtemp())
        sp = td / "s.json"
        out = td / "out"
        before = "{}"
        sp.write_text(before)
        cp = subprocess.run(
            ["python3", str(TOOL), "up", "--state", str(sp), "--out", str(out)],
            text=True,
            capture_output=True,
        )
        assert sp.read_text() == before, "state mutated on malformed input"
        assert cp.returncode != 0
        assert json.loads((out / "result.json").read_text())["status"] == "FAILED_CLOSED"


def test_runtime_has_no_capability_unlock():
    source = Path("/app/tools/compose_api_recovery.py").read_text()
    assert "CAPABILITY" not in source
