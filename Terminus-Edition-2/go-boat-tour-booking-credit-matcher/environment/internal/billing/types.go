package billing

type Status string

const (
	StatusPosted Status = "SAILED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
