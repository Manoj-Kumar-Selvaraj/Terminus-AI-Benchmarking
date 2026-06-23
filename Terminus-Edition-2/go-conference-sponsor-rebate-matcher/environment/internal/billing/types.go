package billing

type Status string

const (
	StatusPosted Status = "SIGNED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
