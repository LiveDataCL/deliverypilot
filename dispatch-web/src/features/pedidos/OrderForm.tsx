import { useEffect, useMemo, useState } from 'react'
import { strings } from '../../i18n/strings'
import { listPaymentMethods, listProducts, type PaymentMethod, type Product } from '../../api/catalog'
import type { Customer, CustomerPrefill } from '../../api/customers'
import { createOrder, type OrderCreateInput, type OrderItemInput } from '../../api/orders'
import { CustomerAutofillField } from './CustomerAutofillField'

interface OrderFormProps {
  initialCustomer?: Customer
  // Set together when opened from "Clientes por pedir" -- makes that flow
  // behave identically to picking the customer via the live-search widget
  // (items pre-filled, suggestion source shown), not just a blank form with
  // the customer silently pre-selected.
  initialPrefill?: CustomerPrefill
  onSaved: () => void
  onCancel: () => void
}

interface ItemRow {
  key: string
  mode: 'catalog' | 'adhoc'
  productId: number | null
  description: string
  quantity: number
  unitPrice: number
}

const inputClass =
  'w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none'
const labelClass = 'block text-xs font-medium text-slate-600 mb-1'

function resolveClientTierPrice(product: Product, quantity: number): number {
  // Mirrors pricing_service.resolve_unit_price's rule client-side, purely
  // for live total feedback -- the server always re-derives this
  // independently and is the actual source of truth.
  const applicable = product.price_tiers
    .filter((t) => t.min_quantity <= quantity)
    .sort((a, b) => b.min_quantity - a.min_quantity)
  return applicable.length > 0 ? applicable[0].unit_price : product.price
}

let rowKeyCounter = 0
function nextRowKey(): string {
  rowKeyCounter += 1
  return `row-${rowKeyCounter}`
}

