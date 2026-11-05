import { notFound } from 'next/navigation';
import { Notice } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { RoleDetail } from '../../components/RoleDetail';
import { RoleEditor } from '../../components/RoleEditor';
import { accessContext } from '../../lib/access-context';
import { pageContext } from '../../lib/page-context';

export default async function RolePage({ params, searchParams }: {
  params: Promise<{ segments: string[] }>; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { session, context } = await pageContext(), access = accessContext(session);
  const { segments } = await params, search = await searchParams, [id, action] = segments;
  const creating = id === 'new', editing = action === 'edit', clone = action === 'clone';
  if (!id || segments.length > 2 || creating && segments.length !== 1 || !creating && !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id) || action && !editing && !clone) notFound();
  const canRead = access.permissions.includes('role.read'), canManage = access.tenantPermissions.includes('role.manage');
  const returnTo = typeof search.returnTo === 'string' ? search.returnTo : undefined;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/roles">
    {!canRead || (creating || editing || clone) && !canManage ? <Notice tone="danger">Role read and tenant-level management permissions are required for this action.</Notice>
      : creating || editing || clone ? <RoleEditor key={access.tenantId + ':' + id + ':' + action} context={access} id={creating ? undefined : id} clone={clone} returnTo={returnTo} /> : <RoleDetail key={access.tenantId + ':' + id} context={access} id={id} returnTo={returnTo} />}
  </ConsoleShell></Providers>;
}
