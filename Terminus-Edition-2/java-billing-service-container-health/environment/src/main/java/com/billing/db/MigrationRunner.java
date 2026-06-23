package com.billing.db;

import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;

public final class MigrationRunner {
    private final ConnectionPool pool;
    private final int migrationSeconds;
    private volatile boolean complete;

    public MigrationRunner(ConnectionPool pool, int migrationSeconds) {
        this.pool = pool;
        this.migrationSeconds = migrationSeconds;
    }

    public void run() {
        try {
            Thread.sleep(migrationSeconds * 1000L);
            Connection connection = pool.borrow();
            try (Statement statement = connection.createStatement()) {
                statement.execute("CREATE TABLE IF NOT EXISTS invoices (id VARCHAR(64) PRIMARY KEY, account_id VARCHAR(64), amount_cents INT)");
                statement.execute("CREATE TABLE IF NOT EXISTS charges (id VARCHAR(64) PRIMARY KEY, account_id VARCHAR(64), amount_cents INT, status VARCHAR(32))");
                statement.execute("DELETE FROM invoices");
                statement.execute("INSERT INTO invoices VALUES ('inv-100', 'acct-1', 2500)");
            } finally {
                pool.release(connection);
            }
            complete = true;
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
        } catch (SQLException sqlException) {
            throw new IllegalStateException("migration failed", sqlException);
        }
    }

    public boolean isComplete() {
        return complete;
    }
}
