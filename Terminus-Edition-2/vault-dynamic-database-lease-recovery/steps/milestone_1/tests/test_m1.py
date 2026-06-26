# ruff: noqa
import json
from pathlib import Path

import pytest

from helpers import *

class TestMilestone1:
    def test_valid_payment_service_account_authenticates(self, ws):
        """The exact configured payment workload receives a stable non-secret identity."""
        token, claims = ws.token(ws.claims())
        result = ws.login(token)
        assert result.ok
        assert result.result["namespace"] == "payments"
        assert result.result["service_account"] == "payment-ledger-api"
        assert result.result["pod_uid"] == claims["pod_uid"]

    @pytest.mark.parametrize("audience", ["vault.payment-ledger.internal", ["vault.payment-ledger.internal"], ["cluster-api", "vault.payment-ledger.internal"]])
    def test_supported_audience_representations_are_accepted(self, ws, audience):
        """A string audience or an audience list containing the required value remains valid."""
        token, _ = ws.token(ws.claims(audience=audience))
        assert ws.login(token).ok

    def test_wrong_namespace_is_denied_without_side_effects(self, ws):
        """A correctly signed token from another namespace cannot create payment credentials."""
        claims = ws.claims(namespace="payments-preview", subject="system:serviceaccount:payments-preview:payment-ledger-api")
        token, claims = ws.token(claims)
        request, _ = ws.request(claims)
        result = ws.issue(token, request)
        assert_denied(result, "WRONG_NAMESPACE")
        assert runtime_user_count(ws) == 0 and runtime_lease_count(ws) == 0

    def test_wrong_service_account_is_denied(self, ws):
        """A different service account in the payment namespace cannot authenticate."""
        claims = ws.claims(service_account="payment-debug", subject="system:serviceaccount:payments:payment-debug")
        token, _ = ws.token(claims)
        assert_denied(ws.login(token), "WRONG_SERVICE_ACCOUNT")

    def test_same_service_account_name_in_another_namespace_is_denied(self, ws):
        """Namespace isolation is exact even when the service-account name is identical."""
        claims = ws.claims(namespace="other", subject="system:serviceaccount:other:payment-ledger-api")
        token, _ = ws.token(claims)
        assert_denied(ws.login(token), "WRONG_NAMESPACE")

    def test_wrong_audience_is_denied(self, ws):
        """A token minted only for the Kubernetes API cannot be used for Vault login."""
        token, _ = ws.token(ws.claims(audience=["cluster-api"]))
        assert_denied(ws.login(token), "INVALID_AUDIENCE")

    def test_missing_audience_is_denied(self, ws):
        """A signed token without an audience claim is not authorized."""
        claims = ws.claims(); claims.pop("aud")
        token, _ = ws.token(claims)
        assert_denied(ws.login(token), "MISSING_CLAIM")

    def test_expired_token_is_denied_at_boundary(self, ws):
        """A token whose exp equals the deterministic clock is already expired."""
        token, _ = ws.token(ws.claims(exp=int(NOW.timestamp())))
        assert_denied(ws.login(token), "TOKEN_EXPIRED")

    def test_not_yet_valid_token_is_denied(self, ws):
        """A token with nbf after the deterministic clock cannot authenticate early."""
        token, _ = ws.token(ws.claims(nbf=int(NOW.timestamp()) + 1))
        assert_denied(ws.login(token), "TOKEN_NOT_YET_VALID")

    def test_untrusted_issuer_is_denied(self, ws):
        """A correctly signed token carrying an untrusted issuer is rejected."""
        token, _ = ws.token(ws.claims(issuer="https://issuer.attacker.invalid"))
        assert_denied(ws.login(token), "INVALID_ISSUER")

    @pytest.mark.parametrize("subject", [
        "serviceaccount:payments:payment-ledger-api",
        "system:serviceaccount:payments",
        "system:serviceaccount::payment-ledger-api",
        "system:serviceaccount:payments:payment-ledger-api:extra",
        "system:serviceaccount:payments:payment-ledger-api-debug",
    ])
    def test_malformed_or_prefix_collision_subjects_are_denied(self, ws, subject):
        """Malformed subjects and prefix collisions never match the configured identity."""
        token, _ = ws.token(ws.claims(subject=subject))
        assert_denied(ws.login(token), "MALFORMED_SUBJECT")

    @pytest.mark.parametrize("claim", ["namespace", "service_account", "pod_uid", "iss", "sub", "exp"])
    def test_required_claims_cannot_be_omitted(self, ws, claim):
        """Every documented workload-identity claim has a direct denial path."""
        claims = ws.claims(); claims.pop(claim)
        token, _ = ws.token(claims)
        assert_denied(ws.login(token), "MISSING_CLAIM")

    def test_tampered_signature_is_denied(self, ws):
        """Changing a signed token after minting is detected by the trusted validator."""
        token, _ = ws.token(ws.claims())
        parts = token.read_text(encoding="utf-8").strip().split(".")
        sig = parts[2]
        parts[2] = sig[:-1] + ("A" if sig[-1] != "A" else "B")
        token.write_text(".".join(parts), encoding="utf-8")
        assert_denied(ws.login(token), "INVALID_SIGNATURE")

    def test_empty_token_is_denied(self, ws):
        """An empty token file produces a stable failure and no runtime side effects."""
        path = ws.root / "tokens" / "empty.jwt"; path.parent.mkdir(); path.write_text("")
        assert_denied(ws.login(path), "EMPTY_TOKEN")
        assert runtime_user_count(ws) == 0

    def test_auth_configuration_key_reordering_does_not_change_validity(self, ws):
        """Authorization is based on configuration fields rather than serialized key order."""
        path = ws.config / "kubernetes-auth.json"
        value = json.loads(path.read_text())
        path.write_text(json.dumps(dict(reversed(list(value.items())))))
        token, _ = ws.token(ws.claims())
        assert ws.login(token).ok

    def test_claim_ordering_in_token_does_not_change_validity(self, ws):
        """Authentication remains stable when JWT claim JSON key order changes before minting."""
        claims = ws.claims()
        cpath = ws.root / "claims" / "reordered-claims.json"
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps(dict(sorted(claims.items(), key=lambda item: item[0], reverse=True)), indent=2))
        minted = ws.runtime_cmd("mint-token", "--claims", cpath).payload["token"]
        tpath = ws.root / "tokens" / "reordered.jwt"
        tpath.parent.mkdir(parents=True, exist_ok=True)
        tpath.write_text(minted)
        assert ws.login(tpath).ok

    def test_raw_token_is_absent_from_application_logs(self, ws):
        """Successful and rejected authentication never copy the JWT into application logs."""
        token, _ = ws.token(ws.claims())
        raw = token.read_text()
        assert ws.login(token).ok
        text = ws.log.read_text() if ws.log.exists() else ""
        assert raw not in text
        assert raw.split(".")[1] not in text

    def test_error_response_does_not_expose_secret_claims(self, ws):
        """A denial response contains a stable code but not the token or private claim values."""
        secret = "claim-secret-" + "x" * 20
        token, _ = ws.token(ws.claims(issuer="https://bad.invalid", extra={"private": secret}))
        raw = token.read_text()
        result = ws.login(token)
        assert_denied(result, "INVALID_ISSUER")
        rendered = json.dumps(result.payload)
        assert secret not in rendered and raw not in rendered

    def test_repeated_valid_login_is_deterministic(self, ws):
        """Repeated login with one token returns the same accessor and creates no credentials."""
        token, _ = ws.token(ws.claims())
        first = ws.login(token); second = ws.login(token)
        assert first.ok and second.ok
        assert first.result == second.result
        assert runtime_user_count(ws) == 0 and runtime_lease_count(ws) == 0

    def test_token_cannot_select_a_different_vault_role(self, ws):
        """An untrusted vault_role claim cannot override the configured role mapping."""
        token, _ = ws.token(ws.claims(extra={"vault_role":"database-admin"}))
        result = ws.login(token)
        assert result.ok and result.result["vault_role"] == "payment-ledger-k8s"

    def test_unauthorized_database_role_request_is_rejected(self, ws):
        """A valid workload cannot use request data to select an unrelated database role."""
        token, claims = ws.token(ws.claims())
        request, _ = ws.request(claims, role="identity-admin")
        result = ws.issue(token, request)
        assert_denied(result, "ROLE_DENIED")
        assert runtime_user_count(ws) == 0
