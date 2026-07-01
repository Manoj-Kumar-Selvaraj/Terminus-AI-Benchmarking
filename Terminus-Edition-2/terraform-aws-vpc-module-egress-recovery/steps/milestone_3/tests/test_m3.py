from vpc_test_support import (
    cfg,
    evidence,
    make_root,
    run,
    save_cfg,
    save_evidence,
    state,
)


class TestMilestone3:
    def test_cidr_overlap_and_outside_vpc_are_rejected(self):
        """CIDR validation rejects both overlapping and outside-VPC subnets."""
        td, root = make_root()
        try:
            config = cfg(root)
            config["subnets"][4]["cidr"] = config["subnets"][3]["cidr"]
            save_cfg(root, config)
            result, out = run(root, "apply", owner="netops")
            assert result.returncode != 0 and "overlaps" in out["error"]
        finally:
            td.cleanup()
        td, root = make_root()
        try:
            config = cfg(root)
            config["subnets"][0]["cidr"] = "10.99.0.0/24"
            save_cfg(root, config)
            result, out = run(root, "apply", owner="netops")
            assert result.returncode != 0 and "outside vpc_cidr" in out["error"]
        finally:
            td.cleanup()

    def test_partial_cidr_overlap_is_rejected(self):
        """CIDR validation rejects containing or contained subnet overlaps."""
        td, root = make_root()
        try:
            config = cfg(root)
            config["subnets"][4]["cidr"] = "10.42.10.0/23"
            save_cfg(root, config)
            result, out = run(root, "apply", owner="netops")
            assert result.returncode != 0 and "overlaps" in out["error"]
        finally:
            td.cleanup()

    def test_imported_state_preserves_subnet_and_route_table_identity(self):
        """imported legacy subnets are matched by CIDR and emitted as moved actions."""
        td, root = make_root()
        try:
            run(root, "apply", owner="netops", check=True)
            recovered = state(root)
            by_cidr = {s["cidr"]: s for s in recovered["subnets"] if s["tier"] == "app"}
            assert by_cidr["10.42.10.0/24"]["id"] == "subnet-import-app-a"
            assert by_cidr["10.42.11.0/24"]["route_table_id"] == "rtb-import-app-b"
            moved = {entry["from"]: entry["to"] for entry in recovered["moved"]}
            assert (
                moved["module.vpc.aws_subnet.private[0]"]
                == by_cidr["10.42.10.0/24"]["address"]
            )
            assert (
                moved["module.vpc.aws_subnet.private[1]"]
                == by_cidr["10.42.11.0/24"]["address"]
            )
            assert (
                moved["module.vpc.aws_subnet.private[2]"]
                == by_cidr["10.42.12.0/24"]["address"]
            )
        finally:
            td.cleanup()

    def test_az_expansion_creates_only_new_identities(self):
        """adding an AZ creates only new CIDRs and does not replace imported subnets."""
        td, root = make_root()
        try:
            config = cfg(root)
            config["availability_zones"].append("us-east-1d")
            config["nat_gateways"].append({"id": "nat-prod-d", "az": "us-east-1d"})
            nat_health = evidence(root, "nat_health.json")
            nat_health["nat_gateways"].append(
                {"id": "nat-prod-d", "az": "us-east-1d", "state": "available"}
            )
            save_evidence(root, "nat_health.json", nat_health)
            config["subnets"] += [
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
            save_cfg(root, config)
            run(root, "apply", owner="netops", check=True)
            recovered = state(root)
            assert any(
                s["cidr"] == "10.42.13.0/24" and s["id"].startswith("subnet-prod-app-d")
                for s in recovered["subnets"]
            )
            by_cidr = {s["cidr"]: s for s in recovered["subnets"]}
            assert by_cidr["10.42.10.0/24"]["id"] == "subnet-import-app-a"
            assert by_cidr["10.42.11.0/24"]["id"] == "subnet-import-app-b"
            assert by_cidr["10.42.12.0/24"]["id"] == "subnet-import-app-c"
            assert not any(action.get("action") == "replace" for action in recovered["plan_actions"])
        finally:
            td.cleanup()

    def test_ambiguous_imported_cidr_fails_closed(self):
        """duplicate imported CIDR matches are rejected instead of picking one arbitrarily."""
        td, root = make_root()
        try:
            imported = evidence(root, "imported_tf_state.json")
            imported["resources"].append(
                dict(
                    imported["resources"][0],
                    address="module.vpc.aws_subnet.private[99]",
                    id="subnet-dup",
                )
            )
            save_evidence(root, "imported_tf_state.json", imported)
            result, out = run(root, "apply", owner="netops")
            assert result.returncode != 0 and "ambiguous imported cidr" in out["error"]
        finally:
            td.cleanup()

    def test_endpoint_recovery_uses_imported_app_route_table_ids(self):
        """endpoint associations follow imported route-table identities, not generated names."""
        td, root = make_root()
        try:
            run(root, "apply", owner="netops", check=True)
            recovered = state(root)
            app = set(recovered["outputs"]["private_app_route_table_ids"])
            assert "rtb-import-app-a" in app
            for ep in recovered["gateway_endpoints"]:
                assert set(ep["route_table_ids"]) == app
        finally:
            td.cleanup()
