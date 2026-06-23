package billing

type Status string

const (
	StatusPosted Status = "ISSUED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
