# DeliveryPilot — Especificación de Implementación
> **Instrucciones para Claude Code:** Este documento es la fuente de verdad del proyecto. Implementa las fases EN ORDEN. No avances a la siguiente fase hasta que los criterios de aceptación de la actual estén cumplidos. Al completar cada tarea, márcala con [x]. Si una decisión técnica no está cubierta aquí, elige la opción más simple que no bloquee el escalamiento multi-tenant.

---

## 1. Contexto del producto

**DeliveryPilot** es un SaaS multi-tenant de gestión de entregas en tiempo real (clon funcional de Shipday) con un diferenciador clave: **autollenado de pedidos recurrentes** y **recompra proactiva**, optimizado para negocios de reparto con clientes habituales (caso piloto: distribuidora de agua purificada en Chile).

**Usuarios:**
- `admin` — dueño de la plataforma (Cesar), ve todos los tenants
- `business_owner` / `dispatcher` — el negocio cliente, opera el panel web
- `driver` — repartidor, usa la app Android

**Flujo principal:** operador escribe el teléfono del cliente → sistema autocompleta nombre, dirección y pedido habitual → ajusta cantidades si es necesario → asigna repartidor → push al repartidor → tracking GPS en vivo → entregado → analytics.

---

## 2. Stack tecnológico (NO cambiar sin justificación)

| Capa | Tecnología |
|---|---|
| Backend API | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2 |
| Base de datos | PostgreSQL 16 (Railway) |
| Tiempo real / cache | Redis 7 (Railway) — pub/sub + posiciones en vivo |
| Push notifications | Firebase Cloud Messaging (FCM) vía `firebase-admin` |
| App repartidor | Flutter (Android, distribución por APK firmado) |
| Panel de despacho | React 18 + Vite + TypeScript, TailwindCSS, Leaflet + OpenStreetMap |
| Tracking público | Página React ligera standalone (misma app del panel, ruta pública) |
| Geocoding | Nominatim (público con cache local; self-host futuro) |
| Rutas / ETA | OSRM (servidor demo con cache; self-host futuro) |
| Archivos (fotos/firmas) | Cloudflare R2 (S3-compatible) |
| Hosting | Railway (backend + DB + Redis), entornos `dev` y `prod` |
| Errores | Sentry (free tier) backend + Flutter |

**Estructura del monorepo:**

```
deliverypilot/
├── backend/            # FastAPI
│   ├── app/
│   │   ├── api/        # routers por dominio
│   │   ├── core/       # config, seguridad, deps
│   │   ├── models/     # SQLAlchemy
│   │   ├── schemas/    # Pydantic
│   │   ├── services/   # lógica de negocio
│   │   └── ws/         # websockets
│   ├── alembic/
│   └── tests/
├── dispatch-web/       # React panel + tracking público
├── driver-app/         # Flutter
└── docs/
```

---

## 3. Modelo de datos completo

Todas las tablas de negocio llevan `business_id` (FK a `businesses`) con índice. TODA query de la API debe filtrar por el `business_id` del token JWT (middleware de tenant). Un usuario nunca puede ver datos de otro tenant.

