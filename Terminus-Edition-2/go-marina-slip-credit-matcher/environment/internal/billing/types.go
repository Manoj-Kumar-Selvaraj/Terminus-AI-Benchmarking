package billing

type Status string

const (
	StatusPosted Status = "DOCKED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
