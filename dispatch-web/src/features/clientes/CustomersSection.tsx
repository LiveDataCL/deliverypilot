import { Fragment, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { strings } from '../../i18n/strings'
import { listCustomers, type Customer } from '../../api/customers'
import { CustomerForm } from './CustomerForm'

export function CustomersSection() {
  const navigate = useNavigate()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [query, setQuery] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)

  async function reload(q: string) {
    const page = await listCustomers(q)
    setCustomers(page.items)
  }

  useEffect(() => {
    setIsLoading(true)
    reload(query).finally(() => setIsLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const timeout = setTimeout(() => {
      void reload(query)
    }, 300)
    return () => clearTimeout(timeout)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  function handleSaved() {
    setEditingId(null)
    void reload(query)
  }

  if (isLoading) return null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <input
          className="w-72 rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
          placeholder={strings.clientes.buscarPlaceholder}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          onClick={() => setEditingId('new')}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          {strings.clientes.nuevoCliente}
        </button>
      </div>

      {editingId === 'new' && <CustomerForm onSaved={handleSaved} onCancel={() => setEditingId(null)} />}

      {customers.length === 0 && editingId !== 'new' && (
        <p className="text-sm text-slate-500">
          {query ? strings.clientes.sinResultadosBusqueda : strings.clientes.sinClientes}
        </p>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2">{strings.clientes.columnNombre}</th>
              <th className="px-4 py-2">{strings.clientes.columnTelefono}</th>
              <th className="px-4 py-2">{strings.clientes.columnDireccion}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {customers.map((customer) => (
              <Fragment key={customer.id}>
                <tr className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2">{customer.name}</td>
                  <td className="px-4 py-2">{customer.phone}</td>
                  <td className="px-4 py-2">{customer.address}</td>
                  <td className="space-x-3 px-4 py-2 text-right">
                    <button
                      onClick={() => navigate(`/clientes/${customer.id}`)}
                      className="text-xs font-medium text-slate-600 hover:text-slate-900"
                    >
                      {strings.clientes.verDetalle}
                    </button>
                    <button
                      onClick={() => setEditingId(customer.id)}
                      className="text-xs font-medium text-slate-600 hover:text-slate-900"
                    >
                      {strings.clientes.editar}
                    </button>
                  </td>
                </tr>
                {editingId === customer.id && (
                  <tr>
                    <td colSpan={4} className="p-4">
                      <CustomerForm
                        customer={customer}
                        onSaved={handleSaved}
                        onCancel={() => setEditingId(null)}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
