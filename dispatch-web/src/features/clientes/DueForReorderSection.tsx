import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { strings } from '../../i18n/strings'
import { listDueForReorder, type Customer } from '../../api/customers'

function daysSince(isoDate: string): number {
  const then = new Date(isoDate).getTime()
  const now = Date.now()
  return Math.floor((now - then) / (1000 * 60 * 60 * 24))
}

export function DueForReorderSection() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    setIsLoading(true)
    listDueForReorder()
      .then((page) => setCustomers(page.items))
      .finally(() => setIsLoading(false))
  }, [])

  if (isLoading) return null

  if (customers.length === 0) {
    return <p className="text-sm text-slate-500">{strings.clientes.sinClientesPorPedir}</p>
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
          <tr>
            <th className="px-4 py-2">{strings.clientes.columnNombre}</th>
            <th className="px-4 py-2">{strings.clientes.columnUltimoPedido}</th>
            <th className="px-4 py-2">{strings.clientes.frecuencia}</th>
            <th className="px-4 py-2" />
          </tr>
        </thead>
        <tbody>
          {customers.map((customer) => (
            <tr key={customer.id} className="border-b border-slate-100 last:border-0">
              <td className="px-4 py-2">{customer.name}</td>
              <td className="px-4 py-2">
                {customer.last_order_at
                  ? strings.clientes.ultimoPedidoHace.replace(
                      '{dias}',
                      String(daysSince(customer.last_order_at)),
                    )
                  : '-'}
              </td>
              <td className="px-4 py-2">
                {customer.order_frequency_days != null
                  ? strings.clientes.frecuenciaDias.replace(
                      '{dias}',
                      String(Math.round(customer.order_frequency_days)),
                    )
                  : '-'}
              </td>
              <td className="space-x-3 px-4 py-2 text-right">
                <a
                  href={`tel:${customer.phone}`}
                  className="text-xs font-medium text-slate-600 hover:text-slate-900"
                >
                  {strings.clientes.llamar}
                </a>
                <a
                  href={`https://wa.me/${customer.phone.replace('+', '')}`}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs font-medium text-slate-600 hover:text-slate-900"
                >
                  {strings.clientes.whatsapp}
                </a>
                <button
                  onClick={() => navigate(`/pedidos?nuevo=1&customer_id=${customer.id}`)}
                  className="text-xs font-medium text-slate-600 hover:text-slate-900"
                >
                  {strings.clientes.crearPedido}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
