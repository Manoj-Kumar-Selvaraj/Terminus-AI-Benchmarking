import json
import os
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
TOOL = APP / "tools" / "compose_api_recovery.py"


def req(td, sp, method, tenant, key, value="", rid="r"):
    out = td / f"out{tenant}{key}{method}{rid}"
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
            method,
            "--tenant",
            tenant,
            "--key",
            key,
            "--value",
            value,
            "--request-id",
            rid,
        ],
        text=True,
        capture_output=True,
    ), out


class TestMilestone2:
    def test_cache_key_is_tenant_namespaced(self):
        """Tenants with the same logical key must not read each other's cache value."""
        td = Path(tempfile.mkdtemp())
        sp = td / "s.json"
        sp.write_text(
            json.dumps(
                {
                    "services": {"db": "healthy", "cache": "healthy", "api": "healthy"},
                    "db": {"a:item": "A", "b:item": "B"},
                    "cache": {},
                    "outbox": [],
                    "schema_version": 1,
                    "app_version": "v1",
                }
            )
        )
        req(td, sp, "GET", "a", "item")
        req(td, sp, "GET", "b", "item")
        cache = json.loads(sp.read_text())["cache"]
        assert len(cache) == 2
        assert "a|schema1|v1|item" in cache
        assert "b|schema1|v1|item" in cache

    def test_put_invalidates_stale_cache(self):
        """Writes must invalidate existing cache entries for that tenant/key."""
        td = Path(tempfile.mkdtemp())
        sp = td / "s.json"
        sp.write_text(
            json.dumps(
                {
                    "services": {"db": "healthy", "cache": "healthy", "api": "healthy"},
                    "db": {"a:item": "old"},
                    "cache": {
                        "a|schema1|v1|item": "stale_v1",
                        "a|schema2|v2|item": "stale_v2",
                        "b|schema1|v1|item": "other_tenant",
                    },
                    "outbox": [],
                    "schema_version": 2,
                    "app_version": "v2",
                }
            )
        )
        req(td, sp, "PUT", "a", "item", "fresh", "w1")
        cache = json.loads(sp.read_text())["cache"]
        assert not any(k.startswith("a|") and k.endswith("|item") for k in cache)
        assert "b|schema1|v1|item" in cache

    def test_put_invalidates_bare_logical_key(self):
        """PUT must also remove legacy bare logical keys, not only namespaced entries."""
        td = Path(tempfile.mkdtemp())
        sp = td / "s.json"
        sp.write_text(
            json.dumps(
                {
                    "services": {"db": "healthy", "cache": "healthy", "api": "healthy"},
                    "db": {"a:item": "fresh"},
                    "cache": {
                        "item": "legacy_bare",
                        "a|schema1|v1|item": "namespaced",
                    },
                    "outbox": [],
                    "schema_version": 1,
                    "app_version": "v1",
                }
            )
        )
        req(td, sp, "PUT", "a", "item", "fresh", "w-bare")
        cache = json.loads(sp.read_text())["cache"]
        assert "item" not in cache
        assert not any(k.endswith("|item") for k in cache if k.startswith("a|"))

    def test_milestone1_dependency_gating_still_blocks(self):
        """Milestone 1 up gating must keep blocking unhealthy dependencies."""
        td = Path(tempfile.mkdtemp())
        sp = td / "s.json"
        out = td / "out"
        sp.write_text(
            json.dumps(
                {
                    "services": {"db": "stopped", "cache": "healthy", "api": "stopped"},
                    "db": {},
                    "cache": {},
                    "outbox": [],
                }
            )
        )
        cp = subprocess.run(
            ["python3", str(TOOL), "up", "--state", str(sp), "--out", str(out)],
            text=True,
            capture_output=True,
        )
        r = json.loads((out / "result.json").read_text())
        assert cp.returncode != 0
        assert r["status"] == "BLOCKED"
        assert json.loads(sp.read_text())["services"]["api"] == "blocked"

    def test_cache_key_includes_schema_and_app(self):
        """Cache provenance should include schema and app version."""
        td = Path(tempfile.mkdtemp())
        sp = td / "s.json"
        sp.write_text(
            json.dumps(
                {
                    "services": {"db": "healthy", "cache": "healthy", "api": "healthy"},
                    "db": {"a:k": "v"},
                    "cache": {},
                    "outbox": [],
                    "schema_version": 2,
                    "app_version": "v2",
                }
            )
        )
        cp, out = req(td, sp, "GET", "a", "k")
        assert json.loads((out / "result.json").read_text())["cache_key"] == "a|schema2|v2|k"


def test_runtime_has_no_capability_unlock():
    source = Path("/app/tools/compose_api_recovery.py").read_text()
    assert "CAPABILITY" not in source
