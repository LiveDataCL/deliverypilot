import type { ReactNode } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { strings } from '../i18n/strings'
import { useAuth } from '../auth/AuthContext'

const NAV_ITEMS = [
  { to: '/pedidos', label: strings.nav.pedidos },
  { to: '/mapa', label: strings.nav.mapa },
  { to: '/clientes', label: strings.nav.clientes },
  { to: '/repartidores', label: strings.nav.repartidores },
  { to: '/ventas', label: strings.nav.ventas },
  { to: '/configuracion', label: strings.nav.configuracion },
]

function linkClassName({ isActive }: { isActive: boolean }): string {
  return `block rounded-md px-3 py-2 text-sm font-medium ${
    isActive ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'
  }`
}

export function AppLayout({ children }: { children?: ReactNode }) {
  const { user, logout } = useAuth()

  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 flex-col border-r border-slate-200 bg-white p-4">
        <div className="mb-6 text-lg font-semibold text-slate-900">{strings.app.name}</div>
        <nav className="flex-1 space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} className={linkClassName}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 pt-4 text-sm text-slate-600">
          <div className="truncate">{user?.email}</div>
          <button onClick={logout} className="mt-2 text-slate-500 hover:text-slate-900">
            {strings.auth.logout}
          </button>
        </div>
      </aside>
      <main className="flex-1 bg-slate-50 p-6">{children ?? <Outlet />}</main>
    </div>
  )
}
