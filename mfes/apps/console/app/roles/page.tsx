import { Notice } from '@janso/ui';
import { Providers } from '../providers';
import { ConsoleShell } from '../components/ConsoleShell';
import { pageContext } from '../lib/page-context';
import { RolesAccess } from './RolesAccess';
import { accessReviewPermissions } from '../lib/access-permissions';
import { accessContext } from '../lib/access-context';

export default async function RolesPage({ searchParams }: { searchParams?: Promise<Record<string, string | string[] | undefined>> }) {
  const { session, context } = await pageContext();
  const accessPermissions = accessReviewPermissions(session);
  const search = await searchParams ?? {};
  const query = new URLSearchParams(Object.entries(search).flatMap(([key, value]) => typeof value === 'string' ? [[key, value]] : [])).toString();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/roles">
    {accessPermissions.includes('role.read')
      ? <RolesAccess key={session.organisation.id} context={accessContext(session)} initialQuery={query} />
      : <Notice tone="danger">Role read permission is required.</Notice>}
  </ConsoleShell></Providers>;
}
