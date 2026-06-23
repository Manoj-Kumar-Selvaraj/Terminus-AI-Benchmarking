package com.billing.db;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.Deque;

public final class ConnectionPool {
    private final Deque<Connection> idle = new ArrayDeque<>();
    private final String url;
    private final String user;
    private final String password;
    private final int maxSize;
    private int active;

    public ConnectionPool(String url, String user, String password, int maxSize) {
        this.url = url;
        this.user = user;
        this.password = password;
        this.maxSize = maxSize;
    }

    public synchronized Connection borrow() throws SQLException {
        if (active >= maxSize && idle.isEmpty()) {
            throw new SQLException("pool exhausted");
        }
        if (!idle.isEmpty()) {
            active++;
            return idle.pop();
        }
        active++;
        return DriverManager.getConnection(url, user, password);
    }

    public synchronized void release(Connection connection) {
        if (connection == null) {
            return;
        }
        active = Math.max(0, active - 1);
        idle.push(connection);
    }

    public synchronized int activeCount() {
        return active;
    }

    public synchronized int idleCount() {
        return idle.size();
    }

    public synchronized int maxSize() {
        return maxSize;
    }
}
