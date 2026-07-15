import { Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import { LoginPage } from './auth/LoginPage'
import { RequireAuth } from './auth/RequireAuth'
import { AppLayout } from './layout/AppLayout'
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
          <Route path="/clientes" element={<PlaceholderPage title={strings.nav.clientes} />} />
          <Route path="/repartidores" element={<PlaceholderPage title={strings.nav.repartidores} />} />
          <Route path="/ventas" element={<PlaceholderPage title={strings.nav.ventas} />} />
          <Route path="/configuracion" element={<PlaceholderPage title={strings.nav.configuracion} />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}

export default App
