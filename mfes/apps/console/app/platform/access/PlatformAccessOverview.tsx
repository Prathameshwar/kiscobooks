'use client';
import { useState } from 'react';
import {
  ActionCard,
  Card,
  CardBody,
  CardHeader,
  Notice,
  PageHeader,
  PageNavigation,
  ReviewList,
  SectionHeader,
  SettingsIcon,
  TableSearch,
  UserIcon,
} from '@janso/ui';
import { PlatformError } from '../../lib/platform-api';
import {
  administratorReturn,
  administratorRoot,
  platformAccessReader,
  type AdministratorRole,
} from '../../lib/platform-access';
import { useServiceRead } from '../../lib/service-resource';

export function PlatformAccessNavigation({
  title,
  back = '/platform/access',
  onLeave,
  tenantId,
}: {
  title: string;
  back?: string;
  onLeave?: React.MouseEventHandler<HTMLAnchorElement>;
  tenantId?: string;
}) {
  const directory = tenantId
    ? administratorReturn(back, tenantId)
    : administratorRoot;
  const scope = tenantId
    ? '?' + new URLSearchParams({ tenant: tenantId, returnTo: directory })
    : '';
  return (
    <>
      <PageNavigation
        back={{
          href: back,
          label: back.startsWith('/platform/access/administrators')
            ? 'tenant administrators'
            : back === '/platform'
              ? 'platform administration'
              : 'platform access',
        }}
        breadcrumbs={[
          { label: 'Platform administration', href: '/platform' },
          { label: 'Users, roles and permissions', href: '/platform/access' },
          { label: title },
        ]}
        onNavigate={onLeave}
      />
      <nav className="janso-page-navigation" aria-label="Platform access">
        <a className="janso-link" href={directory} onClick={onLeave}>
          Tenant administrators
        </a>
        <a
          className="janso-link"
          href={'/platform/access/role' + scope}
          onClick={onLeave}
        >
          Tenant administrator role
        </a>
        <a
          className="janso-link"
          href={'/platform/access/permissions' + scope}
          onClick={onLeave}
        >
          Administrator permissions
        </a>
      </nav>
    </>
  );
}
export function PlatformAccessOverview() {
  return (
    <div className="janso-page">
      <PlatformAccessNavigation title="Access overview" back="/platform" />
      <PageHeader
        title="Users, roles and permissions"
        lede="Manage customer tenant administrators and understand the access their system role provides."
      />
      <div className="janso-action-card-grid">
        <ActionCard
          icon={<UserIcon />}
          title="Tenant administrators"
          description="Choose a tenant to invite administrators, activate or deactivate access, and recover passwords."
          actionLabel="Manage administrators"
          href="/platform/access/administrators"
        />
        <ActionCard
          icon={<SettingsIcon />}
          title="Tenant administrator role"
          description="Review the fixed tenant-wide system role and its responsibilities."
          actionLabel="Review role"
          href="/platform/access/role"
        />
        <ActionCard
          icon={<SettingsIcon />}
          title="Administrator permissions"
          description="Search the permissions included in the tenant-administrator role."
          actionLabel="Review permissions"
          href="/platform/access/permissions"
        />
      </div>
    </div>
  );
}
export function PlatformAdministratorRole({
  permissionsOnly = false,
  tenantId,
  back,
}: {
  permissionsOnly?: boolean;
  tenantId?: string;
  back?: string;
}) {
  const read = useServiceRead<AdministratorRole>(
    '/v1/platform/access/role',
    platformAccessReader,
    (value) => {
      if (
        value.key !== 'tenant_admin' ||
        value.is_system !== true ||
        !Array.isArray(value.permissions)
      )
        throw {
          status: 502,
          message: 'The administrator role could not be verified.',
        };
    },
    'platform access service',
  );
  const [search, setSearch] = useState(''),
    title = permissionsOnly
      ? 'Administrator permissions'
      : 'Tenant administrator role';
  const permissions =
    read.data?.permissions.filter((key) =>
      key.toLowerCase().includes(search.trim().toLowerCase()),
    ) ?? [];
  const groups = [...new Set(permissions.map((key) => key.split('.')[0]))];
  return (
    <div className="janso-page">
      <PlatformAccessNavigation
        title={title}
        tenantId={tenantId}
        back={tenantId ? administratorReturn(back, tenantId) : undefined}
      />
      <PageHeader
        title={title}
        lede={
          permissionsOnly
            ? 'Review the permissions granted by the tenant-administrator system role.'
            : 'Tenant-wide administration of the organisation, its companies and access.'
        }
      />
      <PlatformError
        value={read.failure}
        returnTo={
          '/platform/access/' + (permissionsOnly ? 'permissions' : 'role')
        }
      />
      {read.loading && <p role="status">Loading administrator role…</p>}
      {read.data && (
        <>
          {!permissionsOnly && (
            <Card>
              <CardHeader
                title={read.data.name}
                subtitle="Installation-maintained system role"
              />
              <CardBody>
                <div className="janso-flow">
                  <ReviewList
                    items={[
                      { label: 'Role key', value: read.data.key },
                      {
                        label: 'Scope',
                        value: 'Selected tenant and its companies',
                      },
                      { label: 'Description', value: read.data.description },
                      {
                        label: 'Permissions',
                        value: String(read.data.permissions.length),
                      },
                    ]}
                  />
                  <Notice tone="info">
                    This system role is maintained by the installation. Invite
                    or restore a tenant administrator to assign it. Tenant
                    administrators manage ordinary users and custom roles within
                    their own tenant.
                  </Notice>
                </div>
              </CardBody>
            </Card>
          )}
          <Card>
            <CardHeader
              title="Role permissions"
              subtitle={`${permissions.length} of ${read.data.permissions.length} permissions`}
            />
            <CardBody>
              <div className="janso-flow">
                <TableSearch
                  label="Search administrator permissions"
                  value={search}
                  onChange={setSearch}
                  placeholder="Search by resource or action"
                  maxLength={100}
                />
                {groups.map((group) => (
                  <div className="janso-flow" key={group}>
                    <SectionHeader title={group.replaceAll('_', ' ')} />
                    <ul>
                      {permissions
                        .filter((key) => key.startsWith(group + '.'))
                        .map((key) => (
                          <li key={key}>
                            <code>{key}</code>
                          </li>
                        ))}
                    </ul>
                  </div>
                ))}
                {!permissions.length && (
                  <p>No permissions match this search.</p>
                )}
              </div>
            </CardBody>
          </Card>
        </>
      )}
    </div>
  );
}
