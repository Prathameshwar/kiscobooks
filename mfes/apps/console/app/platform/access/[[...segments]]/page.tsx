import { Notice } from '@janso/ui';
import { ConsoleShell } from '../../../components/ConsoleShell';
import { Providers } from '../../../providers';
import { pageContext } from '../../../lib/page-context';
import { uuidPattern } from '../../../lib/platform-access';
import {
  PlatformAccessOverview,
  PlatformAdministratorRole,
} from '../PlatformAccessOverview';
import { PlatformAdministratorDirectory } from '../PlatformAdministratorDirectory';
import { PlatformAdministratorDetail } from '../PlatformAdministratorDetail';
import { PlatformAdministratorEditor } from '../PlatformAdministratorEditor';

export default async function PlatformAccessPage({
  params,
  searchParams,
}: {
  params: Promise<{ segments?: string[] }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { session, context } = await pageContext(),
    { segments = [] } = await params,
    query = await searchParams;
  const tenant =
    typeof query.tenant === 'string' && uuidPattern.test(query.tenant)
      ? query.tenant
      : '';
  const back = typeof query.returnTo === 'string' ? query.returnTo : undefined;
  const canRead = session.permissions.includes('platform.tenant_access.read'),
    canManage = session.permissions.includes('platform.tenant_access.manage');
  let content;
  if (!canRead)
    content = (
      <Notice tone="danger">
        Platform tenant-access permission is required.
      </Notice>
    );
  else if (!segments.length) content = <PlatformAccessOverview />;
  else if (
    segments.length === 1 &&
    ['role', 'permissions'].includes(segments[0])
  )
    content = (
      <PlatformAdministratorRole
        permissionsOnly={segments[0] === 'permissions'}
        tenantId={tenant || undefined}
        back={back}
      />
    );
  else if (segments[0] === 'administrators' && segments.length === 1)
    content = (
      <PlatformAdministratorDirectory
        key={tenant}
        tenantId={tenant}
        canManage={canManage}
        canReadTenant={session.permissions.includes('platform.tenant.read')}
      />
    );
  else if (
    segments[0] === 'administrators' &&
    tenant &&
    segments[1] === 'new' &&
    segments.length === 2 &&
    canManage
  )
    content = (
      <PlatformAdministratorEditor
        key={tenant + ':new'}
        tenantId={tenant}
        back={back}
      />
    );
  else if (
    segments[0] === 'administrators' &&
    tenant &&
    uuidPattern.test(segments[1] ?? '') &&
    segments.length === 2
  )
    content = (
      <PlatformAdministratorDetail
        key={tenant + ':' + segments[1]}
        tenantId={tenant}
        userId={segments[1]}
        canManage={canManage}
        back={back}
      />
    );
  else if (
    segments[0] === 'administrators' &&
    tenant &&
    uuidPattern.test(segments[1] ?? '') &&
    segments[2] === 'edit' &&
    segments.length === 3 &&
    canManage
  )
    content = (
      <PlatformAdministratorEditor
        key={tenant + ':' + segments[1]}
        tenantId={tenant}
        userId={segments[1]}
        back={back}
      />
    );
  else
    content = (
      <Notice tone="danger">
        This administrator page is unavailable. Select a tenant from the{' '}
        <a className="janso-link" href="/platform/access/administrators">
          administrator directory
        </a>
        .
      </Notice>
    );
  return (
    <Providers session={session}>
      <ConsoleShell
        session={session}
        context={context}
        activeHref={'/platform/access' + (segments.length ? '/' + segments.join('/') : '')}
      >
        {content}
      </ConsoleShell>
    </Providers>
  );
}
