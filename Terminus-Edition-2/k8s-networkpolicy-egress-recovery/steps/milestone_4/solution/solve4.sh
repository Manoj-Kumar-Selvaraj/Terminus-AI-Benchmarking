#!/usr/bin/env bash
set -Eeuo pipefail
cat > /app/k8s/networkpolicy.yaml <<'YAML'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-adapter-egress
  namespace: payments
  labels:
    incident: invoice-egress-20260613
spec:
  podSelector:
    matchLabels:
      app: payment-adapter
      component: invoice-batch
  policyTypes:
    - Egress
  egress:
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
    - to:
        - namespaceSelector:
            matchLabels:
              name: ledger
          podSelector:
            matchLabels:
              app: ledger-api
      ports:
        - protocol: TCP
          port: 443
    - to:
        - namespaceSelector:
            matchLabels:
              name: identity
          podSelector:
            matchLabels:
              app: token-service
      ports:
        - protocol: TCP
          port: 8443
    - to:
        - ipBlock:
            cidr: 10.44.0.0/24
            except:
              - 10.44.0.200/32
      ports:
        - protocol: TCP
          port: 9443
YAML
