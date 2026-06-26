package store

import "cardrollout/internal/model"

type snapshotFile struct {
	SchemaVersion int64        `json:"schema_version"`
	JournalOffset int64        `json:"journal_offset"`
	State         *model.State `json:"state"`
}
