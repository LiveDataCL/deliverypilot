import { apiClient } from './client'

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface Customer {
  id: number
  business_id: number
  phone: string
  name: string
  address: string
  address_detail: string | null
  lat: number | null
  lng: number | null
  notes: string | null
  order_frequency_days: number | null
  last_order_at: string | null
  created_at: string
}

export interface CustomerInput {
  phone: string
  name: string
  address: string
  address_detail?: string | null
  notes?: string | null
}

export interface SuggestedItem {
  product_id: number
  name: string
  quantity: number
  unit_price: number
}

export interface CustomerPrefill {
  customer: Customer
  suggested_items: SuggestedItem[]
  suggestion_source: 'last_order' | 'defaults'
}

export async function listCustomers(query?: string): Promise<Page<Customer>> {
  const response = await apiClient.get<Page<Customer>>('/api/v1/customers', {
    params: { limit: 200, q: query || undefined },
  })
  return response.data
}

export async function createCustomer(input: CustomerInput): Promise<Customer> {
  const response = await apiClient.post<Customer>('/api/v1/customers', input)
  return response.data
}

export async function updateCustomer(id: number, input: Partial<CustomerInput>): Promise<Customer> {
  const response = await apiClient.patch<Customer>(`/api/v1/customers/${id}`, input)
  return response.data
}

export async function searchCustomersByPhonePrefix(phonePrefix: string): Promise<Customer[]> {
  const response = await apiClient.get<Customer[]>('/api/v1/customers/search', {
    params: { phone_prefix: phonePrefix },
  })
  return response.data
}

export async function getCustomerPrefill(id: number): Promise<CustomerPrefill> {
  const response = await apiClient.get<CustomerPrefill>(`/api/v1/customers/${id}/prefill`)
  return response.data
}

export async function listDueForReorder(): Promise<Page<Customer>> {
  const response = await apiClient.get<Page<Customer>>('/api/v1/customers/due-for-reorder', {
    params: { limit: 200 },
  })
  return response.data
}
