'use client';
import { useEffect, useRef, useState } from 'react';
import { Button, Card, CardBody, ConfirmDialog, FormActions, FormLayout, Notice, PageHeader, ReviewList, SearchSelect, SectionHeader, Select, TextField } from '@janso/ui';
import { accessCall, useAccessCommand, useAccessLookup, useAccessRecord, type AccessContext, type Assignment, type RoleRecord, type UserRow } from '../lib/access-directory';
import { companyAccess } from '../lib/access-permissions';
import { requestFailure, type RequestFailure } from '../lib/service-call';
import { validateAssignment, type AccessDraft } from '../lib/access-forms';
import { goTo } from '../lib/navigate';
import { administrationReturn, administrationLink } from '../lib/administration-navigation';
import { AccessFailure, AccessFocusErrors, AccessNavigation, useAccessDraft } from './AccessCommon';

export function AssignmentEditor({ context, returnTo, initialSubject }: { context: AccessContext; returnTo?: string; initialSubject?: string }) {
  const tenantDirectory = context.tenantPermissions.includes('user.read');
  const [draft, setDraft] = useState<AccessDraft>({ role_id: '', subject_type: 'user', subject_id: initialSubject ?? '', scope_type: context.tenantPermissions.includes('role.assign') ? 'tenant' : 'company', scope_id: initialSubject && !context.tenantPermissions.includes('role.assign') ? context.companyId ?? '' : '', company_id: '', reason: '', valid_from: '', valid_to: '' });
  const [labels, setLabels] = useState<Record<string, string>>({}), [errors, setErrors] = useState<Record<string, string>>({}), [reviewing, setReviewing] = useState(false), [saved, setSaved] = useState<Assignment | null>(null);
  const [checking, setChecking] = useState(false), [checkFailure, setCheckFailure] = useState<RequestFailure | null>(null), check = useRef<AbortController | null>(null);
  useEffect(() => () => check.current?.abort(), []);
  const role = useAccessRecord<RoleRecord>(draft.role_id ? '/v1/roles/' + draft.role_id : undefined, context.tenantId), command = useAccessCommand();
  const subjectCompany = draft.scope_type === 'company' ? draft.scope_id : draft.scope_type === 'department' ? draft.company_id : '';
  const users = useAccessLookup('users', tenantDirectory ? undefined : subjectCompany, context.userId), groups = useAccessLookup('groups'), roles = useAccessLookup('roles'), companies = useAccessLookup('companies'), departments = useAccessLookup('departments', draft.company_id);
  const initialUser = useAccessRecord<UserRow>(initialSubject && draft.subject_id === initialSubject && (tenantDirectory || subjectCompany && companyAccess(context, 'user.read', subjectCompany)) ? tenantDirectory ? '/v1/users/' + initialSubject : '/v1/companies/' + subjectCompany + '/users/' + initialSubject : undefined, context.tenantId);
  const back = administrationReturn('assignments', returnTo), locked = command.pending || command.uncertain || !!saved || checking, canAssign = context.permissions.includes('role.assign');
  const canReadSubject = draft.subject_type === 'user' ? tenantDirectory || companyAccess(context, 'user.read', subjectCompany) : context.tenantPermissions.includes('group.read');
  const dirty = !saved && !!(draft.role_id || draft.subject_id || draft.scope_id || draft.reason || draft.valid_from || draft.valid_to), guard = useAccessDraft(dirty, command.pending || checking);
  const fields = { ...errors, ...(command.failure?.fields ?? {}) };
  function change(key: string, value: string, label?: string) {
    if (locked || reviewing) return;
    setDraft(prior => ({ ...prior, [key]: value, ...(key === 'subject_type' || !tenantDirectory && ['scope_type', 'scope_id', 'company_id'].includes(key) ? { subject_id: '' } : {}), ...(key === 'scope_type' || key === 'company_id' ? { scope_id: '' } : {}) }));
    setLabels(prior => ({ ...prior, [key]: label ?? value, ...(!tenantDirectory && ['scope_type', 'scope_id', 'company_id'].includes(key) ? { subject_id: '' } : {}) })); setErrors({}); setCheckFailure(null);
  }
  const body = () => ({ role_id: draft.role_id, subject_type: draft.subject_type, subject_id: draft.subject_id, scope_type: draft.scope_type, scope_id: draft.scope_type === 'tenant' ? null : draft.scope_id, grant_reason: draft.reason.trim(), valid_from: draft.valid_from || null, valid_to: draft.valid_to || null });
  async function review() {
    if (locked || reviewing || check.current || !canAssign || !canReadSubject) return;
    const next = validateAssignment(draft, context.userId);
    if (!role.data || !role.data.is_active) next.role_id = 'Select an active role and wait for its permissions to load.';
    if (draft.scope_type === 'department' && !draft.company_id) next.company_id = 'Select the company before its department.';
    setErrors(next); if (Object.keys(next).length) return;
    const controller = new AbortController(); check.current = controller; setChecking(true); setCheckFailure(null);
    try {
      const result = await accessCall<{ allowed: true }>({ path: '/v1/role-assignments/check', method: 'POST', body: body(), signal: controller.signal });
      if (!controller.signal.aborted) {
        if (result?.allowed !== true) throw { status: 502, message: 'The access check could not be confirmed. Retry checking before granting.' };
        setReviewing(true);
      }
    } catch (error) { if (!controller.signal.aborted) setCheckFailure(requestFailure(error)); }
    finally { if (!controller.signal.aborted) setChecking(false); if (check.current === controller) check.current = null; }
  }
  async function grant() {
    if (locked || !reviewing || !canAssign) return;
    await command.execute<Assignment>({ path: '/v1/role-assignments', method: 'POST', body: body() }, row => { if (!row?.id) throw { status: 502, message: 'Unexpected assignment response.' }; setSaved(row); setReviewing(false); });
  }
  const scopeLabel = labels.scope_id || (draft.scope_type === 'company' && draft.scope_id === context.companyId ? context.companyName : undefined);
  const summary = [{ label: 'Role', value: labels.role_id ?? role.data?.name ?? 'Not selected' }, { label: 'Subject', value: labels.subject_id || initialUser.data?.display_name || 'Not selected' }, { label: 'Scope', value: draft.scope_type === 'tenant' ? 'Whole tenant' : scopeLabel ?? 'Not selected' }, { label: 'Start', value: draft.valid_from || 'Today (UTC)' }, { label: 'Expiry', value: draft.valid_to || 'No expiry' }, { label: 'Reason', value: draft.reason }];
  return <div className="janso-page"><AccessNavigation context={context} resource="assignments" mode="new" back={back} backLabel="assignments" onLeave={guard.leave} /><PageHeader title="Assign role" lede="Grant a permission bundle to a person or group at a specific scope. Every access change is audited." /><AccessFocusErrors fields={fields} />
    {saved && <Notice tone="success">Role assigned. <a className="janso-link" href={administrationLink('/assignments?subject_type=' + draft.subject_type + '&subject_id=' + draft.subject_id, back)}>Review subject assignments</a></Notice>}
    {!reviewing && <AccessFailure failure={command.failure ?? checkFailure ?? role.failure ?? initialUser.failure} uncertain={command.uncertain} refresh={command.uncertain ? () => goTo(back) : role.refresh} />}
    {!canAssign ? <Notice tone="danger">Role assignment permission is required.</Notice> : <FormLayout aside={<><SectionHeader title="Before granting access" /><p>The server checks that you hold every permission in this role at the selected scope. You cannot change your own grants, including grants to groups you belong to.</p><p>Membership and default company preferences do not grant permissions.</p>{role.loading ? <p role="status">Loading role permissions…</p> : role.data && <><h3>{role.data.name}</h3><ul>{role.data.permissions.map(key => <li key={key}>{key}</li>)}</ul></>}</>}>
      <Card><form noValidate aria-label="Assign role" onSubmit={event => { event.preventDefault(); review(); }}><CardBody><div className="janso-flow">
        <SearchSelect label="Role" scopeKey={context.tenantId} value={draft.role_id || null} loadOptions={roles} minQueryLength={0} required disabled={locked || reviewing} error={fields.role_id} onChange={(value, option) => change('role_id', value ?? '', option?.label)} />
        <Select label="Scope" value={draft.scope_type} options={[...(context.tenantPermissions.includes('role.assign') ? [{ value: 'tenant', label: 'Whole tenant' }] : []), { value: 'company', label: 'Company' }, { value: 'department', label: 'Department' }]} onChange={value => change('scope_type', value)} disabled={locked || reviewing} />
        {draft.scope_type === 'company' && <SearchSelect label="Company" scopeKey={context.tenantId} value={draft.scope_id || null} selected={draft.scope_id === context.companyId && context.companyName ? { id: context.companyId, label: context.companyName } : undefined} loadOptions={companies} minQueryLength={0} required disabled={locked || reviewing} error={fields.scope_id} onChange={(value, option) => change('scope_id', value ?? '', option?.label)} />}
        {draft.scope_type === 'department' && <><SearchSelect label="Department company" scopeKey={context.tenantId} value={draft.company_id || null} loadOptions={companies} minQueryLength={0} required disabled={locked || reviewing} error={fields.company_id} onChange={(value, option) => change('company_id', value ?? '', option?.label)} /><SearchSelect label="Department" scopeKey={draft.company_id || 'no-company'} value={draft.scope_id || null} loadOptions={departments} required disabled={locked || reviewing || !draft.company_id} error={fields.scope_id} hint="Search by department code prefix. Only departments you can read are returned." onChange={(value, option) => change('scope_id', value ?? '', option?.label)} /></>}
        <Select label="Subject type" value={draft.subject_type} options={[{ value: 'user', label: 'User' }, ...(context.tenantPermissions.includes('group.read') ? [{ value: 'user_group', label: 'User group' }] : [])]} onChange={value => change('subject_type', value)} disabled={locked || reviewing} />
        {!canReadSubject && <Notice tone="warning">{draft.subject_type === 'user' ? 'Choose a company where you have user.read to search its affiliated people, or ask a tenant administrator.' : 'Tenant-level group.read is required for tenant group assignments.'}</Notice>}
        <SearchSelect label={draft.subject_type === 'user' ? 'User' : 'User group'} scopeKey={context.tenantId + ':' + draft.subject_type + ':' + (tenantDirectory ? 'tenant' : subjectCompany)} value={draft.subject_id || null} selected={initialUser.data ? { id: initialUser.data.id, label: initialUser.data.display_name } : undefined} loadOptions={draft.subject_type === 'user' ? users : groups} disabled={locked || reviewing || !canReadSubject} required error={fields.subject_id} hint={draft.subject_type === 'user' ? tenantDirectory ? 'Search by name or email.' : 'Search current affiliated company users by name or email. Company selection comes first.' : 'Search by group code prefix.'} onChange={(value, option) => change('subject_id', value ?? '', option?.label)} />
        <TextField label="Access reason" value={draft.reason} onChange={event => change('reason', event.target.value)} required maxLength={500} error={fields.reason ?? fields.grant_reason} disabled={locked || reviewing} />
        <TextField label="Start date" type="date" value={draft.valid_from} onChange={event => change('valid_from', event.target.value)} error={fields.valid_from} disabled={locked || reviewing} hint="Leave empty for today (UTC)." /><TextField label="Expiry date" type="date" value={draft.valid_to} onChange={event => change('valid_to', event.target.value)} error={fields.valid_to} disabled={locked || reviewing} hint="Access includes this date. Leave empty for no expiry." />
      </div></CardBody><FormActions cancel={{ href: back, onClick: guard.leave }}><Button type="submit" loading={checking} disabled={locked || reviewing || !canReadSubject || role.loading}>Review assignment</Button></FormActions></form></Card>
    </FormLayout>}
    <ConfirmDialog open={reviewing} title="Grant role access?" confirmLabel="Grant access" busy={command.pending} onCancel={() => { if (!command.pending) setReviewing(false); }} onConfirm={() => void grant()}><ReviewList items={summary} /><AccessFailure failure={command.failure} uncertain={command.uncertain} refresh={() => goTo(back)} /></ConfirmDialog>{guard.confirmation}
  </div>;
}
