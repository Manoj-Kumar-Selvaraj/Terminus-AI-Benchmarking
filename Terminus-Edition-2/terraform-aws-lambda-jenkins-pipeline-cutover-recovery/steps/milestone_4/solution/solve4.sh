#!/usr/bin/env bash
set -Eeuo pipefail

cd /app
mkdir -p "$(dirname /app/infra/main.tf)"
cat > /app/infra/main.tf <<'__M4_INFRA_MAIN_TF__'
terraform {
  required_version = ">= 1.6.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  stage_document = jsondecode(file("${path.module}/stages.json"))
  stages = {
    for stage in local.stage_document.stages : stage.name => merge(stage, {
      function_name = stage.function_name
    })
  }
}

module "pipeline_stage" {
  for_each = local.stages

  source  = "terraform-aws-modules/lambda/aws"
  version = "7.20.1"

  function_name = each.value.function_name
  description   = "Settlement cutover stage ${each.key}"
  runtime       = "provided.al2023"
  handler       = "bootstrap"
  architectures = ["arm64"]

  create_package         = false
  local_existing_package = "${path.module}/../dist/${each.key}.zip"
  source_code_hash       = each.value.package_hash
  publish                = true

  timeout                       = each.value.timeout_seconds
  memory_size                   = each.value.memory_mb
  reserved_concurrent_executions = each.value.reserved_concurrency

  create_current_version_allowed_triggers = false
  allowed_triggers = {
    states = {
      principal  = "states.amazonaws.com"
      source_arn = aws_sfn_state_machine.settlement_pipeline.arn
    }
  }

  environment_variables = {
    PIPELINE_STAGE       = each.key
    PIPELINE_GENERATION  = tostring(jsondecode(file("${path.module}/deployment.json")).generation)
    CHECKPOINT_TABLE     = aws_dynamodb_table.pipeline_checkpoint.name
    EFFECT_LEDGER_TABLE  = aws_dynamodb_table.effect_ledger.name
  }

  attach_policy_statements = true
  policy_statements = {
    stage_permissions = {
      effect    = "Allow"
      actions   = each.value.permissions
      resources = local.stage_resources[each.key]
    }
  }
}

resource "aws_lambda_alias" "live" {
  for_each = module.pipeline_stage

  name             = "live"
  function_name    = each.value.lambda_function_name
  function_version = each.value.lambda_function_version
}
__M4_INFRA_MAIN_TF__

