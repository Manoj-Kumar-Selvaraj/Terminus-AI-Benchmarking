package reconciliation

type Status string

const (
	StatusApproved Status = "APPROVED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