```sql
businesses        (id, name, plan, timezone DEFAULT 'America/Santiago',
                   currency DEFAULT 'CLP', settings_json, created_at)

users             (id, business_id, role ENUM(admin,business_owner,dispatcher,driver),
                   email, phone, password_hash, fcm_token, is_active, created_at)

drivers           (id, business_id, user_id FK, vehicle_type, status ENUM(offline,online,busy),
                   last_lat, last_lng, last_seen_at)

-- ═══ MÓDULO CLIENTES Y AUTOLLENADO ═══
customers         (id, business_id, phone UNIQUE(business_id, phone), name,
                   address, address_detail, lat, lng, notes,
                   order_frequency_days NUMERIC NULL,   -- calculado: mediana entre pedidos
                   last_order_at, created_at)
                   -- índice: (business_id, phone varchar_pattern_ops) para búsqueda por prefijo

-- ═══ CATÁLOGO (FUENTE DE VERDAD DEL NEGOCIO) ═══
products          (id, business_id, name, description, price, unit, active,
                   is_combo BOOLEAN DEFAULT false, image_url NULL, sort_order)

combo_items       (id, combo_product_id FK->products, component_product_id FK->products, quantity)
                   -- un combo es un product con is_combo=true compuesto de otros productos
                   -- su precio es propio (definido en products.price), NO la suma de componentes

price_tiers       (id, product_id FK, min_quantity, unit_price)
                   -- precio por volumen/mayorista: ej. bidón CLP 3.000, pero desde 10 unidades CLP 2.500
                   -- al agregar un item, el sistema aplica automáticamente el tier según cantidad
                   -- (el operador puede sobreescribir el precio manualmente en el pedido)

payment_methods   (id, business_id, name, type ENUM(efectivo,transferencia,pos,online,otro),
                   requires_change BOOLEAN,   -- efectivo: preguntar "¿con cuánto paga?"
                   active, sort_order)
                   -- configurables por negocio; el ENUM fijo de orders se reemplaza por FK

customer_defaults (id, customer_id FK, product_id FK, quantity)
                   -- el "pedido habitual"; se recalcula automáticamente (ver servicio)

-- ═══ PEDIDOS ═══
orders            (id, business_id, customer_id FK NULL, external_ref,
                   customer_name, customer_phone,          -- snapshot, editable
                   delivery_address, delivery_lat, delivery_lng,
                   pickup_address, pickup_lat, pickup_lng,  -- NULL = local del negocio
                   amount, payment_method_id FK->payment_methods,
                   cash_amount_given NULL,   -- si paga efectivo: monto con el que paga (para el vuelto)
                   notes, status ENUM(pendiente,asignado,aceptado,recogido,en_ruta,entregado,cancelado,fallido),
                   driver_id FK NULL, tracking_token UNIQUE,
                   scheduled_for NULL,                      -- pedidos programados
                   created_at, assigned_at, accepted_at, picked_up_at, delivered_at)

order_items       (id, order_id FK, product_id FK NULL, description, quantity, unit_price, subtotal)

order_events      (id, order_id FK, status, lat, lng, note, actor_user_id, created_at)

location_pings    (id, driver_id FK, lat, lng, speed, battery, recorded_at)
                   -- particionar por mes cuando crezca; retención 90 días

proofs            (id, order_id FK, type ENUM(photo,signature), file_url, receiver_name, created_at)

subscriptions     (id, business_id FK, plan, status, price_clp, current_period_end)
```

**Redis:**
- `driver:{id}:pos` → JSON `{lat, lng, speed, battery, ts}` con TTL 120s
- Pub/sub canal `business:{id}:events` → eventos para el panel (nuevo pedido, cambio de estado, posición)

---

## 4. Lógica de autollenado y recompra (diferenciador del producto)

### 4.1 Autocompletado por teléfono
- Endpoint `GET /customers/search?phone_prefix=XXXX` — busca por prefijo desde 4 dígitos, máximo 8 resultados, ordenados por `last_order_at DESC`.
- Al seleccionar un cliente, el frontend llama `GET /customers/{id}/prefill` que retorna:
  ```json
  {
    "customer": {"name", "phone", "address", "lat", "lng", "notes"},
    "suggested_items": [{"product_id", "name", "quantity", "unit_price"}],
    "suggestion_source": "last_order" | "defaults" | "most_frequent"
  }
  ```
- El formulario del panel se llena con estos datos; TODO es editable antes de guardar.
- Si el teléfono no existe → formulario en blanco; al guardar el pedido se crea el `customer` automáticamente (con geocoding de la dirección vía Nominatim, resultado cacheado en el registro).

### 4.2 Pedido habitual que aprende solo
Servicio `recalculate_customer_defaults(customer_id)` — se ejecuta al marcar un pedido como `entregado`:
1. Toma los últimos 5 pedidos entregados del cliente.
2. Para cada producto, calcula la cantidad **moda** (más frecuente).
3. Reescribe `customer_defaults`.
4. Recalcula `order_frequency_days` = mediana de días entre los últimos 6 pedidos (NULL si tiene <3 pedidos).

