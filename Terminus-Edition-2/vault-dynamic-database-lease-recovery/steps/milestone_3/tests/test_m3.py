# ruff: noqa
from helpers import *


def rotation_request(ws, claims, *, request_id=None, protocol=2):
    return ws.request(claims, request_id=request_id, protocol=protocol, generation=2)


def active_pool(ws, pod_uid):
    pools = ws.app_json("connection-pools.json")
    generation = pools["active_by_pod"].get(pod_uid, 0)
    matches = [p for p in pools["pools"].get(pod_uid, []) if p["generation"] == generation]
    assert len(matches) == 1
    return matches[0], pools


class TestMilestone3:
    def test_successful_rotation_swaps_then_revokes_old_lease(self, ws):
        """A healthy replacement becomes active and the former lease is revoked afterwards."""
        token, claims, _, _, old = ws.issue_lease(pod_uid="pod-rotate-ok")
        request, _ = rotation_request(ws, claims)
        result = ws.rotate(token, request)
        assert result.ok and result.result["active_generation"] == 2
        leases = {x["lease_id"]: x for x in ws.inspect("leases")["leases"]}
        assert leases[old["lease_id"]]["status"] == "REVOKED"
        assert leases[result.result["new_lease_id"]]["status"] == "ACTIVE"

    def test_new_credential_is_validated_before_pool_swap(self, ws):
        """The runtime audit proves replacement validation precedes old-user revocation."""
        token, claims, _, _, _ = ws.issue_lease(pod_uid="pod-order")
        request, _ = rotation_request(ws, claims)
        result = ws.rotate(token, request); assert result.ok
        audit = ws.inspect("audit")["audit"]
        validated = next(i for i,e in enumerate(audit) if e["event"] == "credential_validated" and e.get("lease_id") == result.result["new_lease_id"])
        revoked = next(i for i,e in enumerate(audit) if e["event"] == "lease_revoked" and e.get("lease_id") == result.result["old_lease_id"])
        assert validated < revoked

    def test_invalid_new_credential_leaves_old_pool_active(self, ws):
        """Replacement validation failure rolls back the candidate without an outage."""
        token, claims, _, _, old = ws.issue_lease(pod_uid="pod-invalid-new")
        request, request_value = rotation_request(ws, claims)
        ws.fail("VALIDATE_CREDENTIAL")
        result = ws.rotate(token, request)
        assert not result.ok and result.code == "POOL_VALIDATION_FAILED"
        pool, _ = active_pool(ws, claims["pod_uid"])
        assert pool["generation"] == 1 and pool["lease_id"] == old["lease_id"]
        assert ws.dbop(claims["pod_uid"]).ok

    def test_failure_during_pool_creation_preserves_old_pool(self, ws):
        """A pool-construction fault revokes the unused candidate and preserves generation one."""
        token, claims, _, _, old = ws.issue_lease(pod_uid="pod-create-fail")
        request, request_value = rotation_request(ws, claims)
        ws.fail("POOL_CREATE", request_id=request_value["request_id"])
        result = ws.rotate(token, request)
        assert not result.ok and result.code == "INJECTED_FAILURE"
        pool, _ = active_pool(ws, claims["pod_uid"])
        assert pool["lease_id"] == old["lease_id"]
        users = ws.inspect("database-users")["database_users"]
        candidates = [u for u in users if u["request_id"] == request_value["request_id"]]
        assert len(candidates) == 1 and candidates[0]["active"] is False

    def test_failure_before_swap_removes_candidate(self, ws):
        """A pre-swap crash leaves no candidate generation eligible for traffic."""
        token, claims, _, _, old = ws.issue_lease(pod_uid="pod-before-swap")
        request, request_value = rotation_request(ws, claims)
        ws.fail("BEFORE_POOL_SWAP", request_id=request_value["request_id"])
        assert not ws.rotate(token, request).ok
        pool, pools = active_pool(ws, claims["pod_uid"])
        assert pool["lease_id"] == old["lease_id"]
        assert all(p["generation"] != 2 for p in pools["pools"][claims["pod_uid"]])

    def test_restart_after_swap_recovers_one_active_generation(self, ws):
        """A crash after atomic swap is recovered without reverting to the revoked generation."""
        token, claims, _, _, old = ws.issue_lease(pod_uid="pod-after-swap")
        request, request_value = rotation_request(ws, claims)
        ws.fail("AFTER_POOL_SWAP", request_id=request_value["request_id"])
        result = ws.rotate(token, request)
        assert not result.ok and result.code == "INJECTED_FAILURE"
        recovered = ws.reconcile(); assert recovered.ok
        pool, pools = active_pool(ws, claims["pod_uid"])
        assert pool["generation"] == 2
        assert sum(p["state"] == "ACTIVE" for p in pools["pools"][claims["pod_uid"]]) == 1
        assert ws.app_json("active-leases.json")["leases"][old["lease_id"]]["status"] == "REVOKED"

    def test_old_pool_rejects_new_work_after_swap(self, ws):
        """Generation fencing prevents callers from selecting the draining pool for new work."""
        token, claims, _, _, _ = ws.issue_lease(pod_uid="pod-stale-gen")
        request, _ = rotation_request(ws, claims); assert ws.rotate(token, request).ok
        denied = ws.dbop(claims["pod_uid"], generation=1)
        assert not denied.ok and denied.code == "STALE_POOL_GENERATION"
        assert ws.dbop(claims["pod_uid"], generation=2).ok

    def test_inflight_session_obeys_drain_grace(self, ws):
        """An existing session finishes inside grace and is terminated after the deterministic deadline."""
        token, claims, _, _, _ = ws.issue_lease(pod_uid="pod-session")
        opened = ws.session_open(claims["pod_uid"]); assert opened.ok
        request, _ = rotation_request(ws, claims); assert ws.rotate(token, request).ok
        sid = opened.result["session_id"]
        assert ws.session_exec(sid).ok
        ws.advance("46s")
        denied = ws.session_exec(sid)
        assert not denied.ok and denied.code == "SESSION_TERMINATED"

    def test_revoked_database_user_cannot_reauthenticate(self, ws):
        """Revocation disables the PostgreSQL identity rather than changing Vault state alone."""
        token, claims, _, _, old = ws.issue_lease(pod_uid="pod-reconnect")
        request, _ = rotation_request(ws, claims); assert ws.rotate(token, request).ok
        users = {u["username"]: u for u in ws.inspect("database-users")["database_users"]}
        assert users[old["username"]]["active"] is False
        denied = ws.runtime_cmd("validate-credential", "--lease-id", old["lease_id"], "--password-reference", old["password_reference"], check=False)
        assert not denied.ok and denied.code == "CREDENTIAL_REVOKED"

    def test_revocation_failure_becomes_independent_retry_work(self, ws):
        """A transient PostgreSQL disable failure records pending cleanup and later succeeds."""
        token, _, _, _, lease = ws.issue_lease(pod_uid="pod-revoke-retry")
        ws.fail("DURING_REVOCATION", lease_id=lease["lease_id"])
        first = ws.revoke(token, lease["lease_id"])
        assert first.ok and first.result["retry_pending"] is True
        assert ws.app_json("active-leases.json")["leases"][lease["lease_id"]]["status"] == "REVOKE_PENDING"
        cleanup = ws.cleanup(); assert cleanup.ok
        assert ws.app_json("active-leases.json")["leases"][lease["lease_id"]]["status"] == "REVOKED"

    def test_one_failed_revocation_does_not_block_another(self, ws):
        """Cleanup attempts each lease independently when one user disable continues failing."""
        ta, _, _, _, a = ws.issue_lease(pod_uid="pod-revoke-a")
        tb, _, _, _, b = ws.issue_lease(pod_uid="pod-revoke-b")
        ws.fail("DURING_REVOCATION", count=2, lease_id=a["lease_id"])
        assert ws.revoke(ta, a["lease_id"]).result["retry_pending"]
        ws.fail("DURING_REVOCATION", lease_id=b["lease_id"])
        assert ws.revoke(tb, b["lease_id"]).result["retry_pending"]
        cleanup = ws.cleanup(); assert cleanup.ok
        states = ws.app_json("active-leases.json")["leases"]
        assert states[a["lease_id"]]["status"] == "REVOKE_PENDING"
        assert states[b["lease_id"]]["status"] == "REVOKED"

    def test_repeated_revocation_is_idempotent(self, ws):
        """Retrying an already completed revocation performs no privilege resurrection."""
        token, _, _, _, lease = ws.issue_lease(pod_uid="pod-revoke-idempotent")
        first = ws.revoke(token, lease["lease_id"]); second = ws.revoke(token, lease["lease_id"])
        assert first.ok and second.ok and second.result["status"] == "REVOKED"
        events = [e for e in ws.inspect("audit")["audit"] if e["event"] == "lease_revoked" and e.get("lease_id") == lease["lease_id"]]
        assert len(events) == 1

    def test_shutdown_revokes_only_the_pods_owned_lease_set(self, ws):
        """Normal shutdown cleans the caller's users while leaving another pod available."""
        ta, _, _, _, a = ws.issue_lease(pod_uid="pod-shutdown-a")
        _, cb, _, _, b = ws.issue_lease(pod_uid="pod-shutdown-b")
        result = ws.shutdown(ta); assert result.ok
        leases = {x["lease_id"]: x for x in ws.inspect("leases")["leases"]}
        assert leases[a["lease_id"]]["status"] == "REVOKED"
        assert leases[b["lease_id"]]["status"] == "ACTIVE"
        assert ws.dbop(cb["pod_uid"]).ok

    def test_pool_metadata_survives_client_restart(self, ws):
        """A simulated process restart retains the selected pool and database availability."""
        _, claims, _, _, lease = ws.issue_lease(pod_uid="pod-restart-pool")
        ws.runtime_cmd("restart-client")
        pool, _ = active_pool(ws, claims["pod_uid"])
        assert pool["lease_id"] == lease["lease_id"] and ws.dbop(claims["pod_uid"]).ok

    def test_static_fallback_credentials_are_absent(self, ws):
        """Editable rotation code contains no emergency static username or password path."""
        text = source_text().lower()
        for forbidden in ("static_password", "emergency_password", "fallback-password", "static-breakglass", "payment_static", "secret/static", "static_fallback"):
            assert forbidden not in text

    def test_breakglass_reference_is_not_used_as_runtime_fallback(self, ws):
        """Failed candidate validation does not authenticate using the emergency static reference."""
        token, claims, _, _, lease = ws.issue_lease(pod_uid="pod-no-breakglass")
        request, request_value = rotation_request(ws, claims)
        ws.fail("POOL_CREATE", request_id=request_value["request_id"])
        denied = ws.rotate(token, request)
        assert not denied.ok
        assert ws.dbop(claims["pod_uid"]).ok
        pool, _ = active_pool(ws, claims["pod_uid"])
        assert pool["lease_id"] == lease["lease_id"]

    @pytest.mark.parametrize("operation", [
        "SELECT_PAYMENT_STATUS", "INSERT_LEDGER_EVENT", "UPDATE_RETRY_METADATA", "EXECUTE_APPROVED_PROCEDURE",
    ])
    def test_documented_database_operations_remain_allowed(self, ws, operation):
        """The dynamic role executes each documented payment-ledger operation."""
        _, claims, _, _, _ = ws.issue_lease()
        result = ws.dbop(claims["pod_uid"], operation=operation)
        assert result.ok and result.result["allowed"] is True

    @pytest.mark.parametrize("operation", ["CREATE_ROLE", "DROP_TABLE", "ALTER_TABLE", "GRANT_PRIVILEGES", "SELECT_IDENTITY_SECRETS"])
    def test_privilege_expansion_is_denied_by_runtime(self, ws, operation):
        """Administrative and customer-identity operations stay outside the dynamic role."""
        _, claims, _, _, _ = ws.issue_lease()
        denied = ws.dbop(claims["pod_uid"], operation=operation)
        assert not denied.ok and denied.code == "PRIVILEGE_DENIED"

    def test_cross_tenant_access_is_denied(self, ws):
        """A valid payment credential cannot cross into another tenant schema."""
        _, claims, _, _, _ = ws.issue_lease()
        denied = ws.dbop(claims["pod_uid"], tenant="identity")
        assert not denied.ok and denied.code == "CROSS_TENANT_DENIED"

    def test_active_pool_and_active_lease_generations_agree(self, ws):
        """The selected pool references the same generation as its active lease after rotation."""
        token, claims, _, _, _ = ws.issue_lease(pod_uid="pod-generation")
        request, _ = rotation_request(ws, claims); result = ws.rotate(token, request); assert result.ok
        pool, _ = active_pool(ws, claims["pod_uid"])
        lease = ws.app_json("active-leases.json")["leases"][pool["lease_id"]]
        assert pool["generation"] == lease["generation"] == result.result["active_generation"]

    def test_manually_revoked_active_credential_fails_closed(self, ws):
        """When no valid replacement exists, security wins over serving with a revoked user."""
        token, claims, _, _, lease = ws.issue_lease(pod_uid="pod-fail-closed")
        assert ws.revoke(token, lease["lease_id"]).ok
        denied = ws.dbop(claims["pod_uid"])
        assert not denied.ok and denied.code == "CREDENTIAL_REVOKED"
