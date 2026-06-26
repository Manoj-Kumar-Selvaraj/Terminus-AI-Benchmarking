package model

import "sort"

const (
	StatusPending    = "pending"
	StatusClaimed    = "claimed"
	StatusAcked      = "acked"
	StatusSuperseded = "superseded"
	StatusFailed     = "failed"
)

type Delivery struct {
	Region          string `json:"region"`
	CommandID       string `json:"command_id"`
	Status          string `json:"status"`
	LeaseOwner      string `json:"lease_owner,omitempty"`
	LeaseUntil      int64  `json:"lease_until,omitempty"`
	ClaimToken      int64  `json:"claim_token,omitempty"`
	GatewaySequence int64  `json:"gateway_sequence,omitempty"`
	LastError       string `json:"last_error,omitempty"`
}

type Rollout struct {
	ID           string               `json:"id"`
	Generation   int64                `json:"generation"`
	Policy       string               `json:"policy"`
	PolicySHA256 string               `json:"policy_sha256"`
	Deliveries   map[string]*Delivery `json:"deliveries"`
}

type State struct {
	SchemaVersion    int64               `json:"schema_version"`
	Rollouts         map[string]*Rollout `json:"rollouts"`
	ActiveGeneration map[string]int64    `json:"active_generation"`
}

func NewState() *State {
	return &State{
		SchemaVersion:    2,
		Rollouts:         map[string]*Rollout{},
		ActiveGeneration: map[string]int64{},
	}
}

func (s *State) SortedRollouts() []*Rollout {
	out := make([]*Rollout, 0, len(s.Rollouts))
	for _, rollout := range s.Rollouts {
		out = append(out, rollout)
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Generation != out[j].Generation {
			return out[i].Generation < out[j].Generation
		}
		return out[i].ID < out[j].ID
	})
	return out
}