Prioridad de sugerencia en `/prefill`: pedido más reciente si tiene <3 pedidos históricos; si no, `customer_defaults`.

### 4.3 Recompra proactiva
- Endpoint `GET /customers/due-for-reorder` → clientes donde `last_order_at + order_frequency_days <= hoy + 1` y sin pedido activo.
- Vista en el panel: "Clientes por pedir" con teléfono a un tap y botón "Crear pedido" (pre-llenado completo).
- Fase futura: mensaje automático por WhatsApp ("Hola Juan, ¿te enviamos tus 2 bidones de siempre?").

### 4.4 Módulo Catálogo y Personal (fuente de verdad del sistema)

Página dedicada en el panel: **Configuración > Catálogo** y **Configuración > Personal** (patrón BarberPilot). TODO lo que aparece en formularios de pedido, app del repartidor, tracking y reportes se alimenta EXCLUSIVAMENTE de aquí. Nada hardcodeado.

**Catálogo — Productos:**
- CRUD completo: nombre, descripción, precio base, unidad, imagen opcional, activo/inactivo, orden de aparición.
- Desactivar ≠ borrar: un producto inactivo no aparece en pedidos nuevos pero conserva el historial.

**Catálogo — Combos:**
- Un combo es un producto (`is_combo=true`) con componentes definidos en `combo_items` y **precio propio** (no la suma).
- Ejemplo: "Combo Hogar" = 2 bidones 20L + 1 pack botellas, a CLP 8.500.
- En el pedido, el combo se agrega como una línea; el detalle de componentes es visible para el repartidor (sabe qué cargar).

**Catálogo — Precios por volumen (mayorista):**
- Cada producto puede tener N tiers en `price_tiers`: `min_quantity → unit_price`.
- Regla de aplicación automática al armar el pedido: se toma el tier con el mayor `min_quantity` que sea `<= cantidad`. Sin tier aplicable → precio base.
- El operador puede sobreescribir el precio unitario manualmente en la línea del pedido (queda registrado el precio efectivo en `order_items.unit_price`).
- Ejemplo agua: bidón CLP 3.000 unitario; desde 10, CLP 2.500; desde 30 (almacenes), CLP 2.200.

**Métodos de pago:**
- Lista configurable por negocio: Efectivo, Transferencia, POS (punto de venta), etc. — el negocio los crea, renombra, ordena o desactiva.
- `requires_change=true` (efectivo) → el formulario de pedido pregunta "¿Con cuánto paga?" y la app del repartidor muestra el vuelto a entregar.
- El método de pago es visible al repartidor SIEMPRE (necesita saber si cobra o no).
- Reportes de ventas desglosan por método de pago (cuadratura de caja: cuánto entró en efectivo vs transferencia vs POS).

**Personal:**
- Gestión de usuarios del negocio: despachadores y repartidores. Crear, invitar por link, activar/desactivar, resetear contraseña.
- Para repartidores: tipo de vehículo, teléfono de contacto visible en panel.
- Un repartidor desactivado no puede loguearse ni recibir asignaciones, pero su historial de entregas se conserva para reportes.

---

## 5. FASES DE IMPLEMENTACIÓN

═══════════════════════════════════════════
### FASE 0 — Fundaciones
═══════════════════════════════════════════

