package billing

type Status string

const (
	StatusTapped Status = "TAPPED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
