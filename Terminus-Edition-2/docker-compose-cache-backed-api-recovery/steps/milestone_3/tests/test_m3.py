import json
import os
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
TOOL = APP / "tools" / "compose_api_recovery.py"


def request(td, sp, rid):
    out = td / f"out{rid}"
    return subprocess.run(
        [
            "python3",
            str(TOOL),
            "request",
            "--state",
            str(sp),
            "--out",
            str(out),
            "--method",
            "PUT",
            "--tenant",
            "a",
            "--key",
            "k",
            "--value",
            "v",
            "--request-id",
            rid,
        ],
        text=True,
        capture_output=True,
    ), out


class TestMilestone3:
    def test_duplicate_request_id_does_not_duplicate_outbox(self):
        """Retrying the same request id should not duplicate DB/outbox side effects."""
        td = Path(tempfile.mkdtemp())
        sp = td / "s.json"
        sp.write_text(
            json.dumps(
                {
                    "services": {"db": "healthy", "cache": "healthy", "api": "healthy"},
                    "db": {},
                    "cache": {},
                    "outbox": [],
                    "processed_requests": [],
                    "schema_version": 1,
                    "app_version": "v1",
                }
            )
        )
        _, out1 = request(td, sp, "r1")
        db_after_first = json.loads(sp.read_text())["db"].copy()
        cp2, out2 = request(td, sp, "r1")
        st = json.loads(sp.read_text())
        assert st["db"] == db_after_first
        assert len([e for e in st["outbox"] if e["request_id"] == "r1"]) == 1
        assert "r1" in st["processed_requests"]
        r2 = json.loads((out2 / "result.json").read_text())
        assert r2["status"] == "DUPLICATE"
        assert cp2.returncode == 0

    def test_restart_replays_outbox_idempotently(self):
        """Restart should coalesce duplicate outbox entries and clear stale cache once."""
        td = Path(tempfile.mkdtemp())
        sp = td / "s.json"
        out = td / "out"
        sp.write_text(
            json.dumps(
                {
                    "services": {"db": "healthy", "cache": "healthy", "api": "stopped"},
                    "db": {},
                    "cache": {"a|schema1|v1|k": "old"},
                    "outbox": [
                        {"request_id": "r1", "tenant": "a", "key": "k", "op": "invalidate"},
                        {"request_id": "r1", "tenant": "a", "key": "k", "op": "invalidate"},
                    ],
                    "schema_version": 1,
                    "app_version": "v1",
                }
            )
        )
        cp = subprocess.run(
            ["python3", str(TOOL), "restart", "--state", str(sp), "--out", str(out)],
            text=True,
            capture_output=True,
        )
        st = json.loads(sp.read_text())
        rj = json.loads((out / "result.json").read_text())
        assert cp.returncode == 0
        assert len(st["outbox"]) == 1
        assert st["cache"] == {}
        assert rj["status"] == "RESTARTED"

    def test_api_blocked_after_restart_if_dependency_unhealthy(self):
        """Restart readiness must re-check dependencies, not reuse prior API status."""
        td = Path(tempfile.mkdtemp())
        sp = td / "s.json"
        out = td / "out"
        sp.write_text(
            json.dumps(
                {
                    "services": {"db": "healthy", "cache": "created", "api": "healthy"},
                    "db": {},
                    "cache": {},
                    "outbox": [],
                    "schema_version": 1,
                    "app_version": "v1",
                }
            )
        )
        subprocess.run(
            ["python3", str(TOOL), "restart", "--state", str(sp), "--out", str(out)],
            text=True,
            capture_output=True,
        )
        assert json.loads(sp.read_text())["services"]["api"] == "blocked"


def test_runtime_has_no_capability_unlock():
    source = Path("/app/tools/compose_api_recovery.py").read_text()
    assert "CAPABILITY" not in source
