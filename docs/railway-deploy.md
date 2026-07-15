# Deploy a Railway

Este documento es una guía manual. El deploy lo ejecuta el dueño del proyecto — Claude
no crea el proyecto de Railway ni introduce secretos reales.

## 1. Crear el proyecto

1. En Railway, `New Project` → `Deploy from GitHub repo` → seleccionar este repositorio.
2. Crear dos entornos: `dev` y `prod` (Railway → Settings → Environments).
3. Agregar servicios `PostgreSQL` y `Redis` desde el marketplace de plantillas de Railway
   en cada entorno.

## 2. ⚠️ CRÍTICO — Degradar el rol de Postgres antes de conectar el backend

**No saltarse este paso.** El servicio PostgreSQL de Railway (igual que la imagen oficial
de Docker) crea el usuario inicial como **superusuario** durante la inicialización del
cluster. Un superusuario **se salta Row-Level Security incondicionalmente**, incluso en
tablas con `FORCE ROW LEVEL SECURITY` (migración `0002_row_level_security.py`). Si el
backend se conecta con ese rol tal cual, **todas las políticas RLS quedan inertes en
producción** — el aislamiento de tenant pasaría a depender solo del filtro de la capa de
aplicación (`tenant_query()`), sin la defensa de base de datos que se diseñó para cubrir
justo el caso de que ese filtro se olvide en algún endpoint futuro.

**Antes de que el backend reciba tráfico real:**

1. Abrir la consola/`psql` de Railway para el servicio Postgres (Railway → servicio
   Postgres → "Connect" / "Query").
2. Ejecutar, reemplazando `<rol>` por el usuario real que Railway generó (visible en
   `DATABASE_URL`):
   ```sql
   ALTER ROLE <rol> NOSUPERUSER;
   ```
3. Verificar que quedó aplicado:
   ```sql
   SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = '<rol>';
   -- ambas columnas deben quedar en 'f'
   ```

Este mismo chequeo corre automáticamente en la suite de tests (`tests/conftest.py`,
`_assert_db_role_is_not_superuser`) y falla con un mensaje explícito si el rol de
`TEST_DATABASE_URL`/`DATABASE_URL` es superusuario — pero eso solo protege dev/CI. En
Railway hay que hacerlo a mano, una vez por entorno (`dev` y `prod` tienen roles
distintos).

## 3. Variables de entorno del servicio backend

Copiar los nombres de `backend/.env.example` y completar los valores reales en Railway
(Settings → Variables). Nunca commitear estos valores.

| Variable | Origen |
|---|---|
| `DATABASE_URL` | Railway lo inyecta automáticamente al vincular el servicio Postgres |
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
para que cada deploy aplique migraciones pendientes automáticamente.

## 6. Verificar

- `https://<servicio>.up.railway.app/docs` debe responder con el Swagger UI.
- Confirmar en los logs de Railway que Sentry se inicializó sin errores.
- Confirmar que el paso 2 (degradar el rol) quedó hecho en **ambos** entornos.
