package com.billing.http;

import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.util.concurrent.Executors;

public final class BillingHttpServer {
    private final int port;
    private final HealthHandlers health;
    private final InvoiceHandlers invoices;
    private HttpServer server;

    public BillingHttpServer(int port, HealthHandlers health, InvoiceHandlers invoices) {
        this.port = port;
        this.health = health;
        this.invoices = invoices;
    }

    public void start() throws IOException {
        server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/health/live", health::handleLive);
        server.createContext("/health/ready", health::handleReady);
        server.createContext("/api/invoices", invoices::handleList);
        server.createContext("/api/charge", invoices::handleCharge);
        server.createContext("/internal/pool", invoices::handlePoolStats);
        server.setExecutor(Executors.newFixedThreadPool(8));
        server.start();
    }

}
