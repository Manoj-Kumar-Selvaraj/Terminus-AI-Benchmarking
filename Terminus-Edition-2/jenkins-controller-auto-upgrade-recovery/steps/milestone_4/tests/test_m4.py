import json
import subprocess
import pathlib
import xml.etree.ElementTree as ET

APP = pathlib.Path("/app")


def load(rel):
    with (APP / rel).open() as f:
        return json.load(f)


def diagnose():
    proc = subprocess.run(
        ["python3", "/app/scripts/jenkins_cluster_sim.py", "diagnose", "--json"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.returncode, json.loads(proc.stdout)


def run_start():
    return subprocess.run(
        ["/app/scripts/run_controller.sh"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def check(name, diag=None):
    if diag is None:
        _, diag = diagnose()
    for c in diag["checks"]:
        if c["name"] == name:
            return c
    raise AssertionError(f"missing check {name}: {diag}")


def assert_xml(rel):
    ET.parse(APP / rel)


class TestMilestone4:
    def test_automation_phase_is_not_blocking(self):
        """Upgrade automation safeguards must no longer block diagnostics."""
        _, diag = diagnose()
        assert diag["phase"] not in {
            "RUNTIME_INCOMPATIBLE",
            "HOME_CORRUPT",
            "PLUGIN_INCOMPATIBLE",
            "UNSAFE_AUTOMATION",
        }, diag
        assert check("upgrade_policy", diag)["ok"] is True

    def test_unattended_latest_upgrade_disabled(self):
        """Recovered controller must not remain on an unguarded moving upgrade channel."""
        p = load("cluster/auto_upgrade_policy.json")
        assert p["auto_upgrade_enabled"] is False
        assert p["channel"] == "pinned-lts"
        assert p["pin_target_version"] is True
        assert p["target_version"] == "2.462.3"

    def test_preflight_and_backup_are_mandatory(self):
        """Future upgrades must require Java preflight and a real backup snapshot."""
        p = load("cluster/auto_upgrade_policy.json")
        assert p["java_preflight_required"] is True
        assert p["backup_required"] is True
        assert p["abort_on_failed_preflight"] is True
        snapshot = APP / "backups" / p["required_backup_snapshot"]
        assert snapshot.exists() and snapshot.is_dir()

    def test_lock_strategy_is_safe_after_verified_restore(self):
        """Upgrade lock lifecycle must be explicit and safe after restore."""
        p = load("cluster/auto_upgrade_policy.json")
        assert p["lock_strategy"] == "clear-after-verified-restore"

    def test_policy_evidence_not_deleted(self):
        """Incident audit evidence and policy files must remain available for review."""
        assert (APP / "evidence/upgrade_controller_audit.json").exists()
        audit = load("evidence/upgrade_controller_audit.json")
        assert audit["cluster"] == "prod-ci-east"

    def test_prior_milestones_still_satisfied(self):
        """Automation recovery must not regress runtime, home, or plugin checks."""
        _, diag = diagnose()
        assert check("runtime", diag)["ok"] is True
        assert check("home_integrity", diag)["ok"] is True
        assert check("plugins", diag)["ok"] is True

    def test_target_not_silently_rolled_back(self):
        """Safe policy must preserve the selected target version instead of hiding the incident by rollback."""
        assert (
            load("cluster/controller_deployment.json")["jenkins_version"] == "2.462.3"
        )
        assert load("cluster/auto_upgrade_policy.json")["target_version"] == "2.462.3"
