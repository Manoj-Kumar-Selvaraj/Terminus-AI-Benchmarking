# ruff: noqa
from helpers import *

V1_KEYS = {"lease_id", "username", "password_reference", "expires_at", "renewable"}
V2_KEYS = {"lease_id", "request_id", "username", "password_reference", "issued_at", "expires_at", "max_expires_at", "renewable", "generation", "owner_pod_uid"}


def new_request(ws, claims, *, protocol=2, request_id=None, pod_uid=None):
    return ws.request(claims, protocol=protocol, request_id=request_id, pod_uid=pod_uid)


def active_generation(ws, pod):
    return ws.app_json("connection-pools.json")["active_by_pod"].get(pod, 0)


class TestMilestone5:
    @pytest.mark.parametrize("version,expected", [(1, V1_KEYS), (2, V2_KEYS)])
    def test_versioned_issuance_schema_is_compatible(self, ws, version, expected):
        """Legacy and extended clients receive their documented response shape."""
        token, claims = ws.token(ws.claims(pod_uid=f"pod-schema-v{version}"))
        request, _ = new_request(ws, claims, protocol=version)
        result = ws.issue(token, request, version)
        assert result.ok and set(result.result) == expected

    def test_version_one_renewal_preserves_legacy_schema(self, ws):
        """A legacy client can renew without receiving mandatory Version 2 fields."""
        token, _, _, _, lease = ws.issue_lease(pod_uid="pod-v1-renew", protocol=1)
        ws.advance("210s")
        result = ws.renew(token, lease["lease_id"], protocol=1)
        assert result.ok and result.result["action"] == "RENEWED"
        assert V1_KEYS.issubset(result.result) and "owner_pod_uid" not in result.result

    def test_version_two_renewal_returns_generation_and_owner(self, ws):
        """An extended client retains owner and generation metadata across renewal."""
        token, claims, _, _, lease = ws.issue_lease(pod_uid="pod-v2-renew", protocol=2)
        ws.advance("210s")
        result = ws.renew(token, lease["lease_id"], protocol=2)
        assert result.ok and result.result["generation"] == 1
        assert result.result["owner_pod_uid"] == claims["pod_uid"]

    def test_mixed_version_pods_operate_simultaneously(self, ws):
        """Version 1 and Version 2 pools coexist without sharing credential ownership."""
        _, c1, _, _, l1 = ws.issue_lease(pod_uid="pod-mixed-v1", protocol=1)
        _, c2, _, _, l2 = ws.issue_lease(pod_uid="pod-mixed-v2", protocol=2)
        assert l1["lease_id"] != l2["lease_id"]
        assert ws.dbop(c1["pod_uid"]).ok and ws.dbop(c2["pod_uid"]).ok
        assert active_generation(ws, c1["pod_uid"]) == active_generation(ws, c2["pod_uid"]) == 1

    def test_each_pod_has_unique_lease_ownership(self, ws):
        """Shared Kubernetes role membership does not collapse pods onto one database user."""
        leases = [ws.issue_lease(pod_uid=f"pod-owner-{n}")[4] for n in range(3)]
        assert len({l["lease_id"] for l in leases}) == 3
        assert len({l["owner_pod_uid"] for l in leases}) == 3
        assert len({l["username"] for l in leases}) == 3

    def test_one_pod_cannot_revoke_another_pods_lease(self, ws):
        """Revocation authorization is bound to the authenticated workload instance."""
        token_a, _, _, _, _ = ws.issue_lease(pod_uid="pod-revoke-owner-a")
        _, claims_b, _, _, lease_b = ws.issue_lease(pod_uid="pod-revoke-owner-b")
        denied = ws.revoke(token_a, lease_b["lease_id"])
        assert not denied.ok and denied.code == "LEASE_OWNERSHIP_DENIED"
        assert ws.dbop(claims_b["pod_uid"]).ok

    def test_one_pod_cannot_renew_another_pods_lease(self, ws):
        """Renewal ownership prevents a sibling pod from extending another credential."""
        token_a, _, _, _, _ = ws.issue_lease(pod_uid="pod-renew-owner-a")
        _, _, _, _, lease_b = ws.issue_lease(pod_uid="pod-renew-owner-b")
        ws.advance("210s")
        denied = ws.renew(token_a, lease_b["lease_id"])
        assert not denied.ok and denied.code == "LEASE_OWNERSHIP_DENIED"

    def test_request_owner_must_match_authenticated_pod(self, ws):
        """A valid token cannot submit issuance work on behalf of a different pod UID."""
        token, claims = ws.token(ws.claims(pod_uid="pod-token-owner"))
        request, _ = new_request(ws, claims, pod_uid="pod-forged-owner")
        denied = ws.issue(token, request, 2)
        assert not denied.ok and denied.code == "WORKLOAD_OWNERSHIP_DENIED"
        assert runtime_user_count(ws) == runtime_lease_count(ws) == 0

    def test_stale_superseded_lease_cannot_be_renewed(self, ws):
        """After rotation, the former generation cannot be extended by a stale client."""
        token, claims, _, _, old = ws.issue_lease(pod_uid="pod-stale-renew")
        request, _ = new_request(ws, claims, protocol=2); assert ws.rotate(token, request, 2).ok
        denied = ws.renew(token, old["lease_id"], 2)
        assert not denied.ok and denied.code in {"LEASE_REVOKED", "SUPERSEDED_LEASE"}

    @pytest.mark.parametrize("point", ["POOL_CREATE", "BEFORE_POOL_SWAP", "AFTER_POOL_SWAP"])
    def test_restart_during_rotation_selects_one_safe_generation(self, ws, point):
        """Recovery after each rotation crash point exposes at most one active pool generation."""
        token, claims, _, _, _ = ws.issue_lease(pod_uid=f"pod-restart-{point.lower()}")
        request, value = new_request(ws, claims, protocol=2)
        ws.fail(point, request_id=value["request_id"])
        result = ws.rotate(token, request, 2); assert not result.ok
        ws.runtime_cmd("restart-client")
        recovered = ws.reconcile(); assert recovered.ok
        pools = ws.app_json("connection-pools.json")
        active = [p for p in pools["pools"][claims["pod_uid"]] if p["state"] == "ACTIVE"]
        assert len(active) == 1
        assert active[0]["generation"] == pools["active_by_pod"][claims["pod_uid"]]
        assert ws.dbop(claims["pod_uid"]).ok

    def test_password_and_raw_jwt_never_enter_durable_state_or_logs(self, ws):
        """Only opaque password references are persisted; bearer and secret values are absent."""
        token, _, _, _, _ = ws.issue_lease(pod_uid="pod-secret-scan")
        corpus = "\n".join(
            p.read_text(errors="ignore")
            for p in list(ws.state.rglob("*")) + list((ws.root / "logs").rglob("*")) + list(ws.runtime.rglob("*"))
            if p.is_file()
        )
        raw = token.read_text().strip()
        assert raw not in corpus
        assert '"password":' not in corpus and "static_password" not in corpus
        assert "vaultref://" in corpus

    @pytest.mark.parametrize("version", [0, 3, 99])
    def test_unsupported_protocol_versions_are_rejected(self, ws, version):
        """Clients cannot silently negotiate an undefined response contract."""
        token, claims = ws.token(ws.claims(pod_uid=f"pod-version-{version}"))
        request, value = new_request(ws, claims, protocol=version)
        if version == 0: value["protocol_version"] = 3; request.write_text(json.dumps(value)); version = 3
        denied = ws.issue(token, request, version)
        assert not denied.ok and denied.code == "UNSUPPORTED_PROTOCOL"

    def test_malformed_version_two_request_is_rejected(self, ws):
        """Version 2 requires a stable issuance operation identifier."""
        token, claims = ws.token(ws.claims(pod_uid="pod-v2-malformed"))
        request, value = new_request(ws, claims, protocol=2)
        value["request_id"] = ""; request.write_text(json.dumps(value))
        denied = ws.issue(token, request, 2)
        assert not denied.ok and denied.code == "INVALID_REQUEST"

    def test_missing_owner_pod_uid_is_rejected(self, ws):
        """Issuance cannot create an unowned credential record."""
        token, claims = ws.token(ws.claims(pod_uid="pod-missing-owner"))
        request, value = new_request(ws, claims, protocol=2)
        value["pod_uid"] = ""; request.write_text(json.dumps(value))
        denied = ws.issue(token, request, 2)
        assert not denied.ok and denied.code == "MISSING_OWNER"

    def test_rollout_from_version_one_to_version_two_rotates_without_gap(self, ws):
        """A legacy pool can be replaced by an extended-client generation while traffic continues."""
        token, claims, _, _, _ = ws.issue_lease(pod_uid="pod-rollout", protocol=1)
        assert ws.dbop(claims["pod_uid"]).ok
        request, _ = new_request(ws, claims, protocol=2)
        result = ws.rotate(token, request, 2)
        assert result.ok and result.result["active_generation"] == 2
        assert ws.dbop(claims["pod_uid"]).ok

    def test_rollback_from_version_two_to_version_one_is_supported(self, ws):
        """A Version 2 pod can return to the legacy response contract without losing availability."""
        token, claims, _, _, _ = ws.issue_lease(pod_uid="pod-rollback", protocol=2)
        request, _ = new_request(ws, claims, protocol=1)
        result = ws.rotate(token, request, 1); assert result.ok
        pool = next(p for p in ws.app_json("connection-pools.json")["pools"][claims["pod_uid"]] if p["state"] == "ACTIVE")
        assert pool["protocol_version"] == 1 and ws.dbop(claims["pod_uid"]).ok

    def test_failed_replacement_has_no_availability_gap(self, ws):
        """A healthy old pool remains available when candidate validation fails."""
        token, claims, _, _, old = ws.issue_lease(pod_uid="pod-no-gap")
        request, _ = new_request(ws, claims, protocol=2)
        ws.fail("VALIDATE_CREDENTIAL")
        denied = ws.rotate(token, request, 2)
        assert not denied.ok and ws.dbop(claims["pod_uid"]).ok
        pool = next(p for p in ws.app_json("connection-pools.json")["pools"][claims["pod_uid"]] if p["state"] == "ACTIVE")
        assert pool["lease_id"] == old["lease_id"]

    def test_expired_only_credential_fails_securely(self, ws):
        """When every credential is expired, the API fails closed rather than using static access."""
        _, claims, _, _, _ = ws.issue_lease(pod_uid="pod-expired-only")
        ws.advance("5m")
        denied = ws.dbop(claims["pod_uid"])
        assert not denied.ok and denied.code == "CREDENTIAL_EXPIRED"

    def test_completed_reconciliation_is_idempotent(self, ws):
        """A second completed recovery pass reports no new durable changes."""
        ws.issue_lease(pod_uid="pod-idempotent-recovery")
        first = ws.reconcile(); second = ws.reconcile()
        assert first.ok and second.ok and second.result["changes"] == 0

    def test_unrelated_pods_rotate_concurrently(self, ws):
        """Per-request and per-pod ownership does not globally serialize independent rotations."""
        inputs = []
        for n in range(2):
            token, claims, _, _, _ = ws.issue_lease(pod_uid=f"pod-concurrent-rotate-{n}")
            request, _ = new_request(ws, claims, protocol=2)
            inputs.append((token, request, claims["pod_uid"]))
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda x: ws.rotate(x[0], x[1], 2), inputs))
        assert all(r.ok for r in results)
        assert all(active_generation(ws, pod) == 2 for _, _, pod in inputs)

    def test_same_pod_duplicate_request_remains_idempotent(self, ws):
        """Duplicate delivery for one pod returns the same lease and pool generation."""
        token, claims = ws.token(ws.claims(pod_uid="pod-same-request"))
        request, _ = new_request(ws, claims, request_id="req-same-pod")
        a = ws.issue(token, request, 2); b = ws.issue(token, request, 2)
        assert a.ok and b.ok and a.result["lease_id"] == b.result["lease_id"]
        assert active_generation(ws, claims["pod_uid"]) == 1

    def test_legacy_and_new_records_restore_together(self, ws):
        """Restart recovery retains active pools created through both protocol versions."""
        _, c1, _, _, _ = ws.issue_lease(pod_uid="pod-restore-v1", protocol=1)
        _, c2, _, _, _ = ws.issue_lease(pod_uid="pod-restore-v2", protocol=2)
        ws.runtime_cmd("restart-client"); assert ws.reconcile().ok
        assert ws.dbop(c1["pod_uid"]).ok and ws.dbop(c2["pod_uid"]).ok


