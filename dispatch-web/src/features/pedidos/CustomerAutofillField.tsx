import { useEffect, useRef, useState } from 'react'
import { strings } from '../../i18n/strings'
import {
  getCustomerPrefill,
  searchCustomersByPhonePrefix,
  type Customer,
  type CustomerPrefill,
} from '../../api/customers'

interface CustomerAutofillFieldProps {
  onSelectCustomer: (customer: Customer, prefill: CustomerPrefill) => void
  onPhoneChange: (fullPhone: string) => void
  selectedCustomerName?: string
  onClearSelection: () => void
}

const inputClass =
  'w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none'
const labelClass = 'block text-xs font-medium text-slate-600 mb-1'

// The live phone-search-autofill widget deferred from the clientes/autofill
// checkpoint (SPEC.md §4.1) -- built here because this is the order form it
// was always meant to live inside; had no home until this checkpoint.
export function CustomerAutofillField({
  onSelectCustomer,
  onPhoneChange,
  selectedCustomerName,
  onClearSelection,
}: CustomerAutofillFieldProps) {
  const [digits, setDigits] = useState('')
  const [results, setResults] = useState<Customer[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    onPhoneChange(digits ? `+56${digits}` : '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [digits])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (digits.length < 4) {
      setResults([])
      setIsSearching(false)
      return
    }
    setIsSearching(true)
    debounceRef.current = setTimeout(() => {
      searchCustomersByPhonePrefix(digits)
        .then(setResults)
        .finally(() => setIsSearching(false))
    }, 300)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [digits])

  async function handlePick(customer: Customer) {
    const prefill = await getCustomerPrefill(customer.id)
    setResults([])
    setDigits('')
    onSelectCustomer(customer, prefill)
  }

  if (selectedCustomerName) {
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium text-slate-700">{strings.pedidos.clienteSeleccionado}:</span>
        <span>{selectedCustomerName}</span>
        <button
          type="button"
          onClick={onClearSelection}
          className="text-xs font-medium text-slate-600 hover:text-slate-900"
        >
          {strings.pedidos.cambiarCliente}
        </button>
      </div>
    )
  }

  return (
    <div className="relative">
      <label className={labelClass}>{strings.pedidos.telefonoLabel}</label>
      <div className="flex items-center gap-2">
        <span className="text-sm text-slate-500">+56</span>
        <input
          className={inputClass}
          placeholder={strings.pedidos.telefonoPlaceholder}
          value={digits}
          onChange={(e) => setDigits(e.target.value.replace(/\D/g, ''))}
        />
      </div>
      {isSearching && <p className="mt-1 text-xs text-slate-400">{strings.pedidos.buscando}</p>}
      {results.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full rounded-md border border-slate-200 bg-white shadow-sm">
          {results.map((customer) => (
            <li key={customer.id}>
              <button
                type="button"
                onClick={() => void handlePick(customer)}
                className="w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
              >
                <span className="font-medium">{customer.name}</span>{' '}
                <span className="text-slate-500">{customer.phone}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
