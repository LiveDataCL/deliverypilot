# DeliveryPilot

SaaS multi-tenant de gestión de entregas en tiempo real (clon funcional de Shipday) con autollenado de pedidos recurrentes y recompra proactiva. Ver `deliverypilot-spec-claude-code.md` (fases y modelo de datos) y `CLAUDE.md` (reglas de trabajo) antes de tocar el código.

## Estructura

```
backend/         # FastAPI + SQLAlchemy 2.0 async + Alembic
dispatch-web/    # React + Vite + TypeScript (panel de despacho + tracking público)
driver-app/      # Flutter (repartidor) — se construye en Fase 1
docs/            # documentación operativa (deploy, build de APK)
```

## Levantar el entorno local

Requisitos: Python 3.12, [Poetry](https://python-poetry.org/), Docker.

```bash
docker compose up -d              # Postgres 16 + Redis 7

cd backend
poetry install
cp .env.example .env              # completar JWT_SECRET, etc.
poetry run alembic upgrade head
poetry run python -m app.seed
poetry run uvicorn app.main:app --reload   # http://localhost:8000/docs
```

## Tests (obligatorio antes de marcar una tarea como terminada)

```bash
cd backend
poetry run pytest
```

Los tests corren contra una base de datos Postgres real (no SQLite) porque Row-Level
Security no se puede validar sin Postgres. Requieren `docker compose up -d` corriendo.

## Frontend

```bash
cd dispatch-web
npm install
npm run dev
```

## Deploy

El deploy a Railway (proyecto, variables de entorno, conexión del repo) lo hace el
dueño del proyecto manualmente al cerrar cada fase — ver `docs/railway-deploy.md`.
