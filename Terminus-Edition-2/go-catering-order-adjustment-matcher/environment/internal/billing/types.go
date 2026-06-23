package billing

type Status string

const (
	StatusPosted Status = "FULFILLED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
