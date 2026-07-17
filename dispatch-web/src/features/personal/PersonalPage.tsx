import { useEffect, useState } from 'react'
import { strings } from '../../i18n/strings'
import { activateStaff, deactivateStaff, listStaff, resetStaffPassword, type Staff } from '../../api/staff'
import { InviteLinkModal } from './InviteLinkModal'
import { StaffForm } from './StaffForm'

function statusLabel(staff: Staff): string {
  if (staff.invite_accepted_at === null) return strings.personal.estadoInvitado
  return staff.is_active ? strings.personal.estadoActivo : strings.personal.estadoDesactivado
}

function roleLabel(role: Staff['role']): string {
  return role === 'dispatcher' ? strings.personal.rolDespachador : strings.personal.rolRepartidor
}

export function PersonalPage() {
  const [staff, setStaff] = useState<Staff[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [inviteToken, setInviteToken] = useState<string | null>(null)

  async function reload() {
    setStaff(await listStaff())
  }

  useEffect(() => {
    setIsLoading(true)
    reload().finally(() => setIsLoading(false))
  }, [])

  function handleCreated(token: string) {
    setShowForm(false)
    setInviteToken(token)
    void reload()
  }

  async function handleToggleActive(member: Staff) {
    if (member.is_active) {
      await deactivateStaff(member.id)
    } else {
      await activateStaff(member.id)
    }
    await reload()
  }

  async function handleResetPassword(member: Staff) {
    const response = await resetStaffPassword(member.id)
    setInviteToken(response.invite_token)
  }

  if (isLoading) return null

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => setShowForm(true)}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          {strings.personal.nuevoPersonal}
        </button>
      </div>

      {showForm && <StaffForm onSaved={handleCreated} onCancel={() => setShowForm(false)} />}

      {staff.length === 0 && !showForm && (
        <p className="text-sm text-slate-500">{strings.personal.sinPersonal}</p>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2">{strings.personal.columnEmail}</th>
              <th className="px-4 py-2">{strings.personal.columnRol}</th>
              <th className="px-4 py-2">{strings.personal.columnTelefono}</th>
              <th className="px-4 py-2">{strings.personal.columnVehiculo}</th>
              <th className="px-4 py-2">{strings.personal.columnEstado}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {staff.map((member) => (
              <tr key={member.id} className="border-b border-slate-100 last:border-0">
                <td className="px-4 py-2">{member.email}</td>
                <td className="px-4 py-2">{roleLabel(member.role)}</td>
                <td className="px-4 py-2">{member.phone ?? '-'}</td>
                <td className="px-4 py-2">{member.vehicle_type ?? '-'}</td>
                <td className="px-4 py-2">{statusLabel(member)}</td>
                <td className="space-x-3 px-4 py-2 text-right">
                  <button
                    onClick={() => void handleToggleActive(member)}
                    className="text-xs font-medium text-slate-600 hover:text-slate-900"
                  >
                    {member.is_active ? strings.personal.desactivar : strings.personal.activar}
                  </button>
                  <button
                    onClick={() => void handleResetPassword(member)}
                    className="text-xs font-medium text-slate-600 hover:text-slate-900"
                  >
                    {strings.personal.resetearContrasena}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {inviteToken && <InviteLinkModal token={inviteToken} onClose={() => setInviteToken(null)} />}
    </div>
  )
}
