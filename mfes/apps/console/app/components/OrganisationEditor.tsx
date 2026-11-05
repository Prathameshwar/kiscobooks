'use client';
import { useEffect, useState } from 'react';
import { Button, Card, CardBody, FormActions, FormLayout, Notice, PageHeader, SearchSelect, SectionHeader, TextField } from '@janso/ui';
import { useAccessCommand, useAccessLookup, useAccessRecord, useAccessSelection, type AccessContext, type UserRow } from '../lib/access-directory';
import { organisationBase, organisationPayload, organisationPermission, organisationReturn, useDepartmentOptions, useOrganisationFields, type OrganisationRecord, type OrganisationResource } from '../lib/organisation-ui';
import { goTo } from '../lib/navigate';
import { companyAccess } from '../lib/access-permissions';
import { administrationReturn, administrationLink } from '../lib/administration-navigation';
import { AccessFailure, AccessFocusErrors, AccessNavigation, useAccessDraft } from './AccessCommon';

export function OrganisationEditor({ resource, context, id, parentId, returnTo }: { resource: OrganisationResource; context: AccessContext; id?: string; parentId?: string; returnTo?: string }) {
  const base = organisationBase(resource, context), record = useAccessRecord<OrganisationRecord>(id ? base + '/' + id : undefined, context.tenantId ?? ''), parent = useAccessRecord<OrganisationRecord>(!id && parentId ? base + '/' + parentId : undefined);
  const metadata = useOrganisationFields(base + '/field-set?operation=' + (id ? 'update&id=' + id : 'create' + (parentId ? '&id=' + parentId : '')), resource === 'departments' ? 'identity.department' : 'identity.user_group');
  const command = useAccessCommand(), [draft, setDraft] = useState<Record<string, string>>({ ...(parentId ? { parent_id: parentId } : {}) }), [errors, setErrors] = useState<Record<string, string>>({}), [saved, setSaved] = useState<OrganisationRecord | null>(null), [message, setMessage] = useState('');
  const baseline = record.data ? Object.fromEntries(Object.entries(record.data).map(([key, value]) => [key, value == null ? '' : String(value)])) : { ...(parentId ? { parent_id: parentId } : {}) };
  useEffect(() => { if (record.data) setDraft(Object.fromEntries(Object.entries(record.data).map(([key, value]) => [key, value == null ? '' : String(value)]))); }, [record.data]);
  const dirty = !saved && Object.entries(draft).some(([key, value]) => value !== (baseline[key] ?? '')), guard = useAccessDraft(dirty, command.pending);
  const back = administrationReturn(resource, returnTo), singular = resource === 'departments' ? 'department' : 'user group', entity = record.data ?? parent.data ?? undefined;
  const allowed = organisationPermission(context, resource, 'manage', entity), headAllowed = context.tenantPermissions.includes('user.read') || companyAccess(context, 'user.read');
  const fields = (metadata.data?.fields ?? []).map(field => field.key === 'head_user_id' && !headAllowed ? { ...field, writable: false } : field);
  const locked = command.pending || command.uncertain || !!saved, canWrite = fields.some(field => field.writable && field.is_visible);
  const parents = useDepartmentOptions(context), selectedParent = useAccessSelection('departments', draft.parent_id, context.companyId), heads = useAccessLookup('users', context.tenantPermissions.includes('user.read') ? undefined : context.companyId, undefined, true);
  const head = useAccessRecord<UserRow>(headAllowed && draft.head_user_id ? (context.tenantPermissions.includes('user.read') ? '/v1/users/' : '/v1/companies/' + context.companyId + '/users/') + draft.head_user_id : undefined);
  function change(key: string, value: string) { setDraft(previous => ({ ...previous, [key]: value })); setErrors(previous => { const next = { ...previous }; delete next[key]; return next; }); setMessage(''); }
  async function save() {
    if (!allowed || locked || !canWrite) return;
    const result = organisationPayload(fields, draft, record.data);
    if (resource === 'departments' && !id && !draft.parent_id && !organisationPermission(context, resource, 'manage')) result.errors.parent_id = 'Choose a parent department within your authorized scope.';
    setErrors(result.errors); if (Object.keys(result.errors).length) return;
    if (id && !Object.keys(result.body).length) { setMessage('No changes to save.'); return; }
    await command.execute<OrganisationRecord>({ path: base + (id ? '/' + id : ''), method: id ? 'PATCH' : 'POST', body: result.body }, row => {
      if (!row?.id || id && row.id !== id) throw { status: 502, message: 'Unexpected saved record. Review the directory.' };
      setSaved(row); setMessage(id ? 'Details updated.' : (resource === 'departments' ? 'Department' : 'User group') + ' created.');
    });
  }
  const fieldErrors = { ...errors, ...(command.failure?.fields ?? {}) }, failure = command.failure ?? record.failure ?? parent.failure ?? metadata.failure;
  return <div className="janso-page"><AccessNavigation context={context} resource={resource} mode={id ? 'edit' : 'new'} id={id} title={record.data?.name} back={back} backLabel={resource === 'departments' ? 'departments' : 'user groups'} onLeave={guard.leave} /><PageHeader title={(id ? 'Edit ' : 'New ') + singular} lede={resource === 'departments' ? 'Company-owned organization and cost-centre details. Parent changes are reviewed separately.' : 'A tenant collection of users. Creating a group does not grant roles or add members.'} />
    <AccessFocusErrors fields={fieldErrors} /><AccessFailure failure={failure} uncertain={command.uncertain} refresh={() => { if (command.failure) goTo(id ? '/' + resource + '/' + id : back); else { record.refresh(); parent.refresh(); metadata.refresh(); } }} />
    {message && <Notice tone="success">{message}{saved && organisationPermission(context, resource, 'read', saved) && <p><a className="janso-link" href={administrationLink('/' + resource + '/' + saved.id, back)}>View {singular}</a></p>}</Notice>}
    {record.loading || parent.loading || metadata.loading ? <p role="status">Loading form…</p> : !allowed ? <Notice tone="danger">You need management permission for this {singular}.</Notice> : failure && !metadata.data || id && !record.data ? null : <FormLayout aside={<><SectionHeader title="Before you save" /><p>{resource === 'departments' ? 'Codes must be unique within this company. A department affiliation is separate from role authorization.' : 'Group codes remain fixed. Membership and role assignments are separately reviewed security changes.'}</p><p>Existing records and audit history are retained when a record is deactivated.</p></>}>
      <Card><form noValidate aria-label={singular + ' editor'} onSubmit={event => { event.preventDefault(); void save(); }}><CardBody><div className="janso-flow">
        {id && resource === 'user-groups' && record.data && <p>Code: <strong>{record.data.code}</strong> (fixed)</p>}
        {fields.filter(field => field.is_visible).map(field => field.key === 'parent_id' ? <SearchSelect key={field.key} label="Parent department" scopeKey={context.companyId} value={draft.parent_id || null} selected={selectedParent} loadOptions={parents} disabled={locked || !field.writable} error={fieldErrors.parent_id} hint="Optional for a root department. Search by department code prefix." onChange={value => change('parent_id', value ?? '')} />
          : field.key === 'head_user_id' ? <SearchSelect key={field.key} label="Head user" scopeKey={context.tenantId + ':' + context.companyId} value={draft.head_user_id || null} selected={draft.head_user_id ? { id: draft.head_user_id, label: head.data?.display_name ?? 'Saved head user', disabled: !headAllowed } : null} loadOptions={heads} disabled={locked || !field.writable} error={fieldErrors.head_user_id} hint={headAllowed ? 'Choose an active user. Company administrators can search affiliated people.' : 'User read permission is required to change this selection.'} onChange={value => change('head_user_id', value ?? '')} />
          : <TextField key={field.key} label={field.label ?? field.key} value={draft[field.key] ?? ''} required={field.required} maxLength={typeof field.validation?.max_length === 'number' ? field.validation.max_length : undefined} disabled={locked || !field.writable} error={fieldErrors[field.key]} onChange={event => change(field.key, event.target.value)} />)}
        {!canWrite && <Notice>No editable fields are available. Reactivate an inactive department before editing it.</Notice>}
      </div></CardBody><FormActions cancel={{ href: back, onClick: guard.leave }}><Button type="submit" loading={command.pending} disabled={locked || !canWrite}>{id ? 'Save changes' : 'Create ' + singular}</Button></FormActions></form></Card>
    </FormLayout>}{guard.confirmation}
  </div>;
}
