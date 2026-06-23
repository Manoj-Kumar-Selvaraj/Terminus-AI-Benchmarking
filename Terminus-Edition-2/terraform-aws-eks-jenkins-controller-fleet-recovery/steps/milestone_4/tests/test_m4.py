import json
import os
import subprocess
import sys
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF = APP / "terraform"


def read(name):
    return (TF / name).read_text(encoding="utf-8")


def all_tf():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tf")))


class TestMilestone4:
    def test_simulator_runs_all_jobs_on_own_controller(self):
        """Offline simulator proves every job succeeded on its matching controller."""
        result = subprocess.run(
            [sys.executable, str(APP / "scripts/jenkins_fleet_simulator.py")],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        payload = json.loads(result.stdout)
        assert payload["ok"]
        assert len(payload["jobs"]) >= 6
        assert any(job.startswith("payments-") for job in payload["jobs"])
        assert any(job.startswith("risk-") for job in payload["jobs"])
        assert any(job.startswith("platform-") for job in payload["jobs"])

    def test_trace_no_cross_controller_runs(self):
        """Run trace must not hide failed or cross-controller executions."""
        jobs = json.loads(read("jenkins_jobs.json"))["jobs"]
        runs = json.loads(read("job_run_trace.json"))["runs"]
        assert len(jobs) >= 6
        counts = {controller: 0 for controller in {
            "payments-controller", "risk-controller", "platform-controller"
        }}
        for spec in jobs.values():
            counts[spec["controller"]] += 1
        assert all(count >= 2 for count in counts.values())
        assert len(runs) == len(jobs)
        seen = set()
        for run in runs:
            assert run.get("status") == "SUCCESS"
            assert isinstance(run.get("build_number"), int) and run["build_number"] > 0
            assert run["job"] in jobs
            assert run["controller"] == jobs[run["job"]]["controller"]
            assert run["job"] not in seen, "duplicate successful run evidence"
            seen.add(run["job"])
        assert seen == set(jobs)
