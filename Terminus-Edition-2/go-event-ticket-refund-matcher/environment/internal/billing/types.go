package billing

type Status string

const (
	StatusPosted Status = "CONFIRMED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
