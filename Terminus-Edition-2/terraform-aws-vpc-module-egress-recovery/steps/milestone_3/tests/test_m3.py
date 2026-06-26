import json
import os
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))
SIM = APP / "bin" / "vpcsim"
CFG = APP / "infra/envs/prod/vpc_config.json"


def cfg():
    return json.loads(CFG.read_text())


def run(c, prior=None):
    with tempfile.TemporaryDirectory() as td:
        cp = Path(td) / "c.json"
        out = Path(td) / "o.json"
        cp.write_text(json.dumps(c))
        cmd = [str(SIM), "plan", "--config", str(cp), "--out", str(out)]
        if prior:
            pp = Path(td) / "p.json"
            pp.write_text(json.dumps(prior))
            cmd += ["--prior-state", str(pp)]
        r = subprocess.run(
            cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return r, json.loads(out.read_text())


class TestMilestone3:
    def test_overlapping_subnets_are_rejected(self):
        """CIDR overlap must fail closed."""
        c = cfg()
        c["subnets"][4]["cidr"] = c["subnets"][3]["cidr"]
        r, o = run(c)
        assert r.returncode != 0 and "overlaps" in o["error"]

    def test_partial_cidr_overlap_is_rejected(self):
        """Partial subnet overlap must fail closed, not only identical CIDR strings."""
        c = cfg()
        c["subnets"][0]["cidr"] = "10.42.0.0/23"
        r, o = run(c)
        assert r.returncode != 0 and "overlaps" in o["error"]

    def test_subnet_outside_vpc_is_rejected(self):
        """Subnets outside VPC CIDR must fail closed."""
        c = cfg()
        c["subnets"][0]["cidr"] = "10.99.0.0/24"
        r, o = run(c)
        assert r.returncode != 0 and "outside vpc_cidr" in o["error"]

    def test_az_append_preserves_existing_subnet_ids(self):
        """Appending a fourth AZ must not reindex existing subnet identities."""
        r, base = run(cfg())
        assert r.returncode == 0
        c = cfg()
        c["availability_zones"].append("us-east-1d")
        c["nat_gateways"].append({"id": "nat-prod-d", "az": "us-east-1d"})
        c["subnets"] += [
            {
                "name": "prod-public-d",
                "tier": "public",
                "az": "us-east-1d",
                "cidr": "10.42.3.0/24",
            },
            {
                "name": "prod-app-d",
                "tier": "app",
                "az": "us-east-1d",
                "cidr": "10.42.13.0/24",
            },
            {
                "name": "prod-data-d",
                "tier": "data",
                "az": "us-east-1d",
                "cidr": "10.42.23.0/24",
            },
        ]
        r2, new = run(c, base)
        assert r2.returncode == 0
        old = {s["cidr"]: s["id"] for s in base["subnets"]}
        assert all(
            s["id"] == old[s["cidr"]] for s in new["subnets"] if s["cidr"] in old
        )
        assert not any(
            a.get("action") == "replace" for a in new.get("plan_actions", [])
        ), "AZ append must not trigger destructive replacements"
