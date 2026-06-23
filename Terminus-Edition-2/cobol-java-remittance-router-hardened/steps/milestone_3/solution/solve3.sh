#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path
path = Path("/app/java/RemittanceAdapter.java")
text = path.read_text()
text = text.replace(
    'List<Row> rows = readRows(export);\n        List<Result> results = new ArrayList<>();',
    'List<Row> rows = readRows(export);\n        Set<String> openDates = loadOpenDates(Path.of("/app/config/cycle_calendar.txt"));\n        List<Result> results = new ArrayList<>();',
)
text = text.replace(
    '''        for (Row row : rows) {
            boolean allowed = railAllowed(rulesUrl, row.rail());
            if (seen.contains(row.id())) {
                rejectedCount++;
                results.add(new Result(row, "DUPLICATE"));
                continue;
            }
            if (allowed) {
                seen.add(row.id());
                acceptedCount++;
                acceptedAmount += Integer.parseInt(row.amount());
                results.add(new Result(row, "ACCEPTED"));
            } else {
                rejectedCount++;
                results.add(new Result(row, "REJECTED"));
            }
        }''',
    '''        for (Row row : rows) {
            if (!openDates.contains(row.date())) {
                rejectedCount++;
                results.add(new Result(row, "CLOSED_DATE"));
                continue;
            }
            boolean allowed = railAllowed(rulesUrl, row.rail());
            if (seen.contains(row.id())) {
                rejectedCount++;
                results.add(new Result(row, "DUPLICATE"));
                continue;
            }
            if (allowed) {
                seen.add(row.id());
                acceptedCount++;
                acceptedAmount += Integer.parseInt(row.amount());
                results.add(new Result(row, "ACCEPTED"));
            } else {
                rejectedCount++;
                results.add(new Result(row, "REJECTED"));
            }
        }''',
)
text = text.replace(
    '''    private static boolean railAllowed(String rulesUrl, String rail) throws Exception {''',
    '''    private static Set<String> loadOpenDates(Path path) throws IOException {
        Set<String> openDates = new HashSet<>();
        for (String line : Files.readAllLines(path)) {
            String[] parts = line.trim().split("\\\\s+");
            if (parts.length >= 2 && parts[1].equalsIgnoreCase("OPEN")) {
                openDates.add(parts[0]);
            }
        }
        return openDates;
    }

    private static boolean railAllowed(String rulesUrl, String rail) throws Exception {''',
)
path.write_text(text)
PY
/app/scripts/run_all.sh
test -s /app/out/remit_payload.json
