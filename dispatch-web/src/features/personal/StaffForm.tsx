import { useState, type FormEvent } from 'react'
import { strings } from '../../i18n/strings'
import { createStaff, type StaffRole } from '../../api/staff'

interface StaffFormProps {
  onSaved: (inviteToken: string) => void
  onCancel: () => void
}

const inputClass =
  'w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none'
const labelClass = 'block text-xs font-medium text-slate-600 mb-1'

export function StaffForm({ onSaved, onCancel }: StaffFormProps) {
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [role, setRole] = useState<StaffRole>('dispatcher')
  const [vehicleType, setVehicleType] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSaving(true)
    try {
      const response = await createStaff({
        email,
        phone: phone || null,
        role,
        vehicle_type: role === 'driver' ? vehicleType : null,
      })
      onSaved(response.invite_token)
    } catch (err) {
      const code = (err as { response?: { data?: { code?: string } } })?.response?.data?.code
      setError(code === 'email_taken' ? strings.personal.emailDuplicado : strings.personal.errorGenerico)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-4"
    >
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass}>{strings.personal.email}</label>
          <input
            type="email"
            className={inputClass}
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass}>{strings.personal.telefono}</label>
          <input className={inputClass} value={phone} onChange={(e) => setPhone(e.target.value)} />
        </div>
        <div>
          <label className={labelClass}>{strings.personal.rol}</label>
          <select
            className={inputClass}
            value={role}
            onChange={(e) => setRole(e.target.value as StaffRole)}
          >
            <option value="dispatcher">{strings.personal.rolDespachador}</option>
            <option value="driver">{strings.personal.rolRepartidor}</option>
          </select>
        </div>
        {role === 'driver' && (
          <div>
            <label className={labelClass}>{strings.personal.vehiculo}</label>
            <input
              className={inputClass}
              required
              value={vehicleType}
              onChange={(e) => setVehicleType(e.target.value)}
            />
          </div>
        )}
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={isSaving}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {strings.personal.guardar}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
        >
          {strings.personal.cancelar}
        </button>
      </div>
    </form>
  )
}
