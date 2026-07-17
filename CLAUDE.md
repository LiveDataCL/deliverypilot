# CLAUDE.md — Reglas de trabajo para DeliveryPilot

> Este archivo son las **reglas de la casa**. `SPEC.md` es el **plan** (qué construir y en qué orden); este archivo es **cómo** construirlo. Lee ambos completos al iniciar cada sesión. Si hay conflicto entre este archivo y una instrucción puntual mía en el chat, pregúntame antes de continuar.

---

## 0. Protocolo de arranque de cada sesión

1. Lee `SPEC.md` y `CLAUDE.md` completos antes de escribir una sola línea.
2. Identifica en qué fase estamos (la primera tarea sin `[x]` en `SPEC.md`).
3. Si es la primera vez que trabajas en el repo: **no escribas código todavía**. Confírmame que entendiste el modelo multi-tenant, hazme las preguntas sobre decisiones no cubiertas, y propón la estructura de archivos de la fase actual para que la apruebe.
4. Espera mi aprobación explícita antes de implementar.

---

## 1. Auditoría primero (regla innegociable)

Esta es la regla más importante del proyecto.

- **Antes de modificar cualquier archivo, léelo COMPLETO.** No edites por parches sobre un archivo que no revisaste entero.
- **Antes de crear un archivo nuevo, verifica que no exista ya** algo equivalente que debas extender en su lugar.
- **Antes de tocar el modelo de datos, revisa TODOS los modelos existentes** y las migraciones aplicadas. Un cambio de esquema mal hecho arrastra a todo el sistema.
- Cuando te pida un cambio, primero **dime qué archivos vas a tocar y por qué**, luego procede. Para cambios grandes, espera mi OK.
- Nunca asumas el contenido de un archivo por su nombre. Ábrelo.

Si te encuentras "reescribiendo" mentalmente un requisito para que calce más fácil con lo que ya tienes, detente y pregúntame en vez de improvisar.

---

## 2. Estándares de construcción

Estas son las mismas condiciones que ya aplicamos en BarberPilot. No se negocian por rapidez.

**Elementos definitivos, no provisorios.**
- Nada de mocks, stubs o "TODO: implementar después" en código que se marca como terminado. Si algo queda pendiente, no marques la tarea `[x]`.
- No dejes valores hardcodeados que deberían ser configuración. Todo lo del negocio (precios, métodos de pago, productos) viene de la base de datos, nunca del código.
- No dupliques lógica. Si algo se usa en dos lugares, va a un servicio compartido.

**Escalable desde el día uno.**
- Multi-tenant real: TODA query filtra por `business_id`. No existe una consulta que pueda cruzar datos entre negocios. Esto se testea.
- Diseña pensando en 100 negocios, no en 1. El código del piloto es el mismo código del cliente número 50.
- Índices en toda FK y en toda columna usada para filtrar o buscar (especialmente `business_id`, `phone`, `status`).
- Paginación en todo endpoint que liste. Nunca retornes "todos los registros" sin límite.

**Redundancia y a prueba de fallos.**
- Toda operación externa (geocoding, FCM, OSRM, R2) puede fallar: envuélvela con manejo de error, reintentos con backoff donde aplique, y un fallback claro. El sistema nunca se cae porque Nominatim no respondió.
- El WebSocket del repartidor debe reconectar solo y tener buffer offline: si el repartidor pierde señal, los pings se acumulan y se envían al reconectar. No se pierde el rastro.
- Ninguna falla de un tenant puede afectar a otro.
- Toda transacción de base de datos que toca varias tablas es atómica (o todo, o nada). Un pedido nunca queda a medias.
- Validación en el backend SIEMPRE, aunque el frontend ya valide. El frontend valida por UX; el backend valida por seguridad.

**Trazabilidad total.**
- Todo cambio de estado de un pedido se registra en `order_events` con quién, cuándo y dónde. Nada cambia de estado en silencio.
- Logs estructurados en operaciones críticas (creación de pedido, asignación, cambio de estado, cobro). Nunca loguees secretos ni datos personales completos.

---

## 3. Entorno de desarrollo

El proyecto se construye y prueba **local** contra `docker-compose`. El deploy a Railway lo hago yo al cerrar cada fase.

**Levantar el entorno:**
```bash
docker compose up -d          # Postgres 16 + Redis 7
cd backend
uv sync                       # o poetry install (usa lo que definas en Fase 0 y documéntalo)
alembic upgrade head          # aplica migraciones
python -m app.seed            # carga datos demo (negocio de agua)
uvicorn app.main:app --reload # API en http://localhost:8000/docs
```

**Correr los tests (obligatorio antes de marcar cualquier tarea como terminada):**
```bash
cd backend && pytest
```

**Frontend:**
```bash
cd dispatch-web && npm install && npm run dev
```

Si en la Fase 0 defines una forma distinta de levantar algo, **actualiza esta sección** para que quede documentada.

