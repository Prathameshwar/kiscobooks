'use client';
import { Card, CardBody, CardHeader, DataTable, Notice, PageHeader, ReviewList, type Column } from '@janso/ui';
import type { Session } from '../session';
import { accessContext } from '../lib/access-context';
import { AccessNavigation } from './AccessCommon';

export function MyAccess({ session }: { session: Session }) {
  const today = new Date().toISOString().slice(0, 10), context = accessContext(session);
  const grants = (session.grants ?? []).map((grant, index) => ({ ...grant, id: String(index),
    scope: grant.scope_type === 'tenant' ? 'Whole tenant' : grant.scope_type === 'company' && grant.scope_id?.toLowerCase() === session.company.id?.toLowerCase() ? session.company.name : grant.scope_type + ': ' + grant.scope_id,
    state: grant.valid_from > today ? 'Scheduled' : grant.valid_to && grant.valid_to < today ? 'Expired' : 'Active',
    permissionsText: grant.permissions.join(', '),
  }));
  const columns: Column<(typeof grants)[number]>[] = [{ key: 'scope', header: 'Scope', type: 'text' }, { key: 'state', header: 'Status', type: 'text' }, { key: 'valid_from', header: 'Starts', type: 'date' }, { key: 'valid_to', header: 'Expires', type: 'date' }, { key: 'permissionsText', header: 'Permissions', type: 'text' }];
  return <div className="janso-page"><AccessNavigation context={context} resource="my-access" /><PageHeader title="My access" lede="Review your own permissions and where they apply. This page does not grant administrative access." />
    <Card><CardBody><ReviewList items={[{ label: 'Signed in as', value: session.user.name }, { label: 'Account type', value: session.role }, { label: 'Organisation', value: session.organisation.name }, { label: 'Open company', value: session.company.id ? session.company.name : 'No company selected' }]} /><Notice tone="info">Account type determines the application surface. Assigned roles determine authority. Company membership and default preferences do not grant permissions. Contact your administrator to request a change.</Notice>{session.role === 'platform admin' && <p>Platform administration covers tenants and configuration. Support access to tenant business data requires the existing time-bound, audited support process.</p>}</CardBody></Card>
    <Card><CardHeader title="Effective permissions in the open company" /><CardBody>{session.permissions.length ? <ul>{[...new Set(session.permissions)].sort().map(key => <li key={key}><code>{key}</code></li>)}</ul> : <p>No effective permissions in the current context. Select an authorized company or ask your administrator.</p>}</CardBody></Card>
    <Card><CardHeader title="Your scoped grants" /><DataTable caption="Your scoped grants" columns={columns} rows={grants} rowId={row => row.id} emptyTitle="No grants available" emptyBody="Ask your administrator if you need access. A company affiliation alone provides no permissions." /></Card>
  </div>;
}
