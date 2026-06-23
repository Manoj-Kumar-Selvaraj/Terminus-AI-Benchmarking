package pipeline

type Scenario struct {
	Branch           string            `json:"branch"`
	BranchTipSHA     string            `json:"branch_tip_sha"`
	CommitSHA        string            `json:"commit_sha"`
	BuildNumber      string            `json:"build_number"`
	Environment      string            `json:"environment"`
	ParallelStages   bool              `json:"parallel_stages"`
	QualityGate      QualityGateReport `json:"quality_gate"`
	PreviousReleases []ReleaseRecord   `json:"previous_releases"`
	Notes            []string          `json:"notes"`
}

type BuildResult struct {
	BuildNumber  string `json:"build_number"`
	CommitSHA    string `json:"commit_sha"`
	Branch       string `json:"branch"`
	ArtifactHash string `json:"artifact_hash"`
	ArtifactPath string `json:"artifact_path"`
}

type ArtifactManifest struct {
	SchemaVersion string `json:"schema_version"`
	BuildNumber   string `json:"build_number"`
	CommitSHA     string `json:"commit_sha"`
	Branch        string `json:"branch"`
	ArtifactHash  string `json:"artifact_hash"`
	ArtifactPath  string `json:"artifact_path"`
	CreatedBy     string `json:"created_by"`
}

type StageReport struct {
	Stage                 string   `json:"stage"`
	StageName             string   `json:"stage_name"`
	BuildNumber           string   `json:"build_number"`
	CommitSHA             string   `json:"commit_sha"`
	ArtifactHash          string   `json:"artifact_hash"`
	Workspace             string   `json:"workspace"`
	WorkspaceContaminated bool     `json:"workspace_contaminated"`
	PackageHash           string   `json:"package_hash,omitempty"`
	Checks                []string `json:"checks"`
}

type QualityGateReport struct {
	Status       string  `json:"status"`
	CommitSHA    string  `json:"commit_sha"`
	ArtifactHash string  `json:"artifact_hash"`
	Coverage     float64 `json:"coverage"`
	ReportID     string  `json:"report_id"`
}

type ReleaseManifest struct {
	SchemaVersion        string            `json:"schema_version"`
	Environment          string            `json:"environment"`
	BuildNumber          string            `json:"build_number"`
	CommitSHA            string            `json:"commit_sha"`
	ArtifactHash         string            `json:"artifact_hash"`
	PromotedArtifactHash string            `json:"promoted_artifact_hash"`
	PackageHash          string            `json:"package_hash"`
	QualityGate          QualityGateReport `json:"quality_gate"`
	StageOrder           []string          `json:"stage_order"`
	PromotionStatus      string            `json:"promotion_status"`
}

type ReleaseRecord struct {
	Environment            string           `json:"environment"`
	BuildNumber            string           `json:"build_number"`
	CommitSHA              string           `json:"commit_sha"`
	ArtifactHash           string           `json:"artifact_hash"`
	PromotedArtifactHash   string           `json:"promoted_artifact_hash"`
	PackageHash            string           `json:"package_hash"`
	PromotionStatus        string           `json:"promotion_status"`
	ReleaseContractVersion string `json:"release_contract_version"`
	DeploymentUnits        []DeploymentUnit `json:"deployment_units,omitempty"`
}

type DeploymentUnit struct {
	Name                   string `json:"name"`
	ArtifactHash           string `json:"artifact_hash"`
	PackageHash            string `json:"package_hash"`
	ReleaseContractVersion string `json:"release_contract_version"`
}

type ReleaseHistory struct {
	SchemaVersion string          `json:"schema_version"`
	Releases      []ReleaseRecord `json:"releases"`
}

type RollbackManifest struct {
	SchemaVersion        string           `json:"schema_version"`
	Environment          string           `json:"environment"`
	TargetBuildNumber    string           `json:"target_build_number"`
	CommitSHA            string           `json:"commit_sha"`
	ArtifactHash         string           `json:"artifact_hash"`
	PromotedArtifactHash string           `json:"promoted_artifact_hash"`
	DeploymentUnits      []DeploymentUnit `json:"deployment_units,omitempty"`
	RollbackSource       string           `json:"rollback_source"`
	CommandInterface     string           `json:"command_interface"`
}
