# Digital debt

Tracks technical debt, deferred decisions, and pending follow-ups that would
otherwise only live in chat history. Scoped to debt/pending items only — not
a general project doc (see `SPEC.md`/`CLAUDE.md` for those). Every entry: date
discovered, what it is, current status, relevant IDs. Update this file
whenever new debt is identified or an existing entry changes status — don't
let it go stale.

## Open

### asyncpg fails to connect on Windows (local dev blocked)

- **Discovered:** during Fase 0 local pytest verification; reconfirmed 2026-07-17
  against a live Neon endpoint.
- **What:** `asyncpg` connections raise `ConnectionDoesNotExistError` /
  `ConnectionResetError [WinError 10054]` on this Windows machine — reproduces
  against both local Postgres (via pytest/`conftest.py`) and a freshly created
  Neon branch (via a standalone script, no pytest involved). `psql` and
  `psycopg2` both connect cleanly to the same Neon endpoint from the same
  machine, ruling out network/TLS/Neon-side causes. Root cause isolated to
  `asyncpg` on Windows specifically, but not yet identified further.
- **Status:** Blocking local dev on Windows specifically. CI (Linux) is
  unaffected — GitHub Actions runs green. The `WindowsSelectorEventLoopPolicy`
  fix (commit `82bb250`) did not resolve it.
- **Impact:** The app's real runtime (`app/db/base.py`, built on `asyncpg`)
  still cannot run locally on this machine until resolved.

### deliverypilot_app has BYPASSRLS=true on both Neon branches

- **Discovered:** 2026-07-17, during Neon provisioning step 5 (role safety check).
- **What:** `neonctl roles create` provisioned `deliverypilot_app` with
  `BYPASSRLS=true` on both branches (`rolsuper=False` was correct, but
  `BYPASSRLS` alone is just as fatal — it skips RLS unconditionally, same as
  a superuser, even with `FORCE ROW LEVEL SECURITY`). Attempted fix via
  `ALTER ROLE deliverypilot_app NOBYPASSRLS;` (connected as `neondb_owner`)
  failed: `permission denied to alter role` — `neondb_owner` is not `ADMIN`
  on `deliverypilot_app` because Neon's control-plane role creation doesn't
  chain Postgres role-ownership the way SQL `CREATE ROLE` would. `neonctl`
  has no CLI subcommand to alter an existing role's attributes (`roles
  create`/`list`/`delete` only).
- **Status:** Blocking. Provisioning is paused at step 5/6 until this has a
  fix path — candidates not yet tried: Neon dashboard UI (may expose a
  role-edit control the CLI doesn't), Neon support, or provisioning
  `deliverypilot_app` a different way (e.g. via SQL as `neondb_owner`
  instead of `neonctl roles create`, so ownership chains correctly).
- **IDs:** Project `deliverypilot` (`red-heart-43608078`), org `LiveData`
  (`org-aged-rain-76663648`). Branch `main` (endpoint `ep-billowing-grass-au0fhjiy`).
  Branch `test` (`br-bitter-base-au9qdf8c`, endpoint `ep-divine-grass-au5hsmgx`).
  Roles: `neondb_owner` (default/bootstrap), `deliverypilot_app` (app role).
  Database: `neondb` (both branches).

### CLAUDE.md needs the Neon BYPASSRLS-default note

- **Discovered:** 2026-07-17.
- **What:** `neonctl roles create` defaults new roles to `BYPASSRLS=true`,
  unlike vanilla Postgres's `NOSUPERUSER`-only default. Every Neon-provisioned
  role must be verified with the `rolsuper`/`rolbypassrls` query before being
  trusted — on this project or any other.
- **Status:** Deferred until the BYPASSRLS blocker above is resolved, then add
  to `CLAUDE.md` alongside the existing two-role pattern documentation.

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
