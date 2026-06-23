package billing

type Status string

const (
	StatusPosted Status = "CLOSED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
