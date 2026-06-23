package finbulk

// Profile selects milestone behavior for the FNBULKUP batch driver.
var Profile = Options{
	StrictValidate:    false,
	FailClosed:        false,
	SkipApplied:       false,
	RejectNotFound:    false,
	RejectBusiness:    false,
	LockAsPending:     false,
	AtomicLimitUpdate: false,
	ControlManifest:   false,
	RejectReason:      "",
}
