package com.billing.http;

import com.billing.db.ConnectionPool;
import com.billing.db.MigrationRunner;
import com.sun.net.httpserver.HttpExchange;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;

public final class HealthHandlers {
    private final ConnectionPool pool;
    private final MigrationRunner migration;

    public HealthHandlers(ConnectionPool pool, MigrationRunner migration) {
        this.pool = pool;
        this.migration = migration;
    }

    public void handleLive(HttpExchange exchange) throws IOException {
        if (!migration.isComplete()) {
            write(exchange, 503, "DOWN");
            return;
        }
        write(exchange, 200, "UP");
    }

    public void handleReady(HttpExchange exchange) throws IOException {
        if (!migration.isComplete()) {
            write(exchange, 503, "DOWN");
            return;
        }
        Connection connection = null;
        try {
            connection = pool.borrow();
            if (!connection.isValid(2)) {
                write(exchange, 503, "DOWN");
                return;
            }
            write(exchange, 200, "UP");
        } catch (Exception exception) {
            write(exchange, 503, "DOWN");
        } finally {
            pool.release(connection);
        }
    }

    private void write(HttpExchange exchange, int status, String body) throws IOException {
        byte[] payload = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, payload.length);
        exchange.getResponseBody().write(payload);
        exchange.close();
    }
}
