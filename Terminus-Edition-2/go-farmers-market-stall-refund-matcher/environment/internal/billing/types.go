package billing

type Status string

const (
	StatusPosted Status = "RESERVED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
