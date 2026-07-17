import { useState, type FormEvent } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { strings } from '../i18n/strings'
import { acceptInvite } from '../api/staff'
import { useAuth } from './AuthContext'

// Public route, no auth -- the recipient has no credentials yet, only the
// link (SPEC.md §4.4). Reuses the same accept-invite mechanism for both a
// first-time invite and an admin-triggered password reset.
export function AcceptInvitePage() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const { loginWithTokens } = useAuth()
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [succeeded, setSucceeded] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    if (password !== confirmPassword) {
      setError(strings.aceptarInvitacion.contrasenasNoCoinciden)
      return
    }
    if (!token) return

    setIsSubmitting(true)
    try {
      const result = await acceptInvite(token, password)
      setSucceeded(true)
      await loginWithTokens(result.access_token, result.refresh_token)
      navigate('/')
    } catch {
      setError(strings.aceptarInvitacion.enlaceInvalido)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-slate-200 bg-white p-8 shadow-sm"
      >
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{strings.aceptarInvitacion.titulo}</h1>
          <p className="mt-1 text-sm text-slate-500">{strings.aceptarInvitacion.subtitulo}</p>
        </div>

        <div className="space-y-1">
          <label htmlFor="password" className="text-sm font-medium text-slate-700">
            {strings.aceptarInvitacion.nuevaContrasena}
          </label>
          <input
            id="password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="confirmPassword" className="text-sm font-medium text-slate-700">
            {strings.aceptarInvitacion.confirmarContrasena}
          </label>
          <input
            id="confirmPassword"
            type="password"
            required
            minLength={8}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          />
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        {succeeded && <p className="text-sm text-emerald-600">{strings.aceptarInvitacion.exito}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {isSubmitting ? strings.aceptarInvitacion.enviando : strings.aceptarInvitacion.enviar}
        </button>
      </form>
    </div>
  )
}
