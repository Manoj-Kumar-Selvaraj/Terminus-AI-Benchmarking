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


class TestMilestone2:
    def test_home_phase_is_not_blocking(self):
        """The recovered home must progress beyond the HOME_CORRUPT diagnostic phase."""
        code, diag = diagnose()
        assert diag["phase"] != "RUNTIME_INCOMPATIBLE", diag
        assert diag["phase"] != "HOME_CORRUPT", diag
        assert check("home_integrity", diag)["ok"] is True

    def test_required_xml_files_parse(self):
        """Core Jenkins home XML files must be structurally valid after restoration."""
        assert_xml("jenkins_home/config.xml")
        assert_xml("jenkins_home/credentials.xml")
        assert_xml("jenkins_home/queue.xml")

    def test_config_records_target_version(self):
        """Restored config must represent the target controller, not only the old pre-upgrade version."""
        text = (APP / "jenkins_home/config.xml").read_text()
        assert "<version>2.462.3</version>" in text

    def test_failed_upgrade_lock_removed(self):
        """Failed boot upgrade lock must not remain active in live Jenkins home."""
        assert not (APP / "jenkins_home/UPGRADE.lock").exists()

    def test_restore_state_has_snapshot_evidence(self):
        """Controller state must document recovered target schema and restore evidence."""
        state = load("jenkins_home/controller_state.json")
        assert state["target_version"] == "2.462.3"
        assert state["home_schema"] == "recovered-target"
        assert state["upgrade_status"] == "RESTORED"
        assert state["restored_from_snapshot"] == "pre-upgrade-20260618"

    def test_jobs_preserved_from_backup(self):
        """Recovery must preserve all required jobs rather than replacing home with a minimal fake."""
        jobs = set(load("jenkins_home/jobs.json")["jobs"])
        assert {
            "payments-ledger/main",
            "shared-library/test",
            "platform-smoke/healthcheck",
        } <= jobs
        assert (APP / "jenkins_home/jobs/payments-ledger/config.xml").exists()
        assert (APP / "jenkins_home/jobs/shared-library/config.xml").exists()
        assert (APP / "jenkins_home/jobs/platform-smoke/config.xml").exists()

    def test_credentials_preserved_from_backup(self):
        """Critical credential IDs from backup must still be present after home recovery."""
        text = (APP / "jenkins_home/credentials.xml").read_text()
        assert "cred-prod-ledger" in text
        assert "cred-scm-bot" in text
