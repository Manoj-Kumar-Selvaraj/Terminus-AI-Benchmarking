#!/usr/bin/env python3
import sys
from pathlib import Path

import yaml

APP = Path("/app")
POL = APP / "k8s" / "networkpolicy.yaml"
TOPOLOGY = APP / "config" / "simulator" / "topology.yaml"


def load_topology():
    data = yaml.safe_load(TOPOLOGY.read_text())
    return data["namespaces"], data["pods"], data["ips"]


def match_labels(labels, sel):
    if not sel:
        return True
    ml = sel.get("matchLabels", {})
    return all(labels.get(k) == v for k, v in ml.items())


def cidr_contains(cidr, ip):
    return (
        cidr == "0.0.0.0/0"
        or (cidr == "10.44.0.0/24" and ip.startswith("10.44.0."))
        or (cidr.endswith("/32") and cidr[:-3] == ip)
    )


def allowed(dest, proto, port, namespaces, pods, ips):
    doc = yaml.safe_load(POL.read_text())
    if doc.get("kind") != "NetworkPolicy":
        return False
    if doc.get("metadata", {}).get("namespace") != "payments":
        return False
    if not match_labels(pods["payment-adapter"]["labels"], doc.get("spec", {}).get("podSelector", {})):
        return False
    for rule in doc.get("spec", {}).get("egress", []) or []:
        port_ok = any(
            str(p.get("protocol", "TCP")).upper() == proto.upper() and int(p.get("port")) == int(port)
            for p in rule.get("ports", []) or []
        )
        if not port_ok:
            continue
        for to in rule.get("to", []) or []:
            if dest in pods:
                ns = pods[dest]["namespace"]
                labels = pods[dest]["labels"]
                ns_ok = (
                    match_labels(namespaces[ns], to.get("namespaceSelector"))
                    if "namespaceSelector" in to
                    else (ns == "payments")
                )
                pod_ok = match_labels(labels, to.get("podSelector")) if "podSelector" in to else True
                if ns_ok and pod_ok:
                    return True
            if dest in ips and "ipBlock" in to:
                ip = ips[dest]
                block = to["ipBlock"]
                if cidr_contains(block.get("cidr", ""), ip) and all(
                    not cidr_contains(exc, ip) for exc in block.get("except", []) or []
                ):
                    return True
    return False


def main():
    if len(sys.argv) != 4:
        print("usage: simulate_egress.py DEST PROTO PORT", file=sys.stderr)
        return 2
    namespaces, pods, ips = load_topology()
    print("ALLOW" if allowed(sys.argv[1], sys.argv[2], int(sys.argv[3]), namespaces, pods, ips) else "DENY")


if __name__ == "__main__":
    raise SystemExit(main() or 0)
