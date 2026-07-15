# DeliveryPilot — Plan de Infraestructura Completo
### Clon de Shipday · Producto SaaS multi-tenant · Solo Android (fase inicial)

---

## 1. Visión general de la arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                        RAILWAY (Cloud)                        │
│                                                               │
│  ┌────────────┐   ┌────────────┐   ┌────────────┐            │
│  │  FastAPI   │◄──┤ PostgreSQL │   │   Redis    │            │
│  │  (API +    │   │ (datos)    │   │ (ubicación │            │
│  │ WebSockets)│   └────────────┘   │  en vivo + │            │
│  └─────┬──────┘                    │  pub/sub)  │            │
│        │                           └────────────┘            │
└────────┼──────────────────────────────────────────────────────┘
         │
         ├──────────────┬──────────────────┬────────────────┐
         ▼              ▼                  ▼                ▼
  ┌────────────┐ ┌──────────────┐ ┌──────────────┐ ┌─────────────┐
  │ Panel Web  │ │ App Flutter  │ │ Página de    │ │  Firebase   │
  │ Despacho   │ │ Repartidor   │ │ tracking     │ │  Cloud      │
  │ (React)    │ │ (APK Android)│ │ cliente final│ │  Messaging  │
  └────────────┘ └──────────────┘ └──────────────┘ └─────────────┘
```

**Principios de diseño:**

- **Multi-tenant desde el día 1:** toda tabla lleva `business_id`. Un solo deploy sirve a todos tus clientes.
- **Python-first:** el mismo stack que ya dominas (FastAPI + PostgreSQL + Railway), reutilizando patrones de RestoPilot y BarberPilot.
- **Tiempo real barato:** WebSockets nativos de FastAPI + Redis pub/sub. Sin servicios pagados de terceros.
- **Mapas gratis:** Leaflet + OpenStreetMap + Nominatim (geocoding) / OSRM (rutas). Google Maps solo si un cliente lo exige.
- **Distribución sin fricción:** APK directo por link de descarga. Play Store queda para cuando haya tracción.

---

## 2. Componentes del sistema

### 2.1 Backend — FastAPI (Railway)

| Módulo | Responsabilidad |
|---|---|
| `auth` | JWT con roles: `admin` (tú), `business_owner` (tu cliente), `dispatcher`, `driver`. Refresh tokens. |
| `businesses` | Multi-tenancy: negocios, planes, configuración por tenant (logo, zona horaria, moneda). |
| `orders` | CRUD de pedidos, estados, asignación manual y auto-asignación (fase 3). |
| `drivers` | Registro de repartidores, disponibilidad (online/offline), vehículo, zona. |
| `tracking` | Ingesta de GPS vía WebSocket, escritura en Redis (posición actual) + PostgreSQL (historial cada 60s). |
| `notifications` | FCM: push al repartidor (nuevo pedido, cancelación) y eventos al panel. |
| `public_tracking` | Endpoint público con token único por pedido → página de seguimiento del cliente final. |
| `analytics` | Ventas por día/semana/mes, por repartidor, tiempos promedio de entrega, tasa de cumplimiento. |
| `webhooks` | Entrada de pedidos desde sistemas externos (¡aquí conecta RestoPilot después!). |

**Flujo de estados del pedido:**
`pendiente → asignado → aceptado → recogido → en_ruta → entregado` (+ `cancelado`, `fallido` con motivo)

### 2.2 Modelo de datos (PostgreSQL)

```
businesses      (id, name, plan, timezone, currency, settings_json, created_at)
users           (id, business_id, role, email, phone, password_hash, fcm_token)
drivers         (id, business_id, user_id, vehicle_type, status, last_lat, last_lng, last_seen_at)
orders          (id, business_id, external_ref, customer_name, customer_phone,
                 pickup_address, pickup_lat, pickup_lng,
                 delivery_address, delivery_lat, delivery_lng,
                 amount, payment_method, notes, status,
                 driver_id, tracking_token,
                 created_at, assigned_at, accepted_at, picked_up_at, delivered_at)
