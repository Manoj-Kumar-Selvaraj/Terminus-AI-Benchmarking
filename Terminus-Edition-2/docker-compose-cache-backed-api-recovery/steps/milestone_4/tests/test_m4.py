import json
import os
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
TOOL = APP / "tools" / "compose_api_recovery.py"


def mig(state, target="2", app="v2"):
    td = Path(tempfile.mkdtemp())
    sp = td / "s.json"
    out = td / "out"
    sp.write_text(json.dumps(state))
    cp = subprocess.run(
        [
            "python3",
            str(TOOL),
            "migrate",
            "--state",
            str(sp),
            "--out",
            str(out),
            "--target-schema",
            target,
            "--holder",
            "h1",
            "--app-version",
            app,
        ],
        text=True,
        capture_output=True,
    )
    return cp, out, sp


class TestMilestone4:
    def test_existing_migration_lock_blocks_new_migration(self):
        """A held migration lock must stop another migration from altering schema."""
        cp, out, sp = mig(
            {
                "services": {},
                "db": {},
                "cache": {},
                "outbox": [],
                "schema_version": 1,
                "migration_lock": "other",
            },
            "2",
            "v2",
        )
        res = json.loads((out / "result.json").read_text())
        assert cp.returncode != 0
        assert res["status"] == "FAILED_CLOSED"
        assert json.loads(sp.read_text())["schema_version"] == 1

    def test_incompatible_app_version_fails_without_partial_schema_change(self):
        """Incompatible app/schema pairs should fail closed before schema mutation."""
        cp, out, sp = mig(
            {
                "services": {},
                "db": {},
                "cache": {},
                "outbox": [],
                "schema_version": 1,
                "migration_lock": None,
            },
            "2",
            "v1",
        )
        res = json.loads((out / "result.json").read_text())
        assert cp.returncode != 0
        assert res["status"] == "FAILED_CLOSED"
        assert json.loads(sp.read_text())["schema_version"] == 1

    def test_invalid_app_version_v4_is_rejected(self):
        """Only v2 and v3 are valid for schema 2+ migrations."""
        cp, out, sp = mig(
            {
                "services": {},
                "db": {},
                "cache": {},
                "outbox": [],
                "schema_version": 1,
                "migration_lock": None,
            },
            "2",
            "v4",
        )
        res = json.loads((out / "result.json").read_text())
        assert cp.returncode != 0
        assert res["status"] == "FAILED_CLOSED"

    def test_app_version_v3_is_accepted(self):
        """Schema 2 migrations should accept app version v3."""
        cp, out, sp = mig(
            {
                "services": {},
                "db": {},
                "cache": {},
                "outbox": [],
                "schema_version": 1,
                "migration_lock": None,
            },
            "2",
            "v3",
        )
        res = json.loads((out / "result.json").read_text())
        assert cp.returncode == 0
        assert res["status"] == "MIGRATED"
        assert json.loads(sp.read_text())["schema_version"] == 2

    def test_successful_migration_releases_lock(self):
        """Successful migration should update schema and release the migration lock."""
        cp, out, sp = mig(
            {
                "services": {},
                "db": {},
                "cache": {},
                "outbox": [],
                "schema_version": 1,
                "migration_lock": None,
            },
            "2",
            "v2",
        )
        st = json.loads(sp.read_text())
        res = json.loads((out / "result.json").read_text())
        assert cp.returncode == 0
        assert res["status"] == "MIGRATED"
        assert st["schema_version"] == 2
        assert st["migration_lock"] is None


def test_runtime_has_no_capability_unlock():
    source = Path("/app/tools/compose_api_recovery.py").read_text()
    assert "CAPABILITY" not in source
