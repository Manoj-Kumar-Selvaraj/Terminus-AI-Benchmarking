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