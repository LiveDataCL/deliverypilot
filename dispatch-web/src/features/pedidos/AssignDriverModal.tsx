import { useEffect, useState } from 'react'
import { strings } from '../../i18n/strings'
import { listDrivers, type Driver } from '../../api/drivers'

interface AssignDriverModalProps {
  onConfirm: (driverId: number) => void
  onCancel: () => void
}

export function AssignDriverModal({ onConfirm, onCancel }: AssignDriverModalProps) {
  const [drivers, setDrivers] = useState<Driver[]>([])
  const [selectedDriverId, setSelectedDriverId] = useState<number | null>(null)

  useEffect(() => {
    listDrivers().then((list) => {
      setDrivers(list)
      if (list.length > 0) setSelectedDriverId(list[0].id)
    })
  }, [])

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/30">
      <div className="w-80 rounded-lg bg-white p-4 shadow-lg">
        <h3 className="mb-3 text-sm font-medium text-slate-700">{strings.pedidos.asignarRepartidor}</h3>
        {drivers.length === 0 ? (
          <p className="text-sm text-slate-500">{strings.pedidos.sinRepartidores}</p>
        ) : (
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">
              {strings.pedidos.seleccionarRepartidor}
            </label>
            <select
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none"
              value={selectedDriverId ?? ''}
              onChange={(e) => setSelectedDriverId(Number(e.target.value))}
            >
              {drivers.map((driver) => (
                <option key={driver.id} value={driver.id}>
                  {driver.vehicle_type} (#{driver.id})
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            disabled={selectedDriverId === null}
            onClick={() => selectedDriverId !== null && onConfirm(selectedDriverId)}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
          >
            {strings.pedidos.confirmar}
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
    </div>
  )
}