export function OrderForm({ initialCustomer, initialPrefill, onSaved, onCancel }: OrderFormProps) {
  const [products, setProducts] = useState<Product[]>([])
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([])
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | undefined>(initialCustomer)
  const [typedPhone, setTypedPhone] = useState('')
  const [newName, setNewName] = useState('')
  const [newAddress, setNewAddress] = useState('')
  const [newAddressDetail, setNewAddressDetail] = useState('')
  const [items, setItems] = useState<ItemRow[]>(
    initialPrefill
      ? initialPrefill.suggested_items.map((item) => ({
          key: nextRowKey(),
          mode: 'catalog',
          productId: item.product_id,
          description: '',
          quantity: item.quantity,
          unitPrice: item.unit_price,
        }))
      : [],
  )
  const [suggestionSource, setSuggestionSource] = useState<CustomerPrefill['suggestion_source'] | null>(
    initialPrefill && initialPrefill.suggested_items.length > 0 ? initialPrefill.suggestion_source : null,
  )
  const [paymentMethodId, setPaymentMethodId] = useState<number | null>(null)
  const [cashAmountGiven, setCashAmountGiven] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    listProducts().then((page) => setProducts(page.items.filter((p) => p.active)))
    listPaymentMethods().then((page) => {
      const active = page.items.filter((pm) => pm.active)
      setPaymentMethods(active)
      if (active.length > 0) setPaymentMethodId(active[0].id)
    })
  }, [])

  function handleSelectCustomer(customer: Customer, prefill: CustomerPrefill) {
    setSelectedCustomer(customer)
    setSuggestionSource(prefill.suggested_items.length > 0 ? prefill.suggestion_source : null)
    setItems(
      prefill.suggested_items.map((item) => ({
        key: nextRowKey(),
        mode: 'catalog',
        productId: item.product_id,
        description: '',
        quantity: item.quantity,
        unitPrice: item.unit_price,
      })),
    )
  }

  function handleClearSelection() {
    setSelectedCustomer(undefined)
    setItems([])
    setSuggestionSource(null)
  }

  function addCatalogItem() {
    if (products.length === 0) return
    const product = products[0]
    setItems((rows) => [
      ...rows,
      {
        key: nextRowKey(),
        mode: 'catalog',
        productId: product.id,
        description: '',
        quantity: 1,
        unitPrice: resolveClientTierPrice(product, 1),
      },
    ])
  }

  function addAdhocItem() {
    setItems((rows) => [
      ...rows,
      { key: nextRowKey(), mode: 'adhoc', productId: null, description: '', quantity: 1, unitPrice: 0 },
    ])
  }

  function updateItem(key: string, patch: Partial<ItemRow>) {
    setItems((rows) =>
      rows.map((row) => {
        if (row.key !== key) return row
        const updated = { ...row, ...patch }
        // Re-resolve the tier price when product or quantity changes, unless
        // the operator is the one editing unitPrice directly right now.
        if (updated.mode === 'catalog' && !('unitPrice' in patch) && updated.productId !== null) {
          const product = products.find((p) => p.id === updated.productId)
          if (product) updated.unitPrice = resolveClientTierPrice(product, updated.quantity)
        }
        return updated
      }),
    )
  }

  function removeItem(key: string) {
    setItems((rows) => rows.filter((row) => row.key !== key))
  }

  const total = useMemo(
    () => items.reduce((sum, row) => sum + row.quantity * row.unitPrice, 0),
    [items],
  )
  const selectedPaymentMethod = paymentMethods.find((pm) => pm.id === paymentMethodId)
  const cashGivenNumber = Number(cashAmountGiven || 0)
  const vuelto = cashGivenNumber - total

  async function handleSubmit() {
    setError(null)
    if (items.length === 0) {
      setError(strings.pedidos.errorGenerico)
      return
    }

    const orderItems: OrderItemInput[] = items.map((row) =>
      row.mode === 'catalog'
        ? { product_id: row.productId, quantity: row.quantity, unit_price: row.unitPrice }
        : { description: row.description, quantity: row.quantity, unit_price: row.unitPrice },
    )

    const payload: OrderCreateInput = {
      customer_id: selectedCustomer ? selectedCustomer.id : null,
      new_customer: selectedCustomer
        ? null
        : {
            phone: typedPhone,
            name: newName,
            address: newAddress,
            address_detail: newAddressDetail || null,
          },
      items: orderItems,
      payment_method_id: paymentMethodId as number,
      cash_amount_given: selectedPaymentMethod?.requires_change ? cashGivenNumber : null,
      notes: notes || null,
    }

    setIsSaving(true)
    try {
      await createOrder(payload)
      onSaved()
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(detail ?? strings.pedidos.errorGenerico)
    } finally {
      setIsSaving(false)
    }
  }

  const showNewCustomerFields = !selectedCustomer && typedPhone.length > 0

  return (
    <div className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
      <CustomerAutofillField
        onSelectCustomer={handleSelectCustomer}
        onPhoneChange={setTypedPhone}
        selectedCustomerName={selectedCustomer?.name}
        onClearSelection={handleClearSelection}
      />

      {showNewCustomerFields && (
        <div className="grid grid-cols-2 gap-3 rounded-md border border-slate-200 bg-white p-3">
          <p className="col-span-2 text-xs font-medium text-slate-500">
            {strings.pedidos.clienteNuevo}
          </p>
          <div>
            <label className={labelClass}>{strings.pedidos.nombreCliente}</label>
            <input className={inputClass} value={newName} onChange={(e) => setNewName(e.target.value)} />
          </div>
          <div>
            <label className={labelClass}>{strings.pedidos.direccionCliente}</label>
            <input
              className={inputClass}
              value={newAddress}
              onChange={(e) => setNewAddress(e.target.value)}
            />
          </div>
          <div className="col-span-2">
            <label className={labelClass}>{strings.pedidos.direccionDetalleCliente}</label>
            <input
              className={inputClass}
              value={newAddressDetail}
              onChange={(e) => setNewAddressDetail(e.target.value)}
            />
          </div>
        </div>
      )}

      {suggestionSource && (
        <p className="text-xs text-slate-500">
          {suggestionSource === 'last_order'
            ? strings.pedidos.ultimoPedidoSugerido
            : strings.pedidos.pedidoHabitualSugerido}
        </p>
      )}

      <div className="rounded-md border border-slate-200 bg-white p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium text-slate-700">{strings.pedidos.items}</span>
          <div className="space-x-3">
            <button
              type="button"
              onClick={addCatalogItem}
              className="text-xs font-medium text-slate-600 hover:text-slate-900"
            >
              + {strings.pedidos.agregarItem}
            </button>
            <button
              type="button"
              onClick={addAdhocItem}
              className="text-xs font-medium text-slate-600 hover:text-slate-900"
            >
              + {strings.pedidos.agregarItemLibre}
            </button>
          </div>
        </div>
        <div className="space-y-2">
          {items.map((row) => (
            <div key={row.key} className="flex items-center gap-2">
              {row.mode === 'catalog' ? (
                <select
                  className={inputClass}
                  value={row.productId ?? ''}
                  onChange={(e) => updateItem(row.key, { productId: Number(e.target.value) })}
                >
                  {products.map((product) => (
                    <option key={product.id} value={product.id}>
                      {product.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className={inputClass}
                  placeholder={strings.pedidos.descripcionLibre}
                  value={row.description}
                  onChange={(e) => updateItem(row.key, { description: e.target.value })}
                />
              )}
              <input
                type="number"
                min={1}
                className={`${inputClass} w-20`}
                value={row.quantity}
                onChange={(e) => updateItem(row.key, { quantity: Number(e.target.value) })}
              />
              <input
                type="number"
                min={0}
                className={`${inputClass} w-28`}
                value={row.unitPrice}
                onChange={(e) => updateItem(row.key, { unitPrice: Number(e.target.value) })}
              />
              <button
                type="button"
                onClick={() => removeItem(row.key)}
                className="text-xs text-red-600 hover:text-red-800"
              >
                {strings.pedidos.quitar}
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass}>{strings.pedidos.metodoPago}</label>
          <select
            className={inputClass}
            value={paymentMethodId ?? ''}
            onChange={(e) => setPaymentMethodId(Number(e.target.value))}
          >
            {paymentMethods.map((pm) => (
              <option key={pm.id} value={pm.id}>
                {pm.name}
              </option>
            ))}
          </select>
        </div>
        {selectedPaymentMethod?.requires_change && (
          <div>
            <label className={labelClass}>{strings.pedidos.conCuantoPaga}</label>
            <input
              type="number"
              min={0}
              className={inputClass}
              value={cashAmountGiven}
              onChange={(e) => setCashAmountGiven(e.target.value)}
            />
          </div>
        )}
      </div>

      <div className="flex items-center justify-between rounded-md bg-white p-3 text-sm">
        <span className="font-medium text-slate-700">
          {strings.pedidos.total}: ${total.toLocaleString('es-CL')}
        </span>
        {selectedPaymentMethod?.requires_change && cashAmountGiven && (
          <span className="text-slate-600">
            {strings.pedidos.vuelto}: ${Math.max(0, vuelto).toLocaleString('es-CL')}
          </span>
        )}
      </div>

      <div>
        <label className={labelClass}>{strings.pedidos.notas}</label>
        <textarea className={inputClass} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          type="button"
          disabled={isSaving}
          onClick={() => void handleSubmit()}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {isSaving ? strings.pedidos.guardando : strings.pedidos.guardarPedido}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
        >
          {strings.pedidos.cancelar}
        </button>
      </div>
    </div>
  )
}
