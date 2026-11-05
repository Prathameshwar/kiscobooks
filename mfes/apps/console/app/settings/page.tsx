import { ActionCard, BookIcon, BoxIcon, CalendarIcon, CustomersIcon, GlobeIcon, Notice, PageHeader, PageNavigation, ReceiptIcon, RolesIcon, SectionHeader, SettingsIcon, StockIcon } from '@janso/ui';
import { ConsoleShell } from '../components/ConsoleShell';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { NoCompany } from '../components/NoCompany';
import { accessContext } from '../lib/access-context';
import { companyPermission } from '../lib/company-permissions';
import { accountingReadPermissions } from '../lib/accounting-configuration-resources';
import { administrationLink } from '../lib/administration-navigation';
import { organisationNavigationAvailable } from '../lib/organisation-navigation';
import { catalogConfig } from '../platform/references/reference-config';

export default async function SettingsPage() {
  const { session, context } = await pageContext(), access = accessContext(session);
  const company = session.company.id;
  const has = (permission: string) => !!company && companyPermission(session, permission, company);
  const readiness = ['company.read', 'period.read', 'accounting.finance.read'].some(has);
  const accounting = accountingReadPermissions.some(has);
  const users = has('user.read') || has('user.invite'), roles = has('role.read');
  const vouchers = has('vouchers.read');
  const business = has('product_configuration.read') || accounting || has('warehouse.read') || vouchers;
  const organisation = organisationNavigationAvailable(session);
  const today = new Date().toISOString().slice(0, 10);
  const manageReferences = session.permissions.includes('platform.config.manage') && (session.grants ?? []).some(grant =>
    ['tenant', 'platform'].includes(grant.scope_type) && grant.permissions.includes('platform.config.manage')
    && grant.valid_from <= today && (!grant.valid_to || grant.valid_to >= today));
  const link = (path: string) => administrationLink(path, '/settings');
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/settings">
    <div className="janso-page"><PageNavigation back={{ href: '/', label: 'business overview' }} breadcrumbs={[{ label: 'Business overview', href: '/' }, { label: 'Company settings' }]} /><PageHeader title="Company settings" lede="Setup and controls for the company currently open." />
      {!company ? <NoCompany action="configure" context={context} canCreate={companyPermission(session, 'company.create')} /> : <>
        <Notice>These settings apply to {session.company.name}. {organisation && <>Shared notifications and tenant-wide administration are available in <a className="janso-link" href="/organisation">Administration</a>.</>}</Notice>
        {readiness && <section className="janso-flow" aria-label="Company setup">
          <SectionHeader title="Company setup" description="Company defaults, financial calendar and setup checks." />
          <div className="janso-action-card-grid">
            {has('company.read') && <ActionCard title="Company configuration" icon={<SettingsIcon />} description="Review company defaults, display preferences and enabled features." actionLabel={has('company.update') ? 'Configure company' : 'View company configuration'} href={link('/companies/' + company + '/configuration')} />}
            {has('period.read') && <ActionCard title="Financial years" icon={<CalendarIcon />} description="Review financial years and monthly periods. Manage the calendar with the required access." actionLabel={has('period.manage') ? 'Manage financial years' : 'View financial years'} href={link('/companies/' + company + '/years')} />}
            <ActionCard title="Company readiness" icon={<SettingsIcon />} description="Check company setup, accounting books and financial-year prerequisites within your read access." actionLabel="Check company readiness" href="/settings/readiness" />
          </div>
        </section>}
        {business && <section className="janso-flow" aria-label="Business configuration">
          <SectionHeader title="Business configuration" description="Product, accounting, voucher and warehouse settings for this company." />
          <div className="janso-action-card-grid">
            {has('product_configuration.read') && <ActionCard title="Product configuration" icon={<BoxIcon />} description="Review dated product defaults, inherited settings and configuration publication." actionLabel={has('product_configuration.manage') ? 'Configure products' : 'View product configuration'} href={link('/products/configuration')} />}
            {accounting && <ActionCard title="Accounting configuration" icon={<BookIcon />} description="Accounts, parties, suppliers, profiles and dated accounting policies." actionLabel="Open accounting settings" href={link('/accounting')} />}
            {vouchers && <ActionCard title="Voucher types" icon={<ReceiptIcon />} description="Review voucher types and their entry rules for this company." actionLabel={has('vouchers.type.manage') ? 'Manage voucher types' : 'View voucher types'} href="/masters/voucher-types" />}
            {has('warehouse.read') && <ActionCard title="Warehouse settings" icon={<StockIcon />} description="Review storage locations and choose the default warehouses used by this company." actionLabel={has('warehouse.manage') || has('warehouse.publish') ? 'Configure warehouses' : 'View warehouse settings'} href={link('/masters/warehouses/settings')} />}
          </div>
        </section>}
        {(users || roles) && <section className="janso-flow" aria-label="People and access">
          <SectionHeader title="People and access" description="Users, roles and delegated access within your authority." />
          <div className="janso-action-card-grid">
            {users && <ActionCard title="Users" icon={<CustomersIcon />} description="Review company affiliations and authorized user profiles. Invitations and role assignments are separate actions." actionLabel={!has('user.read') ? 'Invite user' : has('user.invite') || access.tenantPermissions.includes('user.update') ? 'Manage users' : 'View users'} href={link(has('user.read') ? '/users' : '/users/new')} />}
            {roles && <ActionCard title="Roles" icon={<RolesIcon />} description="Review permission bundles. Custom role composition is maintained by tenant administrators." actionLabel={access.tenantPermissions.includes('role.manage') ? 'Manage roles' : 'Review roles'} href={link('/roles')} />}
            {roles && <ActionCard title="Role assignments" icon={<RolesIcon />} description="Review who has access, its scope and validity. Delegate only within your own authority." actionLabel={has('role.assign') ? 'Manage role assignments' : 'View role assignments'} href={link('/assignments')} />}
            {roles && <ActionCard title="Permissions" icon={<RolesIcon />} description="Browse the read-only permission catalogue. Grant access through roles and assignments." actionLabel="Review permissions" href={link('/permissions')} />}
          </div>
        </section>}
        {!readiness && !business && !users && !roles && <Notice><p>No company settings are available with your current access.</p><a className="janso-link" href="/my-access">Review my access</a></Notice>}
      </>}
      {/* Only someone who can actually manage these sees them. A company reader gets no disabled
        * copy: it is a control they can never use, on a screen about their own company. */}
      {manageReferences && <section className="janso-flow" aria-label="Global references">
        <SectionHeader title="Global references" description="Shared across all companies and maintained by platform administrators. Active values are available in company forms; company feature switches do not change these shared catalogues." />
        <div className="janso-action-card-grid">
          {(['countries', 'states', 'currencies', 'languages', 'timezones'] as const).map(catalog => <ActionCard key={catalog}
            title={catalog === 'timezones' ? 'Timezones' : catalogConfig[catalog].title}
            description={catalog === 'timezones' ? 'Browse installed IANA timezone identifiers and their availability for regional settings.' : catalogConfig[catalog].description}
            icon={<GlobeIcon />} actionLabel={catalog === 'timezones' ? 'Browse timezones' : 'Manage ' + catalog}
            href={'/platform/references/' + catalog} />)}
        </div>
      </section>}
    </div>
  </ConsoleShell></Providers>;
}
