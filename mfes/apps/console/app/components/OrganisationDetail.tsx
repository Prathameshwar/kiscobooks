'use client';
import { useState } from 'react';
import { Badge, Button, Card, CardBody, CardHeader, ConfirmDialog, Notice, PageHeader, ReviewList, SearchSelect, TextField } from '@janso/ui';
import { useAccessCommand, useAccessRecord, useAccessSelection, type AccessContext, type UserRow } from '../lib/access-directory';
import { companyAccess } from '../lib/access-permissions';
import { organisationBase, organisationPermission, organisationReturn, useDepartmentOptions, type Department, type OrganisationRecord, type OrganisationResource } from '../lib/organisation-ui';
import { administrationReturn, administrationLink } from '../lib/administration-navigation';
import { AccessFailure, AccessFocusErrors, AccessNavigation, useAccessDraft } from './AccessCommon';
import { UserGroupMembers } from './UserGroupMembers';

export function OrganisationDetail({ resource, context, id, returnTo }: { resource: OrganisationResource; context: AccessContext; id: string; returnTo?: string }) {
  const base = organisationBase(resource, context), record = useAccessRecord<OrganisationRecord>(base + '/' + id, context.tenantId ?? ''), command = useAccessCommand();
  const [action, setAction] = useState<'lifecycle' | 'move' | null>(null), [reason, setReason] = useState(''), [parentId, setParentId] = useState<string | null>(null), [errors, setErrors] = useState<Record<string, string>>({}), [message, setMessage] = useState(''), [memberDirty, setMemberDirty] = useState(false);
  const row = record.data, manage = !!row && organisationPermission(context, resource, 'manage', row), department = row && 'path' in row ? row as Department : null;
  const [memberPending, setMemberPending] = useState(false);
  const back = administrationReturn(resource, returnTo), guard = useAccessDraft(!!action || memberDirty, command.pending || memberPending), singular = resource === 'departments' ? 'department' : 'user group';
  const parents = useDepartmentOptions(context, department?.path), selectedParent = useAccessSelection('departments', department?.parent_id ?? undefined, context.companyId), selectedMove = useAccessSelection('departments', parentId ?? undefined, context.companyId);
  const readHead = context.tenantPermissions.includes('user.read') || companyAccess(context, 'user.read');
  const head = useAccessRecord<UserRow>(readHead && department?.head_user_id ? (context.tenantPermissions.includes('user.read') ? '/v1/users/' : '/v1/companies/' + context.companyId + '/users/') + department.head_user_id : undefined);
  const canRoot = organisationPermission(context, 'departments', 'manage');
  function open(value: 'lifecycle' | 'move') { if (!manage || command.pending || command.uncertain) return; command.reset(); setAction(value); setReason(''); setParentId(department?.parent_id ?? null); setErrors({}); setMessage(''); }
  async function submit() {
    if (!row || !manage || !action || command.pending || command.uncertain) return;
    const invalid: Record<string, string> = {};
    if (action === 'lifecycle' && (!reason.trim() || reason.length > 500 || /[\x00-\x1f\x7f]/.test(reason))) invalid.reason = 'Enter a printable reason of 1–500 characters.';
    if (action === 'move' && (!parentId && !canRoot || parentId === row.id)) invalid.parent_id = 'Choose an authorized parent department.';
    setErrors(invalid); if (Object.keys(invalid).length) return;
    if (action === 'move' && parentId === department?.parent_id) { setMessage('The parent department is unchanged.'); setAction(null); return; }
    await command.execute<OrganisationRecord>({ path: base + '/' + id + (action === 'move' ? '/reparent' : '/lifecycle'), method: 'POST', body: action === 'move' ? { parent_id: parentId } : { is_active: !row.is_active, reason: reason.trim() } }, saved => {
      if (saved?.id !== id) throw { status: 502, message: 'Unexpected action response. Reload before continuing.' };
      record.setData(saved); setAction(null); setMessage(action === 'move' ? 'Parent department updated. Review department-scoped access for the moved subtree.' : saved.is_active ? 'Record reactivated.' : 'Record deactivated. Existing history is retained.');
    });
  }
  const fieldErrors = { ...errors, ...(command.failure?.fields ?? {}) }, refresh = () => { command.reset(); setAction(null); setErrors({}); record.refresh(); };
  const detail = administrationLink('/' + resource + '/' + id, back);
  return <div className="janso-page"><AccessNavigation context={context} resource={resource} mode="detail" id={id} title={row?.name} back={back} backLabel={resource === 'departments' ? 'departments' : 'user groups'} onLeave={guard.leave} /><PageHeader title={row?.name ?? (resource === 'departments' ? 'Department details' : 'User group details')} lede={resource === 'departments' ? 'Company organization and reviewed department hierarchy.' : 'Tenant collection, membership and separately scoped role assignments.'} actions={manage && row && (resource === 'user-groups' || row.is_active) ? <a className="janso-btn janso-btn--primary" href={'/' + resource + '/' + id + '/edit?returnTo=' + encodeURIComponent(detail)} onClick={guard.leave}>Edit details</a> : undefined} />
    <AccessFocusErrors fields={fieldErrors} /><AccessFailure failure={command.failure ?? record.failure} uncertain={command.uncertain} refresh={refresh} />{message && <Notice tone="success">{message}</Notice>}
    {record.loading ? <p role="status">Loading details…</p> : row && <>
      <Card><CardHeader title={singular === 'department' ? 'Department' : 'User group'} /><CardBody><ReviewList items={[{ label: 'Code', value: row.code }, { label: 'Name', value: row.name }, { label: 'Status', value: <Badge tone={row.is_active ? 'success' : 'neutral'}>{row.is_active ? 'Active' : 'Inactive'}</Badge> }, ...(department ? [{ label: 'Company', value: context.companyName ?? 'Selected company' }, { label: 'Parent department', value: department.parent_id ? selectedParent?.label ?? 'Saved parent department' : 'Root department' }, { label: 'Cost centre code', value: department.cost_centre_code ?? 'Not specified' }, { label: 'Head user', value: department.head_user_id ? head.data ? <a className="janso-link" href={administrationLink('/users/' + head.data.id, detail)} onClick={guard.leave}>{head.data.display_name}</a> : 'Assigned user (details unavailable)' : 'Not specified' }] : [{ label: 'Description', value: 'description' in row ? row.description ?? 'Not specified' : 'Not specified' }])]} /></CardBody></Card>
      <div className="janso-form-actions">{manage && <Button type="button" variant="ghost" disabled={command.pending || command.uncertain || memberDirty} onClick={() => open('lifecycle')}>{row.is_active ? 'Deactivate ' : 'Reactivate '}{singular}</Button>}
        {department && manage && row.is_active && <><Button type="button" variant="ghost" disabled={command.pending || command.uncertain} onClick={() => open('move')}>Change parent</Button><a className="janso-btn janso-btn--ghost" href={administrationLink('/departments/new?parent_id=' + id, detail)} onClick={guard.leave}>Add child department</a></>}
        {resource === 'user-groups' && context.permissions.includes('role.read') && <a className="janso-link" href={administrationLink('/assignments?subject_type=user_group&subject_id=' + id, detail)} onClick={guard.leave}>Group role assignments</a>}
        <Button type="button" variant="ghost" disabled={command.pending || !!action || memberDirty} onClick={refresh}>Reload record</Button>
      </div>{!row.is_active && <Notice>This record is inactive. Historical references remain available; reactivation is subject to current server access checks.</Notice>}
      {memberDirty && <Notice>Finish or clear the member selection before changing this group’s status.</Notice>}
      {resource === 'user-groups' && <UserGroupMembers key={id + ':' + row.is_active} groupId={id} active={row.is_active} context={context} onDraftChange={setMemberDirty} onPendingChange={setMemberPending} />}
    </>}
    <ConfirmDialog open={!!action} title={action === 'move' ? 'Change parent department?' : (row?.is_active ? 'Deactivate ' : 'Reactivate ') + singular + '?'} confirmLabel={action === 'move' ? 'Confirm parent change' : row?.is_active ? 'Deactivate' : 'Reactivate'} tone={action === 'lifecycle' && row?.is_active ? 'danger' : 'default'} busy={command.pending} error={command.uncertain ? 'The result is unconfirmed. Cancel and reload the record before making another change.' : command.failure?.message} onCancel={() => setAction(null)} onConfirm={() => void submit()}>
      {action === 'move' ? <><p>Moving this department also moves its descendants and changes which department-scoped grants apply. The server rejects cycles and unauthorized destinations.</p><SearchSelect label="New parent department" scopeKey={context.companyId} value={parentId} selected={selectedMove} loadOptions={parents} clearable={canRoot} disabled={command.pending || command.uncertain} error={fieldErrors.parent_id} onChange={value => { setParentId(value); setErrors({}); }} hint={canRoot ? 'Clear to make this a root department.' : 'A root move requires company-wide department management.'} /></>
        : <><p>{resource === 'departments' ? 'Active children must be deactivated first. Reactivation requires an active company and parent.' : 'Changing group status changes effective access for its members. You cannot change your own access through a group.'}</p><TextField label="Reason" value={reason} required maxLength={500} disabled={command.pending || command.uncertain} error={fieldErrors.reason} onChange={event => { setReason(event.target.value); setErrors({}); }} /></>}
    </ConfirmDialog>{guard.confirmation}
  </div>;
}
