#!/usr/bin/env python3
"""Build NetworkPolicy YAML from lab evidence and contract docs."""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

APP = Path("/app")
POL = APP / "k8s" / "networkpolicy.yaml"


def _parse_key_values(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def _deployment_labels() -> dict[str, str]:
    doc = yaml.safe_load((APP / "k8s/payment-adapter-deployment.yaml").read_text())
    labels = doc.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
    if not labels:
        raise SystemExit("payment adapter labels missing from deployment manifest")
    return labels


def _dns_rule() -> dict:
    return {
        "to": [
            {
                "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
                "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
            }
        ],
        "ports": [{"protocol": "UDP", "port": 53}, {"protocol": "TCP", "port": 53}],
    }


def _ledger_rule() -> dict:
    return {
        "to": [
            {
                "namespaceSelector": {"matchLabels": {"name": "ledger"}},
                "podSelector": {"matchLabels": {"app": "ledger-api"}},
            }
        ],
        "ports": [{"protocol": "TCP", "port": 443}],
    }


def _identity_rule() -> dict:
    return {
        "to": [
            {
                "namespaceSelector": {"matchLabels": {"name": "identity"}},
                "podSelector": {"matchLabels": {"app": "token-service"}},
            }
        ],
        "ports": [{"protocol": "TCP", "port": 8443}],
    }


def _audit_rule() -> dict:
    audit = _parse_key_values(APP / "evidence/audit_approval.txt")
    return {
        "to": [
            {
                "ipBlock": {
                    "cidr": audit["approved_cidr"],
                    "except": [audit["blocked_host"]],
                }
            }
        ],
        "ports": [{"protocol": "TCP", "port": int(audit["service_port"])}],
    }


def render(milestone: int) -> None:
    egress: list[dict] = []
    if milestone >= 1:
        dns_log = (APP / "evidence/dns_failure_events.log").read_text()
        if "kube-dns" not in dns_log or "kube-system" not in dns_log:
            raise SystemExit("dns evidence missing kube-dns peer requirements")
        egress.append(_dns_rule())
    if milestone >= 2:
        ledger_log = (APP / "evidence/ledger_timeout_trace.log").read_text()
        if "ledger-api" not in ledger_log or "port=443" not in ledger_log:
            raise SystemExit("ledger evidence missing API peer requirements")
        egress.append(_ledger_rule())
    if milestone >= 3:
        contract = (APP / "docs/egress_contract.md").read_text()
        if "token-service" not in contract or "8443" not in contract:
            raise SystemExit("egress contract missing identity token requirements")
        egress.append(_identity_rule())
    if milestone >= 4:
        review = (APP / "evidence/security_review.txt").read_text()
        if "10.44.0.0/24" not in review or "10.44.0.200/32" not in review:
            raise SystemExit("security review missing audit CIDR requirements")
        egress.append(_audit_rule())

    doc = {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": "payment-adapter-egress",
            "namespace": "payments",
            "labels": {"incident": "invoice-egress-20260613"},
        },
        "spec": {
            "podSelector": {"matchLabels": _deployment_labels()},
            "policyTypes": ["Egress"],
            "egress": egress,
        },
    }
    POL.write_text(yaml.safe_dump(doc, sort_keys=False))


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: render_policy.py MILESTONE")
    render(int(sys.argv[1]))


if __name__ == "__main__":
    main()
