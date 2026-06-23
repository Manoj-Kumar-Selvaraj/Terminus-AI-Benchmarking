package billing

type Status string

const (
	StatusPosted Status = "PAID"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
