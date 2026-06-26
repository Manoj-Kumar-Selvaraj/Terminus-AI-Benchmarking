package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
)

func PolicyDigest(policy string) string {
	sum := sha256.Sum256([]byte(policy))
	return hex.EncodeToString(sum[:])
}

func StableCommandID(rolloutID, region string) string {
	sum := sha256.Sum256([]byte("card-policy\x00" + rolloutID + "\x00" + region))
	return "cmd-" + hex.EncodeToString(sum[:12])
}

func ApplyEvent(state *State, event Event) error {
	switch event.Type {
	case "queued":
		if event.RolloutID == "" || event.Generation <= 0 || len(event.Regions) == 0 {
			return errors.New("invalid queued event")
		}
		if event.PolicySHA256 == "" {
			event.PolicySHA256 = PolicyDigest(event.Policy)
		}
		if existing, ok := state.Rollouts[event.RolloutID]; ok {
			if existing.Generation != event.Generation || existing.PolicySHA256 != event.PolicySHA256 {
				return fmt.Errorf("rollout %s conflicts with existing definition", event.RolloutID)
			}
			return nil
		}
		rollout := &Rollout{
			ID:           event.RolloutID,
			Generation:   event.Generation,
			Policy:       event.Policy,
			PolicySHA256: event.PolicySHA256,
			Deliveries:   map[string]*Delivery{},
		}
		for _, region := range event.Regions {
			if region == "" {
				return errors.New("empty region")
			}
			rollout.Deliveries[region] = &Delivery{
				Region:    region,
				CommandID: StableCommandID(event.RolloutID, region),
				Status:    StatusPending,
			}
		}
		state.Rollouts[event.RolloutID] = rollout
	case "claimed":
		d, err := findDelivery(state, event.RolloutID, event.Region)
		if err != nil {
			return err
		}
		if event.ClaimToken < d.ClaimToken {
			return nil
		}
		d.CommandID = event.CommandID
		d.Status = StatusClaimed
		d.LeaseOwner = event.WorkerID
		d.LeaseUntil = event.LeaseUntil
		d.ClaimToken = event.ClaimToken
		d.LastError = ""
	case "acked":
		d, err := findDelivery(state, event.RolloutID, event.Region)
		if err != nil {
			return err
		}
		if event.ClaimToken != 0 && event.ClaimToken != d.ClaimToken {
			return nil
		}
		d.Status = StatusAcked
		d.LeaseOwner = ""
		d.LeaseUntil = 0
		d.GatewaySequence = event.GatewaySequence
		d.LastError = ""
		rollout := state.Rollouts[event.RolloutID]
		if rollout.Generation > state.ActiveGeneration[event.Region] {
			state.ActiveGeneration[event.Region] = rollout.Generation
		}
	case "superseded":
		d, err := findDelivery(state, event.RolloutID, event.Region)
		if err != nil {
			return err
		}
		if event.ClaimToken != 0 && event.ClaimToken != d.ClaimToken {
			return nil
		}
		d.Status = StatusSuperseded
		d.LeaseOwner = ""
		d.LeaseUntil = 0
		d.LastError = event.Error
		if event.Generation > state.ActiveGeneration[event.Region] {
			state.ActiveGeneration[event.Region] = event.Generation
		}
	case "failed":
		d, err := findDelivery(state, event.RolloutID, event.Region)
		if err != nil {
			return err
		}
		if event.ClaimToken != 0 && event.ClaimToken != d.ClaimToken {
			return nil
		}
		d.Status = StatusFailed
		d.LeaseOwner = ""
		d.LeaseUntil = 0
		d.LastError = event.Error
	default:
		return fmt.Errorf("unknown event type %q", event.Type)
	}
	return nil
}

func findDelivery(state *State, rolloutID, region string) (*Delivery, error) {
	rollout, ok := state.Rollouts[rolloutID]
	if !ok {
		return nil, fmt.Errorf("unknown rollout %s", rolloutID)
	}
	delivery, ok := rollout.Deliveries[region]
	if !ok {
		return nil, fmt.Errorf("unknown region %s for rollout %s", region, rolloutID)
	}
	return delivery, nil
}
