$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$task = Join-Path $root "cobol-java-remittance-router"
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-Lf {
    param([string]$Path, [string]$Text)
    $dir = Split-Path -Parent $Path
    if ($dir -and !(Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
    }
    $Text = ($Text -replace "`r`n", "`n") -replace "`r", "`n"
    [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

if (Test-Path $task) {
    Remove-Item -Recurse -Force $task
}

foreach ($dir in @(
    "environment/src", "environment/java", "environment/rules", "environment/data",
    "environment/config", "environment/docs", "environment/copybooks", "environment/samples",
    "environment/scripts", "steps/milestone_1/tests", "steps/milestone_1/solution",
    "steps/milestone_2/tests", "steps/milestone_2/solution"
)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $task $dir) | Out-Null
}

Write-Lf (Join-Path $task "task.toml") @'
version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous"
difficulty = "hard"
category = "debugging"
subcategories = ["tool_specific", "api_integration"]
number_of_milestones = 2
codebase_size = "small"
languages = ["cobol", "java", "bash"]
tags = ["cobol", "java", "docker-compose", "fixed-width", "http-service"]
expert_time_estimate_min = 95
junior_time_estimate_min = 210
custom_docker_compose = true
is_multi_container = true

[environment]
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
workdir = "/app"

[[steps]]
name = "milestone_1"

[steps.agent]
timeout_sec = 1200.0

[steps.verifier]
timeout_sec = 450.0

[[steps]]
name = "milestone_2"

[steps.agent]
timeout_sec = 1200.0

[steps.verifier]
timeout_sec = 450.0
'@

Write-Lf (Join-Path $task "environment/docker-compose.yaml") @'
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    working_dir: /app
    environment:
      RULES_URL: http://rules:8080
    depends_on:
      rules:
        condition: service_started
    command: ["sleep", "infinity"]
  rules:
    build:
      context: .
      dockerfile: Dockerfile.rules
    working_dir: /srv
    command: ["java", "-cp", "/srv", "RuleServer"]
    expose:
      - "8080"
'@

Write-Lf (Join-Path $task "environment/Dockerfile") @'
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    gnucobol \
    make \
    openjdk-17-jdk \
    python3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY src/ /app/src/
COPY java/ /app/java/
COPY data/ /app/data/
COPY config/ /app/config/
COPY docs/ /app/docs/
COPY copybooks/ /app/copybooks/
COPY samples/ /app/samples/
COPY scripts/ /app/scripts/

RUN mkdir -p /app/out /app/build \
    && chmod +x /app/scripts/*.sh
'@

Write-Lf (Join-Path $task "environment/Dockerfile.rules") @'
FROM eclipse-temurin:17.0.11_9-jdk

WORKDIR /srv
COPY rules/RuleServer.java /srv/RuleServer.java
RUN /opt/java/openjdk/bin/javac /srv/RuleServer.java

EXPOSE 8080
'@

Write-Lf (Join-Path $task "environment/rules/RuleServer.java") @'
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;

public class RuleServer {
    private static final Map<String, Boolean> ALLOWED = Map.of(
        "ACH", true,
        "WIR", true,
        "RTP", true,
        "CHK", false
    );

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", 8080), 0);
        server.createContext("/rail/", RuleServer::handleRail);
        server.start();
    }

    private static void handleRail(HttpExchange exchange) throws IOException {
        String path = exchange.getRequestURI().getPath();
        String rail = path.substring(path.lastIndexOf('/') + 1).toUpperCase();
        boolean allowed = ALLOWED.getOrDefault(rail, false);
        String body = "{\"rail\":\"" + rail + "\",\"allowed\":" + allowed + "}";
        exchange.getResponseHeaders().add("Content-Type", "application/json");
        exchange.sendResponseHeaders(200, body.getBytes(StandardCharsets.UTF_8).length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body.getBytes(StandardCharsets.UTF_8));
        }
    }
}
'@

Write-Lf (Join-Path $task "environment/src/remit_reconcile.cbl") @'
       IDENTIFICATION DIVISION.
       PROGRAM-ID. REMIT-RECON.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT REMIT-FILE ASSIGN TO "/app/data/remittances.dat"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT EXPORT-FILE ASSIGN TO "/app/out/remit_export.csv"
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT SUMMARY-FILE ASSIGN TO "/app/out/remit_summary.txt"
               ORGANIZATION IS LINE SEQUENTIAL.

       DATA DIVISION.
       FILE SECTION.
       FD REMIT-FILE.
       01 REMIT-REC PIC X(80).
       FD EXPORT-FILE.
       01 EXPORT-REC PIC X(160).
       FD SUMMARY-FILE.
       01 SUMMARY-REC PIC X(80).

       WORKING-STORAGE SECTION.
       01 WS-EOF PIC X VALUE "N".
       01 WS-EXPORTED-COUNT PIC 9(6) VALUE 0.
       01 WS-EXPORTED-AMOUNT PIC S9(12) SIGN LEADING SEPARATE VALUE 0.
       01 WS-REJECTED-COUNT PIC 9(6) VALUE 0.
       01 WS-TXN-ID PIC X(12).
       01 WS-ACCOUNT PIC X(8).
       01 WS-RAIL PIC X(3).
       01 WS-AMOUNT PIC 9(10).
       01 WS-DATE PIC X(8).
       01 WS-STATUS PIC X.

       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN INPUT REMIT-FILE
           OPEN OUTPUT EXPORT-FILE
           OPEN OUTPUT SUMMARY-FILE
           MOVE "transaction_id,account_id,rail,amount_cents,business_date" TO EXPORT-REC
           WRITE EXPORT-REC

           PERFORM UNTIL WS-EOF = "Y"
               READ REMIT-FILE
                   AT END
                       MOVE "Y" TO WS-EOF
                   NOT AT END
                       PERFORM PROCESS-REMIT
               END-READ
           END-PERFORM

           PERFORM WRITE-SUMMARY
           CLOSE REMIT-FILE
           CLOSE EXPORT-FILE
           CLOSE SUMMARY-FILE
           STOP RUN.

       PROCESS-REMIT.
           MOVE REMIT-REC(2:12) TO WS-TXN-ID
           MOVE REMIT-REC(14:8) TO WS-ACCOUNT
           MOVE REMIT-REC(22:3) TO WS-RAIL
           MOVE REMIT-REC(25:10) TO WS-AMOUNT
           MOVE REMIT-REC(35:8) TO WS-DATE
           MOVE REMIT-REC(43:1) TO WS-STATUS
           IF WS-STATUS = "P"
              AND (WS-RAIL = "ACH" OR WS-RAIL = "WIR")
               ADD 1 TO WS-EXPORTED-COUNT
               SUBTRACT WS-AMOUNT FROM WS-EXPORTED-AMOUNT
               MOVE SPACES TO EXPORT-REC
               STRING
                   WS-TXN-ID DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-ACCOUNT DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-RAIL DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-AMOUNT DELIMITED BY SIZE
                   "," DELIMITED BY SIZE
                   WS-DATE DELIMITED BY SIZE
                   INTO EXPORT-REC
               END-STRING
               WRITE EXPORT-REC
           ELSE
               ADD 1 TO WS-REJECTED-COUNT
           END-IF.

       WRITE-SUMMARY.
           MOVE SPACES TO SUMMARY-REC
           STRING "exported_count=" DELIMITED BY SIZE
               WS-EXPORTED-COUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "exported_amount_cents=" DELIMITED BY SIZE
               WS-EXPORTED-AMOUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC
           MOVE SPACES TO SUMMARY-REC
           STRING "rejected_count=" DELIMITED BY SIZE
               WS-REJECTED-COUNT DELIMITED BY SIZE INTO SUMMARY-REC
           END-STRING
           WRITE SUMMARY-REC.
'@

Write-Lf (Join-Path $task "environment/java/RemittanceAdapter.java") @'
import java.io.BufferedReader;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class RemittanceAdapter {
    record Row(String id, String account, String rail, String amount, String date) {}
    record Result(Row row, String status) {}

    public static void main(String[] args) throws Exception {
        Path export = Path.of("/app/out/remit_export.csv");
        Path payload = Path.of("/app/out/remit_payload.json");
        String rulesUrl = System.getenv().getOrDefault("RULES_URL", "http://localhost:8080");
        List<Row> rows = readRows(export);
        List<Result> results = new ArrayList<>();
        int acceptedCount = 0;
        int acceptedAmount = 0;
        int rejectedCount = 0;
        for (Row row : rows) {
            boolean allowed = railAllowed(rulesUrl, row.rail());
            if (allowed) {
                acceptedCount++;
                acceptedAmount += Integer.parseInt(row.amount());
                results.add(new Result(row, "ACCEPTED"));
            } else {
                rejectedCount++;
                results.add(new Result(row, "REJECTED"));
            }
        }
        Files.writeString(payload, toJson(acceptedCount, acceptedAmount, rejectedCount, results));
    }

    private static List<Row> readRows(Path path) throws IOException {
        List<Row> rows = new ArrayList<>();
        try (BufferedReader reader = Files.newBufferedReader(path)) {
            String line = reader.readLine();
            while ((line = reader.readLine()) != null) {
                String[] parts = line.split(",", -1);
                rows.add(new Row(parts[0], parts[1], parts[2], parts[3], parts[4]));
            }
        }
        return rows;
    }

    private static boolean railAllowed(String rulesUrl, String rail) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(URI.create(rulesUrl + "/rail/" + rail)).GET().build();
        String body = client.send(request, HttpResponse.BodyHandlers.ofString()).body();
        return body.contains("\"allowed\":true");
    }

    private static String toJson(int acceptedCount, int acceptedAmount, int rejectedCount, List<Result> results) {
        StringBuilder out = new StringBuilder();
        out.append("{\n");
        out.append("  \"accepted_count\": ").append(acceptedCount).append(",\n");
        out.append("  \"accepted_amount_cents\": ").append(acceptedAmount).append(",\n");
        out.append("  \"rejected_count\": ").append(rejectedCount).append(",\n");
        out.append("  \"transactions\": [\n");
        for (int i = 0; i < results.size(); i++) {
            Result result = results.get(i);
            Row row = result.row();
            out.append("    {\"transaction_id\":\"").append(row.id()).append("\",")
                .append("\"account_id\":\"").append(row.account()).append("\",")
                .append("\"rail\":\"").append(row.rail()).append("\",")
                .append("\"amount_cents\":\"").append(row.amount()).append("\",")
                .append("\"business_date\":\"").append(row.date()).append("\",")
                .append("\"status\":\"").append(result.status()).append("\"}");
            if (i + 1 < results.size()) {
                out.append(",");
            }
            out.append("\n");
        }
        out.append("  ]\n");
        out.append("}\n");
        return out.toString();
    }
}
'@

Write-Lf (Join-Path $task "environment/data/remittances.dat") @'
RREM202604101ACCT1001ACH000001250020260430P
RREM202604102ACCT1002RTP000000880020260430P
RREM202604103ACCT1003WIR000000410020260430P
'@

Write-Lf (Join-Path $task "environment/scripts/clean_outputs.sh") @'
#!/usr/bin/env bash
set -euo pipefail
rm -rf /app/out /app/build
mkdir -p /app/out /app/build
'@
Write-Lf (Join-Path $task "environment/scripts/compile_cobol.sh") @'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/build
cobc -x -free -o /app/build/remit_reconcile /app/src/remit_reconcile.cbl
'@
Write-Lf (Join-Path $task "environment/scripts/run_batch.sh") @'
#!/usr/bin/env bash
set -euo pipefail
/app/scripts/clean_outputs.sh
/app/scripts/compile_cobol.sh
/app/build/remit_reconcile
'@
Write-Lf (Join-Path $task "environment/scripts/run_adapter.sh") @'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p /app/build
javac -d /app/build /app/java/RemittanceAdapter.java
java -cp /app/build RemittanceAdapter
'@
Write-Lf (Join-Path $task "environment/scripts/run_all.sh") @'
#!/usr/bin/env bash
set -euo pipefail
/app/scripts/run_batch.sh
/app/scripts/run_adapter.sh
'@

Write-Lf (Join-Path $task "environment/config/rails.csv") "rail,allowed`nACH,true`nWIR,true`nRTP,true`nCHK,false`n"
Write-Lf (Join-Path $task "environment/config/payload_schema.json") @'
{
  "remit_export_csv": {
    "path": "/app/out/remit_export.csv",
    "header": "transaction_id,account_id,rail,amount_cents,business_date",
    "columns": {
      "transaction_id": "string",
      "account_id": "string",
      "rail": "string",
      "amount_cents": "string (10-digit zero-padded)",
      "business_date": "string (YYYYMMDD)"
    }
  },
  "remit_summary_txt": {
    "path": "/app/out/remit_summary.txt",
    "format": "key=value lines",
    "fields": {
      "exported_count": "int",
      "exported_amount_cents": "int (positive sum of exported rows)",
      "rejected_count": "int"
    }
  },
  "remit_payload_json": {
    "path": "/app/out/remit_payload.json",
    "accepted_count": "int",
    "accepted_amount_cents": "int",
    "rejected_count": "int",
    "transactions": {
      "type": "array",
      "item": {
        "transaction_id": "string",
        "account_id": "string",
        "rail": "string",
        "amount_cents": "string (10-digit zero-padded)",
        "business_date": "string (YYYYMMDD)",
        "status": "string (ACCEPTED | REJECTED | DUPLICATE | CLOSED_DATE)"
      }
    }
  }
}
'@
Write-Lf (Join-Path $task "environment/config/job.properties") "rules_url=http://rules:8080`nexport=/app/out/remit_export.csv`npayload=/app/out/remit_payload.json`n"
Write-Lf (Join-Path $task "environment/docs/record_layouts.md") "Remittance records: type(1), transaction id(12), account id(8), rail(3), amount cents(10), business date(8), status(1)."
Write-Lf (Join-Path $task "environment/docs/runbook.md") "Run /app/scripts/run_all.sh from /app. The Java adapter calls the rules service at http://rules:8080."
Write-Lf (Join-Path $task "environment/docs/payload_contract.md") @'
# Remittance output contract

The batch writes three artifacts under `/app/out/`. Normative field definitions live in `/app/config/payload_schema.json`.

## COBOL export (`remit_export.csv`)

- Header (exact): `transaction_id,account_id,rail,amount_cents,business_date`
- One row per exported remittance, in input order among exported rows only.
- `amount_cents` stays the 10-character zero-padded text from the input record (not re-formatted).

## COBOL summary (`remit_summary.txt`)

Three `key=value` lines (integers, no surrounding spaces):

- `exported_count` — number of rows written to `remit_export.csv`
- `exported_amount_cents` — positive sum of exported amounts in cents (must not be negated)
- `rejected_count` — input records rejected by the COBOL filter (non-posted, disallowed rail, etc.)

## Java payload (`remit_payload.json`)

Top-level counters plus a `transactions` array in **export row order** (same order as `remit_export.csv`).

Each transaction object:

| Field | Type | Notes |
|-------|------|-------|
| `transaction_id` | string | From export |
| `account_id` | string | From export |
| `rail` | string | From export |
| `amount_cents` | string | 10-character zero-padded, unchanged from export |
| `business_date` | string | `YYYYMMDD` from export |
| `status` | string | `ACCEPTED`, `REJECTED`, `DUPLICATE`, or `CLOSED_DATE` (milestone 3) |

Summary fields:

- `accepted_count` / `accepted_amount_cents` — only `ACCEPTED` rows
- `rejected_count` — every non-`ACCEPTED` transaction (including `REJECTED`, `DUPLICATE`, `CLOSED_DATE`)
'@
Write-Lf (Join-Path $task "environment/docs/release_notes.md") "Known issue: RTP remittances are missing from downstream payloads."
Write-Lf (Join-Path $task "environment/docs/service_contract.md") "GET /rail/{rail} returns JSON with rail and allowed fields."
Write-Lf (Join-Path $task "environment/copybooks/remittance-record.cpy") "      * Remittance record copybook placeholder."
Write-Lf (Join-Path $task "environment/copybooks/export-record.cpy") "      * Export record copybook placeholder."
Write-Lf (Join-Path $task "environment/copybooks/summary-record.cpy") "      * Summary record copybook placeholder."
Write-Lf (Join-Path $task "environment/samples/remittances_edge.dat") "RREMEDGE0001ACCTEDGECHK000000050020260430P`n"
Write-Lf (Join-Path $task "environment/samples/export_sample.csv") "transaction_id,account_id,rail,amount_cents,business_date`nREM202604101,ACCT1001,ACH,0000012500,20260430`n"

Write-Lf (Join-Path $task "steps/milestone_1/instruction.md") @'
The remittance router under `/app` has a bad COBOL-to-Java handoff. RTP remittances are missing from `/app/out/remit_export.csv`, the COBOL export summary amount is signed backwards, and the Java adapter cannot reach the local rules service when it runs inside Docker Compose.

Fix `/app/src/remit_reconcile.cbl` and `/app/java/RemittanceAdapter.java` so `/app/scripts/run_all.sh` reads `/app/data/remittances.dat`, writes `/app/out/remit_export.csv` and `/app/out/remit_summary.txt`, calls the rules service at `http://rules:8080` when it is reachable, and writes `/app/out/remit_payload.json`. Output shapes are defined in `/app/config/payload_schema.json` and `/app/docs/payload_contract.md`.

**COBOL export (`remit_export.csv`)** — Header: `transaction_id,account_id,rail,amount_cents,business_date`. Posted `ACH`, `WIR`, and `RTP` records are exportable; `CHK` and non-posted records are rejected before the Java adapter. Keep `amount_cents` as the 10-character zero-padded text from the input record.

**COBOL summary (`remit_summary.txt`)** — Three lines: `exported_count=`, `exported_amount_cents=`, `rejected_count=`. Counts must match the export. `exported_amount_cents` must be the **positive** sum of exported amounts in cents (fix the current sign inversion).

**Java payload (`remit_payload.json`)** — One transaction object per export row (same order), with fields and statuses per the schema. The verifier runs the adapter without the Compose `rules` service, so the Java adapter must tolerate a failed or unresolved rules-service call by falling back to the allowed rails in `/app/config/rails.csv`: `ACH`, `WIR`, and `RTP` are allowed, while `CHK` is not. Do not let an unavailable rules service crash the batch.
'@
Write-Lf (Join-Path $task "steps/milestone_2/instruction.md") @'
Continue the remittance router work in `/app`. The Java payload still mishandles duplicate transaction ids after the COBOL export is correct.

Keep milestone 1 behavior and outputs: `/app/out/remit_export.csv`, `/app/out/remit_summary.txt` (`exported_count`, `exported_amount_cents`, `rejected_count`), and `/app/out/remit_payload.json` per `/app/config/payload_schema.json` and `/app/docs/payload_contract.md`.

**Rules service** — Try `http://rules:8080` when available; if the service cannot be reached or `rules` cannot be resolved during verification, fall back to allowed rails in `/app/config/rails.csv` (`ACH`, `WIR`, `RTP`). The adapter must not crash when the rules service is unavailable.

**Duplicate transaction ids** — If the export contains the same `transaction_id` more than once, only the earliest exported row can be `ACCEPTED`; later rows with that id must stay in the payload in export order with status `DUPLICATE`, must not count toward `accepted_count` / `accepted_amount_cents`, and must count in `rejected_count`. Preserve 10-character zero-padded `amount_cents` strings on every transaction object.
'@
Write-Lf (Join-Path $task "steps/milestone_3/instruction.md") @'
Extend the remittance router in `/app` so the Java adapter enforces business-date controls after the COBOL export. The batch must still read `/app/data/remittances.dat`, write `/app/out/remit_export.csv` and `/app/out/remit_summary.txt`, try the rules service at `http://rules:8080`, and write `/app/out/remit_payload.json` per `/app/config/payload_schema.json` and `/app/docs/payload_contract.md`. Preserve milestone 1–2 export/summary semantics and duplicate-id rules.

**Rules service fallback** — If the rules service is unavailable or `rules` cannot be resolved, use `/app/config/rails.csv` (or equivalent local logic) so `ACH`, `WIR`, and `RTP` are allowed and `CHK` is rejected instead of crashing.

**Business-date calendar (`/app/config/cycle_calendar.txt`)** — Each line is `YYYYMMDD` followed by a status token. Compare status **case-insensitively**. Only `OPEN` (any casing, e.g. `open` or `OPEN`) means the date is open. A transaction can be `ACCEPTED` only when its `business_date` is listed as open, the rail is allowed, and the transaction id has not already been accepted. Dates missing from the file or with any other status (e.g. `CLOSED`, `holiday`) must produce status `CLOSED_DATE`, must not count toward accepted totals, and must count in `rejected_count`.

**Status precedence** — `CLOSED_DATE` applies before duplicate detection on later rows: a row on a non-open date is `CLOSED_DATE` even if the same `transaction_id` was accepted earlier on an open date. Later rows with an id that has already been **accepted** must be `DUPLICATE`.

**Payload totals** — Preserve export row order, keep 10-character zero-padded `amount_cents` strings, and count every non-accepted transaction in `rejected_count`. `accepted_count` and `accepted_amount_cents` include only `ACCEPTED` transactions. Rails blocked by the rules service still use status `REJECTED`.
'@

$testCommon = @'
"""Verifier tests for the COBOL and Java remittance router."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
DATA = APP / "data" / "remittances.dat"
EXPORT = APP / "out" / "remit_export.csv"
SUMMARY = APP / "out" / "remit_summary.txt"
PAYLOAD = APP / "out" / "remit_payload.json"


def write_inputs(rows):
    """Replace the fixed-width remittance input data for a focused scenario."""
    DATA.write_text("\n".join(rows) + "\n")


def run_all():
    """Run the COBOL batch and Java adapter, returning parsed outputs."""
    subprocess.run(["/app/scripts/run_all.sh"], check=True, cwd=APP)
    with EXPORT.open(newline="") as handle:
        export_rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    payload = json.loads(PAYLOAD.read_text())
    return export_rows, summary, payload


class TestMilestone1:
    def test_rtp_is_exported_and_service_payload_accepts_allowed_rails(self):
        """RTP should be exported by COBOL and accepted after the Java service lookup."""
        write_inputs([
            "RREM202604101ACCT1001ACH000001250020260430P",
            "RREM202604102ACCT1002RTP000000880020260430P",
            "RREM202604103ACCT1003WIR000000410020260430P",
            "RREM202604104ACCT1004CHK000000070020260430P",
            "RREM202604105ACCT1005ACH000000050020260430H",
        ])
        export_rows, summary, payload = run_all()

        assert [row["rail"] for row in export_rows] == ["ACH", "RTP", "WIR"]
        assert summary["exported_count"] == 3
        assert summary["exported_amount_cents"] == 25400
        assert summary["rejected_count"] == 2
        assert payload["accepted_count"] == 3
        assert payload["accepted_amount_cents"] == 25400

    def test_export_schema_order_and_zero_padded_amounts_are_stable(self):
        """The COBOL export should preserve input order and raw zero-padded amount text."""
        write_inputs([
            "RREM900000003ACCT9003WIR000000030020260430P",
            "RREM900000001ACCT9001ACH000000010020260430P",
            "RREM900000002ACCT9002RTP000000020020260430P",
        ])
        export_rows, summary, payload = run_all()

        assert EXPORT.read_text().splitlines()[0] == "transaction_id,account_id,rail,amount_cents,business_date"
        assert [row["transaction_id"] for row in export_rows] == ["REM900000003", "REM900000001", "REM900000002"]
        assert [row["amount_cents"] for row in export_rows] == ["0000000300", "0000000100", "0000000200"]
        assert [tx["amount_cents"] for tx in payload["transactions"]] == ["0000000300", "0000000100", "0000000200"]
        assert summary["exported_amount_cents"] == 600
        assert payload["accepted_amount_cents"] == 600
'@
$testM2 = $testCommon -replace "class TestMilestone1:", "class TestMilestone2:"
$testM2 += @'

    def test_duplicate_transaction_ids_do_not_double_count(self):
        """Later duplicate transaction ids should stay in the payload as DUPLICATE and not count as accepted."""
        write_inputs([
            "RREM555500001ACCT5551ACH000000720020260430P",
            "RREM555500001ACCT5551ACH000000720020260430P",
            "RREM555500002ACCT5552RTP000000410020260430P",
        ])
        export_rows, summary, payload = run_all()

        assert [row["transaction_id"] for row in export_rows] == ["REM555500001", "REM555500001", "REM555500002"]
        assert [tx["status"] for tx in payload["transactions"]] == ["ACCEPTED", "DUPLICATE", "ACCEPTED"]
        assert payload["accepted_count"] == 2
        assert payload["accepted_amount_cents"] == 11300
        assert payload["transactions"][1]["amount_cents"] == "0000007200"
'@
Write-Lf (Join-Path $task "steps/milestone_1/tests/test_m1.py") $testCommon
Write-Lf (Join-Path $task "steps/milestone_2/tests/test_m2.py") $testM2

function TestSh([string]$File) {
@"
#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
if [ "`$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    exit 1
fi
if ! command -v uvx >/dev/null 2>&1; then
  apt-get update
  apt-get install -y curl
  curl -LsSf https://astral.sh/uv/0.9.5/install.sh | sh
fi
export PATH="`$HOME/.local/bin:`$PATH"
uvx \
  -p 3.13 \
  --with pytest==8.4.1 \
  --with pytest-json-ctrf==0.3.5 \
  pytest --ctrf /logs/verifier/ctrf.json /tests/$File -rA
if [ `$? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"@
}
Write-Lf (Join-Path $task "steps/milestone_1/tests/test.sh") (TestSh "test_m1.py")
Write-Lf (Join-Path $task "steps/milestone_2/tests/test.sh") (TestSh "test_m2.py")

Write-Lf (Join-Path $task "steps/milestone_1/solution/solve.sh") @'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve1.sh"
'@
Write-Lf (Join-Path $task "steps/milestone_2/solution/solve.sh") @'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$SCRIPT_DIR/solve2.sh"
'@

Write-Lf (Join-Path $task "steps/milestone_1/solution/solve1.sh") @'
#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path
cobol = Path("/app/src/remit_reconcile.cbl")
text = cobol.read_text()
text = text.replace('AND (WS-RAIL = "ACH" OR WS-RAIL = "WIR")', 'AND (WS-RAIL = "ACH" OR WS-RAIL = "WIR"\n                   OR WS-RAIL = "RTP")')
text = text.replace('SUBTRACT WS-AMOUNT FROM WS-EXPORTED-AMOUNT', 'ADD WS-AMOUNT TO WS-EXPORTED-AMOUNT')
cobol.write_text(text)
java = Path("/app/java/RemittanceAdapter.java")
text = java.read_text()
text = text.replace('System.getenv().getOrDefault("RULES_URL", "http://localhost:8080")', 'System.getenv().getOrDefault("RULES_URL", "http://rules:8080")')
java.write_text(text)
PY
/app/scripts/run_all.sh
test -s /app/out/remit_payload.json
'@

Write-Lf (Join-Path $task "steps/milestone_2/solution/solve2.sh") @'
#!/usr/bin/env bash
set -euo pipefail
cd /app
python3 <<'PY'
from pathlib import Path
path = Path("/app/java/RemittanceAdapter.java")
text = path.read_text()
text = text.replace('import java.util.ArrayList;\nimport java.util.List;', 'import java.util.ArrayList;\nimport java.util.HashSet;\nimport java.util.List;\nimport java.util.Set;')
text = text.replace('int rejectedCount = 0;\n        for (Row row : rows) {', 'int rejectedCount = 0;\n        Set<String> seen = new HashSet<>();\n        for (Row row : rows) {')
text = text.replace('boolean allowed = railAllowed(rulesUrl, row.rail());\n            if (allowed) {', 'boolean allowed = railAllowed(rulesUrl, row.rail());\n            if (seen.contains(row.id())) {\n                results.add(new Result(row, "DUPLICATE"));\n                continue;\n            }\n            if (allowed) {\n                seen.add(row.id());')
path.write_text(text)
PY
/app/scripts/run_all.sh
test -s /app/out/remit_payload.json
'@

Write-Host "Created $task"
