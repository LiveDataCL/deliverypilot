import { apiClient } from './client'

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface ComboItem {
  id: number
  component_product_id: number
  quantity: number
}

export interface ComboItemInput {
  component_product_id: number
  quantity: number
}

export interface PriceTier {
  id: number
  min_quantity: number
  unit_price: number
}

export interface PriceTierInput {
  min_quantity: number
  unit_price: number
}

export interface Product {
  id: number
  business_id: number
  name: string
  description: string | null
  price: number
  unit: string
  active: boolean
  is_combo: boolean
  image_url: string | null
  sort_order: number
  combo_items: ComboItem[]
  price_tiers: PriceTier[]
}

export interface ProductInput {
  name: string
  description?: string | null
  price: number
  unit: string
  is_combo?: boolean
  image_url?: string | null
  active?: boolean
  sort_order?: number
}

export type PaymentMethodType = 'efectivo' | 'transferencia' | 'pos' | 'online' | 'otro'

export interface PaymentMethod {
  id: number
  business_id: number
  name: string
  type: PaymentMethodType
  requires_change: boolean
  active: boolean
  sort_order: number
}

export interface PaymentMethodInput {
  name: string
  type: PaymentMethodType
  requires_change?: boolean
  active?: boolean
  sort_order?: number
}

export async function listProducts(): Promise<Page<Product>> {
  const response = await apiClient.get<Page<Product>>('/api/v1/products', {
    params: { limit: 200, active_only: false },
  })
  return response.data
}

export async function createProduct(input: ProductInput): Promise<Product> {
  const response = await apiClient.post<Product>('/api/v1/products', input)
  return response.data
}

export async function updateProduct(id: number, input: Partial<ProductInput>): Promise<Product> {
  const response = await apiClient.patch<Product>(`/api/v1/products/${id}`, input)
  return response.data
}

export async function replaceComboItems(
  productId: number,
  items: ComboItemInput[],
): Promise<ComboItem[]> {
  const response = await apiClient.put<ComboItem[]>(
    `/api/v1/products/${productId}/combo-items`,
    items,
  )
  return response.data
}

export async function replacePriceTiers(
  productId: number,
  tiers: PriceTierInput[],
): Promise<PriceTier[]> {
  const response = await apiClient.put<PriceTier[]>(
    `/api/v1/products/${productId}/price-tiers`,
    tiers,
  )
  return response.data
}

export async function listPaymentMethods(): Promise<Page<PaymentMethod>> {
  const response = await apiClient.get<Page<PaymentMethod>>('/api/v1/payment-methods', {
    params: { limit: 200, active_only: false },
  })
  return response.data
}

export async function createPaymentMethod(input: PaymentMethodInput): Promise<PaymentMethod> {
  const response = await apiClient.post<PaymentMethod>('/api/v1/payment-methods', input)
  return response.data
}

export async function updatePaymentMethod(
  id: number,
  input: Partial<PaymentMethodInput>,
): Promise<PaymentMethod> {
  const response = await apiClient.patch<PaymentMethod>(`/api/v1/payment-methods/${id}`, input)
  return response.data
}
