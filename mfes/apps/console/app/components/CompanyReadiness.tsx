'use client';
import { useEffect, useState, type ReactNode } from 'react';
import { Badge, Button, Card, CardBody, CardHeader, Notice, PageHeader, PageNavigation, ReviewList, Skeleton, useFormatters } from '@janso/ui';
import type { components as identity } from '@janso/api-client/identity';
import type { components as accounting } from '@janso/api-client/accounting';
import { companyCall, companyFailure, type CompanyFailure, type CompanyService } from '../lib/company-api';
import type { FiscalYearChoice } from '../lib/company-context';
import { CompanyZeroOpening } from './CompanyZeroOpening';
import { AutomaticCompanySetup } from './AutomaticCompanySetup';
import { reload } from '../lib/navigate';
import { BEFORE_COMPANY_CHANGE } from '../lib/use-unsaved-changes';

type Profile = identity['schemas']['CompanyDetail'];
type Setup = identity['schemas']['CompanySetupReadiness'];
type Books = accounting['schemas']['FinancialSetupDetail'];
type Readiness = accounting['schemas']['FiscalReadiness'];
type Check<T> = { path?: string; data?: T; error?: CompanyFailure; loading: boolean; refresh: () => void };
function useCheck<T>(service: CompanyService, path?: string): Check<T> {
  const [revision, setRevision] = useState(0), [state, setState] = useState<Omit<Check<T>, 'refresh'>>({ loading: !!path });
  useEffect(() => {
    const controller = new AbortController(); setState({ path, loading: !!path });
    if (path) companyCall<T>(service, path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ path, data, loading: false });
    }).catch(error => { if (!controller.signal.aborted) setState({ path, error: companyFailure(error), loading: false }); });
    return () => controller.abort();
  }, [service, path, revision]);
  return { ...(state.path === path ? state : { path, loading: !!path }), refresh: () => setRevision(value => value + 1) };
}
function CheckCard<T>({ title, state, children, missing, onRefresh }: { title: string; state: Check<T>; children: (data: T) => ReactNode; missing?: string; onRefresh?: () => void }) {
  return <Card><CardHeader title={title} action={state.path && <Button variant="ghost" aria-label={'Refresh ' + title.toLowerCase()} disabled={state.loading} onClick={onRefresh ?? state.refresh}>Refresh</Button>} /><CardBody>
    {!state.path ? <Notice>This check needs additional read access. Ask your company administrator or accountant.</Notice>
      : state.loading ? <div role="status" aria-label={'Checking ' + title}><Skeleton /></div>
      : state.error ? <Notice tone="warning">{state.error.status === 404 && missing ? missing : state.error.status === 403 ? 'Your access or field policy does not permit this check.' : state.error.status === 401 ? 'Your session needs to be refreshed before checking setup.' : 'This check is unavailable. Refresh it to try again.'}</Notice>
      : state.data !== undefined ? children(state.data) : <Notice>This check has not been assessed.</Notice>}
  </CardBody></Card>;
}
const blockerText: Record<string, string> = {
  INCOMPLETE_CALENDAR: 'The financial-year calendar is incomplete.',
  OPENING_NOT_FINALIZED: 'Opening balances have not been finalised.',
  CONFIGURATION_CHANGED: 'Accounting configuration needs reconciliation with the company settings.',
  COMPANY_INACTIVE: 'The company is inactive.',
};
export function CompanyReadiness({ company, name, permissions, year, fiscalNote }: {
  company: string; name: string; permissions: readonly string[]; year: FiscalYearChoice | null; fiscalNote: string | null;
}) {
  const has = (key: string) => permissions.includes(key); const format = useFormatters();
  const [refreshBlocked, setRefreshBlocked] = useState(false);
  function refreshSafely(refresh: () => void) {
    const allowed = window.dispatchEvent(new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }));
    setRefreshBlocked(!allowed);
    if (allowed) refresh();
  }
  year = has('period.read') ? year : null;
  const base = '/v1/companies/' + company;
  const profile = useCheck<Profile>('identity', has('company.read') ? base : undefined);
  const setup = useCheck<Setup>('identity', has('company.read') ? base + '/setup-readiness' : undefined);
  const books = useCheck<Books>('accounting', has('accounting.finance.read') ? base + '/financial-setup' : undefined);
  const canAssess = ['accounting.finance.read', 'period.read', 'ledger.read'].every(has);
  const readiness = useCheck<Readiness>('accounting', year && canAssess ? `${base}/fiscal-years/${year.id}/readiness` : undefined);
  const openingFinalized = year && readiness.data?.fiscal_year_id === year.id
    ? !readiness.data.blockers.includes('OPENING_NOT_FINALIZED') : undefined;
  const show = (value: unknown) => value === undefined || value === null || value === '' ? 'Not available to this check' : String(value);
  return <div className="janso-page"><PageNavigation back={{ href: '/settings', label: 'Company settings' }} breadcrumbs={[{ label: 'Company settings', href: '/settings' }, { label: 'Company readiness' }]} />
    <PageHeader title="Company readiness" lede={'Setup evidence for ' + name + (year ? ' · ' + year.code : '')} />
    {has('company.read') && <AutomaticCompanySetup company={company} canRetry={has('company.update')} onComplete={() => refreshSafely(reload)} openingFinalized={openingFinalized} />}
    <Notice>These checks show setup evidence your role can read. They do not authorise posting or certify tax compliance. Every transaction still checks its own company, dates, configuration and permissions.</Notice>
    <CheckCard title="Company identity and defaults" state={profile}>{data => data.id !== company ? <Notice tone="danger">The company response does not match the current workspace.</Notice> : <>
      <ReviewList items={[
        { label: 'Company', value: show(data.display_name) }, { label: 'Company code', value: show(data.code) },
        { label: 'Status', value: show(data.status) }, { label: 'Base currency', value: show(data.base_currency) },
        { label: 'Books begin', value: data.books_begin_date ? format.date(data.books_begin_date) : show(null) },
        { label: 'Default tax system', value: show(data.default_tax_system) },
      ]} /><p>A default tax system does not verify registrations, licences or effective tax treatment.</p>
    </>}</CheckCard>
    <CheckCard title="Features and immutable settings" state={setup}>{data => data.company_id !== company ? <Notice tone="danger">The setup response does not match the current workspace.</Notice> : <>
      <Badge tone={data.company_status === 'active' ? 'success' : 'warn'}>{data.company_status}</Badge>
      <p>{data.first_posted_at ? 'The company has posted activity. Protected settings are frozen.' : 'No first posting is recorded by Identity.'}</p>
      <p>Protected settings: {data.frozen_company_fields.length ? data.frozen_company_fields.join(', ') : 'None reported by this check'}.</p>
      <ul>{data.features.filter(feature => feature.state !== 'DISABLED').map(feature => <li key={feature.feature_key}>{feature.feature_key.replaceAll('_', ' ')}: {feature.state.toLowerCase()}{feature.missing_prerequisites.length ? ' — missing ' + feature.missing_prerequisites.join(', ') : ''}{!feature.tax_system_supported ? ' — incompatible tax system' : ''}</li>)}</ul>
      <p>Feature changes and protected-field changes remain subject to server checks.</p>
    </>}</CheckCard>
    {refreshBlocked && <Notice tone="warning">Finish the opening-balance review before refreshing setup checks.</Notice>}
    <CheckCard title="Accounting books" state={books} onRefresh={() => refreshSafely(books.refresh)} missing="Accounting books have not been initialised. An authorised accounting administrator must complete setup.">{data => data.company_id !== undefined && data.company_id !== company ? <Notice tone="danger">The accounting response does not match the current workspace.</Notice> : <>
      <ReviewList items={[{ label: 'Books currency', value: show(data.base_currency) }, { label: 'Books begin', value: data.books_begin_date ? format.date(data.books_begin_date) : show(null) },
        { label: 'First posting', value: data.first_posted_at === undefined ? show(undefined) : data.first_posted_at ? format.dateTime(data.first_posted_at) : 'None recorded' }]} />
      <Notice>Initialised books alone do not prove that account mappings, opening balances or document numbering are ready.</Notice>
      {data.company_id === company && data.first_posted_at === null && data.books_begin_date && <CompanyZeroOpening key={company} company={company} canConfirm={has('opening_balance.initialize_zero') || has('accounting.finance.manage')} onSaved={() => { setRefreshBlocked(false); books.refresh(); readiness.refresh(); }} />}
    </>}</CheckCard>
    <Card><CardHeader title="Financial-year context" /><CardBody>
      {!has('period.read') ? <Notice>Financial-calendar read access is required to inspect this check.</Notice> : year ? <>
        <p>{year.code}: {format.date(year.startDate)} to {format.date(year.endDate)}</p>
        <p>The selected year is display context. A document's posting date determines its accounting period.</p>
      </> : <Notice tone="warning">{fiscalNote ?? 'No financial year is selected. Ask an authorised accountant to check the calendar.'}</Notice>}
    </CardBody></Card>
    {year && <CheckCard title="Posting prerequisites" state={readiness}>{data => data.fiscal_year_id !== year.id ? <Notice tone="danger">The readiness response does not match the selected financial year.</Notice> : <>
      <Badge tone={data.ready_for_posting ? 'success' : 'warn'}>{data.ready_for_posting ? 'Year prerequisites satisfied' : 'Year prerequisites incomplete'}</Badge>
      <ul>{data.blockers.map(code => <li key={code}>{blockerText[code] ?? code.replaceAll('_', ' ').toLowerCase()}</li>)}</ul>
      {!data.periods.some(period => period.status === 'OPEN') && <Notice tone="warning">No period in this year is open.</Notice>}
      <ReviewList items={data.periods.map(period => ({ label: period.code, value: period.status.replaceAll('_', ' ') }))} />
      <p>Opening balances continue across years; a new annual opening voucher is not required.</p>
      <div className="janso-form-actions"><a className="janso-link" href={`/companies/${company}/years/${year.id}`}>View year and manage periods</a>{has('report.read') && <a className="janso-link" href={`/companies/${company}/years/${year.id}/continuity`}>Review opening balances</a>}</div>
    </>}</CheckCard>}
    <Card><CardHeader title="Remaining setup responsibilities" /><CardBody>
      <p>Your accountant must verify the chart of accounts and mappings, opening balances, applicable tax registrations and document numbering before relevant transactions are posted. Those checks are not certified by this view.</p>
      <p>Ask an authorised administrator to resolve incomplete settings. Each available setup action requires its own permission.</p>
      {has('report.read') && <a className="janso-link" href="/reports">Open company reports</a>}
    </CardBody></Card>
  </div>;
}
