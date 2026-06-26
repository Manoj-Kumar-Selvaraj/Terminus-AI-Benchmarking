package controller

import (
	"cardrollout/internal/model"
	"cardrollout/internal/store"
	"sort"
)

type StatusDocument struct {
	SchemaVersion    int64            `json:"schema_version"`
	Rollouts         []StatusRollout  `json:"rollouts"`
	ActiveGeneration map[string]int64 `json:"active_generation"`
}

type StatusRollout struct {
	ID           string           `json:"id"`
	Generation   int64            `json:"generation"`
	PolicySHA256 string           `json:"policy_sha256"`
	Deliveries   []model.Delivery `json:"deliveries"`
}

func Status(st *store.Store) (StatusDocument, error) {
	state, err := st.Read()
	if err != nil {
		return StatusDocument{}, err
	}
	doc := StatusDocument{
		SchemaVersion:    2,
		Rollouts:         []StatusRollout{},
		ActiveGeneration: map[string]int64{},
	}
	for region, generation := range state.ActiveGeneration {
		doc.ActiveGeneration[region] = generation
	}
	for _, rollout := range state.SortedRollouts() {
		item := StatusRollout{ID: rollout.ID, Generation: rollout.Generation, PolicySHA256: rollout.PolicySHA256}
		regions := make([]string, 0, len(rollout.Deliveries))
		for region := range rollout.Deliveries {
			regions = append(regions, region)
		}
		sort.Strings(regions)
		for _, region := range regions {
			item.Deliveries = append(item.Deliveries, *rollout.Deliveries[region])
		}
		doc.Rollouts = append(doc.Rollouts, item)
	}
	return doc, nil
}
