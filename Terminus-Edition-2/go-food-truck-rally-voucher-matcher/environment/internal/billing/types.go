package billing

type Status string

const (
	StatusPosted Status = "COMPLETED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
