package model

var RequiredStages = []string{
	"intake", "verify_manifest", "acquire_lock", "fetch_inputs",
	"validate_inputs", "transform_records", "precheck_ledger", "write_ledger",
	"build_report", "notify_partner", "archive_batch", "release_lock",
}

type StageConfig struct {
	Name                string   `json:"name"`
	FunctionName        string   `json:"function_name"`
	TimeoutSeconds      int      `json:"timeout_seconds"`
	ReservedConcurrency int      `json:"reserved_concurrency"`
	MemoryMB            int      `json:"memory_mb"`
	Permissions         []string `json:"permissions"`
	Alias               string   `json:"alias"`
	PackageHash         string   `json:"package_hash"`
}

type StageFile struct {
	Stages []StageConfig `json:"stages"`
}

type Deployment struct {
	Generation int           `json:"generation"`
	Alias      string        `json:"alias"`
	Module     string        `json:"module"`
	Version    string        `json:"version"`
	Digest     string        `json:"digest"`
	Stages     []StageConfig `json:"stages"`
}

type Item struct {
	ID     string `json:"id"`
	Amount int64  `json:"amount"`
	Tenant string `json:"tenant"`
	Poison bool   `json:"poison,omitempty"`
}

type Request struct {
	ProtocolVersion int               `json:"protocol_version"`
	ExecutionID     string            `json:"execution_id"`
	BatchID         string            `json:"batch_id"`
	ArtifactDigest  string            `json:"artifact_digest"`
	Owner           string            `json:"owner"`
	Items           []Item            `json:"items"`
	Metadata        map[string]string `json:"metadata"`
}

type ItemState struct {
	ID        string `json:"id"`
	Status    string `json:"status"`
	LastStage string `json:"last_stage"`
	Attempts  int    `json:"attempts"`
	Error     string `json:"error,omitempty"`
}

type Checkpoint struct {
	ExecutionID      string            `json:"execution_id"`
	BatchID          string            `json:"batch_id"`
	Owner            string            `json:"owner"`
	ProtocolVersion  int               `json:"protocol_version"`
	ArtifactDigest   string            `json:"artifact_digest"`
	Generation       int               `json:"generation"`
	Epoch            int64             `json:"epoch"`
	NextStage        int               `json:"next_stage"`
	Status           string            `json:"status"`
	Metadata         map[string]string `json:"metadata"`
	Items            []ItemState       `json:"items"`
	CompletedEffects map[string]string `json:"completed_effects"`
	Attempts         map[string]int    `json:"attempts"`
	LastError        string            `json:"last_error,omitempty"`
	UpdatedAt        string            `json:"updated_at"`
}

type CutoverState struct {
	ActiveGeneration   int    `json:"active_generation"`
	PreviousGeneration int    `json:"previous_generation"`
	Writer             string `json:"writer"`
	Epoch              int64  `json:"epoch"`
}

type Invocation struct {
	Stage          string            `json:"stage"`
	ExecutionID    string            `json:"execution_id"`
	BatchID        string            `json:"batch_id"`
	ItemID         string            `json:"item_id,omitempty"`
	Attempt        int               `json:"attempt"`
	Generation     int               `json:"generation"`
	Epoch          int64             `json:"epoch"`
	Owner          string            `json:"owner"`
	IdempotencyKey string            `json:"idempotency_key,omitempty"`
	Metadata       map[string]string `json:"metadata,omitempty"`
}

type InvocationResult struct {
	OK           bool              `json:"ok"`
	Class        string            `json:"class,omitempty"`
	Message      string            `json:"message,omitempty"`
	LostResponse bool              `json:"lost_response,omitempty"`
	Duplicate    bool              `json:"duplicate,omitempty"`
	Output       map[string]string `json:"output,omitempty"`
}

type JournalRecord struct {
	OperationID string `json:"operation_id"`
	ExecutionID string `json:"execution_id"`
	Stage       string `json:"stage"`
	ItemID      string `json:"item_id,omitempty"`
	Generation  int    `json:"generation"`
	Epoch       int64  `json:"epoch"`
	Status      string `json:"status"`
	At          string `json:"at"`
}
