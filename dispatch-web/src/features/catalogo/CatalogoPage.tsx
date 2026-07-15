import { useState } from 'react'
import { strings } from '../../i18n/strings'
import { ProductsSection } from './ProductsSection'
import { PaymentMethodsSection } from './PaymentMethodsSection'

type Tab = 'productos' | 'metodos-pago'

function tabClassName(isActive: boolean): string {
  return `border-b-2 px-1 pb-2 text-sm font-medium ${
    isActive ? 'border-slate-900 text-slate-900' : 'border-transparent text-slate-500 hover:text-slate-700'
  }`
}

export function CatalogoPage() {
  const [tab, setTab] = useState<Tab>('productos')

  return (
    <div className="space-y-4">
      <div className="flex gap-6 border-b border-slate-200">
        <button className={tabClassName(tab === 'productos')} onClick={() => setTab('productos')}>
          {strings.catalogo.tabProductos}
        </button>
        <button
          className={tabClassName(tab === 'metodos-pago')}
          onClick={() => setTab('metodos-pago')}
        >
          {strings.catalogo.tabMetodosPago}
        </button>
      </div>

      {tab === 'productos' ? <ProductsSection /> : <PaymentMethodsSection />}
    </div>
  )
}
