import json
import re
import subprocess
import pathlib
import xml.etree.ElementTree as ET

APP = pathlib.Path("/app")


def version_tuple(v):
    parts = []
    for piece in re.split(r"[.v_-]", str(v)):
        if piece.isdigit():
            parts.append(int(piece))
            if len(parts) == 3:
                break
    return tuple(parts + [0] * (3 - len(parts)))


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


class TestMilestone3:
    def test_plugin_phase_is_not_blocking(self):
        """Plugin baseline must no longer block controller diagnostics."""
        _, diag = diagnose()
        assert diag["phase"] not in {
            "RUNTIME_INCOMPATIBLE",
            "HOME_CORRUPT",
            "PLUGIN_INCOMPATIBLE",
        }, diag
        assert check("plugins", diag)["ok"] is True

    def test_all_essential_plugins_present_and_enabled(self):
        """Every essential plugin in the contract must exist and be enabled."""
        contract = load("config/version_contract.json")
        plugins = load("jenkins_home/plugins/plugins.json")
        for name in contract["essential_plugins"]:
            assert name in plugins
            assert plugins[name]["enabled"] is True

    def test_plugin_versions_meet_target_baseline(self):
        """Essential plugin versions must be upgraded to the target baseline, not merely enabled."""
        plugins = load("jenkins_home/plugins/plugins.json")
        baseline = load("config/version_contract.json")["target_plugin_baseline"]
        for name, req in baseline.items():
            assert version_tuple(plugins[name]["version"]) >= version_tuple(
                req["min_version"]
            )

    def test_version_contract_not_weakened(self):
        """The solution must not pass by deleting essential plugin requirements from the contract."""
        contract = load("config/version_contract.json")
        assert contract["essential_plugins"] == [
            "workflow-job",
            "credentials-binding",
            "matrix-auth",
            "git",
        ]
        assert contract["required_agent_java"] == 17

    def test_home_restore_evidence_survives_plugin_fix(self):
        """Plugin work must not regress the restored Jenkins home evidence from M2."""
        state = load("jenkins_home/controller_state.json")
        assert state["home_schema"] == "recovered-target"
        assert state["restored_from_snapshot"] == "pre-upgrade-20260618"
        assert_xml("jenkins_home/config.xml")

    def test_optional_plugin_does_not_replace_essential_set(self):
        """Noisy optional plugins may remain, but they cannot substitute for essential plugin recovery."""
        plugins = load("jenkins_home/plugins/plugins.json")
        assert "monitoring-theme" in plugins
        assert "workflow-job" in plugins and "credentials-binding" in plugins

    def test_runtime_still_uses_required_java(self):
        """Plugin remediation must not revert the Java runtime from the target requirement."""
        cluster = load("cluster/controller_deployment.json")
        assert cluster["java_major"] >= 17
        assert "jdk17" in cluster["controller_image"]
