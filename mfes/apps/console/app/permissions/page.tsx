import { Notice } from '@janso/ui';
import { Providers } from '../providers';
import { ConsoleShell } from '../components/ConsoleShell';
import { PermissionDirectory } from '../components/PermissionDirectory';
import { accessContext } from '../lib/access-context';
import { pageContext } from '../lib/page-context';

export default async function PermissionsPage({ searchParams }: { searchParams?: Promise<Record<string, string | string[] | undefined>> }) {
  const { session, context } = await pageContext(), access = accessContext(session);
  const query = await searchParams ?? {}, returnTo = typeof query.returnTo === 'string' ? query.returnTo : undefined;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/permissions">
    {access.permissions.includes('role.read') ? <PermissionDirectory context={access} returnTo={returnTo} /> : <Notice tone="danger">Role read permission is required.</Notice>}
  </ConsoleShell></Providers>;
}
