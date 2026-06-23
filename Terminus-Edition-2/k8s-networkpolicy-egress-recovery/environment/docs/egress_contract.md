# Payment adapter egress contract
The payment adapter runs under default-deny egress. It must resolve DNS via kube-dns over UDP and TCP 53, reach the ledger API on TCP 443, reach the identity token service on TCP 8443, and reach the private audit endpoint CIDR on TCP 9443. It must not permit broad Internet egress.
