package iac

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"

	"jenkins-lambda-cutover/internal/model"
)

func Load(infraDir string) (model.Deployment, error) {
	var sf model.StageFile
	data, err := os.ReadFile(filepath.Join(infraDir, "stages.json"))
	if err != nil {
		return model.Deployment{}, err
	}
	if err := json.Unmarshal(data, &sf); err != nil {
		return model.Deployment{}, err
	}
	sort.Slice(sf.Stages, func(i, j int) bool { return sf.Stages[i].Name < sf.Stages[j].Name })
	for i := range sf.Stages {
		sf.Stages[i].FunctionName = "settlement-pipeline"
		sf.Stages[i].Alias = "$LATEST"
	}
	mainTF, _ := os.ReadFile(filepath.Join(infraDir, "main.tf"))
	h := sha256.Sum256(append(data, mainTF...))
	return model.Deployment{Generation: 1, Alias: "$LATEST", Module: "local/lambda", Version: "0.0.0", Digest: hex.EncodeToString(h[:]), Stages: sf.Stages}, nil
}
func StableStageNames(d model.Deployment) []string {
	out := []string{}
	for _, s := range d.Stages {
		out = append(out, s.Name)
	}
	return out
}
func SortedStageNames(d model.Deployment) []string {
	out := StableStageNames(d)
	sort.Strings(out)
	return out
}