mkdir -p "$(dirname /app/infra/stages.json)"
cat > /app/infra/stages.json <<'__M4_INFRA_STAGES_JSON__'
{
  "stages": [
    {
      "name": "intake",
      "function_name": "settlement-pipeline-intake",
      "timeout_seconds": 30,
      "reserved_concurrency": 4,
      "memory_mb": 256,
      "permissions": [
        "logs:PutLogEvents",
        "xray:PutTraceSegments"
      ],
      "alias": "live",
      "package_hash": "c55d3f74559f13257279d4ef78e04e89e22c53a52d558c782983bc0f88238329"
    },
    {
      "name": "verify_manifest",
      "function_name": "settlement-pipeline-verify_manifest",
      "timeout_seconds": 45,
      "reserved_concurrency": 4,
      "memory_mb": 256,
      "permissions": [
        "s3:GetObject",
        "kms:Verify",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "47d92f6af8e1474d9d2b38c88a1d6b908f66f3c12432e0829eda19cb8c33cb69"
    },
    {
      "name": "acquire_lock",
      "function_name": "settlement-pipeline-acquire_lock",
      "timeout_seconds": 20,
      "reserved_concurrency": 8,
      "memory_mb": 128,
      "permissions": [
        "dynamodb:PutItem",
        "dynamodb:GetItem",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "0168ba5af0d61c4b9f6d905b9af7bc13b1ab50848ae595a39c1e0dec200dc0e2"
    },
    {
      "name": "fetch_inputs",
      "function_name": "settlement-pipeline-fetch_inputs",
      "timeout_seconds": 120,
      "reserved_concurrency": 12,
      "memory_mb": 512,
      "permissions": [
        "s3:GetObject",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "8a9816c046492be65c074691326e9f825934b316fb2b4ed30a8761d1e8075af5"
    },
    {
      "name": "validate_inputs",
      "function_name": "settlement-pipeline-validate_inputs",
      "timeout_seconds": 90,
      "reserved_concurrency": 12,
      "memory_mb": 512,
      "permissions": [
        "s3:GetObject",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "4f55a3c6caa194e63460fd2e9d3336da55186a58d0837956f100daaebf81b762"
    },
    {
      "name": "transform_records",
      "function_name": "settlement-pipeline-transform_records",
      "timeout_seconds": 180,
      "reserved_concurrency": 8,
      "memory_mb": 1024,
      "permissions": [
        "s3:GetObject",
        "s3:PutObject",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "5e57e19752d4be73c50e5a38ba5c8a42deeecd02e482b54c1fe73a2fb0dbd54a"
    },
    {
      "name": "precheck_ledger",
      "function_name": "settlement-pipeline-precheck_ledger",
      "timeout_seconds": 60,
      "reserved_concurrency": 6,
      "memory_mb": 256,
      "permissions": [
        "dynamodb:GetItem",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "3f5fec5dbb507979b0038ae3badb9677fb1fb6c32642d8b5dd7cc390777d9964"
    },
    {
      "name": "write_ledger",
      "function_name": "settlement-pipeline-write_ledger",
      "timeout_seconds": 120,
      "reserved_concurrency": 6,
      "memory_mb": 512,
      "permissions": [
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "76cc584cc78e1bcc102a94af4cb276758fc6be427fa3f8a105e74ca688060493"
    },
    {
      "name": "build_report",
      "function_name": "settlement-pipeline-build_report",
      "timeout_seconds": 90,
      "reserved_concurrency": 4,
      "memory_mb": 512,
      "permissions": [
        "s3:PutObject",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "adce74901ae66ad1f2e6f7fd345f638b279336b7c059bdf69346dfce78ebd46d"
    },
    {
      "name": "notify_partner",
      "function_name": "settlement-pipeline-notify_partner",
      "timeout_seconds": 30,
      "reserved_concurrency": 4,
      "memory_mb": 256,
      "permissions": [
        "events:PutEvents",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "354575b439c97cc7c34b99c2a74557ea418f37d1084eaa39e2d3856116fb8e97"
    },
    {
      "name": "archive_batch",
      "function_name": "settlement-pipeline-archive_batch",
      "timeout_seconds": 60,
      "reserved_concurrency": 4,
      "memory_mb": 256,
      "permissions": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "45e6a4b9149d2c7b3e5f613de242c7d99b3cdd22754ccc90bf80006d07d457b8"
    },
    {
      "name": "release_lock",
      "function_name": "settlement-pipeline-release_lock",
      "timeout_seconds": 20,
      "reserved_concurrency": 8,
      "memory_mb": 128,
      "permissions": [
        "dynamodb:DeleteItem",
        "logs:PutLogEvents"
      ],
      "alias": "live",
      "package_hash": "c52998f6ee6b8de4f3879d861673738579c438bbf57eae335e9bcde956da9a9d"
    }
  ]
}
__M4_INFRA_STAGES_JSON__

mkdir -p "$(dirname /app/internal/iac/config.go)"
cat > /app/internal/iac/config.go <<'__M4_INTERNAL_IAC_CONFIG_GO__'
package iac

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"jenkins-lambda-cutover/internal/model"
)

const moduleSource = "terraform-aws-modules/lambda/aws"
const moduleVersion = "7.20.1"

type stageContract struct {
	TimeoutSeconds      int
	MemoryMB             int
	ReservedConcurrency int
	Permissions          []string
}

var expectedStageContracts = map[string]stageContract{
	"intake":            {30, 256, 4, []string{"logs:PutLogEvents", "xray:PutTraceSegments"}},
	"verify_manifest":   {45, 256, 4, []string{"s3:GetObject", "kms:Verify", "logs:PutLogEvents"}},
	"acquire_lock":      {20, 128, 8, []string{"dynamodb:PutItem", "dynamodb:GetItem", "logs:PutLogEvents"}},
	"fetch_inputs":      {120, 512, 12, []string{"s3:GetObject", "logs:PutLogEvents"}},
	"validate_inputs":   {90, 512, 12, []string{"s3:GetObject", "logs:PutLogEvents"}},
	"transform_records": {180, 1024, 8, []string{"s3:GetObject", "s3:PutObject", "logs:PutLogEvents"}},
	"precheck_ledger":   {60, 256, 6, []string{"dynamodb:GetItem", "logs:PutLogEvents"}},
	"write_ledger":      {120, 512, 6, []string{"dynamodb:PutItem", "dynamodb:UpdateItem", "logs:PutLogEvents"}},
	"build_report":      {90, 512, 4, []string{"s3:PutObject", "logs:PutLogEvents"}},
	"notify_partner":    {30, 256, 4, []string{"events:PutEvents", "logs:PutLogEvents"}},
	"archive_batch":     {60, 256, 4, []string{"s3:GetObject", "s3:PutObject", "s3:DeleteObject", "logs:PutLogEvents"}},
	"release_lock":      {20, 128, 8, []string{"dynamodb:DeleteItem", "logs:PutLogEvents"}},
}

func samePermissionSet(actual, expected []string) bool {
	if len(actual) != len(expected) {
		return false
	}
	counts := map[string]int{}
	for _, permission := range expected {
		counts[permission]++
	}
	for _, permission := range actual {
		counts[permission]--
		if counts[permission] < 0 {
			return false
		}
	}
	for _, count := range counts {
		if count != 0 {
			return false
		}
	}
	return true
}

func Load(infraDir string) (model.Deployment, error) {
	var sf model.StageFile
	data, err := os.ReadFile(filepath.Join(infraDir, "stages.json"))
	if err != nil {
		return model.Deployment{}, err
	}
	if err := json.Unmarshal(data, &sf); err != nil {
		return model.Deployment{}, fmt.Errorf("decode stages: %w", err)
	}
	if len(sf.Stages) != len(model.RequiredStages) {
		return model.Deployment{}, fmt.Errorf("expected %d stages, got %d", len(model.RequiredStages), len(sf.Stages))
	}
	seen := map[string]bool{}
	functionNames := map[string]bool{}
	packageHashes := map[string]bool{}
	for i, stage := range sf.Stages {
		if stage.Name != model.RequiredStages[i] {
			return model.Deployment{}, fmt.Errorf("stage %d = %q, want %q", i, stage.Name, model.RequiredStages[i])
		}
		if seen[stage.Name] {
			return model.Deployment{}, fmt.Errorf("duplicate stage %q", stage.Name)
		}
		seen[stage.Name] = true
		if stage.FunctionName != "settlement-pipeline-"+stage.Name {
			return model.Deployment{}, fmt.Errorf("stage %s function name mismatch", stage.Name)
		}
		if functionNames[stage.FunctionName] {
			return model.Deployment{}, fmt.Errorf("shared function identity %q", stage.FunctionName)
		}
		functionNames[stage.FunctionName] = true
		contract, ok := expectedStageContracts[stage.Name]
		if !ok {
			return model.Deployment{}, fmt.Errorf("stage %s has no documented contract", stage.Name)
		}
		if stage.TimeoutSeconds != contract.TimeoutSeconds ||
			stage.MemoryMB != contract.MemoryMB ||
			stage.ReservedConcurrency != contract.ReservedConcurrency {
			return model.Deployment{}, fmt.Errorf("stage %s resource contract mismatch", stage.Name)
		}
		if !samePermissionSet(stage.Permissions, contract.Permissions) {
			return model.Deployment{}, fmt.Errorf("stage %s permission contract mismatch", stage.Name)
		}
		if stage.Alias != "live" {
			return model.Deployment{}, fmt.Errorf("stage %s must use live alias", stage.Name)
		}
		if len(stage.PackageHash) < 16 {
			return model.Deployment{}, fmt.Errorf("stage %s package hash missing", stage.Name)
		}
		if packageHashes[stage.PackageHash] {
			return model.Deployment{}, fmt.Errorf("shared package hash %q", stage.PackageHash)
		}
		packageHashes[stage.PackageHash] = true
		for _, p := range stage.Permissions {
			if p == "*" || strings.HasSuffix(p, ":*") {
				return model.Deployment{}, fmt.Errorf("stage %s has wildcard permission", stage.Name)
			}
		}
	}
	mainTF, err := os.ReadFile(filepath.Join(infraDir, "main.tf"))
	if err != nil {
		return model.Deployment{}, err
	}
	tf := strings.Join(strings.Fields(string(mainTF)), " ")
	required := []string{
		`source = "terraform-aws-modules/lambda/aws"`, `version = "7.20.1"`,
		`for_each = local.stages`, `runtime = "provided.al2023"`, `handler = "bootstrap"`,
		`publish = true`, `source_code_hash = each.value.package_hash`,
		`create_current_version_allowed_triggers = false`, `function_name = each.value.function_name`,
		`principal = "states.amazonaws.com"`,
	}
	for _, token := range required {
		token = strings.Join(strings.Fields(token), " ")
		if !strings.Contains(tf, token) {
			return model.Deployment{}, fmt.Errorf("Terraform module contract missing %s", token)
		}
	}
	if strings.Contains(tf, `principal = "*"`) {
		return model.Deployment{}, fmt.Errorf("wildcard invoke principal is forbidden")
	}
	var deploy struct {
		Generation int    `json:"generation"`
		Alias      string `json:"alias"`
	}
	b, err := os.ReadFile(filepath.Join(infraDir, "deployment.json"))
	if err != nil {
		return model.Deployment{}, err
	}
	if err := json.Unmarshal(b, &deploy); err != nil {
		return model.Deployment{}, err
	}
	if deploy.Generation < 1 || deploy.Alias != "live" {
		return model.Deployment{}, fmt.Errorf("invalid deployment generation")
	}
	canonical, _ := json.Marshal(sf.Stages)
	h := sha256.Sum256(append(canonical, mainTF...))
	return model.Deployment{Generation: deploy.Generation, Alias: deploy.Alias, Module: moduleSource, Version: moduleVersion, Digest: hex.EncodeToString(h[:]), Stages: sf.Stages}, nil
}

func StableStageNames(d model.Deployment) []string {
	out := make([]string, 0, len(d.Stages))
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
__M4_INTERNAL_IAC_CONFIG_GO__

mkdir -p "$(dirname /app/internal/fanout/fanout.go)"
cat > /app/internal/fanout/fanout.go <<'__M4_INTERNAL_FANOUT_FANOUT_GO__'
package fanout

import (
	"fmt"

	"jenkins-lambda-cutover/internal/model"
	"jenkins-lambda-cutover/internal/simclient"
)

const MaxAttempts = 3

func Invoke(inv model.Invocation) (model.InvocationResult, int, error) {
	var last model.InvocationResult
	for attempt := 1; attempt <= MaxAttempts; attempt++ {
		inv.Attempt = attempt
		if err := simclient.Call("invoke", inv, &last); err != nil {
			return last, attempt, err
		}
		if last.OK || last.Duplicate {
			return last, attempt, nil
		}
		if last.Class != "transient" {
			if last.Class == "permanent" && inv.Stage == "validate_inputs" &&
				inv.Metadata["poison"] == "true" && attempt < MaxAttempts {
				continue
			}
			return last, attempt, nil
		}
	}
	return last, MaxAttempts, fmt.Errorf("retry budget exhausted: %s", last.Message)
}

func SendDLQ(batchID, itemID string) error {
	return simclient.Call("dlq", map[string]string{"batch_id": batchID, "item_id": itemID}, nil)
}
__M4_INTERNAL_FANOUT_FANOUT_GO__

mkdir -p "$(dirname /app/internal/engine/runner.go)"
cat > /app/internal/engine/runner.go <<'__M4_INTERNAL_ENGINE_RUNNER_GO__'
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
		Class   string `json:"class"`
		Message string `json:"message"`
	}
	for attempt := 0; attempt < 3; attempt++ {
		if err := simclient.Call("deploy", deployment, &response); err != nil {
			return err
		}
		if response.OK {
			break
		}
		if response.Class != "transient" {
			return errors.New(response.Message)
		}
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
	items := make([]model.ItemState, 0, len(req.Items))
	for _, it := range req.Items {
		items = append(items, model.ItemState{ID: it.ID, Status: "PENDING"})
	}
	return model.Checkpoint{ExecutionID: req.ExecutionID, BatchID: req.BatchID, Owner: req.Owner, ProtocolVersion: req.ProtocolVersion, ArtifactDigest: req.ArtifactDigest, Generation: generation, Epoch: epoch, Status: "RUNNING", Metadata: req.Metadata, Items: items, CompletedEffects: map[string]string{}, Attempts: map[string]int{}, UpdatedAt: simclient.Now()}
}

func Run(req model.Request) (model.Checkpoint, error) {
	if existing, err := store.LoadCheckpoint(req.ExecutionID); err == nil {
		if existing.BatchID != req.BatchID || existing.Owner != req.Owner || existing.ArtifactDigest != req.ArtifactDigest {
			return existing, fmt.Errorf("execution id reused with conflicting payload")
		}
		return Resume(req, existing)
	}
	c, err := cutover.Load()
	if err != nil {
		return model.Checkpoint{}, err
	}
	cp := NewCheckpoint(req, c.ActiveGeneration, c.Epoch)
	if err := store.SaveCheckpoint(cp); err != nil {
		return cp, err
	}
	return Resume(req, cp)
}

func Resume(req model.Request, cp model.Checkpoint) (model.Checkpoint, error) {
	if cp.Owner != req.Owner {
		return cp, fmt.Errorf("owner mismatch")
	}
	itemByID := map[string]model.Item{}
	for _, it := range req.Items {
		itemByID[it.ID] = it
	}
	for stageIndex := cp.NextStage; stageIndex < len(model.RequiredStages); stageIndex++ {
		stage := model.RequiredStages[stageIndex]
		if isItemStage(stage) {
			for idx := range cp.Items {
				state := &cp.Items[idx]
				if state.Status == "DLQ" {
					continue
				}
				it := itemByID[state.ID]
				meta := copyMap(req.Metadata)
				meta["artifact_digest"] = req.ArtifactDigest
				if it.Poison {
					meta["poison"] = "true"
				}
				inv := model.Invocation{Stage: stage, ExecutionID: req.ExecutionID, BatchID: req.BatchID, ItemID: it.ID, Generation: cp.Generation, Epoch: cp.Epoch, Owner: req.Owner, IdempotencyKey: operationID(req.ExecutionID, stage, it.ID), Metadata: meta}
				result, attempts, callErr := invokeRecorded(inv)
				cp.Attempts[stage+"/"+it.ID] += attempts
				state.Attempts += attempts
				state.LastStage = stage
				if callErr != nil {
					cp.Status = "RETRY_PENDING"
					cp.LastError = callErr.Error()
					cp.UpdatedAt = simclient.Now()
					_ = store.SaveCheckpoint(cp)
					return cp, callErr
				}
				if !result.OK && !result.Duplicate {
					if result.Class == "permanent" && stage == "validate_inputs" {
						state.Status = "DLQ"
						state.Error = result.Message
						if err := fanout.SendDLQ(req.BatchID, it.ID); err != nil {
							return cp, err
						}
						continue
					}
					cp.Status = "FAILED"
					cp.LastError = result.Message
					cp.UpdatedAt = simclient.Now()
					_ = store.SaveCheckpoint(cp)
					return cp, errors.New(result.Message)
				}
				state.Status = "ACTIVE"
				if stage == "write_ledger" {
					state.Status = "COMPLETED"
				}
			}
		} else {
			inv := model.Invocation{Stage: stage, ExecutionID: req.ExecutionID, BatchID: req.BatchID, Generation: cp.Generation, Epoch: cp.Epoch, Owner: req.Owner, IdempotencyKey: operationID(req.ExecutionID, stage, ""), Metadata: map[string]string{"artifact_digest": req.ArtifactDigest}}
			result, attempts, callErr := invokeRecorded(inv)
			cp.Attempts[stage] += attempts
			if callErr != nil {
				cp.Status = "RETRY_PENDING"
				cp.LastError = callErr.Error()
				cp.UpdatedAt = simclient.Now()
				_ = store.SaveCheckpoint(cp)
				return cp, callErr
			}
			if !result.OK && !result.Duplicate {
				cp.Status = "FAILED"
				cp.LastError = result.Message
				cp.UpdatedAt = simclient.Now()
				_ = store.SaveCheckpoint(cp)
				return cp, errors.New(result.Message)
			}
		}
		cp.NextStage = stageIndex + 1
		cp.UpdatedAt = simclient.Now()
		cp.LastError = ""
		if err := store.SaveCheckpoint(cp); err != nil {
			return cp, err
		}
	}
	cp.Status = "SUCCEEDED"
	for _, it := range cp.Items {
		if it.Status == "DLQ" {
			cp.Status = "PARTIAL"
		}
	}
	cp.UpdatedAt = simclient.Now()
	return cp, store.SaveCheckpoint(cp)
}

func invokeRecorded(inv model.Invocation) (model.InvocationResult, int, error) {
	op := inv.IdempotencyKey
	_ = store.AppendJournal(model.JournalRecord{OperationID: op, ExecutionID: inv.ExecutionID, Stage: inv.Stage, ItemID: inv.ItemID, Generation: inv.Generation, Epoch: inv.Epoch, Status: "STARTED", At: simclient.Now()})
	result, attempts, err := fanout.Invoke(inv)
	status := "FAILED"
	if err == nil && (result.OK || result.Duplicate) {
		status = "COMMITTED"
	}
	_ = store.AppendJournal(model.JournalRecord{OperationID: op, ExecutionID: inv.ExecutionID, Stage: inv.Stage, ItemID: inv.ItemID, Generation: inv.Generation, Epoch: inv.Epoch, Status: status, At: simclient.Now()})
	return result, attempts, err
}
func isItemStage(stage string) bool {
	switch stage {
	case "fetch_inputs", "validate_inputs", "transform_records", "precheck_ledger", "write_ledger":
		return true
	}
	return false
}
func operationID(exec, stage, item string) string {
	parts := []string{exec, stage}
	if item != "" {
		parts = append(parts, item)
	}
	return strings.Join(parts, "/")
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
	if err := jsonUnmarshal(b, &r); err != nil {
		return r, err
	}
	return r, nil
}

var jsonUnmarshal = func(data []byte, v any) error { return json.Unmarshal(data, v) }
__M4_INTERNAL_ENGINE_RUNNER_GO__

mkdir -p "$(dirname /app/internal/cutover/manager.go)"
cat > /app/internal/cutover/manager.go <<'__M4_INTERNAL_CUTOVER_MANAGER_GO__'
package cutover

import (
	"errors"
	"os"

	"jenkins-lambda-cutover/internal/model"
	"jenkins-lambda-cutover/internal/simclient"
	"jenkins-lambda-cutover/internal/store"
)

type controlResponse struct {
	OK         bool   `json:"ok"`
	Generation int    `json:"generation"`
	Writer     string `json:"writer"`
	Epoch      int64  `json:"epoch"`
	Class      string `json:"class"`
	Message    string `json:"message"`
}

func Ensure(generation int) (model.CutoverState, error) {
	c, err := store.LoadCutover()
	if err == nil {
		return c, nil
	}
	if !errors.Is(err, os.ErrNotExist) {
		return model.CutoverState{}, err
	}
	var response controlResponse
	if err := simclient.Call("control", map[string]any{"generation": generation, "writer": "lambda", "epoch": 1}, &response); err != nil {
		return model.CutoverState{}, err
	}
	if !response.OK {
		return model.CutoverState{}, errors.New(response.Message)
	}
	c = model.CutoverState{ActiveGeneration: generation, Writer: "lambda", Epoch: response.Epoch}
	return c, store.SaveCutover(c)
}

func Load() (model.CutoverState, error) { return store.LoadCutover() }

func Shift(generation int, writer string) (model.CutoverState, error) {
	current, err := store.LoadCutover()
	if err != nil {
		return model.CutoverState{}, err
	}
	var response controlResponse
	if err := simclient.Call("control", map[string]any{"generation": generation, "writer": writer, "epoch": current.Epoch + 1}, &response); err != nil {
		return model.CutoverState{}, err
	}
	if !response.OK {
		var state struct {
			ActiveGeneration int    `json:"active_generation"`
			Writer           string `json:"writer"`
			Epoch            int64  `json:"epoch"`
		}
		if err := simclient.CallArgs([]string{"inspect", "state"}, nil, &state); err != nil {
			return model.CutoverState{}, errors.New(response.Message)
		}
		if state.ActiveGeneration != generation {
			return model.CutoverState{}, errors.New(response.Message)
		}
		response.Generation, response.Writer, response.Epoch = state.ActiveGeneration, state.Writer, state.Epoch
	}
	next := model.CutoverState{ActiveGeneration: response.Generation, PreviousGeneration: current.ActiveGeneration, Writer: response.Writer, Epoch: response.Epoch}
	return next, store.SaveCutover(next)
}
__M4_INTERNAL_CUTOVER_MANAGER_GO__

/usr/local/go/bin/gofmt -w /app/cmd /app/internal
mkdir -p /app/bin /app/state
/usr/local/go/bin/go build -o /app/bin/pipelinectl /app/cmd/pipelinectl
