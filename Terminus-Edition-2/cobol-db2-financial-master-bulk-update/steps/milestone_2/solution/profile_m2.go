package finbulk

var Profile = Options{
	StrictValidate:    true,
	FailClosed:        true,
	SkipApplied:       true,
	RejectNotFound:    true,
	RejectBusiness:    true,
	LockAsPending:     false,
	AtomicLimitUpdate: false,
	ControlManifest:   false,
	RejectReason:      "BUSINESS_OR_LOCK_REJECT",
}
