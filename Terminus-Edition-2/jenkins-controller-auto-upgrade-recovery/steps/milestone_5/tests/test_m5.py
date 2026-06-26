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


class TestMilestone5:
    def test_simulator_reaches_ready_and_writes_status(self):
        """Final recovery must reach READY through simulator start and write controller status."""
        proc = run_start()
        assert proc.returncode == 0, proc.stderr + proc.stdout
        status = load("out/controller_status.json")
        assert status["status"] == "READY"
        assert status["cluster"] == "prod-ci-east"
        assert status["deployment"] == "jenkins-controller"
        assert status["jenkins_version"] == "2.462.3"
        assert status["java_major"] >= 17
        assert status["home_claim"] == "jenkins-home-rwo"

    def test_cluster_fencing_check_passes(self):
        """Exactly one elected active controller may mount the RWO home read/write."""
        _, diag = diagnose()
        assert diag["phase"] == "READY", diag
        c = check("cluster_fencing", diag)
        assert c["ok"] is True
        assert c["fencing_ok"] is True
        assert c["service_ok"] is True

    def test_exactly_one_active_rw_elected_controller(self):
        """Topology must not leave restore and primary pods active on the same home claim."""
        topo = load("cluster/topology.json")
        active_rw = [
            p
            for p in topo["pods"]
            if p.get("role") == "active"
            and p.get("mounts_home")
            and p.get("read_write")
        ]
        elected = [p for p in topo["pods"] if p.get("elected") is True]
        assert len(active_rw) == 1
        assert len(elected) == 1
        assert active_rw[0]["name"] == elected[0]["name"]
        assert topo["home_claim"]["access_mode"] == "ReadWriteOnce"

    def test_service_routes_to_elected_active_controller(self):
        """The Jenkins service must point at the elected active controller, not a restore pod."""
        topo = load("cluster/topology.json")
        elected_name = [p["name"] for p in topo["pods"] if p.get("elected")][0]
        assert topo["service"]["name"] == "jenkins-web"
        assert topo["service"]["routes_to"] == elected_name
        assert topo["service"]["routes_to"] != "jenkins-restore-0"

    def test_online_agents_meet_remoting_java_contract(self):
        """Online build agents must satisfy the controller remoting Java requirement."""
        topo = load("cluster/topology.json")
        required = load("config/version_contract.json")["required_agent_java"]
        for agent in topo["agents"]:
            if agent["online"]:
                assert agent["remoting_java_major"] >= required

    def test_queue_deduplicated_but_required_items_preserved(self):
        """Queue recovery must remove duplicate queue IDs without dropping required queued work."""
        items = load("jenkins_home/queue.json")["items"]
        ids = [i["id"] for i in items]
        assert len(ids) == len(set(ids))
        assert {"q-1001", "q-1002"} <= set(ids)
        by_id = {i["id"]: i["job"] for i in items}
        assert by_id["q-1001"] == "payments-ledger/main"
        assert by_id["q-1002"] == "shared-library/test"

    def test_diagnostics_output_matches_ready_status(self):
        """Controller diagnostics and final status output must agree on readiness."""
        _ = run_start()
        diag = load("out/controller_diagnostics.json")
        assert diag["phase"] == "READY"
        assert diag["ready"] is True
        assert not diag["errors"]

    def test_all_previous_checks_still_true(self):
        """Final milestone must remain cumulative across runtime, home, plugin, and policy checks."""
        _, diag = diagnose()
        for name in [
            "runtime",
            "home_integrity",
            "plugins",
            "upgrade_policy",
            "cluster_fencing",
        ]:
            assert check(name, diag)["ok"] is True
