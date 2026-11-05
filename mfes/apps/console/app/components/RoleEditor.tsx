'use client';
import { useEffect, useState } from 'react';
import { Button, Card, CardBody, FormActions, FormLayout, Notice, PageHeader, SearchSelect, SectionHeader, Select, TextField } from '@janso/ui';
import { useAccessCommand, useAccessRecord, usePermissionCatalogue, type AccessContext, type RoleRecord } from '../lib/access-directory';
import { rolePayload, validateRole, type AccessDraft } from '../lib/access-forms';
import { goTo } from '../lib/navigate';
import { administrationReturn, administrationLink } from '../lib/administration-navigation';
import { AccessFailure, AccessFocusErrors, AccessNavigation, useAccessDraft } from './AccessCommon';

const empty = { key: '', name: '', description: '', scope_hint: '' };
export function RoleEditor({ context, id, clone = false, returnTo }: { context: AccessContext; id?: string; clone?: boolean; returnTo?: string }) {
  const record = useAccessRecord<RoleRecord>(id ? '/v1/roles/' + id : undefined, context.tenantId), catalogue = usePermissionCatalogue(), command = useAccessCommand();
  const [draft, setDraft] = useState<AccessDraft>(empty), [permissions, setPermissions] = useState<string[]>([]), [errors, setErrors] = useState<Record<string, string>>({}), [saved, setSaved] = useState<RoleRecord | null>(null), [warnings, setWarnings] = useState<string[][]>([]), [message, setMessage] = useState('');
  const source = record.data;
  useEffect(() => { if (source) { setDraft({ key: clone ? '' : source.key, name: source.name + (clone ? ' copy' : ''), description: source.description ?? '', scope_hint: source.scope_hint ?? '' }); setPermissions(source.permissions); } }, [source, clone]);
  const baseline = source ? { key: clone ? '' : source.key, name: source.name + (clone ? ' copy' : ''), description: source.description ?? '', scope_hint: source.scope_hint ?? '' } : empty;
  const dirty = !saved && (JSON.stringify(draft) !== JSON.stringify(baseline) || [...permissions].sort().join() !== [...(source?.permissions ?? [])].sort().join()), guard = useAccessDraft(dirty, command.pending);
  const allowed = context.tenantPermissions.includes('role.manage') && (!source?.is_system || clone);
  const canCompose = !source || source.permissions.every(key => context.tenantPermissions.includes(key));
  const locked = command.pending || command.uncertain || !!saved, back = administrationReturn('roles', returnTo);
  const fields = { ...errors, ...(command.failure?.fields ?? {}) };
  function change(key: string, value: string) { setDraft(prior => ({ ...prior, [key]: value })); setErrors(prior => { const next = { ...prior }; delete next[key]; return next; }); }
  async function save() {
    if (locked || !allowed || catalogue.loading || catalogue.failure || clone && !canCompose) return;
    const next = validateRole(draft, permissions, catalogue.permissions, !id || clone); setErrors(next); if (Object.keys(next).length) return;
    const body = clone ? { key: draft.key, name: draft.name.trim() } : rolePayload(draft, permissions, source);
    if (!Object.keys(body).length) { setMessage('No changes to save.'); return; }
    await command.execute<RoleRecord | { role: RoleRecord; separation_of_duties_warnings: string[][] }>({ path: '/v1/roles' + (id ? '/' + id + (clone ? '/clone' : '') : ''), method: id && !clone ? 'PATCH' : 'POST', body }, result => {
      const row = 'role' in result ? result.role : result;
      if (!row?.id || id && !clone && row.id.toLowerCase() !== id.toLowerCase()) throw { status: 502, message: 'Unexpected saved role response.' };
      setSaved(row); setWarnings('role' in result ? result.separation_of_duties_warnings : []); setMessage(clone ? 'Role cloned. Review and edit the new role before assigning it.' : 'Role saved.');
    });
  }
  return <div className="janso-page"><AccessNavigation context={context} resource="roles" mode={clone ? 'clone' : id ? 'edit' : 'new'} id={id} title={record.data?.name} back={back} backLabel="roles" onLeave={guard.leave} /><PageHeader title={clone ? 'Clone role' : id ? 'Edit role' : 'New role'} lede="Permissions are defined by the application. A role combines existing keys; creating a role does not grant it to anyone." />
    <AccessFocusErrors fields={fields} /><AccessFailure failure={record.failure ?? catalogue.failure ?? command.failure} uncertain={command.uncertain} refresh={command.uncertain && (!id || clone) ? () => goTo(back) : () => { command.reset(); record.refresh(); catalogue.refresh(); }} />
    {message && <Notice tone="success">{message}{saved && <p><a className="janso-link" href={administrationLink('/roles/' + saved.id, back)}>View saved role</a></p>}</Notice>}
    {!!warnings.length && <Notice tone="warning"><p>Separation of duties conflicts require review:</p><ul>{warnings.map(pair => <li key={pair.join()}>{pair.join(' + ')}</li>)}</ul></Notice>}
    {!allowed ? <Notice tone="danger">Tenant-level role management is required. System roles are read-only.</Notice> : record.loading || catalogue.loading ? <p role="status">Loading role and permissions…</p> : id && !source || catalogue.failure ? null : <FormLayout aside={<><SectionHeader title="Delegation rules" /><p>You can add only permissions you hold at tenant scope. Changing an assigned role also checks every affected assignment and prevents changes to your own access.</p><p>Financial authority must be provisioned through the approved administration policy before it can be delegated.</p></>}>
      <Card><form noValidate aria-label="Role editor" onSubmit={event => { event.preventDefault(); void save(); }}><CardBody><div className="janso-flow">
        {(!id || clone) && <TextField label="Role key" value={draft.key} onChange={event => change('key', event.target.value)} maxLength={60} required error={fields.key} disabled={locked} hint="An immutable identifier, such as branch_viewer." />}
        <TextField label="Role name" value={draft.name} onChange={event => change('name', event.target.value)} maxLength={150} required error={fields.name} disabled={locked} />
        {!clone && <><TextField label="Description" value={draft.description} onChange={event => change('description', event.target.value)} maxLength={500} error={fields.description} disabled={locked} />
          <Select label="Scope hint" value={draft.scope_hint} placeholder="No preferred scope" options={['tenant', 'company', 'department'].map(value => ({ value, label: value }))} onChange={value => change('scope_hint', value)} disabled={locked} hint="Guidance only. The assignment determines the actual scope." /></>}
        {!canCompose && <Notice tone="warning">This role contains permissions you do not hold at tenant scope. {clone ? 'It cannot be cloned with your current authority.' : 'You can edit its metadata; its permission set is locked.'}</Notice>}
        <SearchSelect label="Permissions" multiple value={permissions} options={catalogue.permissions.map(key => ({ id: key, label: key, meta: key.split('.')[0], disabled: !context.tenantPermissions.includes(key) && !permissions.includes(key) }))} maxOptions={catalogue.permissions.length || 200} maxChips={8} error={fields.permissions} required disabled={locked || clone || !canCompose} onChange={values => { setPermissions(values); setErrors(prior => { const next = { ...prior }; delete next.permissions; return next; }); }} hint="Search permission keys and select the required operations." />
      </div></CardBody><FormActions cancel={{ href: back, onClick: guard.leave }}><Button type="submit" loading={command.pending} disabled={locked || clone && !canCompose}>{clone ? 'Clone role' : 'Save role'}</Button></FormActions></form></Card>
    </FormLayout>}{guard.confirmation}
  </div>;
}
