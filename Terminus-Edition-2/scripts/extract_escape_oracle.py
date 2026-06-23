from pathlib import Path

def extract_go(solve_path: Path) -> str:
    text = solve_path.read_text(encoding="utf-8")
    marker = "cat > /app/internal/reconcile/reconcile.go <<'GOEOF'\n"
    start = text.index(marker) + len(marker)
    end = text.index("\nGOEOF", start)
    return text[start:end]

root = Path(__file__).resolve().parents[1] / "go-escape-room-booking-refund-matcher/steps"
m5 = root / "milestone_5/solution/solve5.sh"
go = extract_go(m5)
out = root / "milestone_5/solution/oracle_reconcile.go"
out.write_text(go, encoding="utf-8")
print(f"Wrote {out} ({len(go.splitlines())} lines)")
