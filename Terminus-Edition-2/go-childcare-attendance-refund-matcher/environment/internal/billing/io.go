package billing

import (
    "encoding/csv"
    "os"
    "strconv"
)

func loadSessions(path string) ([]Session, error) {
    rows, err := readRows(path)
    if err != nil { return nil, err }
    sessions := make([]Session, 0, len(rows))
    for _, row := range rows {
        amount, err := strconv.Atoi(row[2])
        if err != nil { return nil, err }
        sessions = append(sessions, Session{ID: row[0], Guardian: row[1], Amount: amount, Status: row[3], Room: row[4]})
    }
    return sessions, nil
}

func loadRefunds(path string) ([]Refund, error) {
    rows, err := readRows(path)
    if err != nil { return nil, err }
    refunds := make([]Refund, 0, len(rows))
    for _, row := range rows {
        amount, err := strconv.Atoi(row[2])
        if err != nil { return nil, err }
        refunds = append(refunds, Refund{SessionID: row[0], Guardian: row[1], Amount: amount, Room: row[3]})
    }
    return refunds, nil
}

func readRows(path string) ([][]string, error) {
    f, err := os.Open(path)
    if err != nil { return nil, err }
    defer f.Close()
    r := csv.NewReader(f)
    r.FieldsPerRecord = -1
    rows, err := r.ReadAll()
    if err != nil { return nil, err }
    if len(rows) <= 1 { return nil, nil }
    return rows[1:], nil
}
