import { ActionCard, ErrorState, GlobeIcon, PageHeader, PageNavigation } from '@janso/ui';
import { ConsoleShell } from '../../components/ConsoleShell';
import { pageContext } from '../../lib/page-context';
import { Providers } from '../../providers';
import { catalogs, catalogConfig } from './reference-config';

export default async function ReferencesPage() {
  const { session, context } = await pageContext();
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref="/platform/references">
    <div className="janso-page">
      <PageNavigation back={{ href: '/platform', label: 'platform administration' }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Reference data' }]} />
      <PageHeader title="Reference data" lede="Regional and currency references used by tenant, company and warehouse settings." />
      {session.permissions.includes('platform.config.manage') ? <div className="janso-action-card-grid">
        {catalogs.map(catalog => <ActionCard key={catalog} title={catalogConfig[catalog].title} description={catalogConfig[catalog].description} icon={<GlobeIcon />} actionLabel={'Manage ' + catalog} href={'/platform/references/' + catalog} />)}
        <ActionCard title="Timezones" description="Browse the installed IANA timezone identifiers and their availability for regional settings." icon={<GlobeIcon />} actionLabel="Browse timezones" href="/platform/references/timezones" />
      </div> : <ErrorState status={403} detail="Platform configuration permission is required to manage reference data." />}
    </div>
  </ConsoleShell></Providers>;
}
