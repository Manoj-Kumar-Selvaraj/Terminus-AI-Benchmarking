package billing

type Status string

const (
	StatusPosted Status = "SHIPPED"
	StatusDraft  Status = "DRAFT"
	StatusVoid   Status = "VOID"
)
