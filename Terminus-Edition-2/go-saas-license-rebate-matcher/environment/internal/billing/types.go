package billing

type Status string

const (
	StatusPosted Status = "LICENSED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
