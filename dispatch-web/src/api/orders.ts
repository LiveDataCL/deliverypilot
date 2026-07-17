import { apiClient } from './client'

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export type OrderStatus =
  | 'pendiente'
  | 'asignado'
  | 'aceptado'
  | 'recogido'
  | 'en_ruta'
  | 'entregado'
  | 'cancelado'
  | 'fallido'

export interface NewCustomerInput {
  phone: string
  name: string
  address: string
  address_detail?: string | null
  lat?: string | null
  lng?: string | null
}

export interface OrderItemInput {
  product_id?: number | null
  description?: string | null
  quantity: number
  // Alongside product_id: omit to auto-resolve the tier price, or set to
  // override it (SPEC.md E2E criterion 6). Required for ad-hoc items.
  unit_price?: number | null
}

export interface OrderCreateInput {
  customer_id?: number | null
  new_customer?: NewCustomerInput | null
  items: OrderItemInput[]
  payment_method_id: number
  cash_amount_given?: number | null
  notes?: string | null
  pickup_address?: string | null
  pickup_lat?: string | null
  pickup_lng?: string | null
}

export interface OrderItem {
  id: number
  product_id: number | null
  description: string | null
  quantity: number
  unit_price: number
  subtotal: number
}

export interface Order {
  id: number
  business_id: number
  customer_id: number | null
  customer_name: string
  customer_phone: string
  delivery_address: string
  delivery_lat: string
  delivery_lng: string
  pickup_address: string | null
  pickup_lat: string | null
  pickup_lng: string | null
  amount: number
  payment_method_id: number
  cash_amount_given: number | null
  notes: string | null
  status: OrderStatus
  driver_id: number | null
  tracking_token: string
  created_at: string
  assigned_at: string | null
  accepted_at: string | null
  picked_up_at: string | null
  delivered_at: string | null
  items: OrderItem[]
}

export async function createOrder(input: OrderCreateInput): Promise<Order> {
  const response = await apiClient.post<Order>('/api/v1/orders', input)
  return response.data
}

export async function listOrders(params: {
  status?: OrderStatus
  on_date?: string
  limit?: number
  offset?: number
}): Promise<Page<Order>> {
  const response = await apiClient.get<Page<Order>>('/api/v1/orders', {
    params: { limit: 200, ...params },
  })
  return response.data
}

export async function getOrder(id: number): Promise<Order> {
  const response = await apiClient.get<Order>(`/api/v1/orders/${id}`)
  return response.data
}

export async function assignDriver(orderId: number, driverId: number): Promise<Order> {
  const response = await apiClient.post<Order>(`/api/v1/orders/${orderId}/assign`, {
    driver_id: driverId,
  })
  return response.data
}

export async function updateOrderStatus(
  orderId: number,
  input: { status: OrderStatus; lat?: string | null; lng?: string | null; note?: string | null },
): Promise<Order> {
  const response = await apiClient.patch<Order>(`/api/v1/orders/${orderId}/status`, input)
  return response.data
}
