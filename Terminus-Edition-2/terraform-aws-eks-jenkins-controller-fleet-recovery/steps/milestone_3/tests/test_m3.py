import json
import os
import re
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF = APP / "terraform"


def read(name):
    return (TF / name).read_text(encoding="utf-8")


def all_tf():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tf")))


class TestMilestone3:
    def test_required_plugins_pinned_internal(self):
        """Required plugins are pinned and not from public update feeds."""
        catalog = read("plugin-catalog.yaml")
        required = [
            "configuration-as-code",
            "kubernetes",
            "workflow-aggregator",
            "job-dsl",
            "git",
            "credentials",
            "matrix-auth",
            "cloudbees-casc-client",
        ]
        for plugin in required:
            assert re.search(rf"id:\s*{re.escape(plugin)}\b", catalog)
        assert re.search(r"pluginSource:\s*internal-mirror", catalog)
        assert "latest" not in catalog.lower()
        assert "updates.jenkins.io" not in catalog.lower()
        assert len(re.findall(r'version:\s*"?([0-9][^"\n ]*)', catalog)) >= 8

    def test_jcasc_and_seed_jobs(self):
        """JCasC is restricted, each controller has a seed job, and JOC owns no jobs."""
        jcasc = read("jcasc.yaml")
        assert "authorizationStrategy" in jcasc
        assert "matrix" in jcasc or "roleBased" in jcasc
        assert re.search(r"allowsSignup:\s*false", jcasc)
        jobs = json.loads(read("jenkins_jobs.json"))
        assert set(jobs.get("controllers", {})) == {
            "payments-controller",
            "risk-controller",
            "platform-controller",
        }
        job_entries = jobs.get("jobs", {})
        assert len(job_entries) >= 6, "Fleet requires at least six production jobs"
        approved_plugins = {
            "configuration-as-code",
            "kubernetes",
            "workflow-aggregator",
            "job-dsl",
            "git",
            "credentials",
            "matrix-auth",
            "cloudbees-casc-client",
        }
        allowed_controllers = {
            "payments-controller",
            "risk-controller",
            "platform-controller",
        }
        for controller, cdata in jobs["controllers"].items():
            assert cdata.get("seed_job") and str(cdata["seed_job"]).strip()
            assert isinstance(cdata.get("jobs"), list) and len(cdata["jobs"]) > 0, (
                f"{controller} must declare a non-empty jobs list"
            )
            for job_name in cdata["jobs"]:
                assert job_name in job_entries, f"{job_name} missing from jobs object"
        per_controller = {name: 0 for name in allowed_controllers}
        controllers = set()
        for job_name, job in job_entries.items():
            assert isinstance(job.get("folder"), str) and job["folder"].strip()
            assert isinstance(job.get("required_plugins"), list)
            assert job["required_plugins"]
            assert set(job["required_plugins"]) <= approved_plugins
            ctrl = job.get("controller", "")
            assert ctrl in allowed_controllers, f"Invalid controller for {job_name}: {ctrl}"
            assert ctrl.lower() != "joc"
            controllers.add(ctrl)
            per_controller[ctrl] += 1
        for controller, count in per_controller.items():
            assert count >= 2, f"{controller} needs at least two production jobs"
        assert controllers == allowed_controllers
        assert "joc" not in controllers
