import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { strings } from '../../i18n/strings'
import { listDrivers, type Driver, type DriverStatus } from '../../api/drivers'
import { listOrders, type Order } from '../../api/orders'
import { useDispatchSocket, type DriverPosition } from './useDispatchSocket'

// Santiago, Chile -- reasonable default center when nothing has a position yet.
const _DEFAULT_CENTER: [number, number] = [-33.4489, -70.6693]

const _DRIVER_COLOR: Record<DriverStatus, string> = {
  offline: '#94a3b8',
  online: '#16a34a',
  busy: '#f59e0b',
}

const _ACTIVE_ORDER_STATUSES = new Set<Order['status']>([
  'pendiente',
  'asignado',
  'aceptado',
  'recogido',
  'en_ruta',
])

function todayLocalDateString(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function MapaPage() {
  const mapContainerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const driverMarkersRef = useRef<Map<number, L.CircleMarker>>(new Map())
  const orderMarkersRef = useRef<Map<number, L.CircleMarker>>(new Map())
  const driversRef = useRef<Map<number, Driver>>(new Map())

  const [isLoading, setIsLoading] = useState(true)
  const [driverMarkerCount, setDriverMarkerCount] = useState(0)

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return
    const map = L.map(mapContainerRef.current).setView(_DEFAULT_CENTER, 12)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)
    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  function upsertDriverMarker(driverId: number, lat: number, lng: number, status: DriverStatus) {
    const map = mapRef.current
    if (!map) return
    const existing = driverMarkersRef.current.get(driverId)
    if (existing) {
      existing.setLatLng([lat, lng])
      existing.setStyle({ color: _DRIVER_COLOR[status], fillColor: _DRIVER_COLOR[status] })
      return
    }
    const marker = L.circleMarker([lat, lng], {
      radius: 9,
      color: _DRIVER_COLOR[status],
      fillColor: _DRIVER_COLOR[status],
      fillOpacity: 0.9,
      weight: 2,
    }).addTo(map)
    driverMarkersRef.current.set(driverId, marker)
    setDriverMarkerCount(driverMarkersRef.current.size)
  }

  function applyPosition(position: DriverPosition) {
    const driver = driversRef.current.get(position.driver_id)
    upsertDriverMarker(position.driver_id, position.lat, position.lng, driver?.status ?? 'online')
  }

  async function reloadOrders() {
    const page = await listOrders({ on_date: todayLocalDateString(), limit: 200 })
    const map = mapRef.current
    if (!map) return

    const activeIds = new Set<number>()
    for (const order of page.items) {
      if (!_ACTIVE_ORDER_STATUSES.has(order.status)) continue
      activeIds.add(order.id)
      const lat = Number(order.delivery_lat)
      const lng = Number(order.delivery_lng)
      const existing = orderMarkersRef.current.get(order.id)
      if (existing) {
        existing.setLatLng([lat, lng])
      } else {
        const marker = L.circleMarker([lat, lng], {
          radius: 6,
          color: '#2563eb',
          fillColor: '#2563eb',
          fillOpacity: 0.7,
          weight: 1,
        }).addTo(map)
        orderMarkersRef.current.set(order.id, marker)
      }
    }
    // Orders that left the active set (delivered/cancelled/failed since the
    // last reload) lose their marker.
    for (const [orderId, marker] of orderMarkersRef.current) {
      if (!activeIds.has(orderId)) {
        marker.remove()
        orderMarkersRef.current.delete(orderId)
      }
    }
  }

  useEffect(() => {
    let cancelled = false
    async function load() {
      const drivers = await listDrivers()
      if (cancelled) return
      driversRef.current = new Map(drivers.map((d) => [d.id, d]))
      for (const driver of drivers) {
        if (driver.last_lat !== null && driver.last_lng !== null) {
          upsertDriverMarker(driver.id, Number(driver.last_lat), Number(driver.last_lng), driver.status)
        }
      }
      await reloadOrders()
      setIsLoading(false)
    }
    void load()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const { isConnected } = useDispatchSocket((event) => {
    if (event.type === 'driver_position') {
      applyPosition(event)
    } else if (event.type === 'positions_snapshot') {
      for (const position of event.positions) applyPosition(position)
    } else if (event.type === 'order_created' || event.type === 'order_status_changed') {
      void reloadOrders()
    }
  })

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">{strings.nav.mapa}</h1>
        <span
          className={`text-xs font-medium ${isConnected ? 'text-green-600' : 'text-amber-600'}`}
        >
          {isConnected ? strings.mapa.conectado : strings.mapa.reconectando}
        </span>
      </div>
      <div
        ref={mapContainerRef}
        className="h-[70vh] w-full rounded-lg border border-slate-200"
        style={{ zIndex: 0 }}
      />
      {!isLoading && driverMarkerCount === 0 && (
        <p className="text-sm text-slate-500">{strings.mapa.sinRepartidoresConPosicion}</p>
      )}
    </div>
  )
}
