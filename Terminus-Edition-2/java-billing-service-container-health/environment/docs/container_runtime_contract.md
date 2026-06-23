# Container runtime contract

The billing pod runs with a 256Mi memory limit. JVM startup options live in
`/app/config/jvm.options` and must respect cgroup limits on JDK 17.

Required JVM options for milestone 3:

- `-XX:+UseContainerSupport`
- `-XX:MaxRAMPercentage=<n>` where `<n>` is a percentage that keeps the effective
  heap within the 256Mi pod limit (tests accept 25–75).

Do not use fixed heap caps such as `-Xmx512m` or `-Xms256m` that exceed the pod
memory limit. Keep `billing.container.memory.mb=256` in
`/app/config/application.properties`.

The service must remain stable under the published memory limit during invoice
traffic.
