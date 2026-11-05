'use client';

import { ActionCard, ErrorState, Notice, PageHeader, PageNavigation, RolesIcon } from '@janso/ui';
import { accessContext } from '../lib/access-context';
import { administrationLink } from '../lib/administration-navigation';
import type { AccessContext } from '../lib/access-directory';
import type { Session } from '../session';

/** Shared cards retain the same scope and action wording on both administration hubs. */
export function RolesAccessCards({ context, returnTo }: { context: AccessContext; returnTo?: string }) {
  if (!context.permissions.includes('role.read')) return null;
  const href = (path: string) => returnTo ? administrationLink(path, returnTo) : path;
  return <>
    <ActionCard title="Roles" icon={<RolesIcon />} description={context.tenantPermissions.includes('role.manage') ? 'Create and manage custom permission bundles. Review or clone installation-maintained system roles.' : 'Review available roles within your authorized scopes. Custom role composition is managed by tenant administrators.'} actionLabel={context.tenantPermissions.includes('role.manage') ? 'Manage roles' : 'Review roles'} href={href('/roles')} />
    <ActionCard title="Role assignments" icon={<RolesIcon />} description="Review who has access, where it applies and when it expires. Grant or revoke assignments with delegated authority." actionLabel={context.permissions.includes('role.assign') ? 'Manage role assignments' : 'View role assignments'} href={href('/assignments')} />
    <ActionCard title="Permissions" icon={<RolesIcon />} description="Browse the application permission catalogue and review your authority. Use roles and assignments to grant access." actionLabel="Review permissions" href={href('/permissions')} />
  </>;
}

export function RolesAccessOverview({ session }: { session: Session }) {
  const context = accessContext(session);
  return <div className="janso-page">
    <PageNavigation back={{ href: '/organisation', label: 'administration' }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: 'Administration', href: '/organisation' }, { label: 'Roles & access' }]} />
    <PageHeader title="Roles & access" lede="Define permission bundles, review role assignments and understand access within your authorized scopes." />
    {context.permissions.includes('role.read') ? <>
      <div className="janso-action-card-grid"><RolesAccessCards context={context} returnTo="/organisation/access" /></div>
      <Notice>Roles define permissions. Assignments grant a role to a user or user group in a tenant, company or department. Each change requires authority for that scope.</Notice>
    </> : <ErrorState status={403} detail="Role read permission is required to review roles and access." />}
  </div>;
}
