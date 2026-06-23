package billing

type Status string

const (
	StatusPosted Status = "BILLED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
