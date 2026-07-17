import { useState } from 'react'
import { strings } from '../../i18n/strings'
import { CustomersSection } from './CustomersSection'
import { DueForReorderSection } from './DueForReorderSection'

type Tab = 'clientes' | 'por-pedir'

function tabClassName(isActive: boolean): string {
  return `border-b-2 px-1 pb-2 text-sm font-medium ${
    isActive ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-500 hover:text-slate-700'
  }`
}

export function ClientesPage() {
  const [tab, setTab] = useState<Tab>('clientes')

  return (
    <div className="space-y-4">
      <div className="flex gap-6 border-b border-slate-200">
        <button className={tabClassName(tab === 'clientes')} onClick={() => setTab('clientes')}>
          {strings.clientes.tabClientes}
        </button>
        <button className={tabClassName(tab === 'por-pedir')} onClick={() => setTab('por-pedir')}>
          {strings.clientes.tabPorPedir}
        </button>
      </div>

      {tab === 'clientes' ? <CustomersSection /> : <DueForReorderSection />}
    </div>
  )
}
