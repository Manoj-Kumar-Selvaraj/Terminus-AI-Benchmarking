package billing

type Status string

const (
	StatusPosted Status = "BOOKED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
