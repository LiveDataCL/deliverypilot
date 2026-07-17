import { apiClient } from './client'

export type StaffRole = 'dispatcher' | 'driver'

export interface Staff {
  id: number
  business_id: number
  role: StaffRole
  email: string
  phone: string | null
  is_active: boolean
  invite_accepted_at: string | null
  created_at: string
  vehicle_type: string | null
  driver_status: string | null
}

export interface StaffCreateInput {
  email: string
  phone?: string | null
  role: StaffRole
  vehicle_type?: string | null
}

export interface StaffCreateResponse {
  staff: Staff
  invite_token: string
}

export interface ResetPasswordResponse {
  invite_token: string
}

export async function listStaff(): Promise<Staff[]> {
  const response = await apiClient.get<Staff[]>('/api/v1/staff')
  return response.data
}

export async function createStaff(input: StaffCreateInput): Promise<StaffCreateResponse> {
  const response = await apiClient.post<StaffCreateResponse>('/api/v1/staff', input)
  return response.data
}

export async function activateStaff(id: number): Promise<Staff> {
  const response = await apiClient.patch<Staff>(`/api/v1/staff/${id}/activate`)
  return response.data
}

export async function deactivateStaff(id: number): Promise<Staff> {
  const response = await apiClient.patch<Staff>(`/api/v1/staff/${id}/deactivate`)
  return response.data
}

export async function resetStaffPassword(id: number): Promise<ResetPasswordResponse> {
  const response = await apiClient.post<ResetPasswordResponse>(`/api/v1/staff/${id}/reset-password`)
  return response.data
}

export interface AcceptInviteResult {
  access_token: string
  refresh_token: string
}

export async function acceptInvite(token: string, newPassword: string): Promise<AcceptInviteResult> {
  const response = await apiClient.post<AcceptInviteResult>('/api/v1/auth/accept-invite', {
    token,
    new_password: newPassword,
  })
  return response.data
}

export function buildInviteLink(token: string): string {
  return `${window.location.origin}/aceptar-invitacion/${token}`
}
