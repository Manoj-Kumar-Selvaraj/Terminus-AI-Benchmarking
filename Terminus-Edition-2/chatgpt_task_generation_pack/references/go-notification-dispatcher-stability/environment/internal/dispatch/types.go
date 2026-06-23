package dispatch

type Job struct {
	OperationKey string
	ClientID     string
	TargetURL    string
	EventType    string
	Payload      map[string]string
}
