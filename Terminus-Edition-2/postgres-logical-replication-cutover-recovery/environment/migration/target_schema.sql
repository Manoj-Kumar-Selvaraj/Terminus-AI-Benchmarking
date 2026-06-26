-- schema-version: 2
CREATE TABLE customer_profile (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(40) NOT NULL,
    middle_name VARCHAR(80),
    email TEXT NOT NULL
);
CREATE TABLE contact_method (
    contact_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    kind VARCHAR(16) NOT NULL,
    value VARCHAR(128) NOT NULL,
    verified_at TIMESTAMPTZ
);
CREATE TABLE communication_preference (
    preference_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    channel VARCHAR(16) NOT NULL,
    enabled BOOLEAN NOT NULL,
    quiet_hours_start TEXT NOT NULL DEFAULT '00:00',
    quiet_hours_end TEXT
);
CREATE TABLE account_status (
    status_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(8) NOT NULL CHECK (status IN ('ACTIVE','PAUSED')),
    changed_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE profile_audit (
    audit_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    payload VARCHAR(256) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
