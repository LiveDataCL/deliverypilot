import { useState, type FormEvent } from 'react'
import { strings } from '../../i18n/strings'
import { createCustomer, updateCustomer, type Customer, type CustomerInput } from '../../api/customers'

interface CustomerFormProps {
  customer?: Customer
  onSaved: () => void
  onCancel: () => void
}

const inputClass =
  'w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none'
const labelClass = 'block text-xs font-medium text-slate-600 mb-1'

const PHONE_PATTERN = /^\+56\d{9}$/

export function CustomerForm({ customer, onSaved, onCancel }: CustomerFormProps) {
  const [phone, setPhone] = useState(customer?.phone ?? '+56')
  const [name, setName] = useState(customer?.name ?? '')
  const [address, setAddress] = useState(customer?.address ?? '')
  const [addressDetail, setAddressDetail] = useState(customer?.address_detail ?? '')
  const [notes, setNotes] = useState(customer?.notes ?? '')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    if (!PHONE_PATTERN.test(phone)) {
      setError(strings.clientes.telefonoInvalido)
      return
    }

    setIsSaving(true)
    try {
      const payload: CustomerInput = {
        phone,
        name,
        address,
        address_detail: addressDetail || null,
        notes: notes || null,
      }
      if (customer) {
        await updateCustomer(customer.id, payload)
      } else {
        await createCustomer(payload)
      }
      onSaved()
    } catch (err) {
      const code = (err as { response?: { data?: { code?: string } } })?.response?.data?.code
      setError(code === 'duplicate_phone' ? strings.clientes.telefonoDuplicado : strings.clientes.errorGenerico)
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
          <label className={labelClass}>{strings.clientes.telefono}</label>
          <input
            className={inputClass}
            required
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass}>{strings.clientes.nombre}</label>
          <input
            className={inputClass}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div className="col-span-2">
          <label className={labelClass}>{strings.clientes.direccion}</label>
          <input
            className={inputClass}
            required
            value={address}
            onChange={(e) => setAddress(e.target.value)}
          />
        </div>
        <div className="col-span-2">
          <label className={labelClass}>{strings.clientes.direccionDetalle}</label>
          <input
            className={inputClass}
            value={addressDetail}
            onChange={(e) => setAddressDetail(e.target.value)}
          />
        </div>
        <div className="col-span-2">
          <label className={labelClass}>{strings.clientes.notas}</label>
          <textarea
            className={inputClass}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={isSaving}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {strings.clientes.guardar}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
        >
          {strings.clientes.cancelar}
        </button>
      </div>
    </form>
  )
}
