import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { strings } from '../../i18n/strings'
import { listProducts, type Product } from '../../api/catalog'
import {
  getCustomer,
  listCustomerDefaults,
  replaceCustomerDefaults,
  type Customer,
  type CustomerDefault,
  type CustomerDefaultInput,
} from '../../api/customers'
import { listOrders, type Order, type OrderStatus } from '../../api/orders'

const HISTORY_LIMIT = 20

const STATUS_LABELS: Record<OrderStatus, string> = {
  pendiente: strings.clientes.estadoPendiente,
  asignado: strings.clientes.estadoAsignado,
  aceptado: strings.clientes.estadoAceptado,
  recogido: strings.clientes.estadoRecogido,
  en_ruta: strings.clientes.estadoEnRuta,
  entregado: strings.clientes.estadoEntregado,
  cancelado: strings.clientes.estadoCancelado,
  fallido: strings.clientes.estadoFallido,
}

interface DefaultRow {
  key: string
  product_id: number
  quantity: number
}

let rowKeyCounter = 0
function nextRowKey(): string {
  rowKeyCounter += 1
  return `default-row-${rowKeyCounter}`
}

function toRows(defaults: CustomerDefault[]): DefaultRow[] {
  return defaults.map((d) => ({ key: nextRowKey(), product_id: d.product_id, quantity: d.quantity }))
}

export function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const customerId = Number(id)
  const navigate = useNavigate()

  const [customer, setCustomer] = useState<Customer | null>(null)
  const [orders, setOrders] = useState<Order[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [rows, setRows] = useState<DefaultRow[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setIsLoading(true)
    Promise.all([
      getCustomer(customerId),
      listOrders({ customer_id: customerId, limit: HISTORY_LIMIT }),
      listCustomerDefaults(customerId),
      listProducts(),
    ])
      .then(([customerData, orderPage, defaults, productPage]) => {
        setCustomer(customerData)
        setOrders(orderPage.items)
        setRows(toRows(defaults))
        setProducts(productPage.items.filter((p) => p.active))
      })
      .finally(() => setIsLoading(false))
  }, [customerId])

  function addRow() {
    if (products.length === 0) return
    setRows((current) => [...current, { key: nextRowKey(), product_id: products[0].id, quantity: 1 }])
  }

  function updateRow(key: string, patch: Partial<DefaultRow>) {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)))
  }

  function removeRow(key: string) {
    setRows((current) => current.filter((row) => row.key !== key))
  }

  async function handleSaveDefaults() {
    setError(null)
    setIsSaving(true)
    try {
      const items: CustomerDefaultInput[] = rows.map((row) => ({
        product_id: row.product_id,
        quantity: row.quantity,
      }))
      const saved = await replaceCustomerDefaults(customerId, items)
      setRows(toRows(saved))
    } catch {
      setError(strings.clientes.errorGenerico)
    } finally {
      setIsSaving(false)
    }
  }

  if (isLoading || customer === null) return null

  return (
    <div className="space-y-6">
      <button
        onClick={() => navigate('/clientes')}
        className="text-xs font-medium text-slate-600 hover:text-slate-900"
      >
        &larr; {strings.clientes.volver}
      </button>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium text-slate-700">{strings.clientes.infoCliente}</h2>
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-xs text-slate-500">{strings.clientes.columnNombre}</dt>
            <dd>{customer.name}</dd>
          </div>
          <div>
            <dt className="text-xs text-slate-500">{strings.clientes.columnTelefono}</dt>
            <dd>{customer.phone}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-xs text-slate-500">{strings.clientes.columnDireccion}</dt>
            <dd>{customer.address}</dd>
          </div>
        </dl>
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-medium text-slate-700">{strings.clientes.pedidoHabitual}</h2>
        <p className="mb-3 text-xs text-slate-500">{strings.clientes.pedidoHabitualAyuda}</p>

        {rows.length === 0 && (
          <p className="mb-2 text-sm text-slate-500">{strings.clientes.sinPedidoHabitual}</p>
        )}

        <div className="space-y-2">
          {rows.map((row) => (
            <div key={row.key} className="flex items-center gap-2">
              <select
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
                value={row.product_id}
                onChange={(e) => updateRow(row.key, { product_id: Number(e.target.value) })}
              >
                {products.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.name}
                  </option>
                ))}
              </select>
              <input
                type="number"
                min={1}
                className="w-24 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
                value={row.quantity}
                onChange={(e) => updateRow(row.key, { quantity: Number(e.target.value) })}
              />
              <button
                type="button"
                onClick={() => removeRow(row.key)}
                className="text-xs text-red-600 hover:text-red-800"
              >
                {strings.clientes.quitar}
              </button>
            </div>
          ))}
        </div>

        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            onClick={addRow}
            disabled={products.length === 0}
            className="text-xs font-medium text-slate-600 hover:text-slate-900 disabled:opacity-40"
          >
            + {strings.clientes.agregarProducto}
          </button>
          <button
            type="button"
            disabled={isSaving}
            onClick={() => void handleSaveDefaults()}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {strings.clientes.guardarPedidoHabitual}
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-medium text-slate-700">{strings.clientes.historialPedidos}</h2>
        <p className="mb-3 text-xs text-slate-500">
          {strings.clientes.mostrandoRecientes.replace('{n}', String(HISTORY_LIMIT))}
        </p>
        {orders.length === 0 ? (
          <p className="text-sm text-slate-500">{strings.clientes.sinHistorialPedidos}</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-2 py-2">{strings.clientes.columnFecha}</th>
                <th className="px-2 py-2">{strings.clientes.columnEstado}</th>
                <th className="px-2 py-2">{strings.clientes.columnMonto}</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-2 py-2">{new Date(order.created_at).toLocaleDateString('es-CL')}</td>
                  <td className="px-2 py-2">{STATUS_LABELS[order.status]}</td>
                  <td className="px-2 py-2">${order.amount.toLocaleString('es-CL')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
