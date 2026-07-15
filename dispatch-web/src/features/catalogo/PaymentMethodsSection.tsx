import { Fragment, useEffect, useState } from 'react'
import { strings } from '../../i18n/strings'
import { listPaymentMethods, updatePaymentMethod, type PaymentMethod } from '../../api/catalog'
import { PaymentMethodForm } from './PaymentMethodForm'

const TYPE_LABELS: Record<string, string> = {
  efectivo: strings.catalogo.tipoEfectivo,
  transferencia: strings.catalogo.tipoTransferencia,
  pos: strings.catalogo.tipoPos,
  online: strings.catalogo.tipoOnline,
  otro: strings.catalogo.tipoOtro,
}

export function PaymentMethodsSection() {
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)

  async function reload() {
    const page = await listPaymentMethods()
    setPaymentMethods(page.items)
  }

  useEffect(() => {
    setIsLoading(true)
    reload().finally(() => setIsLoading(false))
  }, [])

  async function handleToggleActive(paymentMethod: PaymentMethod) {
    await updatePaymentMethod(paymentMethod.id, { active: !paymentMethod.active })
    await reload()
  }

  function handleSaved() {
    setEditingId(null)
    void reload()
  }

  if (isLoading) return null

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => setEditingId('new')}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          {strings.catalogo.nuevoMetodoPago}
        </button>
      </div>

      {editingId === 'new' && (
        <PaymentMethodForm onSaved={handleSaved} onCancel={() => setEditingId(null)} />
      )}

      {paymentMethods.length === 0 && editingId !== 'new' && (
        <p className="text-sm text-slate-500">{strings.catalogo.sinMetodosPago}</p>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2">{strings.catalogo.columnNombre}</th>
              <th className="px-4 py-2">{strings.catalogo.columnTipo}</th>
              <th className="px-4 py-2">{strings.catalogo.columnCambio}</th>
              <th className="px-4 py-2">{strings.catalogo.columnEstado}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {paymentMethods.map((paymentMethod) => (
              <Fragment key={paymentMethod.id}>
                <tr className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2">{paymentMethod.name}</td>
                  <td className="px-4 py-2">{TYPE_LABELS[paymentMethod.type]}</td>
                  <td className="px-4 py-2">{paymentMethod.requires_change ? 'Si' : 'No'}</td>
                  <td className="px-4 py-2">
                    <span className={paymentMethod.active ? 'text-emerald-600' : 'text-slate-400'}>
                      {paymentMethod.active ? strings.catalogo.activo : strings.catalogo.inactivo}
                    </span>
                  </td>
                  <td className="space-x-3 px-4 py-2 text-right">
                    <button
                      onClick={() => setEditingId(paymentMethod.id)}
                      className="text-xs font-medium text-slate-600 hover:text-slate-900"
                    >
                      {strings.catalogo.editar}
                    </button>
                    <button
                      onClick={() => handleToggleActive(paymentMethod)}
                      className="text-xs font-medium text-slate-600 hover:text-slate-900"
                    >
                      {paymentMethod.active ? strings.catalogo.desactivar : strings.catalogo.activar}
                    </button>
                  </td>
                </tr>
                {editingId === paymentMethod.id && (
                  <tr>
                    <td colSpan={5} className="p-4">
                      <PaymentMethodForm
                        paymentMethod={paymentMethod}
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
