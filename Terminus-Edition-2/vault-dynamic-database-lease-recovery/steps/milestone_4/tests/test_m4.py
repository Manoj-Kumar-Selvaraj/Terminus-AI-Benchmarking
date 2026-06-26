# ruff: noqa
import json

from helpers import *


def make_issue(ws, pod_uid, request_id=None):
    token, claims = ws.token(ws.claims(pod_uid=pod_uid))
    request, value = ws.request(claims, request_id=request_id)
    return token, claims, request, value


def related(ws, request_id):
    users = [u for u in ws.inspect("database-users")["database_users"] if u.get("request_id") == request_id]
    leases = [l for l in ws.inspect("leases")["leases"] if l.get("request_id") == request_id]
    return users, leases


class TestMilestone4:
    def test_normal_issuance_has_one_user_and_one_lease(self, ws):
        """A normal operation durably commits exactly one dynamic identity."""
        _, _, _, req, lease = ws.issue_lease(pod_uid="pod-normal-m4")
        users, leases = related(ws, req["request_id"])
        assert len(users) == len(leases) == 1
        assert users[0]["username"] == lease["username"] and leases[0]["lease_id"] == lease["lease_id"]

    def test_failure_before_user_creation_retries_without_leak(self, ws):
        """A retryable pre-create outage eventually commits one identity only."""
        token, _, request, value = make_issue(ws, "pod-before-user")
        ws.fail("BEFORE_DB_USER_CREATE", count=2, request_id=value["request_id"])
        result = ws.issue(token, request); assert result.ok
        users, leases = related(ws, value["request_id"])
        assert len(users) == len(leases) == 1

    @pytest.mark.parametrize("point", ["AFTER_DB_USER_CREATE", "BEFORE_LEASE_JOURNAL"])
    def test_partial_user_creation_is_adopted(self, ws, point):
        """An uncertain response after user creation adopts the orphan rather than creating another."""
        token, _, request, value = make_issue(ws, f"pod-{point.lower()}")
        ws.fail(point, request_id=value["request_id"])
        result = ws.issue(token, request); assert result.ok
        users, leases = related(ws, value["request_id"])
        assert len(users) == len(leases) == 1
        assert users[0]["lease_id"] == leases[0]["lease_id"]

    @pytest.mark.parametrize("point", ["AFTER_LEASE_JOURNAL_WRITE", "LOST_CLIENT_RESPONSE"])
    def test_committed_lost_response_returns_original_issuance(self, ws, point):
        """A committed lease is replayed after response loss with no second database user."""
        token, _, request, value = make_issue(ws, f"pod-{point.lower()}")
        ws.fail(point, request_id=value["request_id"])
        first = ws.issue(token, request); assert first.ok
        second = ws.issue(token, request); assert second.ok
        assert first.result["lease_id"] == second.result["lease_id"]
        assert first.result["username"] == second.result["username"]
        users, leases = related(ws, value["request_id"])
        assert len(users) == len(leases) == 1

    @pytest.mark.parametrize("point", ["FAILOVER_AFTER_DB_USER_CREATE", "FAILOVER_AFTER_LEASE_JOURNAL"])
    def test_failover_during_issuance_reconciles_one_identity(self, ws, point):
        """An active-node epoch change during an uncertain issuance does not duplicate the role."""
        token, _, request, value = make_issue(ws, f"pod-{point.lower()}")
        ws.fail(point, request_id=value["request_id"])
        result = ws.issue(token, request); assert result.ok
        users, leases = related(ws, value["request_id"])
        assert len([u for u in users if u["active"]]) == 1
        assert len([l for l in leases if l["status"] == "ACTIVE"]) == 1
        status = ws.runtime_cmd("status").payload
        checkpoint = ws.app_json("recovery-checkpoint.json")
        assert checkpoint["active_node"] == status["active_node"] and checkpoint["active_epoch"] == status["epoch"]

    def test_standby_node_cannot_commit_issuance(self, ws):
        """The trusted runtime rejects a write directed to the non-active node."""
        _, claims = ws.token(ws.claims(pod_uid="pod-standby"))
        request, value = ws.request(claims)
        value.update({"vault_node": "standby-b", "vault_epoch": 1}); request.write_text(json.dumps(value))
        denied = ws.runtime_cmd("issue", "--request", request, check=False)
        assert not denied.ok and denied.code == "STANDBY_NODE"
        assert related(ws, value["request_id"]) == ([], [])

    def test_stale_epoch_is_rejected(self, ws):
        """A writer carrying an obsolete active-node epoch cannot create a user."""
        ws.runtime_cmd("failover", "--to", "standby-b")
        _, claims = ws.token(ws.claims(pod_uid="pod-stale-epoch"))
        request, value = ws.request(claims)
        value.update({"vault_node": "standby-b", "vault_epoch": 1}); request.write_text(json.dumps(value))
        denied = ws.runtime_cmd("issue", "--request", request, check=False)
        assert not denied.ok and denied.code == "STALE_EPOCH"
        assert related(ws, value["request_id"]) == ([], [])

    def test_identical_duplicate_request_returns_same_credential(self, ws):
        """Repeated delivery of an identical operation ID is a logical read, not a new issuance."""
        token, _, request, value = make_issue(ws, "pod-replay", request_id="req-replay-stable")
        a = ws.issue(token, request); b = ws.issue(token, request)
        assert a.ok and b.ok and a.result == b.result
        users, leases = related(ws, value["request_id"])
        assert len(users) == len(leases) == 1

    def test_conflicting_request_id_is_rejected(self, ws):
        """The same operation ID cannot be rebound to a different pod identity."""
        request_id = "req-conflicting-owner"
        ta, _, ra, _ = make_issue(ws, "pod-conflict-a", request_id)
        tb, _, rb, _ = make_issue(ws, "pod-conflict-b", request_id)
        assert ws.issue(ta, ra).ok
        denied = ws.issue(tb, rb)
        assert not denied.ok and denied.code == "REQUEST_ID_CONFLICT"
        users, leases = related(ws, request_id)
        assert len(users) == len(leases) == 1

    def test_orphan_user_from_prior_process_is_adopted(self, ws):
        """Restart recovery discovers a created user lacking a lease and completes the same request."""
        token, _, request, value = make_issue(ws, "pod-orphan-user")
        value.update({"vault_node": "active-a", "vault_epoch": 1}); request.write_text(json.dumps(value))
        ws.fail("AFTER_DB_USER_CREATE", count=1, request_id=value["request_id"])
        raw = ws.runtime_cmd("issue", "--request", request, check=False)
        assert not raw.ok and raw.code == "UNCERTAIN_ISSUANCE"
        users, leases = related(ws, value["request_id"]); assert len(users) == 1 and not leases
        recovered = ws.issue(token, request); assert recovered.ok
        users, leases = related(ws, value["request_id"])
        assert len(users) == len(leases) == 1 and users[0]["active"]

    def test_orphan_lease_without_user_is_failed_and_replaced(self, ws):
        """A lease record whose database user is absent is not exposed as an active credential."""
        token, _, request, value = make_issue(ws, "pod-orphan-lease")
        ws.runtime_cmd("seed", "--fixture", "orphan-lease", "--request", request)
        result = ws.issue(token, request); assert result.ok
        users, leases = related(ws, value["request_id"])
        assert len(users) == 1
        assert len([l for l in leases if l["status"] == "ACTIVE"]) == 1
        assert len([l for l in leases if l["status"] == "FAILED"]) == 1

    def test_repeated_restart_preserves_request_history(self, ws):
        """Multiple client restarts replay a committed issuance without changing its identity."""
        token, _, request, value = make_issue(ws, "pod-restarts")
        first = ws.issue(token, request); assert first.ok
        for _ in range(3):
            ws.runtime_cmd("restart-client")
            assert ws.issue(token, request).result["lease_id"] == first.result["lease_id"]
        assert len(related(ws, value["request_id"])[0]) == 1

    def test_torn_journal_tail_is_truncated_during_recovery(self, ws):
        """A partial final JSONL record is discarded while committed records remain usable."""
        ws.issue_lease(pod_uid="pod-tail")
        journal = ws.state / "lease-journal.jsonl"
        before = journal.read_text(); journal.write_text(before + '{"event":"TORN"')
        result = ws.reconcile(); assert result.ok
        assert journal.read_text() == before
        for line in journal.read_text().splitlines():
            if line.strip(): json.loads(line)

    def test_malformed_committed_journal_entry_is_not_silently_ignored(self, ws):
        """Corruption before a later committed record stops recovery instead of fabricating state."""
        ws.issue_lease(pod_uid="pod-bad-journal")
        journal = ws.state / "lease-journal.jsonl"
        journal.write_text(journal.read_text() + "{bad}\n" + json.dumps({"event":"COMMITTED_AFTER_BAD"}) + "\n")
        denied = ws.reconcile()
        assert not denied.ok and "malformed committed journal" in (denied.code + " " + denied.payload.get("error", {}).get("message", ""))

    def test_username_collision_is_bounded_and_does_not_duplicate(self, ws):
        """A generated-name collision is retried within policy and still yields one user."""
        token, _, request, value = make_issue(ws, "pod-collision")
        ws.fail("USERNAME_COLLISION", count=2, request_id=value["request_id"])
        result = ws.issue(token, request); assert result.ok
        users, leases = related(ws, value["request_id"])
        assert len(users) == len(leases) == 1

    def test_one_failed_request_does_not_block_unrelated_issuance(self, ws):
        """Request-scoped serialization leaves another pod's issuance path available."""
        ta, _, ra, va = make_issue(ws, "pod-blocked")
        tb, _, rb, vb = make_issue(ws, "pod-independent")
        ws.fail("BEFORE_DB_USER_CREATE", count=4, request_id=va["request_id"])
        failed = ws.issue(ta, ra); successful = ws.issue(tb, rb)
        assert not failed.ok and successful.ok
        assert related(ws, va["request_id"])[0] == []
        assert len(related(ws, vb["request_id"])[0]) == 1

    def test_same_request_concurrency_has_single_logical_commit(self, ws):
        """Overlapping retry delivery for one request converges on one user and lease."""
        token, _, request, value = make_issue(ws, "pod-concurrent-same")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: ws.issue(token, request), range(2)))
        assert all(r.ok for r in results)
        assert len({r.result["lease_id"] for r in results}) == 1
        users, leases = related(ws, value["request_id"])
        assert len(users) == len(leases) == 1

    def test_unrelated_requests_can_issue_concurrently(self, ws):
        """Independent issuance paths are not serialized behind a single process-wide lock."""
        policy_path = ws.config / "failover-policy.json"
        policy = json.loads(policy_path.read_text())
        policy["maximumIssueAttempts"] = 100
        policy_path.write_text(json.dumps(policy, indent=2))

        blocked, independent_a, independent_b = [make_issue(ws, f"pod-parallel-{n}") for n in range(3)]
        ws.fail("BEFORE_DB_USER_CREATE", count=200, request_id=blocked[3]["request_id"])
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                "blocked": pool.submit(ws.issue, blocked[0], blocked[2]),
                "a": pool.submit(ws.issue, independent_a[0], independent_a[2]),
                "b": pool.submit(ws.issue, independent_b[0], independent_b[2]),
            }
            result_a = futures["a"].result(timeout=90)
            result_b = futures["b"].result(timeout=90)
            assert not futures["blocked"].done()
        assert result_a.ok and result_b.ok
        assert result_a.result["lease_id"] != result_b.result["lease_id"]

    def test_issued_user_keeps_least_privilege_contract(self, ws):
        """Failover recovery does not broaden the dynamic PostgreSQL role."""
        _, claims, _, _, _ = ws.issue_lease(pod_uid="pod-m4-priv")
        assert ws.dbop(claims["pod_uid"], operation="INSERT_LEDGER_EVENT").ok
        denied = ws.dbop(claims["pod_uid"], operation="CREATE_ROLE")
        assert not denied.ok and denied.code == "PRIVILEGE_DENIED"

    def test_retry_limit_reports_failure_without_leaking_users(self, ws):
        """Exhausting issuance attempts produces a stable failure and no database role leak."""
        token, _, request, value = make_issue(ws, "pod-retry-limit")
        ws.fail("BEFORE_DB_USER_CREATE", count=10, request_id=value["request_id"])
        result = ws.issue(token, request)
        assert not result.ok and result.code == "UPSTREAM_UNAVAILABLE"
        users, leases = related(ws, value["request_id"])
        assert not users and not leases
        record = ws.app_json("issuance-requests.json")["requests"][value["request_id"]]
        assert record["state"] == "FAILED"

    def test_failback_updates_durable_active_node_checkpoint(self, ws):
        """Failover and failback epochs are reflected in the durable recovery checkpoint."""
        ws.runtime_cmd("failover", "--to", "standby-b")
        ws.issue_lease(pod_uid="pod-on-b")
        ws.runtime_cmd("failover", "--to", "active-a")
        result = ws.reconcile(); assert result.ok
        status = ws.runtime_cmd("status").payload
        checkpoint = ws.app_json("recovery-checkpoint.json")
        assert checkpoint["active_node"] == "active-a"
        assert checkpoint["active_epoch"] == status["epoch"] == 3

    def test_request_order_does_not_change_replay_correctness(self, ws):
        """Generated request IDs remain independent when requests arrive in reverse lexical order."""
        items = [make_issue(ws, f"pod-order-{n}", request_id=f"req-order-{n}") for n in range(4)]
        for token, _, request, _ in reversed(items): assert ws.issue(token, request).ok
        for token, _, request, value in items:
            assert ws.issue(token, request).ok
            assert len(related(ws, value["request_id"])[0]) == 1
