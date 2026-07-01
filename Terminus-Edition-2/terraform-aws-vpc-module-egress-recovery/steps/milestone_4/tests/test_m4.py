from vpc_test_support import (
    cfg,
    data_rts,
    default_target,
    evidence,
    make_root,
    run,
    save_cfg,
    state,
)


class TestMilestone4:
    def test_flow_log_is_subnet_scoped_and_preserves_audit_metadata(self):
        """flow logs cover every subnet with scoped IAM policy and preserved metadata."""
        td, root = make_root()
        try:
            run(root, "apply", owner="audit", check=True)
            recovered = state(root)
            flow_log = recovered["flow_log"]
            assert flow_log["id"] == "fl-prod-vpc-existing"
            assert flow_log["metadata"] == evidence(root, "audit_inventory.json")["flow_log"][
                "metadata"
            ]
            assert set(flow_log["subnet_ids"]) == {s["id"] for s in recovered["subnets"]}
            account_id = cfg(root)["account_id"]
            resource = flow_log["iam_policy"]["Resource"]
            assert resource.startswith(f"arn:aws:logs:us-east-1:{account_id}:")
            assert "log-group:" in resource
            assert resource.endswith(":*")
            assert not resource.startswith(f"arn:aws:logs:us-east-1:{account_id}:*")
            actions = flow_log["iam_policy"]["Action"]
            assert "logs:*" not in actions
            assert len(actions) >= 2
            assert all(action.startswith("logs:") for action in actions)
            assert "logs:CreateLogStream" in actions
            assert "logs:PutLogEvents" in actions
        finally:
            td.cleanup()

    def test_resolver_rules_follow_dynamic_corporate_cidrs(self):
        """resolver ingress allows only TCP/UDP 53 from the current corporate CIDRs."""
        td, root = make_root()
        try:
            config = cfg(root)
            config["resolver"]["allowed_cidrs"] = ["192.0.2.10/32", "192.0.2.11/32"]
            save_cfg(root, config)
            run(root, "apply", owner="audit", check=True)
            rules = state(root)["resolver_security_group"]["ingress"]
            assert sorted(rule["protocol"] for rule in rules) == ["tcp", "udp"]
            assert all(
                rule["from_port"] == 53
                and rule["to_port"] == 53
                and rule["cidr_blocks"] == config["resolver"]["allowed_cidrs"]
                for rule in rules
            )
        finally:
            td.cleanup()

    def test_manual_resolver_rule_is_reported_not_deleted_silently(self):
        """manual resolver rules are surfaced in the drift report as report_only."""
        td, root = make_root()
        try:
            run(root, "apply", owner="audit", check=True)
            drift = state(root)["drift_report"]
            assert any(
                entry.get("action") == "report_only"
                and entry.get("resource") == "resolver_security_group"
                for entry in drift
            )
            manual_entries = [
                entry
                for entry in drift
                if entry.get("action") == "report_only"
                and entry.get("resource") == "resolver_security_group"
            ]
            assert manual_entries
            entry = manual_entries[0]
            assert entry.get("observed", {}).get("owner") == "manual"
            assert entry.get("observed", {}).get("protocol") == "tcp"
            assert entry.get("observed", {}).get("from_port") == 853
            assert entry.get("observed", {}).get("to_port") == 853
            assert entry.get("observed", {}).get("cidr_blocks") == ["10.0.0.0/8"]
        finally:
            td.cleanup()

    def test_flow_log_destination_account_mismatch_fails_closed(self):
        """audit repair fails before mutation when the log destination account mismatches."""
        td, root = make_root()
        try:
            config = cfg(root)
            config["flow_log"]["log_group_arn"] = (
                "arn:aws:logs:us-east-1:999999999999:log-group:/aws/vpc/prod-flow"
            )
            save_cfg(root, config)
            result, out = run(root, "apply", owner="audit")
            assert result.returncode != 0 and "account mismatch" in out["error"]
            assert not (root / "state/vpc_recovered_state.json").exists()
        finally:
            td.cleanup()

    def test_cumulative_routing_endpoint_and_import_behavior_remains(self):
        """M4 keeps the routing, endpoint, and import guarantees from earlier milestones."""
        td, root = make_root()
        try:
            run(root, "apply", owner="audit", check=True)
            recovered = state(root)
            assert len(recovered["gateway_endpoints"]) == 2
            assert {ep["service"] for ep in recovered["gateway_endpoints"]} == {
                "s3",
                "dynamodb",
            }
            observed = {
                ep["service"]: ep
                for ep in evidence(root, "observed_endpoints.json")["endpoints"]
            }
            for ep in recovered["gateway_endpoints"]:
                assert ep["id"] == observed[ep["service"]]["id"]
                assert ep["policy"] == observed[ep["service"]]["policy"]
            moved = {entry["from"]: entry["to"] for entry in recovered["moved"]}
            assert moved["module.vpc.aws_subnet.private[0]"]
            assert moved["module.vpc.aws_subnet.private[1]"]
            assert moved["module.vpc.aws_subnet.private[2]"]
            assert recovered["flow_log"]["id"] == "fl-prod-vpc-existing"
            for rt in data_rts(recovered):
                assert default_target(rt) is None
        finally:
            td.cleanup()