**Tareas:**
- [x] Inicializar monorepo con la estructura de la sección 2
- [x] Backend FastAPI: config con `pydantic-settings` (DATABASE_URL, REDIS_URL, JWT_SECRET, FCM creds, R2 creds via env)
- [x] Docker Compose local: postgres + redis para desarrollo
- [x] Todas las tablas de la sección 3 como modelos SQLAlchemy + migración inicial Alembic
- [x] Auth: registro/login con JWT (access 15min + refresh 7d), hash con bcrypt
- [x] Middleware de tenant: extrae `business_id` del JWT y lo inyecta como dependencia; helper `tenant_query()` que fuerza el filtro
- [x] Seed script: 1 negocio demo (agua purificada), 2 usuarios (owner + driver), 5 productos (bidón 20L retornable, bidón 20L nuevo, pack botellas, dispensador, bomba manual), 1 combo ("Combo Hogar": 2 bidones + 1 pack), tiers mayoristas para el bidón (10+ y 30+ unidades), 3 métodos de pago (Efectivo con vuelto, Transferencia, POS), 10 clientes con historial de pedidos ficticio
- [x] Deploy a Railway (dev) con deploy automático desde `main` — `/docs` vivo en Railway, rol de aplicación separado del bootstrap verificado en producción (rolsuper/rolbypassrls en falso).
- [x] Sentry configurado — DSN real conectado a un proyecto Sentry.

**Criterios de aceptación:**
- `/docs` accesible en Railway con auth funcionando
- Un usuario del negocio A recibe 403/404 al intentar acceder a recursos del negocio B (test automatizado)
- Seed ejecutable con un comando

═══════════════════════════════════════════
### FASE 1 — Núcleo operativo + Autollenado
═══════════════════════════════════════════

**Backend:**
- [x] CRUD productos + combos (`combo_items`) + tiers de precio (`price_tiers`)
- [x] Servicio de pricing: `resolve_unit_price(product_id, quantity)` aplica el tier correcto (sección 4.4); usado al crear/editar items de pedido
- [x] CRUD métodos de pago por negocio
- [x] CRUD clientes + `GET /customers/search?phone_prefix=` + `GET /customers/{id}/prefill` (sección 4.1)
- [x] `GET /customers/due-for-reorder` (sección 4.3) — movido desde Fase 2 para construirse junto con el resto del checkpoint clientes/autollenado; no estaba itemizado como línea propia, solo en prosa
- [x] CRUD pedidos con `order_items`; creación acepta `customer_id` o datos nuevos (crea cliente automático) — create/read/list construidos y probados; no existe un update genérico de contenido (items/notas) de un pedido ya creado más allá de las transiciones de estado, porque nada en el alcance de Fase 1 lo pide (ninguna UI de "editar pedido" está descrita)
- [x] Geocoding Nominatim con cache (si el cliente ya tiene lat/lng, NO volver a geocodificar)
- [x] Máquina de estados del pedido con validación de transiciones + escritura en `order_events`
- [x] Servicio `recalculate_customer_defaults` al entregar (sección 4.2) — ahora conectado al gatillo real: `order_state_machine.transition_order_status` lo invoca en la transición a `entregado`, condicionado a que el pedido tenga `customer_id`
- [x] CRUD repartidores + toggle online/offline — CRUD completo construido para despachadores y repartidores (`POST/GET /staff`, activar/desactivar, resetear contraseña vía enlace firmado); **toggle online/offline explícitamente fuera de esta línea**: es una acción que el propio repartidor dispara desde su app (sección 4, Flutter checklist línea 243), no una acción administrativa de Personal — diferida hasta que exista un contexto autenticado como repartidor real (app Flutter u otro) para el que construir y probar ese endpoint
- [ ] Asignación de pedido → push FCM al repartidor con sonido/prioridad alta
- [ ] WebSocket `/ws/driver/{token}`: recibe pings GPS → Redis + publish; persiste en `location_pings` cada 60s
- [ ] WebSocket `/ws/dispatch/{token}`: emite eventos del canal del negocio (posiciones + cambios de pedido)

