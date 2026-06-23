package billing

import (
    "encoding/csv"
    "encoding/json"
    "os"
    "path/filepath"
    "strconv"
)

func Run() error {
    sessions, err := loadSessions("/app/data/sessions.csv")
    if err != nil { return err }
    refunds, err := loadRefunds("/app/data/refunds.csv")
    if err != nil { return err }
    return writeOutputs(sessions, refunds)
}

func writeOutputs(sessions []Session, refunds []Refund) error {
    if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
    reportFile, err := os.Create(filepath.Join("/app/out", "refund_report.csv"))
    if err != nil { return err }
    defer reportFile.Close()
    w := csv.NewWriter(reportFile)
    defer w.Flush()
    if err := w.Write([]string{"session_id", "guardian_id", "room", "amount_cents", "status"}); err != nil { return err }
    summary := Summary{}
    for _, refund := range refunds {
        match := findMatch(sessions, refund)
        status, room := "UNMATCHED", ""
        if match != nil {
            status, room = "MATCHED", match.Room
            summary.MatchedCount++
            summary.MatchedAmountCents -= refund.Amount
        } else {
            summary.UnmatchedCount++
            summary.UnmatchedAmountCents += refund.Amount
        }
        if err := w.Write([]string{refund.SessionID, refund.Guardian, room, strconv.Itoa(refund.Amount), status}); err != nil { return err }
    }
    if err := w.Error(); err != nil { return err }
    b, err := json.MarshalIndent(summary, "", "  ")
    if err != nil { return err }
    return os.WriteFile("/app/out/refund_summary.json", append(b, '
'), 0o644)
}

func findMatch(sessions []Session, refund Refund) *Session {
    for i := range sessions {
        session := &sessions[i]
        if len(session.ID) >= 8 && len(refund.SessionID) >= 8 && session.ID[:8] == refund.SessionID[:8] &&
            session.Guardian == refund.Guardian && session.Amount == refund.Amount &&
            session.Status == "CHECKEDIN" && allowedRoom(session.Room) && session.Room == refund.Room {
            return session
        }
    }
    return nil
}
