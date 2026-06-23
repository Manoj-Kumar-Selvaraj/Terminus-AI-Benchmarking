package finbulk

var Profile = Options{
	StrictValidate:    true,
	FailClosed:        true,
	SkipApplied:       false,
	RejectNotFound:    true,
	RejectBusiness:    false,
	LockAsPending:     false,
	AtomicLimitUpdate: false,
	ControlManifest:   false,
	RejectReason:      "MASTER_ROW_NOT_FOUND",
}
