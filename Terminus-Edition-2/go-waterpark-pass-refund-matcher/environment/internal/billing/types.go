package billing

type Status string

const (
	StatusActive Status = "ACTIVE"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
