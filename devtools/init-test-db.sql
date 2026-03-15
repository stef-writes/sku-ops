-- Auto-create the test database when the dev Postgres container starts.
-- This runs as part of docker-entrypoint-initdb.d (first boot only).
CREATE DATABASE sku_ops_test OWNER sku_ops;
