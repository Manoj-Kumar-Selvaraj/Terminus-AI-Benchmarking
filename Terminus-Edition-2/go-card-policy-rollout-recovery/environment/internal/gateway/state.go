package gateway

import "sync"

type SeenCommand struct {
	Status           string `json:"status"`
	ActiveGeneration int64  `json:"active_generation"`
	Sequence         int64  `json:"sequence"`
	PolicySHA256     string `json:"policy_sha256"`
}

type AuditEntry struct {
	CommandID    string `json:"command_id"`
	RolloutID    string `json:"rollout_id"`
	Generation   int64  `json:"generation"`
	PolicySHA256 string `json:"policy_sha256"`
	Sequence     int64  `json:"sequence"`
}

type PersistentState struct {
	Region           string                 `json:"region"`
	ActiveGeneration int64                  `json:"active_generation"`
	PolicySHA256     string                 `json:"policy_sha256"`
	Sequence         int64                  `json:"sequence"`
	Seen             map[string]SeenCommand `json:"seen"`
	RequestAttempts  map[string]int64       `json:"request_attempts"`
	Audits           []AuditEntry           `json:"audits"`
}

type StateFile struct {
	mu    sync.Mutex
	path  string
	state PersistentState
}
