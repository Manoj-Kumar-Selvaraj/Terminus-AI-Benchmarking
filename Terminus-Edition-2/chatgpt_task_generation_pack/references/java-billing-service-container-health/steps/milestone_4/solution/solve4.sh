#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash /steps/milestone_3/solution/solve3.sh
cat > /app/src/main/java/com/billing/http/HealthHandlers.java <<'EOF'
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
EOF
cat > /app/deploy/kube/billing-deployment.yaml <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: billing-service
spec:
  replicas: 1
  template:
    spec:
      containers:
        - name: billing-service
          image: billing-service:1.4.2
          resources:
            limits:
              memory: 256Mi
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            initialDelaySeconds: 2
            periodSeconds: 5
          startupProbe:
            httpGet:
              path: /health/live
              port: 8080
            periodSeconds: 2
            failureThreshold: 10
          livenessProbe:
            httpGet:
              path: /health/live
              port: 8080
            initialDelaySeconds: 12
            periodSeconds: 5
            failureThreshold: 3
EOF
bash /app/scripts/compile_service.sh
