import { ActionCard, GlobeIcon, Notice, PageHeader, PageNavigation, SectionHeader, SettingsIcon, StoreIcon, WalletIcon, UserIcon } from '@janso/ui';
import { NotificationEntryCard } from '../components/NotificationEntryCard';
import { ConsoleShell } from '../components/ConsoleShell';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { catalogs, catalogConfig } from './references/reference-config';
import { platformNavigationPermissions } from '../lib/session-authority';

export default async function PlatformPage() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform">
    <div className="janso-page">
    <PageNavigation back={session.company?.id ? { href: '/', label: 'business overview' } : undefined}
      breadcrumbs={[...(session.company?.id ? [{ label: 'Business overview', href: '/' }] : []), { label: 'Platform administration' }]} />
    <PageHeader title="Platform administration" lede="Manage the workspaces and access that keep your platform running." />
    {platformNavigationPermissions.some(permission => session.permissions.includes(permission)) ? <>
      <SectionHeader title="Platform management" description="Workspaces, platform identity, and commercial settings." />
      <div className="janso-action-card-grid">
        {session.permissions.includes('platform.account.read') ? <ActionCard icon={<UserIcon />} title="Account approvals" description="Review new registrations, independently verify account details, and approve access with an audit trail." actionLabel="Review accounts" href="/platform/accounts" /> : null}
        {session.permissions.includes('platform.tenant.read') ? <ActionCard icon={<StoreIcon />} title="Manage tenants" description="Create workspaces, review tenant details, and manage access with audited administrative actions." actionLabel="Manage tenants" href="/platform/tenants" /> : null}
        {session.permissions.includes('platform.config.manage') ? <ActionCard icon={<SettingsIcon />} title="Edit platform details" description="Keep your platform name and public application URL up to date." actionLabel="Edit details" href="/platform/details" /> : null}
        {session.permissions.includes('platform.config.manage') ? <ActionCard icon={<SettingsIcon />} title="System role updates" description="Review and apply the shipped role catalogue while preserving user assignments and custom roles." actionLabel="Review role updates" href="/platform/system-roles" /> : null}
        <NotificationEntryCard owner="platform" permissions={session.permissions} />
        {session.permissions.includes('platform.config.manage') ? <ActionCard icon={<WalletIcon />} title="Fees and pricing" description="Manage subscription plans, optional add-ons, INR and USD prices, and tax rates." actionLabel="Manage fees and pricing" href="/platform/pricing" /> : null}
      </div>
      {session.permissions.includes('platform.tenant_access.read') && <>
        <SectionHeader title="Users, roles and permissions" description="Manage administrators for customer tenants and review the access their system role provides." />
        <div className="janso-action-card-grid">
          <ActionCard icon={<UserIcon />} title="Tenant administrators" description="Select a tenant to invite, review and manage its administrators with an audit trail." actionLabel="Manage administrators" href="/platform/access/administrators" />
          <ActionCard icon={<SettingsIcon />} title="Tenant administrator role" description="Review the fixed system role, its tenant scope and administration responsibilities." actionLabel="Review role" href="/platform/access/role" />
          <ActionCard icon={<SettingsIcon />} title="Administrator permissions" description="Browse the permissions granted by the tenant-administrator system role." actionLabel="Review permissions" href="/platform/access/permissions" />
        </div>
      </>}
      {platformNavigationPermissions.some(permission => session.permissions.includes(permission)) && <a className="janso-link" href="/platform/history">View platform history</a>}
      {session.permissions.includes('platform.config.manage') && <>
        <SectionHeader title="Global reference catalogs" description="Platform-wide countries, states, currencies, languages and timezones shared by all tenants." />
        <div className="janso-action-card-grid">{catalogs.map(kind => <ActionCard key={kind} title={catalogConfig[kind].title} icon={<GlobeIcon />} description={catalogConfig[kind].description} actionLabel={'Manage ' + kind} href={'/platform/references/' + kind} />)}<ActionCard title="Timezones" icon={<GlobeIcon />} description="Browse installation-maintained IANA timezone identifiers and availability." actionLabel="Browse timezones" href="/platform/references/timezones" /></div>
      </>}
    </> : <Notice tone="danger">Platform administration permission is required.</Notice>}
    </div>
  </ConsoleShell></Providers>;
}
