package billing

type Status string

const (
	StatusPosted Status = "ENROLLED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
