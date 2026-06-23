package reconcile

type Accession struct {
	SampleID  string
	PatientID string
	ChainID   string
	Kind      string
	Amount    string
	SourceTS  string
	Status    string
	Location  string
	Consumed  bool
	Index     int
}

type Reassignment struct {
	ActionID  string
	SampleID  string
	PatientID string
	ChainID   string
	Kind      string
	Amount    string
	ActionTS  string
	Reason    string
	Location  string
}

type Window struct {
	ChainID string
	OpenTS  string
	CloseTS string
	State   string
}

type OutputRow struct {
	ActionID        string
	SampleID        string
	PatientID       string
	ChainID         string
	Kind            string
	Amount          string
	Reason          string
	MatchedSourceTS string
	Status          string
}
