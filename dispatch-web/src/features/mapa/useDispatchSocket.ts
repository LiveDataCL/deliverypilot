import { useEffect, useRef, useState } from 'react'
import { tokenStorage } from '../../api/client'

export interface DriverPosition {
  driver_id: number
  lat: number
  lng: number
  speed: number | null
  battery: number | null
  recorded_at: string
}

export interface DriverPositionEvent extends DriverPosition {
  type: 'driver_position'
}

export interface PositionsSnapshotEvent {
  type: 'positions_snapshot'
  positions: DriverPosition[]
}

export interface OrderCreatedEvent {
  type: 'order_created'
  order_id: number
  status: string
}

export interface OrderStatusChangedEvent {
  type: 'order_status_changed'
  order_id: number
  status: string
  driver_id?: number
}

export type DispatchEvent =
  | DriverPositionEvent
  | PositionsSnapshotEvent
  | OrderCreatedEvent
  | OrderStatusChangedEvent

function wsUrl(path: string): string {
  const apiUrl = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'
  return apiUrl.replace(/^http/, 'ws') + path
}

// Reconnects on its own with backoff -- CLAUDE.md SS2's "el WebSocket ...
// debe reconectar solo" requirement, applied here to the dispatch panel's
// socket too, not only the driver app's.
export function useDispatchSocket(onEvent: (event: DispatchEvent) => void): { isConnected: boolean } {
  const [isConnected, setIsConnected] = useState(false)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null
    let stopped = false
    let attempt = 0

    function connect() {
      const token = tokenStorage.getAccess()
      if (!token || stopped) return

      socket = new WebSocket(wsUrl(`/ws/dispatch/${token}`))
      socket.onopen = () => {
        attempt = 0
        setIsConnected(true)
      }
      socket.onmessage = (event: MessageEvent<string>) => {
        try {
          onEventRef.current(JSON.parse(event.data) as DispatchEvent)
        } catch {
          // Malformed frame -- ignore rather than crash the handler.
        }
      }
      socket.onclose = () => {
        setIsConnected(false)
        if (stopped) return
        const delay = Math.min(1000 * 2 ** attempt, 15000)
        attempt += 1
        reconnectTimeout = setTimeout(connect, delay)
      }
      socket.onerror = () => {
        socket?.close()
      }
    }

    connect()

    return () => {
      stopped = true
      if (reconnectTimeout) clearTimeout(reconnectTimeout)
      socket?.close()
    }
  }, [])

  return { isConnected }
}
