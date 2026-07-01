from vpc_test_support import (
    app_rts,
    cfg,
    data_rts,
    default_target,
    evidence,
    make_root,
    run,
    save_cfg,
    save_evidence,
    state,
)


class TestMilestone2:
    def test_endpoint_associations_are_reconciled_to_app_route_tables(self):
        """gateway endpoints keep existing IDs but attach only to app route tables."""
        td, root = make_root()
        try:
            run(root, "apply", owner="netops", check=True)
            recovered = state(root)
            app = set(recovered["outputs"]["private_app_route_table_ids"])
            expected_app = {rt["id"] for rt in recovered["route_tables"] if rt["tier"] == "app"}
            assert app == expected_app
            observed = {
                ep["service"]: ep
                for ep in evidence(root, "observed_endpoints.json")["endpoints"]
            }
            for ep in recovered["gateway_endpoints"]:
                assert set(ep["route_table_ids"]) == app
                assert ep["id"] == observed[ep["service"]]["id"]
                assert ep["policy"] == observed[ep["service"]]["policy"]
                assert ep["metadata"] == observed[ep["service"]]["metadata"]
                assert ep["tags"] == observed[ep["service"]]["tags"]
        finally:
            td.cleanup()

    def test_endpoint_service_order_does_not_change_identity(self):
        """endpoint reconciliation follows service names even when config order changes."""
        td, root = make_root()
        try:
            config = cfg(root)
            config["gateway_endpoints"] = list(reversed(config["gateway_endpoints"]))
            save_cfg(root, config)
            run(root, "apply", owner="netops", check=True)
            ids = {ep["service"]: ep["id"] for ep in state(root)["gateway_endpoints"]}
            assert ids["s3"] == "vpce-prod-s3-existing"
            assert ids["dynamodb"] == "vpce-prod-dynamodb-existing"
        finally:
            td.cleanup()

    def test_unsupported_gateway_service_fails_closed(self):
        """unsupported endpoint services fail before writing state."""
        td, root = make_root()
        try:
            config = cfg(root)
            config["gateway_endpoints"].append({"service": "sqs"})
            save_cfg(root, config)
            result, out = run(root, "apply", owner="netops")
            assert result.returncode != 0 and "unsupported" in out["error"]
            assert not (root / "state/vpc_recovered_state.json").exists()
        finally:
            td.cleanup()

    def test_endpoint_policy_account_mismatch_fails_closed(self):
        """existing endpoint policy account mismatches are not silently preserved."""
        td, root = make_root()
        try:
            endpoints = evidence(root, "observed_endpoints.json")
            endpoints["endpoints"][0]["policy"]["Statement"][0]["Condition"][
                "StringEquals"
            ]["aws:PrincipalAccount"] = "999999999999"
            save_evidence(root, "observed_endpoints.json", endpoints)
            result, out = run(root, "apply", owner="netops")
            assert result.returncode != 0 and "account mismatch" in out["error"]
        finally:
            td.cleanup()

    def test_unsupported_gateway_service_fails_closed_on_resume(self):
        """resume must reject unsupported endpoint services before writing state."""
        td, root = make_root()
        try:
            run(root, "apply", owner="netops", check=True)
            config = cfg(root)
            config["gateway_endpoints"].append({"service": "sqs"})
            save_cfg(root, config)
            (root / "state/vpc_recovered_state.json").unlink()
            result, out = run(root, "resume", owner="netops")
            assert result.returncode != 0
            assert "unsupported" in out["error"] or "config digest changed" in out["error"]
            assert not (root / "state/vpc_recovered_state.json").exists()
        finally:
            td.cleanup()

    def test_endpoint_policy_account_mismatch_fails_closed_on_resume(self):
        """resume must reject endpoint policy account mismatches before writing state."""
        td, root = make_root()
        try:
            run(root, "apply", owner="netops", check=True)
            endpoints = evidence(root, "observed_endpoints.json")
            endpoints["endpoints"][0]["policy"]["Statement"][0]["Condition"][
                "StringEquals"
            ]["aws:PrincipalAccount"] = "999999999999"
            save_evidence(root, "observed_endpoints.json", endpoints)
            (root / "state/vpc_recovered_state.json").unlink()
            result, out = run(root, "resume", owner="netops")
            assert result.returncode != 0
            assert "account mismatch" in out["error"] or "config digest changed" in out["error"]
            assert not (root / "state/vpc_recovered_state.json").exists()
        finally:
            td.cleanup()

    def test_replay_does_not_duplicate_endpoint_associations(self):
        """rerunning apply keeps endpoint associations unique and unchanged."""
        td, root = make_root()
        try:
            run(root, "apply", owner="netops", check=True)
            first = state(root)["gateway_endpoints"]
            run(root, "apply", owner="netops", check=True)
            second = state(root)["gateway_endpoints"]
            assert first == second
            for ep in second:
                assert len(ep["route_table_ids"]) == len(set(ep["route_table_ids"]))
        finally:
            td.cleanup()

    def test_routing_recovery_is_preserved(self):
        """M2 keeps the same-AZ app routing and isolated data-subnet behavior from M1."""
        td, root = make_root()
        try:
            run(root, "apply", owner="netops", check=True)
            recovered = state(root)
            nats = {n["az"]: n["id"] for n in cfg(root)["nat_gateways"]}
            for rt in app_rts(recovered):
                assert default_target(rt) == nats[rt["az"]]
            for rt in data_rts(recovered):
                assert default_target(rt) is None
        finally:
            td.cleanup()
