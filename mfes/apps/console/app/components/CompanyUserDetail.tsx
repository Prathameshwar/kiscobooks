'use client';
import { useState } from 'react';
import { Card, CardBody, Notice, PageHeader, ReviewList } from '@janso/ui';
import { companyAccess } from '../lib/access-permissions';
import { useAccessRecord, type AccessContext, type UserRow } from '../lib/access-directory';
import { administrationReturn, administrationLink } from '../lib/administration-navigation';
import { AccessFailure, AccessNavigation, useAccessDraft } from './AccessCommon';
import { UserAffiliations } from './UserAffiliations';

export function CompanyUserDetail({ context, id, returnTo }: { context: AccessContext; id: string; returnTo?: string }) {
  const record = useAccessRecord<UserRow>('/v1/companies/' + context.companyId + '/users/' + id, context.tenantId), row = record.data;
  const [affiliationDirty, setAffiliationDirty] = useState(false), [affiliationPending, setAffiliationPending] = useState(false), guard = useAccessDraft(affiliationDirty, affiliationPending);
  const canAssign = companyAccess(context, 'role.assign') && context.permissions.includes('role.read') && id.toLowerCase() !== context.userId?.toLowerCase() && ['active', 'invited'].includes(row?.status ?? '');
  const back = administrationReturn('users', returnTo), detail = administrationLink('/users/' + id, back);
  return <div className="janso-page"><AccessNavigation context={context} resource="users" mode="detail" id={id} title={row?.display_name} back={administrationReturn('users', returnTo)} backLabel="users" onLeave={guard.leave} /><PageHeader title={row?.display_name ?? 'Company user'} lede={'Current affiliation in ' + (context.companyName ?? 'the selected company') + '.'} actions={canAssign ? <a className="janso-btn janso-btn--primary" href={administrationLink('/assignments/new?subject_id=' + id, detail)} onClick={guard.leave}>Assign role</a> : undefined} />
    <AccessFailure failure={record.failure} refresh={record.refresh} />
    {record.loading ? <p role="status">Loading company user…</p> : row && <Card><CardBody><ReviewList items={[{ label: 'Name', value: row.display_name }, { label: 'Email', value: row.email }, { label: 'Status', value: row.status }, { label: 'Job title', value: row.job_title ?? 'Not set' }]} /><Notice tone="info">This affiliation does not grant system access. A tenant administrator manages account-wide profile changes, suspension and invitation recovery.</Notice>{context.permissions.includes('role.read') && <a className="janso-link" href={administrationLink('/assignments?subject_type=user&subject_id=' + id, detail)} onClick={guard.leave}>View authorized assignments</a>}</CardBody></Card>}
    {row && companyAccess(context, 'department.read') && <UserAffiliations key={context.companyId + ':' + id} userId={id} userStatus={row.status} context={context} onDraftChange={setAffiliationDirty} onPendingChange={setAffiliationPending} />}{guard.confirmation}
  </div>;
}
