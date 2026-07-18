# Digital debt

Tracks technical debt, deferred decisions, and pending follow-ups that would
otherwise only live in chat history. Scoped to debt/pending items only — not
a general project doc (see `SPEC.md`/`CLAUDE.md` for those). Every entry: date
discovered, what it is, current status, relevant IDs. Update this file
whenever new debt is identified or an existing entry changes status — don't
let it go stale.

## Open

### asyncpg fails to connect on Windows (local dev blocked) — partially narrowed, not resolved

- **Discovered:** during Fase 0 local pytest verification; reconfirmed 2026-07-17
  against a live Neon endpoint; narrowed further 2026-07-17 during Neon
  provisioning.
- **What:** `asyncpg` connections raise `ConnectionDoesNotExistError` /
  `ConnectionResetError [WinError 10054]` on this Windows machine when
  `asyncpg.connect()` is called directly with a raw DSN string — reproduces
  against both local Postgres (via pytest/`conftest.py`, back during Fase 0)
  and a freshly created Neon branch (via a standalone diagnostic script, no
  pytest involved). `psql` and `psycopg2` both connect cleanly to the same
  Neon endpoint from the same machine, ruling out network/TLS/Neon-side
  causes — isolated to `asyncpg` on Windows specifically.
  **New evidence (2026-07-17):** the app's *actual* connection path —
  SQLAlchemy's async engine → asyncpg dialect, which calls `asyncpg.connect()`
  with explicit keyword arguments rather than a raw DSN string — did **not**
  reproduce the bug. `alembic upgrade head` and the full `pytest -v` suite
  (34/34 passed, including RLS/tenant-isolation/driver-rejection tests) both
  ran clean against the Neon `test`/`main` branches on this same machine. This
  suggests the bug may be specific to the raw-DSN-string calling convention,
  not the keyword-argument one SQLAlchemy uses — but this is **not yet
  re-tested against local Postgres** via the app's real code path (only ever
  re-tested against Neon so far), so it's still open whether local dev is
  actually unblocked or whether Neon just happens not to trigger it.
- **Status:** Open, narrowed. Not blocking Neon-backed dev/test on this
  machine (confirmed working). Still unconfirmed whether local
  Postgres-backed dev/test works again — needs a real re-test against
  `localhost` Postgres via `pytest`/`alembic` (not a bare diagnostic script)
  before this can be marked resolved for local dev. CI (Linux) was never
  affected — GitHub Actions runs green throughout.
- **Impact:** Neon-backed dev/test work (this session's provisioning, and
  presumably Fase 1+ going forward) is unblocked. Local Postgres-backed dev
  is unconfirmed either way.

## Resolved

### deliverypilot_app had BYPASSRLS=true on both Neon branches

- **Discovered:** 2026-07-17, during Neon provisioning step 5 (role safety check).
  **Resolved:** 2026-07-17, same day.
