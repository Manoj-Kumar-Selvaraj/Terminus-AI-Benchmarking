package com.billing.http;

import com.billing.db.ConnectionPool;
import com.sun.net.httpserver.HttpExchange;

import java.io.IOException;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class InvoiceHandlers {
    private final ConnectionPool pool;

    public InvoiceHandlers(ConnectionPool pool) {
        this.pool = pool;
    }

    public void handleList(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            write(exchange, 405, "method not allowed");
            return;
        }
        Connection connection = null;
        try {
            connection = pool.borrow();
            PreparedStatement statement = connection.prepareStatement("SELECT id, account_id, amount_cents FROM invoices ORDER BY id");
            ResultSet rows = statement.executeQuery();
            List<String> lines = new ArrayList<>();
            while (rows.next()) {
                lines.add(rows.getString(1) + "," + rows.getString(2) + "," + rows.getInt(3));
            }
            write(exchange, 200, String.join("\n", lines));
        } catch (SQLException sqlException) {
            write(exchange, 500, "database error");
        } finally {
            pool.release(connection);
        }
    }

    public void handleCharge(HttpExchange exchange) throws IOException {
        if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
            write(exchange, 405, "method not allowed");
            return;
        }
        String query = exchange.getRequestURI().getRawQuery();
        String accountId = queryValue(query, "account_id");
        int amount = Integer.parseInt(queryValue(query, "amount_cents"));
        Connection connection = null;
        try {
            connection = pool.borrow();
            if (amount <= 0) {
                write(exchange, 400, "invalid amount");
                return;
            }
            if (accountId == null || accountId.isBlank()) {
                write(exchange, 400, "missing account");
                return;
            }
            PreparedStatement lookup = connection.prepareStatement("SELECT amount_cents FROM invoices WHERE account_id = ?");
            lookup.setString(1, accountId);
            ResultSet existing = lookup.executeQuery();
            if (!existing.next()) {
                write(exchange, 404, "account not found");
                return;
            }
            PreparedStatement insert = connection.prepareStatement("INSERT INTO charges VALUES (?, ?, ?, ?)");
            insert.setString(1, UUID.randomUUID().toString());
            insert.setString(2, accountId);
            insert.setInt(3, amount);
            insert.setString(4, "posted");
            insert.executeUpdate();
            write(exchange, 201, "accepted");
        } catch (SQLException sqlException) {
            write(exchange, 500, "database error");
            return;
        } catch (NumberFormatException numberFormatException) {
            write(exchange, 400, "invalid amount");
            return;
        }
        pool.release(connection);
    }

    public void handlePoolStats(HttpExchange exchange) throws IOException {
        String body = "active=" + pool.activeCount() + "\nidle=" + pool.idleCount() + "\nmax=" + pool.maxSize();
        write(exchange, 200, body);
    }

    private String queryValue(String query, String key) {
        if (query == null) {
            return null;
        }
        for (String part : query.split("&")) {
            String[] pair = part.split("=", 2);
            if (pair.length == 2 && pair[0].equals(key)) {
                return URLDecoder.decode(pair[1], StandardCharsets.UTF_8);
            }
        }
        return null;
    }

    private void write(HttpExchange exchange, int status, String body) throws IOException {
        byte[] payload = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, payload.length);
        exchange.getResponseBody().write(payload);
        exchange.close();
    }
}
