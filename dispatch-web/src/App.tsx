import { Navigate, Route, Routes } from 'react-router-dom'
import { AcceptInvitePage } from './auth/AcceptInvitePage'
import { AuthProvider } from './auth/AuthContext'
import { LoginPage } from './auth/LoginPage'
import { RequireAuth } from './auth/RequireAuth'
import { AppLayout } from './layout/AppLayout'
import { CatalogoPage } from './features/catalogo/CatalogoPage'
import { ClientesPage } from './features/clientes/ClientesPage'
import { CustomerDetailPage } from './features/clientes/CustomerDetailPage'
import { MapaPage } from './features/mapa/MapaPage'
import { PedidosPage } from './features/pedidos/PedidosPage'
import { PersonalPage } from './features/personal/PersonalPage'
import { PlaceholderPage } from './pages/PlaceholderPage'
import { TrackingPage } from './tracking/TrackingPage'
import { strings } from './i18n/strings'

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/track/:trackingToken" element={<TrackingPage />} />
        <Route path="/aceptar-invitacion/:token" element={<AcceptInvitePage />} />

        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route index element={<Navigate to="/pedidos" replace />} />
          <Route path="/pedidos" element={<PedidosPage />} />
          <Route path="/mapa" element={<MapaPage />} />
          <Route path="/clientes" element={<ClientesPage />} />
          <Route path="/clientes/:id" element={<CustomerDetailPage />} />
          <Route path="/repartidores" element={<PlaceholderPage title={strings.nav.repartidores} />} />
          <Route path="/ventas" element={<PlaceholderPage title={strings.nav.ventas} />} />
          <Route path="/configuracion" element={<Navigate to="/configuracion/catalogo" replace />} />
          <Route path="/configuracion/catalogo" element={<CatalogoPage />} />
          <Route path="/configuracion/personal" element={<PersonalPage />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}

export default App
