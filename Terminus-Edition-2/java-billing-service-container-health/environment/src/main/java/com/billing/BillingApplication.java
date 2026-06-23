package com.billing;

import com.billing.config.AppConfig;
import com.billing.db.ConnectionPool;
import com.billing.db.MigrationRunner;
import com.billing.http.BillingHttpServer;
import com.billing.http.HealthHandlers;
import com.billing.http.InvoiceHandlers;

import java.nio.file.Path;

public final class BillingApplication {
    public static void main(String[] args) throws Exception {
        Path configDir = Path.of("/app/config");
        AppConfig config = new AppConfig(configDir);
        ConnectionPool pool = new ConnectionPool(
                config.getString("billing.datasource.url", ""),
                config.getString("billing.datasource.user", "sa"),
                config.getString("billing.datasource.password", ""),
                config.getInt("billing.pool.max", 5)
        );
        MigrationRunner migration = new MigrationRunner(pool, config.getInt("billing.migration.seconds", 8));
        Thread migrationThread = new Thread(migration::run, "billing-migration");
        migrationThread.start();

        HealthHandlers health = new HealthHandlers(pool, migration);
        InvoiceHandlers invoices = new InvoiceHandlers(pool);
        BillingHttpServer server = new BillingHttpServer(config.getInt("billing.server.port", 8080), health, invoices);
        server.start();
        migrationThread.join();
        while (true) {
            Thread.sleep(3_600_000L);
        }
    }
}
