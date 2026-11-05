import { notFound } from 'next/navigation';
import { Notice } from '@janso/ui';
import { Providers } from '../providers';
import { ConsoleShell } from './ConsoleShell';
import { OrganisationDirectory } from './OrganisationDirectory';
import { OrganisationEditor } from './OrganisationEditor';
import { OrganisationDetail } from './OrganisationDetail';
import { AccessNavigation } from './AccessCommon';
import { accessContext } from '../lib/access-context';
import { pageContext } from '../lib/page-context';
import { departmentDirectoryAccess, organisationPermission, validOrganisationId, type OrganisationResource } from '../lib/organisation-contract';

export async function OrganisationMasterPage({ resource, params, searchParams }: { resource: OrganisationResource; params: Promise<{ segments?: string[] }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { session, context } = await pageContext(), access = accessContext(session), { segments = [] } = await params, search = await searchParams;
  const id = segments[0]?.toLowerCase(), creating = id === 'new', editing = segments[1] === 'edit';
  const parentId = resource === 'departments' && typeof search.parent_id === 'string' ? search.parent_id.toLowerCase() : undefined;
  if (segments.length > 2 || id && !creating && !validOrganisationId(id) || segments.length === 2 && !editing || creating && segments.length !== 1 || parentId && !validOrganisationId(parentId)) notFound();
  const canRead = resource === 'departments' ? departmentDirectoryAccess(access) : organisationPermission(access, resource, 'read');
  const canCreate = organisationPermission(access, resource, 'manage') || resource === 'departments' && !!parentId && canRead && departmentDirectoryAccess(access, 'manage');
  const returnTo = typeof search.returnTo === 'string' ? search.returnTo : undefined;
  const query = new URLSearchParams(Object.entries(search).flatMap(([key, value]) => typeof value === 'string' ? [[key, value]] : [])).toString();
  const key = access.tenantId + ':' + (resource === 'departments' ? access.companyId : '') + ':' + id;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={'/' + resource}>
    {resource === 'departments' && !access.companyId ? <div className="janso-page"><AccessNavigation context={access} resource={resource} /><Notice>Select an authorized company to manage its departments.</Notice></div>
      : creating && !canCreate || !creating && !canRead ? <div className="janso-page"><AccessNavigation context={access} resource={resource} /><Notice tone="danger">{resource === 'user-groups' ? 'Tenant-wide group ' : 'Department '}{creating ? 'management' : 'read'} permission is required.</Notice>{!id && canCreate && <a className="janso-btn janso-btn--primary" href={'/' + resource + '/new'}>Create {resource === 'departments' ? 'department' : 'user group'}</a>}</div>
        : !id ? <OrganisationDirectory key={key} resource={resource} context={access} initialQuery={query} />
          : creating || editing ? <OrganisationEditor key={key} resource={resource} context={access} id={creating ? undefined : id} parentId={creating ? parentId : undefined} returnTo={returnTo} />
            : <OrganisationDetail key={key} resource={resource} context={access} id={id} returnTo={returnTo} />}
  </ConsoleShell></Providers>;
}
