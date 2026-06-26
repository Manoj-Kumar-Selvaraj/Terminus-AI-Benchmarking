# ruff: noqa
import json
from datetime import datetime, timezone

import pytest

from helpers import *

class TestMilestone2:
    def test_renewal_succeeds_inside_safety_window(self, ws):
        """A valid lease renews before expiry once it enters the configured safety window."""
        token, claims, _, _, lease = ws.issue_lease()
        ws.advance("211s")
        result = ws.renew(token, lease["lease_id"])
        assert result.ok and result.result["action"] == "RENEWED"

    def test_renewal_occurs_exactly_at_window_boundary(self, ws):
        """The exact expires-minus-window boundary is eligible for renewal."""
        token, _, _, _, lease = ws.issue_lease()
        ws.advance("210s")
        result = ws.renew(token, lease["lease_id"])
        assert result.ok and result.result["action"] == "RENEWED"

    def test_renewal_too_early_is_a_noop(self, ws):
        """A lease one second outside the safety window is not renewed prematurely."""
        token, _, _, _, lease = ws.issue_lease()
        before = lease["expires_at"]
        ws.advance("209s")
        result = ws.renew(token, lease["lease_id"])
        assert result.ok and result.result["action"] == "NO_ACTION"
        assert result.result["expires_at"] == before

    def test_renewal_after_expiry_is_rejected(self, ws):
        """At the expiry boundary a lease becomes expired instead of being revived."""
        token, _, _, _, lease = ws.issue_lease()
        ws.advance("300s")
        result = ws.renew(token, lease["lease_id"])
        assert result.ok and result.result["action"] == "EXPIRED" and not result.result["usable"]

    def test_renewal_never_extends_past_maximum_ttl(self, ws):
        """Repeated deterministic renewals stop at max_expires_at and request rotation."""
        token, _, _, _, lease = ws.issue_lease()
        current = lease
        for _ in range(9):
            ws.advance("210s")
            result = ws.renew(token, lease["lease_id"])
            assert result.ok
            current = result.result
            if current["expires_at"] == current["max_expires_at"]:
                break
        assert current["expires_at"] == current["max_expires_at"]
        ws.advance("210s")
        final = ws.renew(token, lease["lease_id"])
        assert final.ok and final.result["action"] in {"ROTATION_REQUIRED", "EXPIRED"}

    def test_requested_renewal_target_is_clamped_before_runtime_call(self, ws):
        """The application does not ask the runtime to renew beyond the documented maximum."""
        token, _, _, _, lease = ws.issue_lease()
        ws.runtime_cmd("admin-set-lease", "--lease-id", lease["lease_id"], "--field", "expires_at", "--value", "2026-06-23T10:28:00Z")
        data = ws.app_json("active-leases.json"); data["leases"][lease["lease_id"]]["expires_at"] = "2026-06-23T10:28:00Z"; (ws.state/"active-leases.json").write_text(json.dumps(data))
        ws.set_clock("2026-06-23T10:27:00Z")
        result = ws.renew(token, lease["lease_id"])
        assert result.ok and result.result["expires_at"] == lease["max_expires_at"]
        events = ws.inspect("audit")["audit"]
        renew = [e for e in events if e["event"] == "lease_renewed"][-1]
        assert renew["requested_expires_at"] == lease["max_expires_at"]

    def test_renewal_preserves_lease_and_database_identity(self, ws):
        """Renewal keeps the lease ID, username, owner, and pool generation unchanged."""
        token, _, _, _, lease = ws.issue_lease()
        ws.advance("210s")
        renewed = ws.renew(token, lease["lease_id"])
        assert renewed.ok
        for key in ("lease_id", "username", "owner_pod_uid", "generation", "request_id"):
            assert renewed.result[key] == lease[key]

    def test_transient_renewal_failure_retries_then_succeeds(self, ws):
        """One transient Vault failure is retried without replacing the credential."""
        token, _, _, _, lease = ws.issue_lease()
        ws.advance("210s"); ws.fail("RENEW_TRANSIENT", lease_id=lease["lease_id"])
        result = ws.renew(token, lease["lease_id"])
        assert result.ok and result.result["action"] == "RENEWED" and result.result["attempts"] == 2

    def test_retry_limit_is_enforced_while_valid_lease_remains_usable(self, ws):
        """Four transient failures stop at policy limit and retain only the still-valid lease."""
        token, _, _, _, lease = ws.issue_lease()
        ws.advance("210s"); ws.fail("RENEW_TRANSIENT", count=4, lease_id=lease["lease_id"])
        result = ws.renew(token, lease["lease_id"])
        assert result.ok and result.result["action"] == "RETRY_PENDING"
        assert result.result["attempts"] == 4 and result.result["usable"] is True

    def test_repeated_renewal_request_is_idempotent(self, ws):
        """Repeating maintenance at one clock instant does not create another renewal or user."""
        token, _, _, _, lease = ws.issue_lease(); ws.advance("210s")
        first = ws.renew(token, lease["lease_id"]); second = ws.renew(token, lease["lease_id"])
        assert first.ok and second.ok and second.result["action"] == "NO_ACTION"
        assert first.result["lease_id"] == second.result["lease_id"]
        assert runtime_user_count(ws) == 1

    def test_renewal_respects_minimum_interval(self, ws):
        """Renewal inside the safety window is throttled by minimumRenewalIntervalSeconds."""
        token, _, _, _, lease = ws.issue_lease()
        ws.set_clock("2026-06-23T10:03:30Z")
        data = ws.app_json("active-leases.json")
        record = data["leases"][lease["lease_id"]]
        record["expires_at"] = "2026-06-23T10:04:30Z"
        record["last_renewed_at"] = "2026-06-23T10:03:15Z"
        (ws.state / "active-leases.json").write_text(json.dumps(data))

        throttled = ws.renew(token, lease["lease_id"])
        assert throttled.ok and throttled.result["action"] == "NO_ACTION"

        ws.advance("16s")
        renewed = ws.renew(token, lease["lease_id"])
        assert renewed.ok and renewed.result["action"] == "RENEWED"

    def test_process_restart_before_renewal_reconstructs_state(self, ws):
        """A new lease-agent process renews from durable snapshots without in-memory ownership."""
        token, _, _, _, lease = ws.issue_lease(); ws.runtime_cmd("restart-client"); ws.advance("210s")
        result = ws.renew(token, lease["lease_id"])
        assert result.ok and result.result["action"] == "RENEWED"

    def test_process_restart_during_retry_uses_same_lease(self, ws):
        """After an exhausted transient retry, a restarted process resumes the same lease."""
        token, _, _, _, lease = ws.issue_lease(); ws.advance("210s"); ws.fail("RENEW_TRANSIENT", count=4, lease_id=lease["lease_id"])
        first = ws.renew(token, lease["lease_id"]); assert first.result["action"] == "RETRY_PENDING"
        ws.runtime_cmd("restart-client")
        second = ws.renew(token, lease["lease_id"])
        assert second.ok and second.result["action"] == "RENEWED" and second.result["lease_id"] == lease["lease_id"]

    def test_expired_lease_is_not_returned_as_database_active(self, ws):
        """Database authentication fails once deterministic time reaches lease expiry."""
        _, claims, _, _, lease = ws.issue_lease(); ws.advance("300s")
        result = ws.dbop(claims["pod_uid"])
        assert not result.ok and result.code == "CREDENTIAL_EXPIRED"

    def test_renewal_creates_no_additional_database_user(self, ws):
        """Successful and retried renewal preserve the single dynamic database identity."""
        token, _, _, _, lease = ws.issue_lease(); ws.advance("210s"); ws.fail("RENEW_TRANSIENT", lease_id=lease["lease_id"])
        assert ws.renew(token, lease["lease_id"]).ok
        assert runtime_user_count(ws) == 1 and runtime_lease_count(ws) == 1

    def test_retry_backoff_is_deterministic_and_does_not_sleep(self, ws):
        """Retry reports the configured deterministic backoff sequence without wall-clock sleeping."""
        token, _, _, _, lease = ws.issue_lease(); ws.advance("210s"); ws.fail("RENEW_TRANSIENT", count=4, lease_id=lease["lease_id"])
        started = time.monotonic(); result = ws.renew(token, lease["lease_id"]); elapsed = time.monotonic() - started
        assert result.result["backoff_seconds"] == [1, 2, 4]
        assert elapsed < 8

    def test_clock_moving_forward_across_expiry_never_revives_lease(self, ws):
        """Advancing beyond expiry then farther forward keeps the lease unusable."""
        token, _, _, _, lease = ws.issue_lease(); ws.advance("5m")
        first = ws.renew(token, lease["lease_id"]); ws.advance("5m"); second = ws.renew(token, lease["lease_id"])
        assert first.result["action"] == "EXPIRED" and second.result["action"] == "EXPIRED"

    def test_clock_regression_is_handled_safely(self, ws):
        """A runtime clock moving backwards is classified instead of extending a lease."""
        token, _, _, _, lease = ws.issue_lease(); ws.advance("30s"); assert ws.renew(token, lease["lease_id"]).ok
        ws.set_clock("2026-06-23T10:00:00Z")
        result = ws.renew(token, lease["lease_id"])
        assert not result.ok and result.code == "CLOCK_REGRESSION"

    def test_nonrenewable_lease_requests_rotation(self, ws):
        """A non-renewable but valid lease follows rotation policy rather than reissuance."""
        token, _, _, _, lease = ws.issue_lease(); ws.runtime_cmd("admin-set-lease", "--lease-id", lease["lease_id"], "--field", "renewable", "--value", "false")
        data=ws.app_json("active-leases.json");data["leases"][lease["lease_id"]]["renewable"]=False;(ws.state/"active-leases.json").write_text(json.dumps(data))
        ws.advance("210s"); result=ws.renew(token,lease["lease_id"])
        assert result.ok and result.result["action"]=="ROTATION_REQUIRED"

    def test_malformed_lease_metadata_is_rejected(self, ws):
        """Invalid durable lease timestamps fail closed instead of being guessed or overwritten."""
        token, _, _, _, lease = ws.issue_lease(); data=ws.app_json("active-leases.json");data["leases"][lease["lease_id"]]["expires_at"]="not-a-time";(ws.state/"active-leases.json").write_text(json.dumps(data))
        result=ws.renew(token,lease["lease_id"]);assert not result.ok and result.code=="MALFORMED_LEASE"

    def test_unknown_lease_id_is_rejected(self, ws):
        """Renewing an unknown lease never creates a credential as a side effect."""
        token,_=ws.token(ws.claims());result=ws.renew(token,"vdb-missing")
        assert not result.ok and result.code=="UNKNOWN_LEASE" and runtime_user_count(ws)==0

    def test_revoked_lease_cannot_renew(self, ws):
        """A successfully revoked lease remains revoked when maintenance is retried."""
        token, _, _, _, lease = ws.issue_lease(); assert ws.revoke(token,lease["lease_id"]).ok
        result=ws.renew(token,lease["lease_id"]);assert not result.ok and result.code=="LEASE_REVOKED"

    def test_renewal_journal_is_atomic_valid_json_lines(self, ws):
        """Renewal and retry events leave a parseable durable JSONL journal."""
        token, _, _, _, lease = ws.issue_lease();ws.advance("210s");ws.fail("RENEW_TRANSIENT",lease_id=lease["lease_id"]);assert ws.renew(token,lease["lease_id"]).ok
        lines=[x for x in ws.app_text("lease-journal.jsonl").splitlines() if x.strip()]
        events=[json.loads(x) for x in lines]
        assert any(e["event"]=="RENEW_RETRY" for e in events) and any(e["event"]=="RENEWED" for e in events)

    def test_renewal_survives_checkpoint_loss_with_journal_intact(self, ws):
        """A restarted process can renew when durable journal evidence outlives a lost checkpoint."""
        token, _, _, _, lease = ws.issue_lease()
        ws.advance("210s")
        assert ws.renew(token, lease["lease_id"]).ok
        assert ws.app_text("lease-journal.jsonl").strip()
        (ws.state / "recovery-checkpoint.json").unlink(missing_ok=True)
        ws.runtime_cmd("restart-client")
        ws.advance("210s")
        result = ws.renew(token, lease["lease_id"])
        assert result.ok and result.result["lease_id"] == lease["lease_id"]

    def test_unrelated_leases_renew_independently(self, ws):
        """A targeted failure for one lease does not prevent another pod lease from renewing."""
        token_a, _, _, _, a=ws.issue_lease(pod_uid="pod-a");token_b, _, _, _, b=ws.issue_lease(pod_uid="pod-b")
        ws.advance("210s");ws.fail("RENEW_TRANSIENT",count=4,lease_id=a["lease_id"])
        ra=ws.renew(token_a,a["lease_id"]);rb=ws.renew(token_b,b["lease_id"])
        assert ra.result["action"]=="RETRY_PENDING" and rb.result["action"]=="RENEWED"

    def test_renewal_uses_only_deterministic_clock_interfaces(self, ws):
        """Editable lifecycle code contains no wall-clock sleeps or time.Now scheduling."""
        text=source_text()
        assert "time.Sleep(" not in text
        assert "time.Now(" not in text

    def test_lease_policy_key_reordering_does_not_change_boundaries(self, ws):
        """Renewal policy is read by field name rather than serialized object order."""
        path=ws.config/"lease-policy.json";value=json.loads(path.read_text());path.write_text(json.dumps(dict(reversed(list(value.items())))))
        token, _, _, _, lease=ws.issue_lease();ws.advance("210s")
        assert ws.renew(token,lease["lease_id"]).result["action"]=="RENEWED"
