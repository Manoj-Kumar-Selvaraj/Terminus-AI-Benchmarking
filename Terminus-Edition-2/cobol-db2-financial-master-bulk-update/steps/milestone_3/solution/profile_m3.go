package finbulk

var Profile = Options{
	StrictValidate:    true,
	FailClosed:        true,
	SkipApplied:       true,
	RejectNotFound:    false,
	RejectBusiness:    true,
	LockAsPending:     true,
	AtomicLimitUpdate: false,
	ControlManifest:   false,
	RejectReason:      "BUSINESS_REJECT",
}
