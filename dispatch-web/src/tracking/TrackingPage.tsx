import { useParams } from 'react-router-dom'
import { strings } from '../i18n/strings'

// Public route, no auth — lives inside dispatch-web per SPEC.md SS4 ("misma app
// del panel, ruta publica"). Real live map + ETA is Fase 2; this Fase 0
// placeholder just proves the public, unauthenticated route works end to end.
export function TrackingPage() {
  const { trackingToken } = useParams<{ trackingToken: string }>()

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
      <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-8 text-center shadow-sm">
        <h1 className="text-lg font-semibold text-slate-900">{strings.tracking.title}</h1>
        <p className="mt-2 break-all text-xs text-slate-400">{trackingToken}</p>
        <p className="mt-4 text-sm text-slate-500">{strings.tracking.comingInPhase2}</p>
      </div>
    </div>
  )
}
