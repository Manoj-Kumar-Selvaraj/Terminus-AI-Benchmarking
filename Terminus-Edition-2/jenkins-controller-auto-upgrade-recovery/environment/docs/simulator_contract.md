# Offline Jenkins cluster simulator contract

The task uses an offline simulator and does not start a real Jenkins process or connect to Kubernetes. The simulator treats the JSON files under `/app/cluster`, `/app/config`, `/app/jenkins_home`, and `/app/state` as the controller's persisted operational state.

Run the diagnostic command with:

```bash
python3 /app/scripts/jenkins_cluster_sim.py diagnose --json
```

A healthy controller reaches phase `READY`. Earlier phases indicate the first blocking production symptom observed by the simulator.

Required output files are written by the simulator under `/app/out` when `start` is executed:

```bash
python3 /app/scripts/jenkins_cluster_sim.py start
```

The simulator phases are intentionally cumulative:

1. Runtime compatibility is evaluated before Jenkins home integrity.
2. Jenkins home integrity is evaluated before plugin loading.
3. Plugin loading is evaluated before upgrade automation safeguards.
4. Upgrade automation safeguards are evaluated before active-controller fencing and queue recovery.
5. A `READY` controller writes `/app/out/controller_status.json`.

The simulator is deterministic. Agents should repair the configuration and persisted state files that are part of the incident, not replace the simulator or write final output files by hand.
