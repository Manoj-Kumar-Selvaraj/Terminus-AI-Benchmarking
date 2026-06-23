import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "tools/ec2sim.py"
CFG = APP / "infra/envs/prod/ec2_config.json"


def cfg():
    return json.loads(CFG.read_text())


def run(cmd, c, prior=None, state=None):
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "c.json"
        out = Path(td) / "o.json"
        cp.write_text(json.dumps(c))
        args = [sys.executable, str(SIM), cmd, "--config", str(cp), "--out", str(out)]
        if prior is not None:
            pp = Path(td) / "prior.json"
            pp.write_text(json.dumps(prior))
            args += ["--prior-state", str(pp)]
        if state is not None:
            args += ["--state", str(state)]
        r = subprocess.run(
            args,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return r, json.loads(out.read_text())


class TestMilestone1:
    def test_launch_template_uses_release_artifact(self):
        """LT AMI, user-data hash, commit, and build must come from immutable release artifact."""
        c = cfg()
        r, s = run("plan", c)
        assert r.returncode == 0
        lt = s["launch_template"]
        assert (
            lt["ami_id"] == c["release_artifact"]["ami_id"]
            and lt["ami_id"] != c["ami_catalog"]["latest"]
        )
        assert lt["user_data_sha256"] == c["release_artifact"]["user_data_sha256"]
        assert lt["provenance"]["commit_sha"] == c["release_artifact"]["commit_sha"]
        assert lt["provenance"]["build_id"] == c["release_artifact"]["build_id"]

    def test_instances_tag_release_provenance(self):
        """Rendered instances must carry build and commit tags."""
        c = cfg()
        r, s = run("apply", c)
        assert r.returncode == 0
        assert all(
            i["tags"]["CommitSha"] == c["release_artifact"]["commit_sha"]
            and i["tags"]["BuildId"] == c["release_artifact"]["build_id"]
            for i in s["instances"]
        )
        assert (
            s["outputs"]["launch_template_version"] == s["launch_template"]["version"]
        )

    @pytest.mark.parametrize(
        "field", ["ami_id", "commit_sha", "build_id", "user_data_sha256"]
    )
    def test_missing_artifact_fails_closed(self, field):
        """Incomplete artifact manifest must fail validation for every required field."""
        c = cfg()
        del c["release_artifact"][field]
        r, o = run("validate", c)
        assert r.returncode != 0
        assert o["valid"] is False
        assert f"release_artifact.{field}" in o["error"]

    def test_prior_state_and_state_flags_accepted(self):
        """plan must accept --prior-state and --state CLI flags."""
        c = cfg()
        with tempfile.TemporaryDirectory() as td:
            cp = Path(td) / "c.json"
            out = Path(td) / "o.json"
            prior = Path(td) / "prior.json"
            state = Path(td) / "state.json"
            cp.write_text(json.dumps(c))
            prior.write_text("{}")
            r = subprocess.run(
                [
                    sys.executable,
                    str(SIM),
                    "plan",
                    "--config",
                    str(cp),
                    "--prior-state",
                    str(prior),
                    "--out",
                    str(out),
                    "--state",
                    str(state),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            assert r.returncode == 0
