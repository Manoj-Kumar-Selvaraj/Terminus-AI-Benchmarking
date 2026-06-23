import json
import os
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
TOOL = APP / "tools" / "compose_api_recovery.py"


def rb(state, app="v1"):
    td = Path(tempfile.mkdtemp())
    sp = td / "s.json"
    out = td / "out"
    sp.write_text(json.dumps(state))
    cp = subprocess.run(
        [
            "python3",
            str(TOOL),
            "rollback",
            "--state",
            str(sp),
            "--out",
            str(out),
            "--app-version",
            app,
        ],
        text=True,
        capture_output=True,
    )
    return cp, out, sp


class TestMilestone5:
    def test_rollback_preserves_database_rows(self):
        """App rollback must not drop committed database rows."""
        cp, out, sp = rb(
            {
                "services": {"cache": "healthy", "api": "healthy"},
                "db": {"a:k": "v", "b:x": "y", "c:z": "w"},
                "cache": {},
                "outbox": [],
                "schema_version": 2,
                "app_version": "v2",
            },
            "v1",
        )
        assert json.loads(sp.read_text())["db"] == {"a:k": "v", "b:x": "y", "c:z": "w"}

    def test_rollback_invalidates_incompatible_cache_namespace(self):
        """Cache entries for a newer app version must be removed during rollback."""
        cp, out, sp = rb(
            {
                "services": {"cache": "healthy", "api": "healthy"},
                "db": {},
                "cache": {"a|schema2|v2|k": "stale", "a|schema2|v1|k": "ok"},
                "outbox": [],
                "schema_version": 2,
                "app_version": "v2",
            },
            "v1",
        )
        cache = json.loads(sp.read_text())["cache"]
        assert list(cache) == ["a|schema2|v1|k"]

    def test_rollback_leaves_api_unchanged_when_cache_healthy(self):
        """Rollback must not block API when cache dependency remains healthy."""
        cp, out, sp = rb(
            {
                "services": {"cache": "healthy", "api": "healthy"},
                "db": {},
                "cache": {"a|schema2|v2|k": "stale", "a|schema2|v1|k": "ok"},
                "outbox": [],
                "schema_version": 2,
                "app_version": "v2",
            },
            "v1",
        )
        assert json.loads(sp.read_text())["services"]["api"] == "healthy"

    def test_cache_outage_blocks_api_after_rollback(self):
        """Rollback must not mark API healthy if cache dependency is down."""
        cp, out, sp = rb(
            {
                "services": {"cache": "created", "api": "healthy"},
                "db": {},
                "cache": {},
                "outbox": [],
                "schema_version": 2,
                "app_version": "v2",
            },
            "v1",
        )
        assert json.loads(sp.read_text())["services"]["api"] == "blocked"

    def test_rollback_writes_result_json(self):
        """Rollback must emit operator-facing result.json metadata."""
        cp, out, sp = rb(
            {
                "services": {"cache": "healthy", "api": "healthy"},
                "db": {"a:k": "v"},
                "cache": {},
                "outbox": [],
                "schema_version": 2,
                "app_version": "v2",
            },
            "v1",
        )
        r = json.loads((out / "result.json").read_text())
        assert cp.returncode == 0
        assert r["status"] == "ROLLED_BACK"
        assert r["app_version"] == "v1"
        assert r["db_count"] == 1
        assert r["cache_count"] == 0


def test_runtime_has_no_capability_unlock():
    source = Path("/app/tools/compose_api_recovery.py").read_text()
    assert "CAPABILITY" not in source
