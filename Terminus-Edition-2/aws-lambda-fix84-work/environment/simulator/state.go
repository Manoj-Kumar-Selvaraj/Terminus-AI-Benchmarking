package main

func loadLedger() ([]map[string]any, error) {
	return loadJSONArray(ledgerPath())
}

func loadDLQ() ([]map[string]any, error) {
	return loadJSONArray(dlqPath())
}

func appendDLQEntry(entry map[string]any) error {
	entries, err := loadDLQ()
	if err != nil {
		return err
	}
	entries = append(entries, entry)
	return saveJSON(dlqPath(), entries)
}
