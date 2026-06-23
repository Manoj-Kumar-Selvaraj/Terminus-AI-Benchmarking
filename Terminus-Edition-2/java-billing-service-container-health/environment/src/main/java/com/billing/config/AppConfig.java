package com.billing.config;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class AppConfig {
    private final Properties props = new Properties();

    public AppConfig(Path configDir) throws IOException {
        Path properties = configDir.resolve("application.properties");
        try (InputStream in = Files.newInputStream(properties)) {
            props.load(in);
        }
    }

    public String getString(String key, String defaultValue) {
        return props.getProperty(key, defaultValue);
    }

    public int getInt(String key, int defaultValue) {
        String raw = props.getProperty(key);
        if (raw == null || raw.isBlank()) {
            return defaultValue;
        }
        return Integer.parseInt(raw.trim());
    }
}
