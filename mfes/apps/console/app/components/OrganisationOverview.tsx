'use client';
import { ActionCard, CustomersIcon, Notice, PageHeader, PageNavigation, StoreIcon } from '@janso/ui';
import { NotificationEntryCard } from './NotificationEntryCard';
import { RolesAccessCards } from './RolesAccessOverview';
import { organisationPermissions } from '../lib/session-authority';
import { organisationLinks, organisationNavigationAvailable } from '../lib/organisation-navigation';
import { accessContext } from '../lib/access-context';
import { notificationAccess } from '../lib/notification-navigation';
import type { Session } from '../session';

export function OrganisationOverview({ session }: { session: Session }) {
  const permissions = organisationPermissions(session);
  const access = accessContext(session), links = organisationLinks(access), visible = (href: string) => links.some(link => link.href === href);
  return (
    <div className="janso-page"><PageNavigation back={{ href: '/', label: 'business overview' }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: 'Administration' }]} /><PageHeader title="Administration" lede="Companies, people and access within your authorized scopes. Departments use the selected company; user groups belong to the tenant." />
      {!organisationNavigationAvailable(session) ? <Notice tone="danger">Administration access is required.</Notice> : <>
        <div className="janso-action-card-grid">
          {visible('/users') && <ActionCard title="Users" icon={<CustomersIcon />} description="Invite people and manage tenant profiles within your permissions. Role assignments are a separate access change." actionLabel="Manage users" href="/users" />}
          {visible('/companies/manage') && <ActionCard title="Companies" icon={<StoreIcon />} description="View, create and edit companies within your permissions." actionLabel="Manage companies" href="/companies/manage" />}
          {visible('/user-groups') && <ActionCard title="User groups" icon={<CustomersIcon />} description="Manage tenant collections and review membership changes separately from role assignments." actionLabel="Manage user groups" href="/user-groups" />}
          {visible('/departments') && <ActionCard title="Departments" icon={<StoreIcon />} description="Manage departments in the selected company. Select an authorized company before opening this directory." actionLabel="Manage departments" href="/departments" />}
          <RolesAccessCards context={access} />
          {notificationAccess('tenant', permissions) && <NotificationEntryCard owner="tenant" permissions={permissions} />}
        </div>
        {notificationAccess('tenant', permissions) && <Notice>Notification providers, sender accounts and recipient policies are tenant-wide. Company-specific assignments remain subject to their own company scope.</Notice>}
      </>}
    </div>
  );
}
