import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { strings } from '../../i18n/strings'
import { getCustomer, getCustomerPrefill, type Customer, type CustomerPrefill } from '../../api/customers'
import { assignDriver, listOrders, updateOrderStatus, type Order, type OrderStatus } from '../../api/orders'
import { AssignDriverModal } from './AssignDriverModal'
import { OrderForm } from './OrderForm'

const STATUS_LABELS: Record<OrderStatus, string> = {
  pendiente: strings.pedidos.estadoPendiente,
  asignado: strings.pedidos.estadoAsignado,
  aceptado: strings.pedidos.estadoAceptado,
  recogido: strings.pedidos.estadoRecogido,
  en_ruta: strings.pedidos.estadoEnRuta,
  entregado: strings.pedidos.estadoEntregado,
  cancelado: strings.pedidos.estadoCancelado,
  fallido: strings.pedidos.estadoFallido,
}

function todayLocalDateString(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function PedidosPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [orders, setOrders] = useState<Order[]>([])
  const [statusFilter, setStatusFilter] = useState<OrderStatus | ''>('')
  const [isLoading, setIsLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [formInitialCustomer, setFormInitialCustomer] = useState<Customer | undefined>(undefined)
  const [formInitialPrefill, setFormInitialPrefill] = useState<CustomerPrefill | undefined>(undefined)
  const [assigningOrderId, setAssigningOrderId] = useState<number | null>(null)

  async function reload() {
    const page = await listOrders({
      on_date: todayLocalDateString(),
      status: statusFilter || undefined,
    })
    setOrders(page.items)
  }

  useEffect(() => {
    setIsLoading(true)
    reload().finally(() => setIsLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter])

  // "Crear pedido" from Clientes por pedir (§4.3) lands here with
  // ?nuevo=1&customer_id=X -- open the form pre-filled exactly as if that
  // customer had just been picked via the live-search widget.
  useEffect(() => {
    const nuevo = searchParams.get('nuevo')
    const customerId = searchParams.get('customer_id')
    if (nuevo && customerId) {
      Promise.all([getCustomer(Number(customerId)), getCustomerPrefill(Number(customerId))]).then(
        ([customer, prefill]) => {
          setFormInitialCustomer(customer)
          setFormInitialPrefill(prefill)
          setShowForm(true)
        },
      )
      setSearchParams({}, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleFormClosed() {
    setShowForm(false)
    setFormInitialCustomer(undefined)
    setFormInitialPrefill(undefined)
    void reload()
  }

  async function handleCancelOrder(orderId: number) {
    await updateOrderStatus(orderId, { status: 'cancelado' })
    await reload()
  }

  async function handleConfirmAssign(driverId: number) {
    if (assigningOrderId === null) return
    await assignDriver(assigningOrderId, driverId)
    setAssigningOrderId(null)
    await reload()
  }

  if (showForm) {
    return (
      <div className="space-y-4">
        <button
          onClick={handleFormClosed}
          className="text-xs font-medium text-slate-600 hover:text-slate-900"
        >
          &larr; {strings.pedidos.volver}
        </button>
        <OrderForm
          initialCustomer={formInitialCustomer}
          initialPrefill={formInitialPrefill}
          onSaved={handleFormClosed}
          onCancel={handleFormClosed}
        />
      </div>
    )
  }

  if (isLoading) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <select
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as OrderStatus | '')}
        >
          <option value="">{strings.pedidos.todos}</option>
          {(Object.keys(STATUS_LABELS) as OrderStatus[]).map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </select>
        <button
          onClick={() => setShowForm(true)}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          {strings.pedidos.nuevoPedido}
        </button>
      </div>

      {orders.length === 0 && <p className="text-sm text-slate-500">{strings.pedidos.sinPedidos}</p>}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2">{strings.pedidos.columnCliente}</th>
              <th className="px-4 py-2">{strings.pedidos.columnDireccion}</th>
              <th className="px-4 py-2">{strings.pedidos.columnMonto}</th>
              <th className="px-4 py-2">{strings.pedidos.columnEstado}</th>
              <th className="px-4 py-2">{strings.pedidos.columnHora}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => (
              <tr key={order.id} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-2">{order.customer_name}</td>
                <td className="px-4 py-2">{order.delivery_address}</td>
                <td className="px-4 py-2">${order.amount.toLocaleString('es-CL')}</td>
                <td className="px-4 py-2">{STATUS_LABELS[order.status]}</td>
                <td className="px-4 py-2">{new Date(order.created_at).toLocaleTimeString('es-CL')}</td>
                <td className="space-x-3 px-4 py-2 text-right">
                  {order.status === 'pendiente' && (
                    <>
                      <button
                        onClick={() => setAssigningOrderId(order.id)}
                        className="text-xs font-medium text-slate-600 hover:text-slate-900"
                      >
                        {strings.pedidos.asignar}
                      </button>
                      <button
                        onClick={() => void handleCancelOrder(order.id)}
                        className="text-xs font-medium text-red-600 hover:text-red-800"
                      >
                        {strings.pedidos.cancelar}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {assigningOrderId !== null && (
        <AssignDriverModal
          onConfirm={(driverId) => void handleConfirmAssign(driverId)}
          onCancel={() => setAssigningOrderId(null)}
        />
      )}
    </div>
  )
}
