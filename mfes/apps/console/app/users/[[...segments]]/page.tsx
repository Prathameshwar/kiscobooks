import { notFound } from 'next/navigation';
import { Notice } from '@janso/ui';
import { Providers } from '../../providers';
import { ConsoleShell } from '../../components/ConsoleShell';
import { AccessDirectory } from '../../components/AccessDirectory';
import { UserDetail } from '../../components/UserDetail';
import { UserEditor } from '../../components/UserEditor';
import { CompanyUserInvite } from '../../components/CompanyUserInvite';
import { CompanyUserDetail } from '../../components/CompanyUserDetail';
import { AccessNavigation } from '../../components/AccessCommon';
import { accessContext } from '../../lib/access-context';
import { pageContext } from '../../lib/page-context';
import { companyAccess, hasPeopleAccess } from '../../lib/access-permissions';

export default async function UsersPage({ params, searchParams }: {
  params: Promise<{ segments?: string[] }>; searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { session, context } = await pageContext(), access = accessContext(session);
  const { segments = [] } = await params, search = await searchParams;
  const id = segments[0], creating = id === 'new', editing = segments[1] === 'edit';
  if (segments.length > 2 || id && !creating && !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id) || segments.length === 2 && !editing || creating && segments.length !== 1) notFound();
  const permission = creating ? 'user.invite' : editing ? 'user.update' : 'user.read';
  const tenantAllowed = access.tenantPermissions.includes(permission), companyAllowed = !editing && companyAccess(access, permission);
  const returnTo = typeof search.returnTo === 'string' ? search.returnTo : undefined;
  const query = new URLSearchParams(Object.entries(search).flatMap(([key, value]) => typeof value === 'string' ? [[key, value]] : [])).toString();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/users">
    {!tenantAllowed && !companyAllowed ? <div className="janso-page"><AccessNavigation context={access} /><Notice tone="warning">{editing ? 'Account-wide profile edits require a tenant administrator with user.update.' : hasPeopleAccess(access) && !access.companyId ? 'Select an authorized company to manage its users.' : 'You do not have permission to access this user directory in the selected company.'}</Notice>{!id && (access.tenantPermissions.includes('user.invite') || companyAccess(access, 'user.invite')) && <a className="janso-btn janso-btn--primary" href="/users/new">Invite user</a>}</div>
      : !tenantAllowed ? !id ? <AccessDirectory key={access.tenantId + ':' + access.companyId} resource="users" context={access} companyScoped initialQuery={query} /> : creating ? <CompanyUserInvite key={access.tenantId + ':' + access.companyId} context={access} returnTo={returnTo} /> : <CompanyUserDetail key={access.tenantId + ':' + access.companyId + ':' + id} context={access} id={id} returnTo={returnTo} />
      : !id ? <AccessDirectory key={access.tenantId} resource="users" context={access} initialQuery={query} />
        : creating || editing ? <UserEditor key={access.tenantId + ':' + id} context={access} id={creating ? undefined : id} returnTo={returnTo} />
          : <UserDetail key={access.tenantId + ':' + id} context={access} id={id} returnTo={returnTo} />}
  </ConsoleShell></Providers>;
}
