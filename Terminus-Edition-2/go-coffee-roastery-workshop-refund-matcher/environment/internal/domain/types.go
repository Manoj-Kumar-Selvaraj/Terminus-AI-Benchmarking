package workshoping

type Status string

const (
	StatusPosted Status = "ACTIVE"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
