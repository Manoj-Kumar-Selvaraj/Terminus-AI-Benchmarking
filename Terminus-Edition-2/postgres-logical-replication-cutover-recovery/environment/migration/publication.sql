CREATE PUBLICATION profile_migration_pub
FOR TABLE customer_profile, contact_method, account_status, profile_audit, migration_heartbeat
WITH (publish = 'insert, update');
