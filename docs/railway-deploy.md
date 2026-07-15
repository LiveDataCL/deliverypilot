# Deploy a Railway

Este documento es una guía manual. El deploy lo ejecuta el dueño del proyecto — Claude
no crea el proyecto de Railway ni introduce secretos reales.

## 1. Crear el proyecto

1. En Railway, `New Project` → `Deploy from GitHub repo` → seleccionar este repositorio.
2. Crear dos entornos: `dev` y `prod` (Railway → Settings → Environments).
3. Agregar servicios `PostgreSQL` y `Redis` desde el marketplace de plantillas de Railway
   en cada entorno.

## 2. Variables de entorno del servicio backend

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

## 3. Deploy automático desde `main`

Railway despliega automáticamente en cada push a `main` una vez conectado el repo
(Settings → Deploy Triggers). No requiere configuración de CI adicional para el deploy
en sí — el workflow de GitHub Actions (`.github/workflows/backend-tests.yml`) solo
corre tests, nunca despliega.

## 4. Migraciones en producción

Railway ejecuta el `Start Command` del servicio. Configurar como release step (o al
inicio del start command) `poetry run alembic upgrade head` antes de levantar `uvicorn`,
para que cada deploy aplique migraciones pendientes automáticamente.

## 5. Verificar

- `https://<servicio>.up.railway.app/docs` debe responder con el Swagger UI.
- Confirmar en los logs de Railway que Sentry se inicializó sin errores.
