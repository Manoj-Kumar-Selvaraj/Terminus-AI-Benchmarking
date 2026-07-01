from vpc_test_support import (
    app_rts,
    cfg,
    data_rts,
    default_target,
    evidence,
    journal_lines,
    make_root,
    run,
    save_cfg,
    save_evidence,
    state,
)


class TestMilestone1:
    def test_inspect_reports_recovery_controller_contract(self):
        """inspect exposes the recovery-controller workflow instead of only rendering state."""
        td, root = make_root()
        try:
            _, out = run(root, "inspect", check=True)
            assert isinstance(out["feature_level"], int)
            assert "observed_routes.json" in out["evidence_files"]
        finally:
            td.cleanup()

    def test_plan_repairs_routes_without_mutating_state(self):
        """plan corrects route ownership but does not write the recovery state file."""
        td, root = make_root()
        try:
            _, out = run(root, "plan", check=True)
            assert not (root / "state/vpc_recovered_state.json").exists()
            nats = {n["az"]: n["id"] for n in cfg(root)["nat_gateways"]}
            for rt in app_rts(out):
                assert default_target(rt) == nats[rt["az"]]
            for rt in data_rts(out):
                assert default_target(rt) is None
            app_a = next(rt for rt in app_rts(out) if rt["az"] == "us-east-1a")
            assert app_a.get("metadata", {}).get("ticket") == "INC-74291"
            assert app_a.get("metadata", {}).get("observed_by") == "vpc-audit-3"
            assert any(
                route.get("owner") == "manual" and route["target"] == "tgw-core"
                for route in app_a["routes"]
            )
            data_a = next(rt for rt in data_rts(out) if rt["az"] == "us-east-1a")
            assert any(
                route.get("owner") == "manual" and route["target"] == "tgw-analytics"
                for route in data_a["routes"]
            )
        finally:
            td.cleanup()

    def test_dynamic_environment_and_nat_ids_are_derived(self):
        """recovery follows mutated config values and does not hardcode prod NAT IDs."""
        td, root = make_root()
        try:
            config = cfg(root)
            config["environment"] = "qa"
            for nat in config["nat_gateways"]:
                nat["id"] = "nat-qa-" + nat["az"][-1]
            save_cfg(root, config)
            nat_health = evidence(root, "nat_health.json")
            for nat in nat_health["nat_gateways"]:
                nat["id"] = "nat-qa-" + nat["az"][-1]
            save_evidence(root, "nat_health.json", nat_health)
            _, out = run(root, "plan", check=True)
            assert out["environment"] == "qa"
            for rt in app_rts(out):
                assert default_target(rt).startswith("nat-qa-")
        finally:
            td.cleanup()

    def test_apply_writes_state_and_journal(self):
        """apply persists recovered state and durable journal records for replay."""
        td, root = make_root()
        try:
            run(root, "apply", owner="operator-a", check=True)
            recovered = state(root)
            assert recovered["schema_version"] == "vpc-recovery.aws.1"
            nats = {n["az"]: n["id"] for n in cfg(root)["nat_gateways"]}
            for rt in app_rts(recovered):
                assert default_target(rt) == nats[rt["az"]]
            for rt in data_rts(recovered):
                assert default_target(rt) is None
            assert recovered["environment"] == "prod"
            assert isinstance(recovered.get("config_digest"), str) and recovered["config_digest"]
            events = [entry["event"] for entry in journal_lines(root)]
            assert "route_plan_written" in events and "apply_committed" in events
        finally:
            td.cleanup()

    def test_verify_reports_ready_only_after_recovered_state_exists(self):
        """verify reads recovered state and does not act as an unimplemented no-op."""
        td, root = make_root()
        try:
            result, out = run(root, "verify")
            assert result.returncode != 0 or out.get("phase") != "READY"
            assert out.get("valid") is not True

            run(root, "apply", owner="operator-a", check=True)
            _, out = run(root, "verify", check=True)
            assert out["valid"] is True
            assert out["phase"] == "READY"
        finally:
            td.cleanup()

    def test_lost_response_after_route_commit_can_resume(self):
        """a crash after route commit can be resumed by the same owner without losing state."""
        td, root = make_root()
        try:
            result, _ = run(root, "apply", owner="operator-a", fail_after="route_commit")
            assert result.returncode != 0
            assert (root / "state/vpc_recovered_state.json").exists()
            run(root, "resume", owner="operator-a", check=True)
            recovered = state(root)
            assert recovered["schema_version"] == "vpc-recovery.aws.1"
            nats = {n["az"]: n["id"] for n in cfg(root)["nat_gateways"]}
            for rt in app_rts(recovered):
                assert default_target(rt) == nats[rt["az"]]
            for rt in data_rts(recovered):
                assert default_target(rt) is None
            events = [entry["event"] for entry in journal_lines(root)]
            assert "apply_committed" in events
        finally:
            td.cleanup()

    def test_missing_same_az_nat_fails_before_mutation(self):
        """missing or unhealthy same-AZ NAT is rejected before state is written."""
        td, root = make_root()
        try:
            nat_health = evidence(root, "nat_health.json")
            nat_health["nat_gateways"] = [
                n for n in nat_health["nat_gateways"] if n["az"] != "us-east-1c"
            ]
            save_evidence(root, "nat_health.json", nat_health)
            config = cfg(root)
            config["nat_gateways"] = [
                n for n in config["nat_gateways"] if n["az"] != "us-east-1c"
            ]
            save_cfg(root, config)
            result, out = run(root, "apply", owner="operator-a")
            assert result.returncode != 0 and "missing nat gateway" in out["error"]
            assert not (root / "state/vpc_recovered_state.json").exists()
        finally:
            td.cleanup()

    def test_stale_owner_is_fenced(self):
        """an active recovery journal fences another owner from resuming the operation."""
        td, root = make_root()
        try:
            run(root, "apply", owner="operator-a", fail_after="route_commit")
            result, out = run(root, "resume", owner="operator-b")
            assert result.returncode != 0 and "stale owner" in out["error"]
        finally:
            td.cleanup()

    def test_changed_config_digest_fences_resume(self):
        """an interrupted operation cannot resume after desired config changes."""
        td, root = make_root()
        try:
            run(root, "apply", owner="operator-a", fail_after="route_commit")
            config = cfg(root)
            config["nat_gateways"][0]["id"] = "nat-changed"
            save_cfg(root, config)
            result, out = run(root, "resume", owner="operator-a")
            assert result.returncode != 0
            assert "config" in out["error"].lower() or "digest" in out["error"].lower()
        finally:
            td.cleanup()
