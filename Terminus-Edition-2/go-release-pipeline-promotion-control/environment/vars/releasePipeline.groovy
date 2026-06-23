def call(Map cfg = [:]) {
  // Offline model of the production shared library interface.
  // Stage names, manifest schema, build number, commit sha, promoted artifact hash,
  // and rollback command interface are compatibility contracts for the simulator.
  sh "go run ./cmd/pipelinesim run --scenario ${cfg.scenario ?: '/app/scenarios/release_candidate.json'} --out ${cfg.out ?: '/app/out/pipeline'}"
}
