package visiting

type Status string

const (
	StatusPosted Status = "POSTED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