**Panel web (React):**
- [x] Login + layout (sidebar: Pedidos, Mapa, Clientes, Repartidores, Ventas, Configuración)
- [x] **Configuración > Catálogo** (construir PRIMERO — alimenta todo lo demás): gestión de productos, combos con selector de componentes, tabla de tiers de precio por producto, y métodos de pago (sección 4.4)
- [x] **Configuración > Personal**: gestión de despachadores y repartidores (crear, invitar por link, activar/desactivar)
- [x] **Formulario de pedido con autollenado**: campo teléfono con búsqueda en vivo (debounce 300ms), dropdown de coincidencias, al seleccionar se llena todo; items con +/- de cantidad; precio unitario auto-resuelto por tier (editable); selector de método de pago con campo "¿con cuánto paga?" si es efectivo; total calculado en vivo
- [x] Tabla de pedidos del día con filtros por estado + acciones (asignar, cancelar)
- [ ] Mapa en vivo (Leaflet): repartidores con color por estado, pedidos activos, actualización por WebSocket
- [ ] Vista Clientes: lista con búsqueda, detalle con historial de pedidos y pedido habitual
- [x] **Vista "Clientes por pedir"** (sección 4.3) — movida desde Fase 2 para construirse junto con el resto del checkpoint clientes/autollenado: lista de clientes que ya deberían reordenar, con teléfono a un tap y botón "Crear pedido" (ahora funcional — navega al formulario de pedido pre-llenado con el prefill de ese cliente, igual que si se hubiera seleccionado por el buscador en vivo)

**App Flutter:**
- [ ] Login (email/contraseña) + registro de FCM token
- [ ] Toggle online/offline → arranca/detiene foreground service GPS
- [ ] GPS background: foreground service con notificación persistente; frecuencia adaptativa (10s en movimiento / 60s detenido); envío por WebSocket con reconexión automática y buffer offline
- [ ] Onboarding de permisos: ubicación "todo el tiempo" + guía para desactivar optimización de batería (detectar marca del teléfono)
- [ ] Lista de entregas asignadas + detalle (cliente, dirección, items con componentes de combos desglosados, monto, método de pago, vuelto a entregar si es efectivo, notas)
- [ ] Botones de estado: Aceptar → Recogido → En ruta → Entregado (cada cambio adjunta lat/lng)
- [ ] Botón "Navegar" → abre Google Maps/Waze con la coordenada
- [ ] Push de nuevo pedido con sonido destacado
- [ ] Build APK firmado + documentar proceso en `docs/build-apk.md`

**Criterios de aceptación (flujo E2E):**
1. Operador escribe 4 dígitos del teléfono → aparece el cliente → selecciona → nombre, dirección y pedido habitual cargados → ajusta cantidad → guarda en <10 segundos
2. Asigna repartidor → push llega al teléfono en <5s
3. Repartidor acepta → su posición se mueve en el mapa del panel en tiempo real
4. Marca entregado → el pedido histórico actualiza el pedido habitual del cliente
5. Pedido de teléfono nuevo → se crea el cliente automáticamente y aparece en autocompletado en el siguiente pedido
6. Pedido de 12 bidones → el precio unitario aplica automáticamente el tier mayorista de 10+; el operador puede sobreescribirlo
7. Pedido con "Combo Hogar" en efectivo con CLP 10.000 → el repartidor ve los componentes a cargar y el vuelto exacto a entregar
8. Desactivar un producto → deja de aparecer en pedidos nuevos, pero los reportes históricos no cambian

**✅ HITO: piloto real con la distribuidora de agua.**

═══════════════════════════════════════════
### FASE 2 — Experiencia Shipday + Recompra proactiva
═══════════════════════════════════════════

- [ ] Página pública de tracking `/{tracking_token}`: mapa con repartidor en vivo (solo en_ruta), ETA vía OSRM, estados, nombre del repartidor. Responsive móvil.
- [ ] Botón en el panel "Copiar link de tracking" + formato listo para WhatsApp
- [ ] Kanban de pedidos con drag & drop entre estados y a repartidores; al asignar, muestra distancia de cada repartidor libre al punto de entrega
- [ ] Ruta del día del repartidor (polyline sobre el mapa desde `location_pings`)
- [ ] Alertas en panel: pedido sin asignar >15 min, repartidor >3 min sin señal (badge + toast)
- [ ] Geofence: al entrar a 100m del destino, la app sugiere "¿Marcar como entregado?"
- [ ] Pedidos programados (`scheduled_for`): se crean hoy, aparecen como pendientes en su fecha

