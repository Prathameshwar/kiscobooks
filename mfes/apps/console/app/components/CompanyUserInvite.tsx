'use client';
import { useState } from 'react';
import type { components } from '@janso/api-client/identity';
import { Button, Card, CardBody, EmailField, FormActions, FormLayout, Notice, PageHeader, TextField } from '@janso/ui';
import { companyAccess } from '../lib/access-permissions';
import { useAccessCommand, type AccessContext, type UserRow } from '../lib/access-directory';
import { validateUser } from '../lib/access-forms';
import { goTo } from '../lib/navigate';
import { administrationReturn, administrationLink } from '../lib/administration-navigation';
import { AccessFailure, AccessFocusErrors, AccessNavigation, useAccessDraft } from './AccessCommon';

export function CompanyUserInvite({ context, returnTo }: { context: AccessContext; returnTo?: string }) {
  const [draft, setDraft] = useState({ email: '', first_name: '', last_name: '', display_name: '' });
  const [errors, setErrors] = useState<Record<string, string>>({}), [saved, setSaved] = useState<UserRow | null>(null);
  const command = useAccessCommand(), back = administrationReturn('users', returnTo);
  const allowed = companyAccess(context, 'user.invite'), locked = command.pending || command.uncertain || !!saved;
  const guard = useAccessDraft(!saved && Object.values(draft).some(Boolean), command.pending);
  function change(key: keyof typeof draft, value: string) { setDraft(prior => ({ ...prior, [key]: value })); setErrors({}); }
  async function save() {
    if (!allowed || locked) return;
    const next = validateUser({ ...draft, user_type: 'tenant_user' }, true);
    setErrors(next); if (Object.keys(next).length) return;
    const body: components['schemas']['CompanyUserInvite'] = { email: draft.email.trim(), first_name: draft.first_name.trim(), last_name: draft.last_name.trim() || null, display_name: draft.display_name.trim() || null };
    await command.execute<UserRow>({ path: '/v1/companies/' + context.companyId + '/users', method: 'POST', body }, row => {
      if (!row?.id || row.user_type !== 'tenant_user' || row.status !== 'invited') throw { status: 502, message: 'The invitation response could not be confirmed.' };
      setSaved(row);
    });
  }
  const fields = { ...errors, ...(command.failure?.fields ?? {}) };
  return <div className="janso-page"><AccessNavigation context={context} resource="users" mode="new" back={back} backLabel="users" onLeave={guard.leave} /><PageHeader title="Invite company user" lede={'Invite a new person into ' + (context.companyName ?? 'the selected company') + '.'} />
    <AccessFocusErrors fields={fields} /><AccessFailure failure={command.failure} uncertain={command.uncertain} refresh={() => goTo(back)} />
    {saved && <Notice tone="success">User invited and affiliated with this company. Delivery uses the configured notification service. No role access was granted.{companyAccess(context, 'user.read') && <p><a className="janso-link" href={administrationLink('/users/' + saved.id, back)}>View company user</a></p>}</Notice>}
    {!allowed ? <Notice tone="danger">Select a company where you can invite users.</Notice> : <FormLayout aside={<><p>An invitation creates a tenant-user account and company affiliation together. Access must be granted separately by an authorized administrator.</p><p>For an existing account, ask a tenant administrator to manage its affiliation. Account-wide edits, suspension and invitation recovery also remain with tenant administration.</p><p>Passwords and MFA are managed by the sign-in provider.</p></>}><Card><form aria-label="Invite company user" noValidate onSubmit={event => { event.preventDefault(); void save(); }}><CardBody><div className="janso-flow">
      <EmailField label="Email" value={draft.email} onChange={value => change('email', value)} required disabled={locked} error={fields.email} />
      <TextField label="First name" value={draft.first_name} onChange={event => change('first_name', event.target.value)} required maxLength={100} disabled={locked} error={fields.first_name} />
      <TextField label="Last name" value={draft.last_name} onChange={event => change('last_name', event.target.value)} maxLength={100} disabled={locked} error={fields.last_name} />
      <TextField label="Display name" value={draft.display_name} onChange={event => change('display_name', event.target.value)} maxLength={200} disabled={locked} error={fields.display_name} hint="Leave empty to use the person's name." />
    </div></CardBody><FormActions cancel={{ href: back, onClick: guard.leave }}><Button type="submit" loading={command.pending} disabled={locked}>Invite user</Button></FormActions></form></Card></FormLayout>}{guard.confirmation}
  </div>;
}