**⚠️ Provisioning de roles en Neon (u otro proveedor gestionado):** si alguna vez se
crea un rol vía `neonctl roles create` (o el equivalente del dashboard/API), ese rol
queda con `BYPASSRLS=true` por defecto — a diferencia de Postgres plano, donde un
`CREATE ROLE ... NOSUPERUSER` normal no trae `BYPASSRLS`. Un rol con `BYPASSRLS` se
salta RLS igual que un superusuario, incluso con `FORCE ROW LEVEL SECURITY`. **Verificar
siempre `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = '<rol>'` después de
crear cualquier rol en Neon**, antes de confiarle tráfico de la app — ambas columnas deben
quedar en `false`. Si sale en `true`, no se puede corregir con `ALTER ROLE ...
NOBYPASSRLS` (el rol dueño por defecto de Neon no tiene `ADMIN OPTION` sobre roles creados
por el control-plane, así que tampoco `DROP OWNED BY`/`DROP ROLE` funcionan): hay que
borrar el rol vía `neonctl roles delete` y recrearlo con `CREATE ROLE` plano por SQL,
conectado como el rol dueño (`neondb_owner` u equivalente), para que la propiedad quede
encadenada correctamente desde el inicio. Incidente completo documentado en
`docs/digital-debt.md`.

---

## 4. Reglas de código

- **Idioma:** código, variables y comentarios en inglés; textos visibles al usuario en español de Chile, centralizados (nada de strings sueltos en JSX).
- **Backend:** FastAPI + SQLAlchemy 2.0 async + Pydantic v2. Type hints en todo. Servicios con la lógica de negocio; los routers solo orquestan.
- **Migraciones:** nunca edites una migración ya aplicada. Siempre una revisión Alembic nueva. Nunca modifiques el esquema con SQL suelto.
- **Zona horaria:** todo se guarda en UTC. Conversión a `America/Santiago` solo al presentar.
- **Dinero:** montos en enteros CLP, sin decimales. Nunca uses float para dinero.
- **Errores de API:** formato consistente `{"detail": str, "code": str}`.
- **Secretos:** solo por variables de entorno. Jamás en el repo, ni en commits, ni en logs. Si necesitas una credencial que no tienes, pídemela; no inventes ni pongas un placeholder que parezca real.

---

## 5. Tests mínimos (no se marca fase completa sin esto)

- Auth y emisión/refresh de tokens.
- **Aislamiento de tenant:** un usuario del negocio A recibe 403/404 al pedir recursos del negocio B. Este test es obligatorio y no se borra nunca.
  - **Checklist de revisión para todo router/endpoint nuevo que toque una tabla con `business_id`:** confirmar que pasa por `get_tenant_context` (o llama a `set_tenant_session` explícitamente) antes de la primera query. RLS es la red de seguridad — si se olvida el `tenant_query()` de la capa de aplicación, Postgres bloquea igual (0 filas), pero eso se ve como un bug funcional silencioso, no como una fuga de datos. Revisar esto explícitamente en cada PR de un endpoint nuevo, no asumir que RLS lo cubre solo.
- Máquina de estados del pedido: transiciones válidas permitidas, inválidas rechazadas.
- Servicio de pricing: aplicación correcta de tramos por volumen.
- Servicio de recálculo del pedido habitual.
- Endpoint `/prefill` de autollenado.

No perseguimos 100% de cobertura. Perseguimos que lo crítico no se rompa en silencio.

---

## 6. Flujo de trabajo con Git

- Un commit por tarea lógica completada, en formato convencional: `feat:`, `fix:`, `chore:`, `test:`, `refactor:`.
- El mensaje describe el *qué* y el *por qué*, no solo el archivo tocado.
- Al terminar una tarea: corre los tests → si pasan, marca `[x]` en `SPEC.md` → commit.
- No mezcles varias tareas no relacionadas en un mismo commit.
- Rama `main` siempre en estado desplegable.

---

## 7. Ritmo y límites (qué NO hacer sin preguntar)

- **No avances de fase** sin que yo confirme que se cumplen los criterios de aceptación de la fase actual. Al terminar una fase, muéstrame los criterios y cómo los verificaste, y espera mi OK.
- **No cambies el stack** (sección 2 de SPEC.md) ni agregues dependencias nuevas sin justificármelo y esperar aprobación.
- **No tomes decisiones de arquitectura no cubiertas** improvisando. Cuando la spec no diga algo, propón la opción más simple que no bloquee el escalamiento multi-tenant y pregúntame antes de implementarla si es relevante.
- **No borres ni reescribas** trabajo existente para "ordenar" sin avisarme primero qué vas a cambiar.
- **No inventes datos de negocio.** Usa el seed. Si necesitas un caso de prueba, créalo en el seed, no hardcodeado.
- Si una tarea te parece mal planteada o ves un riesgo, dímelo. Prefiero una objeción a tiempo que un error construido prolijamente.

---

## 8. Contexto del proyecto (para que no lo pierdas)

- **Producto:** SaaS multi-tenant de gestión de entregas en tiempo real (clon de Shipday) con autollenado de pedidos recurrentes y recompra proactiva.
- **Piloto:** distribuidora de agua purificada en Santiago, Chile. Cliente fundador.
- **Diferenciador:** el autollenado por teléfono y la recompra proactiva. Eso es lo que hace único al producto; cuídalo.
- **Regla de oro del negocio:** la página de Catálogo y Personal es la fuente de verdad. Todo lo demás se alimenta de ella.