- **What:** `neonctl roles create` provisioned `deliverypilot_app` with
  `BYPASSRLS=true` on both branches (`rolsuper=False` was correct, but
  `BYPASSRLS` alone is just as fatal — it skips RLS unconditionally, same as
  a superuser, even with `FORCE ROW LEVEL SECURITY`). Three separate SQL
  angles were tried, connected as `neondb_owner`, and all three hit the same
  structural wall: `ALTER ROLE deliverypilot_app NOBYPASSRLS;` failed
  (`permission denied to alter role`); `DROP OWNED BY deliverypilot_app;`
  failed (`permission denied to drop objects` — requires membership/privileges
  of the target role); after switching to explicit `REVOKE`s from the grantor
  side (which did succeed) plus `DROP ROLE deliverypilot_app;`, the `DROP
  ROLE` itself failed (`permission denied to drop role`). All three errors
  boil down to the same cause: `neondb_owner` has `CREATEROLE` but not
  `ADMIN OPTION` on this specific role, because Neon's control-plane role
  creation (`neonctl roles create`) doesn't chain Postgres role-ownership the
  way SQL `CREATE ROLE` would — not a SQL problem to keep probing, since the
  block is on role-management statements themselves. `neonctl` has no CLI
  subcommand to alter an existing role's attributes (`roles
  create`/`list`/`delete` only). The Neon dashboard's "Connect" dialog was
  checked too (user-confirmed dead end): it only offers "Reset password", no
  attribute editor.
- **Fix:** deleted `deliverypilot_app` on each branch via `neonctl roles
  delete` (a control-plane action, not blocked by SQL permissions), then
  recreated it via plain SQL `CREATE ROLE deliverypilot_app LOGIN PASSWORD
  '...' NOSUPERUSER NOBYPASSRLS;` connected as `neondb_owner` — this makes
  `neondb_owner` the true SQL owner from the start, sidestepping the
  control-plane/SQL ownership mismatch entirely. Redid the `GRANT USAGE ON
  SCHEMA public` + both `ALTER DEFAULT PRIVILEGES` statements against the
  fresh role. Verified via direct `rolsuper`/`rolbypassrls` query on both
  branches (`False`/`False`), and further confirmed end-to-end by a full
  `pytest -v` run (34/34 passed) against the `test` branch, including the RLS
  tests that this exact bug would have made pass for the wrong reason.
- **IDs:** Project `deliverypilot` (`red-heart-43608078`), org `LiveData`
  (`org-aged-rain-76663648`). Branch `main` (endpoint `ep-billowing-grass-au0fhjiy`).
  Branch `test` (`br-bitter-base-au9qdf8c`, endpoint `ep-divine-grass-au5hsmgx`).
  Roles: `neondb_owner` (default/bootstrap), `deliverypilot_app` (app role,
  now SQL-owned by `neondb_owner`, `rolsuper=False`/`rolbypassrls=False` on
  both branches). Database: `neondb` (both branches).

### CLAUDE.md needed the Neon BYPASSRLS-default note

- **Discovered:** 2026-07-17. **Resolved:** 2026-07-17, same day.
- **What:** `neonctl roles create` defaults new roles to `BYPASSRLS=true`,
  unlike vanilla Postgres's `NOSUPERUSER`-only default. Every Neon-provisioned
  role must be verified with the `rolsuper`/`rolbypassrls` query before being
  trusted — on this project or any other.
- **Fix:** added a note under CLAUDE.md §3 (Entorno de desarrollo) documenting
  the gotcha and the verification/fallback procedure, cross-referenced to this
  file for the full incident detail.

### MapaPage's "pedidos activos" reuses GET /orders?on_date=today with client-side status filtering

- **Discovered:** 2026-07-17, building the FCM/WebSocket/map checkpoint.
- **What:** The live map (`dispatch-web/src/features/mapa/MapaPage.tsx`)
  needs to show active (non-terminal) orders as markers. `GET /orders` only
  supports a single `status` value, not a list, so there's no server-side
  way to ask for "every non-terminal order" in one call. `MapaPage` instead
  calls `listOrders({ on_date: today })` (the same call `PedidosPage`
  already makes) and filters out `entregado`/`cancelado`/`fallido`
  client-side.
- **Decision:** deliberate simplification, not a missing endpoint no one
  noticed. Reasonable at current pilot volume (one business, a handful of
  orders/day) — fetching a full day's orders and filtering in the browser
  is cheap. Revisit (either a `status__in` list param or a dedicated
  `GET /orders/active` endpoint) if daily order volume ever grows enough
  that shipping a full day's order rows to render a handful of map markers
  becomes the wrong tradeoff.
- **Status:** Open, low priority. No user-facing symptom today.

## Deferred (explicit user choice, not forgotten)

### Passwords/keys to rotate before production launch

- **Discovered:** 2026-07-17, during Neon provisioning.
- **What:**
  - `neondb_owner` password on the `main` branch — exposed in plaintext in
    `neonctl projects create` CLI output.
  - `neondb_owner` password on the `test` branch — inherited copy of the same
    password (Neon branches copy-on-write parent roles at creation time).
  - `NEON_API_KEY` — exposed in plaintext via `neonctl roles --help`'s
    `--api-key` default-value echo. **Not deferred, resolved same-day**: old
    key revoked, new key generated, set via `setx`, verified in a fresh
    window, VS Code fully restarted — confirmed 2026-07-17.
- **Status:** Role passwords (`neondb_owner` on `main`/`test`) still deferred
  by explicit user choice until before production launch. API key rotation
  is resolved.

### Redis pub/sub deferred in favor of in-process WebSocket broadcast

- **Discovered:** 2026-07-17, during FCM/WebSocket/map scoping for Fase 1.
- **What:** SPEC.md §2/§3 documents Redis 7 for the WebSocket pub/sub layer
  (`driver:{id}:pos` JSON key with 120s TTL, `business:{id}:events` pub/sub
  channel) — needed to broadcast across multiple backend processes. Actual
  current scale is a single Railway backend instance, one pilot business,
  1-3 drivers — no horizontal scaling yet. The `redis` dependency
  (`pyproject.toml`), the `redis` service in `docker-compose.yml`, and the
  `redis_url` config field all already exist from the Fase 0 stack setup,
  but no code anywhere actually connects to Redis.
- **Decision:** built an in-process `ConnectionManager`
  (`app/core/ws_manager.py`) that holds WebSocket connections and each
  driver's last-known position in memory, keyed by `business_id`,
  broadcasting directly with no pub/sub hop. Its `broadcast(business_id,
  event)` method signature is kept close to what a Redis-backed version
  would need, so swapping the internals to `redis.publish()`/`subscribe()`
  later is a small, mechanical change, not a rewrite.
- **Tradeoff accepted:** in-memory position/connection state resets on every
  backend restart or redeploy — a dispatch client reconnecting right after a
  deploy sees an empty position cache until the next round of driver pings
  arrives. Acceptable at current scale.
- **Status:** Deferred, explicit user choice — not a bug, a scale-appropriate
  simplification. Revisit when Railway actually runs 2+ backend instances,
  since multi-instance broadcast is the only thing here that genuinely
  requires Redis. The Railway Redis add-on for prod is still not
  provisioned; not needed until this is revisited.
