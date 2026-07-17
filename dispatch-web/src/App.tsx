import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { LoginPage } from './auth/LoginPage'
import { RequireAuth } from './auth/RequireAuth'
import { AppLayout } from './layout/AppLayout'
import { CatalogoPage } from './features/catalogo/CatalogoPage'
import { ClientesPage } from './features/clientes/ClientesPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { TrackingPage } from './tracking/TrackingPage'
import { strings } from './i18n/strings'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/track/:trackingToken" element={<TrackingPage />} />

        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/pedidos" replace />} />
          <Route path="/pedidos" element={<PlaceholderPage title={strings.nav.pedidos} />} />
          <Route path="/mapa" element={<PlaceholderPage title={strings.nav.mapa} />} />
          <Route path="/clientes" element={<ClientesPage />} />
          <Route path="/repartidores" element={<PlaceholderPage title={strings.nav.repartidores} />} />
          <Route path="/ventas" element={<PlaceholderPage title={strings.nav.ventas} />} />
          <Route path="/configuracion" element={<Navigate to="/configuracion/catalogo" replace />} />
          <Route path="/configuracion/catalogo" element={<CatalogoPage />} />
          <Route
            path="/configuracion/personal"
            element={<PlaceholderPage title={strings.personal.tab} />}
          />
        </Route>
      </Routes>
    </AuthProvider>
  )
}

export default App
