import { useState, type FormEvent } from 'react'
import { strings } from '../../i18n/strings'
import {
  createPaymentMethod,
  updatePaymentMethod,
  type PaymentMethod,
  type PaymentMethodInput,
  type PaymentMethodType,
} from '../../api/catalog'

interface PaymentMethodFormProps {
  paymentMethod?: PaymentMethod
  onSaved: () => void
  onCancel: () => void
}

const inputClass =
  'w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none'
const labelClass = 'block text-xs font-medium text-slate-600 mb-1'

const TYPE_OPTIONS: { value: PaymentMethodType; label: string }[] = [
  { value: 'efectivo', label: strings.catalogo.tipoEfectivo },
  { value: 'transferencia', label: strings.catalogo.tipoTransferencia },
  { value: 'pos', label: strings.catalogo.tipoPos },
  { value: 'online', label: strings.catalogo.tipoOnline },
  { value: 'otro', label: strings.catalogo.tipoOtro },
]

export function PaymentMethodForm({ paymentMethod, onSaved, onCancel }: PaymentMethodFormProps) {
  const [name, setName] = useState(paymentMethod?.name ?? '')
  const [type, setType] = useState<PaymentMethodType>(paymentMethod?.type ?? 'efectivo')
  const [requiresChange, setRequiresChange] = useState(paymentMethod?.requires_change ?? false)
  const [active, setActive] = useState(paymentMethod?.active ?? true)
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSaving(true)
    try {
      const payload: PaymentMethodInput = {
        name,
        type,
        requires_change: requiresChange,
        active,
      }
      if (paymentMethod) {
        await updatePaymentMethod(paymentMethod.id, payload)
      } else {
        await createPaymentMethod(payload)
      }
      onSaved()
    } catch {
      setError(strings.catalogo.errorGenerico)
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
          <label className={labelClass}>{strings.catalogo.nombre}</label>
          <input
            className={inputClass}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass}>{strings.catalogo.tipoPago}</label>
          <select
            className={inputClass}
            value={type}
            onChange={(e) => setType(e.target.value as PaymentMethodType)}
          >
            {TYPE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex gap-6 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={requiresChange}
            onChange={(e) => setRequiresChange(e.target.checked)}
          />
          {strings.catalogo.pideVuelto}
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          {strings.catalogo.activo}
        </label>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={isSaving}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {strings.catalogo.guardar}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
        >
          {strings.catalogo.cancelar}
        </button>
      </div>
    </form>
  )
}
