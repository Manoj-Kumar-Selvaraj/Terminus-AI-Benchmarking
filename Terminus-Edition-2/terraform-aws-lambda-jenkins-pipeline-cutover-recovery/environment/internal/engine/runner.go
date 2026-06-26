package engine

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"strings"

	"jenkins-lambda-cutover/internal/cutover"
	"jenkins-lambda-cutover/internal/fanout"
	"jenkins-lambda-cutover/internal/model"
	"jenkins-lambda-cutover/internal/simclient"
	"jenkins-lambda-cutover/internal/store"
)

func Deploy(infraDir string, deployment model.Deployment) error {
	var response struct {
		OK      bool   `json:"ok"`
		Message string `json:"message"`
	}
	if err := simclient.Call("deploy", deployment, &response); err != nil {
		return err
	}
	if !response.OK {
		return errors.New(response.Message)
	}
	if err := store.SaveDeployment(deployment); err != nil {
		return err
	}
	_, err := cutover.Ensure(deployment.Generation)
	return err
}
func NewCheckpoint(req model.Request, generation int, epoch int64) model.Checkpoint {
	items := []model.ItemState{}
	for _, it := range req.Items {
		items = append(items, model.ItemState{ID: it.ID, Status: "PENDING"})
	}
	return model.Checkpoint{ExecutionID: req.ExecutionID, BatchID: req.BatchID, Owner: req.Owner, ProtocolVersion: req.ProtocolVersion, ArtifactDigest: req.ArtifactDigest, Generation: generation, Epoch: epoch, Status: "RUNNING", Metadata: req.Metadata, Items: items, CompletedEffects: map[string]string{}, Attempts: map[string]int{}, UpdatedAt: simclient.Now()}
}
func Run(req model.Request) (model.Checkpoint, error) {
	c, err := cutover.Load()
	if err != nil {
		return model.Checkpoint{}, err
	}
	cp := NewCheckpoint(req, c.ActiveGeneration, c.Epoch)
	return Resume(req, cp)
}
func Resume(req model.Request, cp model.Checkpoint) (model.Checkpoint, error) {
	// Jenkins restart semantics were copied incorrectly: every resume starts at intake.
	cp.NextStage = 0
	itemByID := map[string]model.Item{}
	for _, it := range req.Items {
		itemByID[it.ID] = it
	}
	for index, stage := range model.RequiredStages {
		if isItemStage(stage) {
			for x := range cp.Items {
				st := &cp.Items[x]
				it := itemByID[st.ID]
				meta := copyMap(req.Metadata)
				meta["artifact_digest"] = req.ArtifactDigest
				if it.Poison {
					meta["poison"] = "true"
				}
				key := fmt.Sprintf("%s/%s/%s/%d", req.ExecutionID, stage, it.ID, st.Attempts+1)
				inv := model.Invocation{Stage: stage, ExecutionID: req.ExecutionID, BatchID: req.BatchID, ItemID: it.ID, Generation: cp.Generation, Epoch: cp.Epoch, Owner: req.Owner, IdempotencyKey: key, Metadata: meta}
				res, attempts, err := fanout.Invoke(inv)
				st.Attempts += attempts
				cp.Attempts[stage+"/"+it.ID] += attempts
				if err != nil {
					return cp, err
				}
				if !res.OK {
					cp.Status = "FAILED"
					cp.LastError = res.Message
					_ = store.SaveCheckpoint(cp)
					return cp, errors.New(res.Message)
				}
				st.LastStage = stage
				if stage == "write_ledger" {
					st.Status = "COMPLETED"
				} else {
					st.Status = "ACTIVE"
				}
			}
		} else {
			key := fmt.Sprintf("%s/%s/%d", req.ExecutionID, stage, cp.Attempts[stage]+1)
			inv := model.Invocation{Stage: stage, ExecutionID: req.ExecutionID, BatchID: req.BatchID, Generation: cp.Generation, Epoch: cp.Epoch, Owner: req.Owner, IdempotencyKey: key, Metadata: map[string]string{"artifact_digest": req.ArtifactDigest}}
			res, attempts, err := fanout.Invoke(inv)
			cp.Attempts[stage] += attempts
			if err != nil {
				return cp, err
			}
			if !res.OK {
				cp.Status = "FAILED"
				cp.LastError = res.Message
				_ = store.SaveCheckpoint(cp)
				return cp, errors.New(res.Message)
			}
		}
		cp.NextStage = index + 1
		cp.UpdatedAt = simclient.Now()
	}
	cp.Status = "SUCCEEDED"
	cp.UpdatedAt = simclient.Now()
	return cp, store.SaveCheckpoint(cp)
}
func isItemStage(stage string) bool {
	switch stage {
	case "fetch_inputs", "validate_inputs", "transform_records", "precheck_ledger", "write_ledger":
		return true
	}
	return false
}
func copyMap(in map[string]string) map[string]string {
	out := map[string]string{}
	for k, v := range in {
		out[k] = v
	}
	return out
}
func LoadRequest(path string) (model.Request, error) {
	var r model.Request
	b, err := os.ReadFile(path)
	if err != nil {
		return r, err
	}
	err = json.Unmarshal(b, &r)
	return r, err
}

var _ = strings.Builder{}
