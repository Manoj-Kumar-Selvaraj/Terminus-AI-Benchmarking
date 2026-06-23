# Container runtime contract

The billing pod runs with a 256Mi memory limit. JVM startup options live in
`/app/config/jvm.options` and must respect cgroup limits on JDK 17.

The service must remain stable under the published memory limit during invoice
traffic. Heap sizing must use container-aware settings rather than a fixed heap
larger than the pod limit.