order_events    (id, order_id, status, lat, lng, note, created_at)   -- auditoría completa
location_pings  (id, driver_id, lat, lng, speed, battery, recorded_at) -- historial GPS
proofs          (id, order_id, type[photo|signature], file_url, created_at)
subscriptions   (id, business_id, plan, status, current_period_end)   -- facturación SaaS
```

**Redis:**
- `driver:{id}:pos` → posición actual (TTL 2 min; si expira = repartidor sin señal)
- Canal pub/sub `business:{id}:events` → empuja actualizaciones al panel vía WebSocket

### 2.3 App repartidor — Flutter (Android APK)

| Pantalla | Funcionalidad |
|---|---|
| Login | Teléfono + PIN o email/contraseña. Registro del token FCM. |
| Toggle disponibilidad | Online/Offline. Al pasar a online arranca el servicio GPS en background. |
| Lista de entregas | Pedidos asignados hoy, ordenados por prioridad/hora. |
| Detalle de pedido | Dirección, cliente, monto, notas. Botones: Aceptar → Recogido → En ruta → Entregado. Botón "Navegar" abre Google Maps/Waze con la dirección. |
| Prueba de entrega | Foto + firma en pantalla + nombre de quien recibe (fase 3). |
| Historial | Entregas del día y de la semana, con montos si cobra contra entrega. |

**Paquetes clave:**
- `flutter_background_geolocation` (licencia ~USD 400 una vez, la mejor) **o** `background_locator_2` (gratis, requiere más ajuste)
- `firebase_messaging` para push
- `dio` para HTTP, `web_socket_channel` para tiempo real

**⚠️ Crítico en Android (Chile = muchos Xiaomi/Huawei/Samsung):**
1. Solicitar permiso "Permitir todo el tiempo" para ubicación (Android 10+).
2. Foreground service con notificación persistente ("Estás en línea — DeliveryPilot").
3. Pantalla de onboarding que guíe a desactivar optimización de batería (deep link a los ajustes de cada marca — usar paquete `disable_battery_optimization`).
4. Frecuencia GPS adaptativa: cada 10s en movimiento, cada 60s detenido (ahorra batería y datos).

### 2.4 Panel de despacho — React (web)

| Vista | Funcionalidad |
|---|---|
| Mapa en vivo | Leaflet + OSM. Marcadores de repartidores (verde=libre, azul=en ruta, gris=offline) y pedidos activos. Se actualiza por WebSocket. |
| Tablero de pedidos | Kanban por estado o tabla filtrable. Crear pedido manual con autocompletado de dirección (Nominatim). |
| Asignación | Drag & drop de pedido → repartidor, o selector en el detalle. Muestra distancia de cada repartidor al punto de retiro. |
| Repartidores | Lista con estado, entregas del día, última señal, batería. |
| Ventas | Gráficos: ingresos por día/semana/mes, ticket promedio, entregas por repartidor, tiempo promedio de entrega, mapa de calor de zonas. |
| Configuración | Datos del negocio, usuarios, integración por API key (webhooks). |

### 2.5 Página de tracking del cliente final

- URL pública: `track.tudominio.cl/{tracking_token}`
- Mapa con posición del repartidor en vivo (solo mientras el pedido está en ruta), ETA estimado con OSRM, estado del pedido y datos del repartidor (nombre + foto).
- Se comparte por WhatsApp automáticamente al asignar (integrable con la API de WhatsApp que ya usas en RestoPilot).

---

## 3. Infraestructura y servicios

| Servicio | Uso | Costo estimado |
|---|---|---|
| Railway | FastAPI + PostgreSQL + Redis | USD 5–20/mes al inicio |
| Firebase (FCM) | Push notifications | Gratis |
| Cloudflare R2 o Railway volume | Fotos de prueba de entrega | ~USD 0–5/mes |
| OpenStreetMap + Nominatim | Mapas y geocoding | Gratis (respetar rate limits; self-host si crece) |
| OSRM (demo server o self-host) | Cálculo de rutas y ETA | Gratis |
| Dominio + Cloudflare | DNS, SSL, CDN | ~USD 12/año |
| Sentry (free tier) | Monitoreo de errores backend + app | Gratis |

**Total para operar con tus primeros 5–10 clientes: menos de USD 30/mes.**

---

## 4. Plan de ejecución por fases

### FASE 0 — Fundaciones (semana 1)
- [ ] Crear monorepo: `/backend`, `/dispatch-web`, `/driver-app`, `/tracking-page`
- [ ] Setup Railway: servicio FastAPI + PostgreSQL + Redis, entornos `dev` y `prod`
- [ ] Proyecto Firebase + configuración FCM
- [ ] Esquema de base de datos completo con Alembic (migraciones desde el día 1)
- [ ] Auth JWT multi-rol + middleware de tenant (`business_id` inyectado en cada query)
- [ ] CI básico: deploy automático a Railway desde `main`

**Entregable:** API viva con auth funcionando y docs en `/docs` (Swagger).

### FASE 1 — Núcleo operativo (semanas 2–4)
**Backend:**
- [ ] CRUD de pedidos con geocoding automático de direcciones (Nominatim)
- [ ] CRUD de repartidores + toggle online/offline
- [ ] Asignación manual de pedido → push FCM al repartidor
- [ ] Máquina de estados del pedido con `order_events` (auditoría)
- [ ] WebSocket `/ws/driver` (ingesta GPS) y `/ws/dispatch` (eventos al panel)

**App Flutter:**
- [ ] Login + registro FCM token
- [ ] Lista de pedidos + detalle + botones de cambio de estado
- [ ] Recepción de push con sonido destacado (nuevo pedido)
- [ ] GPS en background con foreground service + envío por WebSocket
- [ ] Onboarding de permisos (ubicación siempre + batería sin restricciones)
- [ ] Generación de APK firmado + link de descarga

**Panel web:**
- [ ] Login + layout base
- [ ] Tabla de pedidos + formulario de creación con autocompletado de dirección
- [ ] Asignación a repartidor desde el detalle
- [ ] Mapa en vivo básico (repartidores + pedidos activos)

**Entregable:** flujo completo funcionando — creas un pedido, le llega push al repartidor, lo acepta, ves su ubicación moverse en el mapa, marca entregado.
**✅ Hito: primer piloto real con un negocio (ideal: Mr Takeshi Sushi como beta).**

### FASE 2 — Experiencia Shipday (semanas 5–6)
- [ ] Página pública de tracking con token único + ETA (OSRM)
- [ ] Envío automático del link de tracking por WhatsApp al cliente final
- [ ] Kanban drag & drop en el panel + sugerencia de repartidor más cercano
- [ ] Historial de ruta del repartidor (polyline del día sobre el mapa)
- [ ] Notificaciones del panel: pedido sin asignar >X min, repartidor sin señal
- [ ] Detección de llegada por geofence (auto-sugerencia de "recogido"/"entregado")

**Entregable:** experiencia comparable a Shipday para el flujo diario.

### FASE 3 — Producto vendible (semanas 7–9)
- [ ] Prueba de entrega: foto + firma + nombre del receptor (subida a R2)
- [ ] Dashboard de ventas completo: ingresos, ticket promedio, ranking de repartidores, tiempos, mapa de calor
- [ ] Exportación de reportes (Excel/CSV) por rango de fechas
- [ ] Auto-asignación opcional (repartidor libre más cercano)
- [ ] API pública + webhooks documentados (entrada de pedidos desde otros sistemas)
- [ ] **Integración RestoPilot:** pedido confirmado por WhatsApp → se crea automáticamente en DeliveryPilot
- [ ] Onboarding self-service: registro de negocio, wizard inicial, invitación de repartidores por link

**Entregable:** producto que puedes demostrar y vender.

### FASE 4 — SaaS y escala (semanas 10–12)
- [ ] Planes y facturación: Flow o Mercado Pago (suscripción CLP) — Stripe si vas internacional
- [ ] Límites por plan (N repartidores, N pedidos/mes)
- [ ] Panel admin tuyo: todos los tenants, métricas de uso, impersonación para soporte
- [ ] Landing page comercial + demo con datos de ejemplo
- [ ] Publicación en Play Store (cuenta developer USD 25 una vez)
- [ ] Hardening: rate limiting, backups automáticos de PostgreSQL, alertas de Sentry

**Entregable:** SaaS operando con cobro recurrente.

---

## 5. Riesgos técnicos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Android mata el GPS en background (Xiaomi/Huawei) | Foreground service + onboarding de batería por marca + alerta en panel si un repartidor lleva >2 min sin señal |
| Rate limit de Nominatim/OSRM públicos | Cache agresivo de geocoding en PostgreSQL; self-host cuando haya volumen |
| Costo de datos móviles del repartidor | WebSocket con payloads mínimos (~100 bytes/ping); frecuencia adaptativa |
| Un tenant afecta a otros (multi-tenant) | Índices por `business_id`, rate limit por tenant, monitoreo por tenant |
| Repartidor sin batería/señal a mitad de entrega | Estado "sin señal" visible en panel + teléfono del repartidor a un tap |

---

## 6. Modelo de negocio sugerido (referencia Shipday)

Shipday cobra ~USD 0.10–0.15 por pedido o planes mensuales. Para Chile:

- **Plan Partida:** ~CLP 25.000/mes — 1 negocio, hasta 3 repartidores, 500 pedidos/mes
- **Plan Pro:** ~CLP 45.000/mes — repartidores ilimitados, tracking con marca propia, API
- **Setup/onboarding:** cobro único opcional por implementación e integración

Con 10 clientes en Plan Partida ya cubres infraestructura ~100 veces y generas ingreso recurrente real.

---

## 7. Orden de construcción recomendado (resumen ejecutivo)

1. **Semana 1:** Fundaciones (repo, Railway, DB, auth)
2. **Semanas 2–4:** Núcleo — pedido → push → GPS en vivo → entregado
3. **Piloto real** con un negocio conocido
4. **Semanas 5–6:** Tracking público + UX de despacho
5. **Semanas 7–9:** Prueba de entrega, analytics, integración RestoPilot, onboarding
6. **Semanas 10–12:** Facturación, panel admin, Play Store, venta
