'use client';
import { useEffect, useState } from 'react';
import { Button, Card, CardBody, EmailField, FormActions, FormLayout, Notice, PageHeader, SearchSelect, SectionHeader, Select, TextField } from '@janso/ui';
import { useAccessCommand, useAccessLookup, useAccessRecord, useAccessSelection, type AccessContext, type UserRecord } from '../lib/access-directory';
import { goTo } from '../lib/navigate';
import { userDraft, userFields, userPayload, validateUser, type AccessDraft } from '../lib/access-forms';
import { administrationReturn, administrationLink } from '../lib/administration-navigation';
import { AccessFailure, AccessFocusErrors, AccessNavigation, useAccessDraft } from './AccessCommon';

export function UserEditor({ context, id, returnTo }: { context: AccessContext; id?: string; returnTo?: string }) {
  const record = useAccessRecord<UserRecord>(id ? '/v1/users/' + id : undefined, context.tenantId), command = useAccessCommand();
  const [draft, setDraft] = useState<AccessDraft>({ ...userDraft(), user_type: 'tenant_user' }), [errors, setErrors] = useState<Record<string, string>>({}), [saved, setSaved] = useState<UserRecord | null>(null), [message, setMessage] = useState('');
  const companies = useAccessLookup('companies'), managers = useAccessLookup('users', undefined, id, true), departments = useAccessLookup('departments', draft.default_company_id);
  const manager = useAccessRecord<UserRecord>(context.tenantPermissions.includes('user.read') && draft.reporting_manager_id ? '/v1/users/' + draft.reporting_manager_id : undefined);
  const selectedCompany = useAccessSelection('companies', draft.default_company_id), selectedDepartment = useAccessSelection('departments', draft.default_department_id, draft.default_company_id, context.permissions.includes('department.read'));
  useEffect(() => { if (record.data) setDraft({ ...userDraft(record.data), user_type: record.data.user_type }); }, [record.data]);
  const baseline = { ...userDraft(record.data), user_type: record.data?.user_type ?? 'tenant_user' };
  const dirty = !saved && JSON.stringify(draft) !== JSON.stringify(baseline), guard = useAccessDraft(dirty, command.pending);
  const back = administrationReturn('users', returnTo), failure = command.failure ?? record.failure;
  const allowed = context.tenantPermissions.includes(id ? 'user.update' : 'user.invite');
  const locked = command.pending || command.uncertain || !!saved || record.data?.status === 'deactivated';
  function change(key: string, value: string) { setDraft(prior => ({ ...prior, [key]: value, ...(key === 'default_company_id' ? { default_department_id: '' } : {}) })); setErrors(prior => { const next = { ...prior }; delete next[key]; return next; }); setMessage(''); }
  async function save() {
    if (locked || !allowed) return;
    const fields = validateUser(draft, !id); setErrors(fields); if (Object.keys(fields).length) return;
    const body = userPayload(draft, record.data);
    if (id && !Object.keys(body).length) { setMessage('No changes to save.'); return; }
    await command.execute<UserRecord>({ path: '/v1/users' + (id ? '/' + id : ''), method: id ? 'PATCH' : 'POST', body }, row => { if (!row?.id || id && row.id.toLowerCase() !== id.toLowerCase()) throw { status: 502, message: 'Unexpected saved user response.' }; setSaved(row); setMessage(id ? 'User profile updated.' : 'User invited. The invitation will be delivered through the configured notification service.'); });
  }
  const fieldErrors = { ...errors, ...(command.failure?.fields ?? {}) };
  return <div className="janso-page"><AccessNavigation context={context} resource="users" mode={id ? 'edit' : 'new'} id={id} title={record.data?.display_name} back={back} backLabel="users" onLeave={guard.leave} /><PageHeader title={id ? 'Edit user' : 'Invite user'} lede="Profiles belong to the tenant. Inviting a user does not grant roles or company access." />
    <AccessFocusErrors fields={fieldErrors} /><AccessFailure failure={failure} uncertain={command.uncertain} refresh={command.uncertain && !id ? () => goTo(back) : () => { command.reset(); setSaved(null); record.refresh(); }} />
    {message && <Notice tone="success">{message}{saved && context.tenantPermissions.includes('user.read') && <p><a className="janso-link" href={administrationLink('/users/' + saved.id, back)}>View user</a></p>}</Notice>}
    {!allowed ? <Notice tone="danger">Tenant-level {id ? 'user update' : 'user invite'} permission is required.</Notice> : record.loading ? <p role="status">Loading user…</p> : id && !record.data ? null : <FormLayout aside={<><SectionHeader title="Access is separate" /><p>Use the user’s assignments page to grant roles. A default company is a preference, not permission.</p><p>Passwords, MFA and account recovery are managed by the sign-in provider.</p></>}>
      <Card><form noValidate aria-label={id ? 'User profile editor' : 'Invite user'} onSubmit={event => { event.preventDefault(); void save(); }}><CardBody><div className="janso-flow"><SectionHeader title="Profile" />
        {!id && <EmailField label="Email" value={draft.email ?? ''} onChange={value => change('email', value)} required error={fieldErrors.email} disabled={locked} />}
        {!id && <Select label="User type" value={draft.user_type} options={[{ value: 'tenant_user', label: 'Tenant user' }, { value: 'customer_portal_user', label: 'Customer portal user' }]} onChange={value => change('user_type', value)} disabled={locked} />}
        {userFields.filter(key => !['default_company_id', 'default_department_id', 'reporting_manager_id', 'date_of_exit'].includes(key) || !!id && key === 'date_of_exit').map(key => <TextField key={key} label={key.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase())}
          value={draft[key] ?? ''} onChange={event => change(key, event.target.value)} error={fieldErrors[key]} disabled={locked} required={key === 'first_name' || !!id && key === 'display_name'} type={key.startsWith('date_') ? 'date' : 'text'}
          maxLength={key === 'display_name' ? 200 : key === 'job_title' ? 120 : key === 'phone' ? 20 : key === 'phone_country_code' ? 8 : key === 'employee_code' ? 40 : key === 'salutation' ? 20 : 100} hint={key === 'phone_country_code' ? 'Include + and the country dial code.' : undefined} />)}
        <SearchSelect label="Default company" scopeKey={context.tenantId} value={draft.default_company_id || null} selected={selectedCompany} loadOptions={companies} minQueryLength={0} disabled={locked} error={fieldErrors.default_company_id} onChange={value => change('default_company_id', value ?? '')} hint="A preference only. Changing it clears the saved default department." />
        {id && <SearchSelect label="Default department" scopeKey={draft.default_company_id || 'no-company'} value={draft.default_department_id || null} selected={selectedDepartment} loadOptions={departments} disabled={locked || !draft.default_company_id || !context.permissions.includes('department.read')} error={fieldErrors.default_department_id} onChange={value => change('default_department_id', value ?? '')} hint="Search by department code prefix. Department read permission is required." />}
        {context.tenantPermissions.includes('user.read') && <SearchSelect label="Reporting manager" scopeKey={context.tenantId} value={draft.reporting_manager_id || null} selected={manager.data ? { id: manager.data.id, label: manager.data.display_name } : undefined} loadOptions={managers} disabled={locked} error={fieldErrors.reporting_manager_id} onChange={value => change('reporting_manager_id', value ?? '')} />}
      </div></CardBody><FormActions cancel={{ href: back, onClick: guard.leave }}><Button type="submit" loading={command.pending} disabled={locked}>{id ? 'Save changes' : 'Invite user'}</Button></FormActions></form></Card>
    </FormLayout>}{guard.confirmation}
  </div>;
}
