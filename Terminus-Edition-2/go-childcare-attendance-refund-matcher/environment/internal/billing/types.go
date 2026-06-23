package billing

type Session struct {
    ID string
    Guardian string
    Amount int
    Status string
    Room string
}

type Refund struct {
    SessionID string
    Guardian string
    Amount int
    Room string
}

type Summary struct {
    MatchedCount int `json:"matched_count"`
    MatchedAmountCents int `json:"matched_amount_cents"`
    UnmatchedCount int `json:"unmatched_count"`
    UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}
