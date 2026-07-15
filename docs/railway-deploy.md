# Deploy a Railway

Este documento es una guía manual. El deploy lo ejecuta el dueño del proyecto — Claude
no crea el proyecto de Railway ni introduce secretos reales.

## 1. Crear el proyecto

1. En Railway, `New Project` → `Deploy from GitHub repo` → seleccionar este repositorio.
2. Crear dos entornos: `dev` y `prod` (Railway → Settings → Environments).
3. Agregar servicios `PostgreSQL` y `Redis` desde el marketplace de plantillas de Railway
   en cada entorno.

## 2. ⚠️ CRÍTICO — Crear un rol de aplicación antes de conectar el backend

**No saltarse este paso.** El servicio PostgreSQL de Railway (igual que la imagen oficial
de Docker) crea el usuario inicial como el **rol bootstrap**, y Postgres exige que ese
rol específico mantenga el atributo SUPERUSER — ni siquiera se puede revocárselo a sí
mismo (`ALTER ROLE <rol> NOSUPERUSER` falla con *"the bootstrap user must have the
SUPERUSER attribute"*). Un superusuario **se salta Row-Level Security
incondicionalmente**, incluso en tablas con `FORCE ROW LEVEL SECURITY` (migración
`0002_row_level_security.py`). Si el backend se conecta con ese rol tal cual, **todas las
políticas RLS quedan inertes en producción** — el aislamiento de tenant pasaría a
depender solo del filtro de la capa de aplicación (`tenant_query()`), sin la defensa de
base de datos que se diseñó para cubrir justo el caso de que ese filtro se olvide en
algún endpoint futuro.

La solución no es degradar el rol bootstrap (no se puede) sino usar **dos roles**:
el bootstrap sigue siendo superusuario y corre solo las migraciones; un rol nuevo,
ordinario, es el que el backend usa para todo el tráfico real.

**Antes de que el backend reciba tráfico real, por cada entorno (`dev` y `prod`):**

1. Abrir la consola/`psql` de Railway para el servicio Postgres (Railway → servicio
   Postgres → "Connect" / "Query").
2. Ejecutar (cambiar la contraseña por algo generado, no dejar el valor de ejemplo):
   ```sql
   CREATE ROLE deliverypilot_app LOGIN PASSWORD 'una-contrasena-generada-distinta' NOSUPERUSER;
   GRANT USAGE ON SCHEMA public TO deliverypilot_app;
   ALTER DEFAULT PRIVILEGES FOR ROLE <rol_bootstrap> IN SCHEMA public
       GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO deliverypilot_app;
   ALTER DEFAULT PRIVILEGES FOR ROLE <rol_bootstrap> IN SCHEMA public
       GRANT USAGE, SELECT ON SEQUENCES TO deliverypilot_app;
   ```
   Reemplazar `<rol_bootstrap>` por el usuario real que Railway generó (visible en la
   variable que Railway inyecta al vincular el servicio Postgres — normalmente
   `PGUSER` o el usuario embebido en `DATABASE_URL`/`DATABASE_PUBLIC_URL`). Este paso
   debe correr **antes** de que Alembic cree las tablas (las migraciones corren como
   el rol bootstrap, así que los privilegios por defecto alcanzan a las tablas que cree).
3. Verificar que el rol nuevo no es superusuario:
   ```sql
   SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'deliverypilot_app';
   -- ambas columnas deben quedar en 'f'
   ```

Este mismo chequeo corre automáticamente en la suite de tests (`tests/conftest.py`,
`_assert_db_role_is_not_superuser`) y falla con un mensaje explícito si el rol de
`TEST_DATABASE_URL`/`DATABASE_URL` es superusuario — pero eso solo protege dev/CI. En
Railway hay que crear el rol a mano, una vez por entorno.

## 3. Variables de entorno del servicio backend

Copiar los nombres de `backend/.env.example` y completar los valores reales en Railway
(Settings → Variables). Nunca commitear estos valores.

| Variable | Origen |
|---|---|
| `DATABASE_URL` | Armar a mano con las credenciales de `deliverypilot_app` (paso 2) y el mismo host/puerto/base de datos que Railway usa para Postgres |
| `MIGRATIONS_DATABASE_URL` | La que Railway inyecta automáticamente al vincular el servicio Postgres (rol bootstrap) — **nunca** usar este valor como `DATABASE_URL` |
| `REDIS_URL` | Railway lo inyecta automáticamente al vincular el servicio Redis |
| `JWT_SECRET` | Generar con `openssl rand -hex 32`, uno distinto por entorno |
| `FCM_CREDENTIALS_JSON` | Service account de Firebase (Fase 1) |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` / `R2_ENDPOINT` | Cloudflare R2 (Fase 3) |
| `SENTRY_DSN` | Proyecto Sentry (backend) |
| `ENVIRONMENT` | `dev` o `prod` |

## 4. Deploy automático desde `main`

Railway despliega automáticamente en cada push a `main` una vez conectado el repo
(Settings → Deploy Triggers). No requiere configuración de CI adicional para el deploy
en sí — el workflow de GitHub Actions (`.github/workflows/backend-tests.yml`) solo
corre tests, nunca despliega.

## 5. Migraciones en producción

Railway ejecuta el `Start Command` del servicio. Configurar como release step (o al
inicio del start command) `poetry run alembic upgrade head` antes de levantar `uvicorn`,
para que cada deploy aplique migraciones pendientes automáticamente. Alembic lee
`MIGRATIONS_DATABASE_URL` (no `DATABASE_URL`) — confirmar que esa variable esté seteada
con las credenciales del rol bootstrap, o las migraciones fallarán por falta de
privilegios (el rol de aplicación no puede crear tablas ni políticas RLS).

## 6. Verificar

- `https://<servicio>.up.railway.app/docs` debe responder con el Swagger UI.
- Confirmar en los logs de Railway que Sentry se inicializó sin errores.
- Confirmar que el paso 2 (crear `deliverypilot_app` y sus privilegios) quedó hecho en
  **ambos** entornos, y que `DATABASE_URL` apunta a ese rol, no al bootstrap.