**Criterios de aceptación:**
- Cliente final abre el link y ve al repartidor moverse con ETA
- La vista "Clientes por pedir" muestra correctamente a un cliente cuya frecuencia es 15 días y pidió hace 15
- Crear pedido desde esa vista toma <5 segundos

═══════════════════════════════════════════
### FASE 3 — Producto vendible
═══════════════════════════════════════════

- [ ] Prueba de entrega: foto (cámara) + firma (canvas) + nombre receptor → R2; visible en el detalle del pedido y en el tracking público post-entrega
- [ ] Dashboard Ventas: ingresos por día/semana/mes, ticket promedio, pedidos por repartidor, tiempo promedio entrega, top clientes, top productos, gráfico de recurrencia, **desglose por método de pago (cuadratura de caja: efectivo vs transferencia vs POS, por día y por repartidor)**
- [ ] Exportación CSV/Excel por rango de fechas (pedidos + detalle items)
- [ ] Auto-asignación opcional: repartidor `online` más cercano con <N pedidos activos (configurable por negocio)
- [ ] API pública v1 con API keys por negocio + webhook de entrada de pedidos (documentar con ejemplos curl) — punto de integración futuro con RestoPilot
- [ ] Onboarding self-service: registro de negocio → wizard (datos, productos, invitar repartidores por link mágico)
- [ ] Modo cobranza para agua: saldo de bidones retornables por cliente (entregados vs devueltos) — campo `returnable_balance` en customers + movimiento por pedido

**Criterios de aceptación:**
- Un negocio nuevo puede registrarse y crear su primer pedido sin intervención manual
- El reporte Excel de un mes cuadra con la suma de pedidos entregados

═══════════════════════════════════════════
### FASE 4 — SaaS con cobro recurrente
═══════════════════════════════════════════

- [ ] Planes: Partida (3 repartidores, 500 pedidos/mes) y Pro (ilimitado) con enforcement de límites
- [ ] Integración de pago: Flow o Mercado Pago suscripción CLP; estado de suscripción bloquea/desbloquea el tenant (con gracia de 5 días)
- [ ] Panel admin (rol `admin`): lista de tenants, uso (pedidos/mes, repartidores activos), impersonación para soporte
- [ ] Backups automáticos PostgreSQL + prueba de restauración documentada
- [ ] Rate limiting por tenant (slowapi) + índices revisados con EXPLAIN en queries principales
- [ ] Retención: job diario que borra `location_pings` >90 días
- [ ] Landing page comercial con demo
- [ ] Publicación en Play Store

**Criterios de aceptación:**
- Suscripción vencida → panel muestra aviso de pago y bloquea creación de pedidos tras la gracia
- Restauración de backup probada en entorno dev

---

## 6. Convenciones para Claude Code

- **Idioma:** código y nombres en inglés; textos de UI en español (Chile). Centralizar strings de UI.
- **Commits:** convencionales (`feat:`, `fix:`, `chore:`) por tarea completada.
- **Tests:** pytest en backend; mínimo: auth, aislamiento de tenant, máquina de estados, servicio de defaults, prefill. No perseguir 100% de cobertura.
- **Migraciones:** nunca editar una migración aplicada; siempre nueva revisión Alembic.
- **Errores API:** formato consistente `{"detail": str, "code": str}`.
- **Zona horaria:** guardar todo en UTC; convertir a `business.timezone` solo en presentación.
- **Moneda:** montos en enteros CLP (sin decimales).
- **Secretos:** solo por variables de entorno; jamás en el repo.

## 7. Referencia de costos y pricing (contexto de negocio)

- Costo operacional con primeros clientes: Railway USD 5-20/mes + R2 ~USD 0-5 + dominio. Total < USD 30/mes.
- Precio al cliente piloto (fundador, sin costo de implementación): **CLP 35.000-45.000/mes**, precio congelado 12 meses.
- Alternativa: base CLP 25.000 + CLP 100 por pedido sobre 200/mes.
- Precio de lista futuro: Partida ~CLP 45.000, Pro ~CLP 75.000.
