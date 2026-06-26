CREATE SUBSCRIPTION profile_migration_sub
CONNECTION 'offline://profile-primary-old'
PUBLICATION profile_migration_pub
WITH (slot_name = 'profile_migration_slot', create_slot = false, copy_data = false);
