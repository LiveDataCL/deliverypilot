-- The official postgres image's bootstrap role (POSTGRES_USER) CANNOT have its
-- own SUPERUSER attribute revoked — Postgres refuses:
--   ERROR: permission denied to alter role
--   DETAIL: The bootstrap user must have the SUPERUSER attribute.
-- Since superusers bypass Row-Level Security unconditionally (FORCE ROW LEVEL
-- SECURITY only affects a table's owner, and does not override superuser
-- status), the app must never run its everyday queries as the bootstrap role.
--
-- Two roles instead:
--   - deliverypilot (bootstrap, superuser): owns every table, runs migrations
--     (CREATE TABLE/TYPE, ALTER TABLE ... FORCE ROW LEVEL SECURITY, CREATE
--     POLICY). Used only as MIGRATIONS_DATABASE_URL / TEST_MIGRATIONS_DATABASE_URL.
--   - deliverypilot_app (ordinary, non-superuser): what the app and the test
--     suite connect as for real queries. Since it does NOT own the tables,
--     Row-Level Security applies to it normally. Used as DATABASE_URL /
--     TEST_DATABASE_URL.
--
-- Runs once, on first cluster initialization only (docker-entrypoint-initdb.d
-- scripts do not re-run against an already-initialized data volume). If you
-- already had a postgres_data volume before this file existed, either wipe it
-- (`docker compose down -v`, losing local seed data) or run the statements
-- below by hand once against it.

CREATE ROLE deliverypilot_app LOGIN PASSWORD 'deliverypilot_app' NOSUPERUSER;

-- deliverypilot (POSTGRES_DB) — the dev database. Tables don't exist yet at
-- first-init time (Alembic creates them later, as the bootstrap role), so
-- default privileges make every future object the bootstrap role creates in
-- this schema automatically grant these to deliverypilot_app too.
GRANT USAGE ON SCHEMA public TO deliverypilot_app;
-- TRUNCATE is included for app/seed.py's local-dev reset (TRUNCATE ...
-- RESTART IDENTITY CASCADE) — TRUNCATE bypasses RLS entirely regardless of
-- who runs it, same as it would for any other role.
ALTER DEFAULT PRIVILEGES FOR ROLE deliverypilot IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO deliverypilot_app;
ALTER DEFAULT PRIVILEGES FOR ROLE deliverypilot IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO deliverypilot_app;

-- deliverypilot_test — a second database in the same local cluster, used only
-- when running pytest (backend/.env.example's TEST_* variables). Repeats the
-- same grants there since default privileges are per-database.
CREATE DATABASE deliverypilot_test OWNER deliverypilot;

\connect deliverypilot_test

GRANT USAGE ON SCHEMA public TO deliverypilot_app;
-- TRUNCATE is included for app/seed.py's local-dev reset (TRUNCATE ...
-- RESTART IDENTITY CASCADE) — TRUNCATE bypasses RLS entirely regardless of
-- who runs it, same as it would for any other role.
ALTER DEFAULT PRIVILEGES FOR ROLE deliverypilot IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO deliverypilot_app;
ALTER DEFAULT PRIVILEGES FOR ROLE deliverypilot IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO deliverypilot_app;
