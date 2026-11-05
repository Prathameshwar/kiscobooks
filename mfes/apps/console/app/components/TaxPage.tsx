import { notFound } from 'next/navigation';
import { ErrorState } from '@janso/ui';
import { Providers } from '../providers';
import { pageContext } from '../lib/page-context';
import { companyPermission } from '../lib/company-permissions';
import { taxConfig, taxUuid } from '../lib/tax-masters';
import { ConsoleShell } from './ConsoleShell';
import { NoCompany } from './NoCompany';
import { TaxDirectory, TaxOverview } from './TaxDirectory';
import { TaxDetail } from './TaxDetail';
import { TaxEditor } from './TaxEditor';
import { TaxSetup } from './TaxSetup';
import { TaxReleaseEditor } from './TaxReleaseEditor';

export async function TaxPage({ segments = [], query = {} }: { segments?: string[]; query?: Record<string, string | string[] | undefined> }) {
  const config = segments.length ? taxConfig(segments[0]!) : undefined, overview = !segments.length;
  const directory = !!config && segments.length === 1, create = !!config && segments.length === 2 && segments[1] === 'new';
  const id = taxUuid.test(segments[1] ?? '') ? segments[1]!.toLowerCase() : undefined;
  const detail = !!config && !!id && segments.length === 2, editing = !!config && !config.dated && !!id && segments.length === 3 && segments[2] === 'edit';
  const replacement = !!config?.dated && !!id && segments.length === 3 && segments[2] === 'replace';
  const series = segments.join('/') === 'rates/series/new', applicability = segments[0] === 'rules' && !!id && segments.length === 4 && segments[2] === 'applicability' && segments[3] === 'new';
  const release = segments.join('/') === 'rates/release/new';
  if (!(overview || directory || create || detail || editing || replacement || series || applicability || release)) notFound();
  const { session, context } = await pageContext(), company = session.company.id;
  const read = !!company && companyPermission(session, 'tax_rule.read', company), manage = !!company && companyPermission(session, 'tax_rule.manage', company), publish = !!company && companyPermission(session, 'tax_rule.publish', company);
  const returnTo = typeof query.returnTo === 'string' ? query.returnTo : undefined, ruleId = applicability ? id : typeof query.rule_id === 'string' && taxUuid.test(query.rule_id) ? query.rule_id : undefined;
  const initialQuery = new URLSearchParams(); for (const [key, value] of Object.entries(query)) if (typeof value === 'string') initialQuery.set(key, value);
  const writing = create || editing || replacement || series || applicability || release;
  return <Providers session={session}><ConsoleShell session={session} context={context} activeHref={'/tax' + (segments.length ? '/' + segments.join('/') : '')}>
    {!company ? <NoCompany action="configure" context={context} canCreate={companyPermission(session, 'company.create')} /> : !read || writing && !manage || (release || replacement || create && config?.dated) && !publish ? <ErrorState status={403} detail="Tax read access and the requested management/publication permission are required for this company." />
      : overview ? <TaxOverview canManage={manage} /> : directory ? <TaxDirectory key={company + ':' + config!.key} company={company} config={config!} canManage={manage} canPublish={publish} initialQuery={initialQuery.toString()} />
      : release ? <TaxReleaseEditor key={company + ':' + segments.join('/')} company={company} ruleId={ruleId} returnTo={returnTo} />
      : series || applicability ? <TaxSetup key={company + ':' + segments.join('/')} company={company} ruleId={ruleId} applicability={applicability} returnTo={returnTo} />
      : create || editing || replacement ? <TaxEditor key={company + ':' + segments.join('/')} company={company} config={config!} id={id} superseding={replacement} returnTo={returnTo} seriesId={typeof query.series_id === 'string' && taxUuid.test(query.series_id) ? query.series_id : undefined} />
      : <TaxDetail key={company + ':' + segments.join('/')} company={company} config={config!} id={id!} canManage={manage} canPublish={publish} returnTo={returnTo} />}
  </ConsoleShell></Providers>;
}
