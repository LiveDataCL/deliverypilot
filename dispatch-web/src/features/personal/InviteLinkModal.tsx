import { useState } from 'react'
import { strings } from '../../i18n/strings'
import { buildInviteLink } from '../../api/staff'

interface InviteLinkModalProps {
  token: string
  onClose: () => void
}

export function InviteLinkModal({ token, onClose }: InviteLinkModalProps) {
  const [copied, setCopied] = useState(false)
  const link = buildInviteLink(token)

  async function handleCopy() {
    await navigator.clipboard.writeText(link)
    setCopied(true)
  }

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-black/30">
      <div className="w-96 rounded-lg bg-white p-4 shadow-lg">
        <h3 className="mb-1 text-sm font-medium text-slate-700">{strings.personal.linkInvitacion}</h3>
        <p className="mb-3 text-xs text-slate-500">{strings.personal.linkInvitacionAyuda}</p>
        <div className="break-all rounded-md border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">
          {link}
        </div>
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => void handleCopy()}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
          >
            {copied ? strings.personal.linkCopiado : strings.personal.copiarLink}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
          >
            {strings.personal.cerrar}
          </button>
        </div>
      </div>
    </div>
  )
}
