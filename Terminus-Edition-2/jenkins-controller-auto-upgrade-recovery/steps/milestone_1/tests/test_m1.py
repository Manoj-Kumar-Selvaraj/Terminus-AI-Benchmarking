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


class TestMilestone1:
    def test_runtime_phase_is_not_blocking(self):
        """The recovered deployment must progress beyond the Java/runtime compatibility failure."""
        code, diag = diagnose()
        assert diag["phase"] != "RUNTIME_INCOMPATIBLE", diag
        assert diag["phase"] != "READY", (
            "M1 should not resolve all phases — later damage must remain"
        )
        assert check("runtime", diag)["ok"] is True

    def test_target_version_not_downgraded(self):
        """The incident target version must remain pinned to the upgraded controller version."""
        cluster = load("cluster/controller_deployment.json")
        assert cluster["jenkins_version"] == "2.462.3"

    def test_java_major_satisfies_contract(self):
        """Configured Java major must satisfy the simulator's target-version contract."""
        cluster = load("cluster/controller_deployment.json")
        contract = load("config/version_contract.json")
        assert int(cluster["java_major"]) >= int(
            contract["versions"]["2.462.3"]["required_java"]
        )

    def test_image_metadata_matches_required_runtime(self):
        """The controller image metadata should not still advertise the old JDK line."""
        cluster = load("cluster/controller_deployment.json")
        assert "jdk17" in cluster["controller_image"]
        assert "jdk11" not in cluster["controller_image"]

    def test_cluster_identity_preserved(self):
        """The runtime repair must not change cluster, namespace, deployment, service, replica, or PVC identity."""
        c = load("cluster/controller_deployment.json")
        assert c["cluster"] == "prod-ci-east"
        assert c["namespace"] == "jenkins-prod"
        assert c["deployment"] == "jenkins-controller"
        assert c["service"] == "jenkins-web"
        assert c["replicas"] == 1
        assert c["home_claim"] == "jenkins-home-rwo"

    def test_no_direct_success_output_bypass(self):
        """M1 should not pass by prewriting the final READY status output."""
        status = APP / "out/controller_status.json"
        assert not status.exists(), (
            "controller_status.json should be produced only by simulator start in final recovery"
        )
