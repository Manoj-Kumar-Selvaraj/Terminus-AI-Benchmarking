package gateway

type ApplyRequest struct {
	CommandID    string `json:"command_id"`
	RolloutID    string `json:"rollout_id"`
	Generation   int64  `json:"generation"`
	PolicySHA256 string `json:"policy_sha256"`
	Policy       string `json:"policy"`
}

type ApplyResponse struct {
	Status           string `json:"status"`
	Region           string `json:"region"`
	CommandID        string `json:"command_id"`
	ActiveGeneration int64  `json:"active_generation"`
	Sequence         int64  `json:"sequence"`
	PolicySHA256     string `json:"policy_sha256"`
}
