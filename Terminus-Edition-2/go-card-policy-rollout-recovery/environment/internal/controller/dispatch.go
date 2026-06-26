package controller

import (
	"cardrollout/internal/gateway"
	"cardrollout/internal/model"
	"cardrollout/internal/store"
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"sort"
	"time"
)

const LeaseSeconds int64 = 30

type DispatchOptions struct {
	WorkerID  string
	Workers   int
	NowUnix   int64
	Failpoint string
	Gateways  map[string]string
}

type simpleDelivery struct {
	RolloutID    string
	Region       string
	Generation   int64
	Policy       string
	PolicySHA256 string
	CommandID    string
	GatewayURL   string
}

func Dispatch(ctx context.Context, st *store.Store, opts DispatchOptions) error {
	if opts.WorkerID == "" {
		return errors.New("worker id is required")
	}
	client := gateway.NewClient()
	for {
		item, err := nextSimple(st, opts.Gateways)
		if err != nil {
			return err
		}
		if item == nil {
			return nil
		}
		resp, code, callErr := client.Apply(ctx, item.GatewayURL, gateway.ApplyRequest{
			CommandID: item.CommandID, RolloutID: item.RolloutID, Generation: item.Generation,
			PolicySHA256: item.PolicySHA256, Policy: item.Policy,
		})
		if callErr == nil && code >= 200 && code < 300 && matchesFailpoint(opts.Failpoint, "after-apply", item.Region) {
			os.Exit(86)
		}
		if err := completeSimple(st, item, resp, code, callErr); err != nil {
			return err
		}
	}
}

func nextSimple(st *store.Store, gateways map[string]string) (*simpleDelivery, error) {
	state, err := st.Read()
	if err != nil {
		return nil, err
	}
	type candidate struct {
		rollout *model.Rollout
		region  string
	}
	var candidates []candidate
	for _, rollout := range state.Rollouts {
		for region, delivery := range rollout.Deliveries {
			if delivery.Status == model.StatusPending {
				if _, ok := gateways[region]; ok {
					candidates = append(candidates, candidate{rollout: rollout, region: region})
				}
			}
		}
	}
	if len(candidates) == 0 {
		return nil, nil
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].rollout.Generation != candidates[j].rollout.Generation {
			return candidates[i].rollout.Generation > candidates[j].rollout.Generation
		}
		if candidates[i].rollout.ID != candidates[j].rollout.ID {
			return candidates[i].rollout.ID < candidates[j].rollout.ID
		}
		return candidates[i].region < candidates[j].region
	})
	c := candidates[0]
	delivery := c.rollout.Deliveries[c.region]
	_ = delivery
	commandID := fmt.Sprintf("attempt-%d-%d", os.Getpid(), time.Now().UnixNano())
	return &simpleDelivery{
		RolloutID: c.rollout.ID, Region: c.region, Generation: c.rollout.Generation,
		Policy: c.rollout.Policy, PolicySHA256: c.rollout.PolicySHA256,
		CommandID: commandID, GatewayURL: gateways[c.region],
	}, nil
}

func completeSimple(st *store.Store, item *simpleDelivery, resp gateway.ApplyResponse, code int, callErr error) error {
	return st.WithLock(func(state *model.State) error {
		event := model.Event{Version: 2, RolloutID: item.RolloutID, Region: item.Region, CommandID: item.CommandID}
		if callErr != nil {
			event.Type = "failed"
			event.Error = callErr.Error()
			return st.Append(event)
		}
		if code >= 200 && code < 300 && (resp.Status == "applied" || resp.Status == "already-active") {
			event.Type = "acked"
			event.GatewaySequence = resp.Sequence
			return st.Append(event)
		}
		if code == http.StatusConflict && resp.Status == "stale" {
			event.Type = "failed"
			event.Error = "stale response not reconciled"
			return st.Append(event)
		}
		event.Type = "failed"
		event.Error = fmt.Sprintf("gateway response status=%s http=%d", resp.Status, code)
		return st.Append(event)
	})
}

func matchesFailpoint(value, phase, region string) bool {
	return value == phase || value == phase+":"+region
}
