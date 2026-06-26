# Payment adapter egress contract

The payment adapter runs under default-deny egress in the `payments` namespace. Update `/app/k8s/networkpolicy.yaml` so the policy selects the payment adapter pods and allows only the peers below.

## DNS (kube-system / kube-dns)

- `namespaceSelector.matchLabels.kubernetes.io/metadata.name`: `kube-system`
- `podSelector.matchLabels.k8s-app`: `kube-dns`
- Ports: UDP `53` and TCP `53`

## Ledger API

- `namespaceSelector.matchLabels.name`: `ledger`
- `podSelector.matchLabels.app`: `ledger-api`
- Port: TCP `443`

## Identity token service

- `namespaceSelector.matchLabels.name`: `identity`
- `podSelector.matchLabels.app`: `token-service`
- Port: TCP `8443`

## Private audit endpoint

- `ipBlock.cidr`: `10.44.0.0/24`
- `ipBlock.except`: `10.44.0.200/32`
- Port: TCP `9443`

The adapter must not permit `0.0.0.0/0`, empty selectors, namespace-wide peers without a `podSelector`, or other broad Internet egress.
