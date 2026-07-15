import { strings } from '../i18n/strings'

// Every Fase 0 sidebar destination renders this until its real Fase 1 view
// lands (Pedidos, Mapa, Clientes, Repartidores, Ventas, Configuracion).
export function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center">
      <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
      <p className="mt-2 text-sm text-slate-500">{strings.placeholder.comingInPhase1}</p>
    </div>
  )
}
