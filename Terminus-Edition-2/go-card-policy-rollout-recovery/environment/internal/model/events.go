package model

import "encoding/json"

type Event struct {
	Version         int64    `json:"version"`
	Type            string   `json:"type"`
	RolloutID       string   `json:"rollout_id,omitempty"`
	Generation      int64    `json:"generation,omitempty"`
	Policy          string   `json:"policy,omitempty"`
	PolicySHA256    string   `json:"policy_sha256,omitempty"`
	Regions         []string `json:"regions,omitempty"`
	Region          string   `json:"region,omitempty"`
	CommandID       string   `json:"command_id,omitempty"`
	WorkerID        string   `json:"worker_id,omitempty"`
	LeaseUntil      int64    `json:"lease_until,omitempty"`
	ClaimToken      int64    `json:"claim_token,omitempty"`
	GatewaySequence int64    `json:"gateway_sequence,omitempty"`
	Error           string   `json:"error,omitempty"`
}

type legacyEvent struct {
	Version  int64    `json:"version"`
	Type     string   `json:"type"`
	ID       string   `json:"id"`
	Revision int64    `json:"revision"`
	Policy   string   `json:"policy"`
	Regions  []string `json:"regions"`
}

func DecodeEvent(line []byte, allowLegacy bool) (Event, error) {
	var probe struct {
		Version int64  `json:"version"`
		Type    string `json:"type"`
	}
	if err := json.Unmarshal(line, &probe); err != nil {
		return Event{}, err
	}
	if probe.Version == 1 {
		if !allowLegacy {
			return Event{}, ErrUnsupportedJournalVersion
		}
		var old legacyEvent
		if err := json.Unmarshal(line, &old); err != nil {
			return Event{}, err
		}
		return Event{
			Version:    2,
			Type:       old.Type,
			RolloutID:  old.ID,
			Generation: old.Revision,
			Policy:     old.Policy,
			Regions:    old.Regions,
		}, nil
	}
	var event Event
	if err := json.Unmarshal(line, &event); err != nil {
		return Event{}, err
	}
	if event.Version != 2 {
		return Event{}, ErrUnsupportedJournalVersion
	}
	return event, nil
}
