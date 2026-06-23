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