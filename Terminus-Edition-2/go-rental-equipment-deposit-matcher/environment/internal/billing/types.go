package billing

type Status string

const (
	StatusPosted Status = "RETURNED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
