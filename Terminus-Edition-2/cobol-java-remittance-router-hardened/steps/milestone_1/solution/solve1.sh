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
text = text.replace(
    '''        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(URI.create(rulesUrl + "/rail/" + rail)).GET().build();
        String body = client.send(request, HttpResponse.BodyHandlers.ofString()).body();
        return body.contains("\\"allowed\\":true");''',
    '''        try {
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder(URI.create(rulesUrl + "/rail/" + rail)).GET().build();
            String body = client.send(request, HttpResponse.BodyHandlers.ofString()).body();
            return body.contains("\\"allowed\\":true");
        } catch (Exception ex) {
            return railAllowedByFile(rail);
        }''',
)
text = text.replace(
    '''    private static String toJson(int acceptedCount, int acceptedAmount, int rejectedCount, List<Result> results) {''',
    '''    private static boolean railAllowedByFile(String rail) {
        try (BufferedReader reader = Files.newBufferedReader(Path.of("/app/config/rails.csv"))) {
            String line = reader.readLine();
            while ((line = reader.readLine()) != null) {
                String[] parts = line.split(",", -1);
                if (parts.length >= 2 && parts[0].trim().equalsIgnoreCase(rail)) {
                    return parts[1].trim().equalsIgnoreCase("true");
                }
            }
        } catch (Exception ignored) {
            return false;
        }
        return false;
    }

    private static String toJson(int acceptedCount, int acceptedAmount, int rejectedCount, List<Result> results) {''',
)
java.write_text(text)
PY
/app/scripts/run_all.sh
test -s /app/out/remit_payload.json