class TestEndToEndScenarios:
    def test_scenario_a_normal_pod_lifecycle_leaks_no_active_users(self, ws):
        """Authenticate, use, renew, rotate, revoke and shutdown as one production lifecycle."""
        token, claims, _, _, lease = ws.issue_lease(pod_uid="pod-e2e-normal")
        assert ws.dbop(claims["pod_uid"], operation="INSERT_LEDGER_EVENT").ok
        ws.advance("210s"); assert ws.renew(token, lease["lease_id"], 2).result["action"] == "RENEWED"
        request, _ = new_request(ws, claims, protocol=2); assert ws.rotate(token, request, 2).ok
        assert ws.shutdown(token).ok
        users = [u for u in ws.inspect("database-users")["database_users"] if u["pod_uid"] == claims["pod_uid"]]
        assert users and all(not u["active"] for u in users)

    def test_scenario_b_unauthorized_namespace_creates_nothing(self, ws):
        """A similarly named workload in another namespace is denied before issuance."""
        claims = ws.claims(namespace="fraud", subject="system:serviceaccount:fraud:payment-ledger-api")
        token, claims = ws.token(claims); request, _ = new_request(ws, claims)
        denied = ws.issue(token, request, 2)
        assert not denied.ok and denied.code == "WRONG_NAMESPACE"
        assert runtime_user_count(ws) == runtime_lease_count(ws) == 0

    def test_scenario_c_renewal_outage_is_bounded_by_validity(self, ws):
        """Transient renewal outage retries deterministically and serves only before expiry."""
        token, claims, _, _, lease = ws.issue_lease(pod_uid="pod-e2e-renew-outage")
        ws.advance("210s"); ws.fail("RENEW_TRANSIENT", count=4, lease_id=lease["lease_id"])
        result = ws.renew(token, lease["lease_id"], 2)
        assert result.ok and result.result["action"] == "RETRY_PENDING" and result.result["usable"] is True
        assert ws.dbop(claims["pod_uid"]).ok
        ws.advance("90s")
        assert not ws.dbop(claims["pod_uid"]).ok

    def test_scenario_d_restart_after_pool_swap_eventually_cleans_old_user(self, ws):
        """Crash after swap recovers the new pool and completes old-lease cleanup."""
        token, claims, _, _, old = ws.issue_lease(pod_uid="pod-e2e-rotation")
        request, value = new_request(ws, claims); ws.fail("AFTER_POOL_SWAP", request_id=value["request_id"])
        assert not ws.rotate(token, request, 2).ok
        ws.runtime_cmd("restart-client"); assert ws.reconcile().ok
        assert active_generation(ws, claims["pod_uid"]) == 2 and ws.dbop(claims["pod_uid"]).ok
        assert ws.app_json("active-leases.json")["leases"][old["lease_id"]]["status"] == "REVOKED"

    def test_scenario_e_lost_issuance_response_replays_same_lease(self, ws):
        """A lost response after commit is recovered by stable request identity."""
        token, claims = ws.token(ws.claims(pod_uid="pod-e2e-lost")); request, value = new_request(ws, claims)
        ws.fail("LOST_CLIENT_RESPONSE", request_id=value["request_id"])
        first = ws.issue(token, request, 2); second = ws.issue(token, request, 2)
        assert first.ok and second.ok and first.result["lease_id"] == second.result["lease_id"]
        assert len([u for u in ws.inspect("database-users")["database_users"] if u["request_id"] == value["request_id"]]) == 1

    def test_scenario_f_failover_after_user_create_has_no_duplicate(self, ws):
        """Active-node failover after user creation adopts one orphan and one lease."""
        token, claims = ws.token(ws.claims(pod_uid="pod-e2e-failover")); request, value = new_request(ws, claims)
        ws.fail("FAILOVER_AFTER_DB_USER_CREATE", request_id=value["request_id"])
        assert ws.issue(token, request, 2).ok
        users = [u for u in ws.inspect("database-users")["database_users"] if u["request_id"] == value["request_id"]]
        leases = [l for l in ws.inspect("leases")["leases"] if l["request_id"] == value["request_id"]]
        assert len(users) == len(leases) == 1

    def test_scenario_g_revocation_failure_does_not_block_other_cleanup(self, ws):
        """A failed user disable is retried while another lease cleanup completes."""
        ta, _, _, _, a = ws.issue_lease(pod_uid="pod-e2e-revoke-a")
        tb, _, _, _, b = ws.issue_lease(pod_uid="pod-e2e-revoke-b")
        ws.fail("DURING_REVOCATION", count=2, lease_id=a["lease_id"]); assert ws.revoke(ta, a["lease_id"]).ok
        ws.fail("DURING_REVOCATION", lease_id=b["lease_id"]); assert ws.revoke(tb, b["lease_id"]).ok
        assert ws.cleanup().ok
        states = ws.app_json("active-leases.json")["leases"]
        assert states[a["lease_id"]]["status"] == "REVOKE_PENDING" and states[b["lease_id"]]["status"] == "REVOKED"

    def test_scenario_h_mixed_clients_preserve_ownership_isolation(self, ws):
        """Legacy and new clients coexist while cross-pod revocation remains denied."""
        t1, c1, _, _, _ = ws.issue_lease(pod_uid="pod-e2e-v1", protocol=1)
        _, c2, _, _, l2 = ws.issue_lease(pod_uid="pod-e2e-v2", protocol=2)
        assert ws.dbop(c1["pod_uid"]).ok and ws.dbop(c2["pod_uid"]).ok
        denied = ws.revoke(t1, l2["lease_id"])
        assert not denied.ok and denied.code == "LEASE_OWNERSHIP_DENIED"

    def test_scenario_i_conflicting_duplicate_is_deterministically_rejected(self, ws):
        """A request ID replay under another pod identity cannot hijack the committed credential."""
        rid = "req-e2e-conflict"
        ta, ca = ws.token(ws.claims(pod_uid="pod-e2e-conflict-a")); ra, _ = new_request(ws, ca, request_id=rid)
        tb, cb = ws.token(ws.claims(pod_uid="pod-e2e-conflict-b")); rb, _ = new_request(ws, cb, request_id=rid)
        first = ws.issue(ta, ra, 2); denied = ws.issue(tb, rb, 2)
        assert first.ok and not denied.ok and denied.code == "REQUEST_ID_CONFLICT"

    def test_scenario_j_repeated_completed_recovery_is_stable(self, ws):
        """A completed recovery rerun adds no users, leases, journals or pool generations."""
        ws.issue_lease(pod_uid="pod-e2e-stable-a", protocol=1)
        ws.issue_lease(pod_uid="pod-e2e-stable-b", protocol=2)
        assert ws.reconcile().ok
        before = {
            "users": ws.inspect("database-users"), "leases": ws.inspect("leases"),
            "pools": ws.app_json("connection-pools.json"), "journal": ws.app_text("lease-journal.jsonl"),
        }
        second = ws.reconcile(); assert second.ok and second.result["changes"] == 0
        after = {
            "users": ws.inspect("database-users"), "leases": ws.inspect("leases"),
            "pools": ws.app_json("connection-pools.json"), "journal": ws.app_text("lease-journal.jsonl"),
        }
        assert before == after
