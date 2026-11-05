'use client';
import { useEffect, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, Notice, PageHeader, ReviewList, TextField, useFormatters } from '@janso/ui';
import { useAccessCommand, useAccessRecord, type AccessContext, type RoleRecord } from '../lib/access-directory';
import { administrationReturn, administrationLink } from '../lib/administration-navigation';
import { AccessFailure, AccessNavigation, useAccessDraft } from './AccessCommon';
import { PermissionDirectory } from './PermissionDirectory';

export function RoleDetail({ context, id, returnTo }: { context: AccessContext; id: string; returnTo?: string }) {
  const record = useAccessRecord<RoleRecord>('/v1/roles/' + id, context.tenantId), command = useAccessCommand(), format = useFormatters();
  const [open, setOpen] = useState(false), [reason, setReason] = useState(''), [error, setError] = useState(''), [message, setMessage] = useState('');
  const row = record.data, back = administrationReturn('roles', returnTo), canManage = context.tenantPermissions.includes('role.manage'), locked = command.pending || command.uncertain;
  const guard = useAccessDraft(open, command.pending);
  useEffect(() => {
    if (row && window.location.hash === '#role-permissions') {
      const section = document.getElementById('role-permissions');
      section?.scrollIntoView?.({ block: 'start' });
      section?.focus({ preventScroll: true });
    }
  }, [row]);
  async function toggle() {
    if (!row || locked || !canManage || row.is_system) return;
    if (!reason.trim() || reason.length > 500) { setError('Enter a reason of no more than 500 characters.'); return; }
    await command.execute({ path: '/v1/roles/' + id + '/lifecycle', method: 'POST', body: { is_active: !row.is_active, reason: reason.trim() } }, () => { setOpen(false); setMessage(row.is_active ? 'Role deactivated.' : 'Role reactivated.'); record.refresh(); });
  }
  const detail = administrationLink('/roles/' + id, back);
  return <div className="janso-page"><AccessNavigation context={context} resource="roles" mode="detail" id={id} title={row?.name} back={back} backLabel="roles" onLeave={guard.leave} /><PageHeader title={row?.name ?? 'Role details'} lede="Review this role before assigning it. Assignment scope and validity determine where and when its permissions apply." actions={row && canManage ? <div className="janso-form-actions">{!row.is_system && <a className="janso-btn janso-btn--primary" href={`/roles/${id}/edit?returnTo=${encodeURIComponent(detail)}`} onClick={guard.leave}>Edit role</a>}<a className="janso-btn" href={`/roles/${id}/clone?returnTo=${encodeURIComponent(detail)}`} onClick={guard.leave}>Clone role</a></div> : undefined} />
    <AccessFailure failure={record.failure} refresh={record.refresh} />{message && <Notice tone="success">{message}</Notice>}
    {record.loading ? <p role="status">Loading role…</p> : row && <><Card><CardBody>{row.is_system && <Notice tone="info">System roles are read-only. Clone this role to create a custom permission bundle.</Notice>}<ReviewList items={[{ label: 'Key', value: row.key }, { label: 'Description', value: row.description ?? 'Not set' }, { label: 'Status', value: row.is_active ? 'Active' : 'Inactive' }, { label: 'Scope hint', value: row.scope_hint ?? 'Not set' }, { label: 'Updated', value: format.dateTime(row.updated_at) }]} /><div className="janso-form-actions"><a className="janso-link" href={administrationLink('/assignments?role_id=' + id, detail)} onClick={guard.leave}>View assignments</a>{canManage && !row.is_system && <Button type="button" variant={row.is_active ? 'danger' : 'ghost'} disabled={locked} onClick={() => { setOpen(true); setReason(''); setError(''); command.reset(); }}>{row.is_active ? 'Deactivate role' : 'Reactivate role'}</Button>}</div></CardBody></Card><section id="role-permissions" aria-label="Role permission details" tabIndex={-1}><PermissionDirectory context={context} keys={row.permissions} embedded /></section></>}
    <ConfirmDialog open={open} title={row?.is_active ? 'Deactivate role?' : 'Reactivate role?'} confirmLabel="Confirm change" tone={row?.is_active ? 'danger' : 'default'} busy={command.pending} onCancel={() => { if (!command.pending) setOpen(false); }} onConfirm={() => void toggle()}><p>The server checks affected assignments and your authority. Existing grants can affect access again when a role is reactivated.</p><TextField label="Action reason" value={reason} onChange={event => { setReason(event.target.value); setError(''); }} required maxLength={500} error={error} disabled={locked} /><AccessFailure failure={command.failure} uncertain={command.uncertain} refresh={() => { command.reset(); setOpen(false); record.refresh(); }} /></ConfirmDialog>{guard.confirmation}
    {!open && <AccessFailure failure={command.failure} uncertain={command.uncertain} refresh={() => { command.reset(); record.refresh(); }} />}
  </div>;
}
