import { apiClient } from './client'

export type DriverStatus = 'offline' | 'online' | 'busy'

export interface Driver {
  id: number
  business_id: number
  user_id: number
  vehicle_type: string
  status: DriverStatus
  // Last-known position from before this backend process last restarted --
  // the live map's initial render source; live updates come from
  // /ws/dispatch's driver_position/positions_snapshot events instead.
  last_lat: string | null
  last_lng: string | null
  last_seen_at: string | null
}

// Read-only -- Driver CRUD (create/update/toggle online-offline) belongs to
// the Personal checkpoint, not this one. This only feeds the assignment
// picker on the orders table.
export async function listDrivers(): Promise<Driver[]> {
  const response = await apiClient.get<Driver[]>('/api/v1/drivers')
  return response.data
}
