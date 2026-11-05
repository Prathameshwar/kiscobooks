'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { Badge, Button, Card, CardBody, CardHeader, ConfirmDialog, DataTable, DisplayConfigProvider,
  DEFAULT_DISPLAY_CONFIG, ErrorState, FieldGrid, FilterBar, FormActions, Notice, PageHeader, PageNavigation,
  Pager, ReviewList, Skeleton, TableSearch, TextField, asErrorStatus, resolvedDisplay,
  useFormatters, useListQuery, type Column, type MenuItem, type PageMeta } from '@janso/ui';
import type { components as accounting } from '@janso/api-client/accounting';
import type { components as identity } from '@janso/api-client/identity';
import type { Session } from '../session';
import { companyCall, companyFailure, openCompany, type CompanyFailure, type CompanyService } from '../lib/company-api';
import { administrationBackLabel, administrationLink, administrationReturn } from '../lib/administration-navigation';
import { companyPermission } from '../lib/company-permissions';
import { fiscalYearLabel, fiscalYearSpan, validFiscalAnchor } from '../lib/company-defaults';
import { goTo, stepUpUrl } from '../lib/navigate';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';
import { CompanyBooksRecovery } from './CompanyBooksRecovery';
import { NextFinancialYear } from './NextFinancialYear';
import { completeFiscalCalendar } from '../lib/fiscal-calendar';

type Year = accounting['schemas']['FiscalYearDetail'];
type Period = accounting['schemas']['FiscalPeriodListItem'];
type Fields = accounting['schemas']['FieldSet'];
type Setup = accounting['schemas']['FinancialSetupDetail'];
type Status = NonNullable<Period['status']>;
type ReadState<T> = { loading: boolean; data?: T; error?: CompanyFailure };
function useRead<T>(service: CompanyService, path: string | undefined, revision: number): ReadState<T> {
  const [state, setState] = useState<ReadState<T> & { path?: string }>({ loading: !!path });
  useEffect(() => {
    const controller = new AbortController(); setState({ path, loading: !!path });
    if (path) companyCall<T>(service, path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ path, data, loading: false });
    }).catch(error => { if (!controller.signal.aborted) setState({ path, loading: false, error: companyFailure(error) }); });
    return () => controller.abort();
  }, [service, path, revision]);
  return state.path === path ? state : { loading: !!path };
}
function Failure({ error, retry, companyId }: { error: CompanyFailure; retry: () => void; companyId: string }) {
  return <>{error.status === 404 ? <Notice tone="warning">This financial year or books setup was not found for this company.</Notice>
    : <ErrorState status={asErrorStatus(error.status)} detail={error.message} />}
    {error.code === 'step_up_required' ? <a className="janso-btn janso-btn--primary" href={stepUpUrl(companyId)}>Verify sign-in</a>
      : error.status !== 403 && error.status !== 404 && <Button variant="ghost" onClick={retry}>Retry</Button>}</>;
}
const transitions: { from: Status; to: Status; permission: string; label: string }[] = [
  { from: 'FUTURE', to: 'OPEN', permission: 'period.manage', label: 'Open period' },
  { from: 'OPEN', to: 'SOFT_CLOSED', permission: 'period.close', label: 'Soft close period' },
  { from: 'SOFT_CLOSED', to: 'CLOSED', permission: 'period.close', label: 'Close period' },
  { from: 'SOFT_CLOSED', to: 'OPEN', permission: 'period.reopen', label: 'Reopen period' },
  { from: 'CLOSED', to: 'OPEN', permission: 'period.reopen', label: 'Reopen period' },
  { from: 'CLOSED', to: 'LOCKED', permission: 'period.lock', label: 'Lock period permanently' },
];

export function CompanyFinancialYears(props: { session: Session; companyId: string; companyName: string; mode?: 'list' | 'new' | 'next'; yearId?: string; sourceYearId?: string; returnTo?: string }) {
  const [revision, setRevision] = useState(0);
  const display = useRead<identity['schemas']['DisplayConfig']>('identity', '/v1/companies/' + props.companyId + '/display-config', revision);
  const profile = useRead<identity['schemas']['CompanyDetail']>('identity', companyPermission(props.session, 'company.read', props.companyId)
    ? '/v1/companies/' + props.companyId : undefined, revision);
  const companyName = profile.data?.id === props.companyId ? profile.data.display_name ?? profile.data.code ?? props.companyName : props.companyName;
  const config = { ...DEFAULT_DISPLAY_CONFIG, ...Object.fromEntries(Object.entries(resolvedDisplay(display.data ?? {})).filter(([, value]) => value !== undefined)) };
  return <DisplayConfigProvider config={config}>
    {props.mode === 'next' ? <NextFinancialYear {...props} companyName={companyName} />
      : <YearWorkspace {...props} mode={props.mode} companyName={companyName} revision={revision} refresh={() => setRevision(value => value + 1)} displayError={display.error} />}
  </DisplayConfigProvider>;
}

function YearWorkspace({ session, companyId, companyName, mode = 'list', yearId, revision, refresh, displayError, returnTo }: {
  session: Session; companyId: string; companyName: string; mode?: 'list' | 'new'; yearId?: string;
  revision: number; refresh: () => void; displayError?: CompanyFailure; returnTo?: string;
}) {
  const has = (permission: string) => companyPermission(session, permission, companyId);
  const base = '/companies/' + companyId + '/years', api = '/v1/companies/' + companyId;
  const format = useFormatters();
  const year = useRead<Year>('accounting', yearId ? api + '/fiscal-years/' + yearId : undefined, revision);
  const setup = useRead<Setup>('accounting', has('accounting.finance.read') ? api + '/financial-setup' : undefined, revision);
  const nextYear = useRead<accounting['schemas']['NextYearPreview']>('accounting', mode === 'new' && has('accounting.finance.read') ? api + '/fiscal-years/next-preview' : undefined, revision);
  const yearFields = useRead<Fields>('accounting', mode === 'new' ? api + '/finance/field-sets/fiscal-years' : undefined, revision);
  const periodFields = useRead<Fields>('accounting', yearId ? api + '/finance/field-sets/fiscal-periods' : undefined, revision);
  const periods = useRead<accounting['schemas']['Page_FiscalPeriodListItem_']>('accounting', yearId ? api + '/fiscal-periods?fiscal_year_id=' + yearId + '&limit=13' : undefined, revision);
  const [busy, setBusy] = useState(false), pending = useRef(false);
  const navigating = useRef(false), suggested = useRef(false), originalStart = useRef('');
  const [failure, setFailure] = useState<CompanyFailure | null>(null), [success, setSuccess] = useState<string | null>(null);
  const [startYear, setStartYear] = useState(''), [startError, setStartError] = useState('');
  const [command, setCommand] = useState<{ period: Period; status: Status; label: string } | null>(null);
  const [reviewing, setReviewing] = useState(false), [operation, setOperation] = useState<'initialize' | 'generate' | 'transition' | null>(null);
  const uncertain = !!failure && failure.status >= 500;
  const [reason, setReason] = useState(''), [reasonError, setReasonError] = useState('');
  const keys = useRef(new Map<string, string>()), reasonInput = useRef<HTMLInputElement>(null), startInput = useRef<HTMLInputElement>(null);
  useEffect(() => { if ((startError || failure?.fields?.start_year) && !busy) startInput.current?.focus(); }, [startError, failure, busy]);
  const isDirty = (mode === 'new' && startYear !== originalStart.current) || !!reason || busy || uncertain;
  useUnsavedChanges(useCallback(() => !navigating.current && (isDirty || pending.current), [isDirty]));
  const [discard, setDiscard] = useState<string | null>(null);
  useEffect(() => {
    if (mode !== 'new' || suggested.current || startYear || !nextYear.data) return;
    if (nextYear.data.company_id === companyId && nextYear.data.start_year) {
      originalStart.current = String(nextYear.data.start_year);
      suggested.current = true; setStartYear(originalStart.current);
    }
  }, [mode, nextYear.data, companyId, startYear]);
  function keyFor(body: unknown): string {
    const signature = JSON.stringify(body); let key = keys.current.get(signature);
    if (!key) { key = crypto.randomUUID(); keys.current.set(signature, key); } return key;
  }
  async function initialize() {
    if (pending.current || uncertain && operation !== 'initialize') return; pending.current = true; setOperation('initialize'); setBusy(true); setFailure(null);
    try {
      await companyCall('accounting', api + '/accounting-setup/initialize', { method: 'POST', body: {}, key: 'accounting-init-' + companyId });
      await companyCall('accounting', api + '/financial-setup/initialize', { method: 'POST', body: {}, key: 'init-' + companyId }); setSuccess('Books setup initialized.'); refresh();
    }
    catch (error) { setFailure(companyFailure(error)); } finally { pending.current = false; setBusy(false); }
  }
  async function generate(event: FormEvent) {
    event.preventDefault(); if (pending.current || uncertain && operation !== 'generate') return;
    if (!/^\d{4}$/.test(startYear) || Number(startYear) < 1900 || Number(startYear) > 9997) { setStartError('Enter a whole starting year from 1900 to 9997.'); return; }
    const field = yearFields.data?.fields.find(item => item.key === 'start_year');
    if (!has('period.manage') || !field?.readable || !field.writable || !field.visible) return;
    pending.current = true; setOperation('generate'); setBusy(true); setFailure(null); setStartError('');
    const body = { start_year: Number(startYear) };
    try {
      const data = await companyCall<Year>('accounting', api + '/fiscal-years/generate', { method: 'POST', body, key: keyFor(body) });
      if (data.company_id !== companyId) throw new Error('Year scope mismatch');
      navigating.current = true; setStartYear(''); goTo(administrationLink(base + '/' + data.id, back));
    } catch (error) { setFailure(companyFailure(error)); } finally { pending.current = false; setBusy(false); }
  }
  async function transition() {
    if (!command || pending.current) return;
    if (reason.trim().length < 3 || reason.trim().length > 500) { setReasonError('Give a reason using 3 to 500 characters.'); reasonInput.current?.focus(); return; }
    pending.current = true; setOperation('transition'); setBusy(true); setFailure(null); setReasonError('');
    const body = { status: command.status, reason: reason.trim(), expected_version: command.period.row_version };
    try {
      const data = await companyCall<Period>('accounting', api + '/fiscal-periods/' + command.period.id + '/transition', {
        method: 'POST', body, key: keyFor({ id: command.period.id, ...body }),
      });
      if (data.company_id !== companyId || data.fiscal_year_id !== yearId) throw new Error('Period scope mismatch');
      setSuccess(command.label + ' completed.'); setCommand(null); setReviewing(false); setReason(''); refresh();
    } catch (error) { setFailure(companyFailure(error)); } finally { pending.current = false; setBusy(false); }
  }
  const rows = [...(periods.data?.items ?? [])].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
  const complete = !!yearId && completeFiscalCalendar(companyId, yearId, year.data?.start_date, year.data?.end_date, rows, periods.data?.page.has_more);
  function periodActions(row: Period): MenuItem[] {
    const fields = periodFields.data?.fields;
    if (!complete || !['status', 'reason'].every(key => fields?.some(field => field.key === key && field.readable && field.writable && field.visible))) return [];
    return transitions.filter(item => item.from === row.status && has(item.permission)).map(item => {
      const preceding = rows.filter(period => (period.sequence ?? 0) < (row.sequence ?? 0));
      const blocked = item.to === 'SOFT_CLOSED' ? preceding.some(period => period.status === 'OPEN' || period.status === 'FUTURE')
        : ['CLOSED', 'LOCKED'].includes(item.to) ? preceding.some(period => period.status !== 'CLOSED' && period.status !== 'LOCKED') : false;
      return { id: item.to, label: item.label, destructive: item.to === 'LOCKED', disabledReason: busy ? 'A change is in progress' : uncertain ? 'Recover the unconfirmed change first' : blocked ? 'Close preceding periods first' : undefined };
    });
  }
  const columns: Column<Period>[] = [
    { key: 'code', header: 'Period', type: 'code' }, { key: 'start_date', header: 'Starts', type: 'date' }, { key: 'end_date', header: 'Ends', type: 'date' },
    { key: 'status', header: 'Status', type: 'custom', render: row => <Badge tone={row.status === 'OPEN' ? 'success' : row.status === 'LOCKED' ? 'warn' : 'neutral'}>{row.status ? ({ FUTURE: 'Future', OPEN: 'Open', SOFT_CLOSED: 'Soft closed', CLOSED: 'Closed', LOCKED: 'Locked' }[row.status]) : 'Not available'}</Badge> },
  ];
  const month = setup.data?.fiscal_year_start_month, day = setup.data?.fiscal_year_start_day;
  const preview = month && day && validFiscalAnchor(month, day) ? fiscalYearSpan(Number(startYear), month, day) : null;
  const generator = yearFields.data?.fields.find(field => field.key === 'start_year');
  const canGenerate = has('period.manage') && generator?.visible && generator.readable && generator.writable;
  const origin = returnTo ? administrationReturn('companies', returnTo) : undefined;
  const back = origin ?? (yearId || mode === 'new' ? base : has('company.read') ? '/companies/' + companyId : '/companies');
  const years = administrationLink(base, origin ?? (has('company.read') ? '/companies/' + companyId : '/companies'));
  return <div className="janso-page">
    <PageNavigation back={{ href: back, label: administrationBackLabel(back) }}
      breadcrumbs={[{ label: 'Companies', href: '/companies' }, { label: companyName, href: has('company.read') ? administrationLink('/companies/' + companyId, origin ?? '/companies/manage') : undefined },
        { label: 'Financial years', href: yearId || mode === 'new' ? years : undefined }, ...(yearId || mode === 'new' ? [{ label: yearId ? 'Year details' : 'Generate year' }] : [])]}
      onNavigate={event => { if (!navigating.current && isDirty) { event.preventDefault(); if (!busy) setDiscard(event.currentTarget.href); } }} />
    <PageHeader title={yearId ? year.data?.code ?? 'Financial year' : mode === 'new' ? 'Generate financial year' : 'Financial years'} lede={'Company: ' + companyName}
      actions={mode === 'list' && !yearId && has('period.manage') ? <div className="janso-form-actions"><a className="janso-btn janso-btn--ghost" href={administrationLink(base + '/new', years)}>Generate year</a><a className="janso-btn janso-btn--primary" href={administrationLink(base + '/next', years)}>Start next financial year</a></div> : undefined} />
    {displayError && <Notice tone="warning">Company display settings are unavailable. Dates use the standard format.</Notice>}
    {success && <Notice tone="success">{success}</Notice>}
    {failure && !command && <Notice tone="danger">{failure.message}</Notice>}
    {uncertain && <Notice tone="warning">The result is unconfirmed. Your exact request is retained. Recover it before starting another change.{command && !reviewing && <Button variant="ghost" onClick={() => setReviewing(true)}>Recover period change</Button>}</Notice>}
    {has('accounting.finance.read') && setup.error?.status === 404 && <Notice tone="warning">Initialize the company books before generating years.
      {has('accounting.finance.initialize') || has('accounting.finance.manage') ? <Button variant="ghost" loading={busy} onClick={initialize}>Initialize books</Button> : ' Ask your accounting administrator to initialize the books.'}</Notice>}
    {has('accounting.finance.read') && setup.error && setup.error.status !== 404 && <Failure companyId={companyId} error={setup.error} retry={refresh} />}
    {has('accounting.finance.read') && has('accounting.finance.manage') && setup.data && <CompanyBooksRecovery companyId={companyId}
      onSaved={() => { setSuccess('Unused books reconciled with company settings.'); refresh(); }} />}
    {!yearId && mode === 'list' && <YearDirectory companyId={companyId} revision={revision} returnTo={years} canManage={has('period.manage')} canReport={has('report.read')} />}
    {mode === 'new' && <Card><CardHeader title="Year settings" subtitle="Accounting derives a unique code, date range and twelve monthly periods from the company calendar. An existing year is returned without duplication." /><CardBody>
      {nextYear.error && nextYear.error.status !== 404 && <Notice tone="warning">The suggested next year is unavailable. Enter the starting year explicitly or retry the calendar check. <Button variant="ghost" onClick={refresh}>Retry calendar check</Button></Notice>}
      {yearFields.loading ? <Skeleton /> : yearFields.error ? <Failure companyId={companyId} error={yearFields.error} retry={refresh} /> : !canGenerate ? <Notice>You have read-only access to financial years or the start-year field.</Notice>
        : <form onSubmit={generate} noValidate className="janso-flow"><FieldGrid disabled={busy || uncertain}>
          <TextField ref={startInput} label={generator?.label ?? 'Starting year'} inputMode="numeric" value={startYear} maxLength={4} required error={startError || failure?.fields?.start_year}
            hint="The calendar year in which this financial year starts, such as 2026 for April 2026–March 2027."
            onChange={event => { suggested.current = true; setStartYear(event.target.value); setStartError(''); }} />
          {preview?.start && <ReviewList items={[{ label: 'Year code', value: fiscalYearLabel(preview) }, { label: 'Start date', value: format.date(preview.start) }, { label: 'End date', value: format.date(preview.end) }]} />}
        </FieldGrid>
        {!preview?.start && <Notice>Dates and code are assigned from the company fiscal calendar. Review the generated dates on the year page.</Notice>}
        <FormActions><Button type="submit" loading={busy} loadingLabel="Generating year…" disabled={setup.error?.status === 404 || !!(setup.error && has('accounting.finance.read')) || uncertain && operation !== 'generate'}>{uncertain && operation === 'generate' ? 'Retry same year generation' : 'Generate year'}</Button></FormActions>
      </form>}
    </CardBody></Card>}
    {yearId && (year.loading ? <div role="status" aria-label="Loading financial year"><Skeleton /></div> : year.error ? <Failure companyId={companyId} error={year.error} retry={refresh} />
      : year.data?.company_id !== companyId ? <Notice tone="danger">This year does not belong to this company.</Notice> : <>
        <Card><CardBody><ReviewList items={[{ label: 'Year code', value: year.data.code ?? 'Not available' }, { label: 'Start date', value: format.date(year.data.start_date) }, { label: 'End date', value: format.date(year.data.end_date) }]} /></CardBody></Card>
        <Notice>Year dates are generated from the company calendar. Period statuses control posting. Opening a new year does not close an older year.</Notice>
        <nav className="janso-form-actions" aria-label="Financial-year actions">
          <Button variant="ghost" disabled={busy || uncertain} onClick={() => void openCompany(companyId, yearId).then(error => { if (error) setFailure(error); })}>Use this year</Button>
          {has('period.manage') && <a className="janso-link" href={administrationLink(base + '/next?sourceYear=' + yearId, years)}>Start next financial year</a>}
          {has('report.read') && <a className="janso-link" href={administrationLink(base + '/' + yearId + '/continuity', years)}>Review opening balances</a>}
        </nav>
        <Card><CardHeader title="Monthly periods" action={<Button variant="ghost" disabled={busy || periods.loading || uncertain} onClick={refresh}>Refresh periods</Button>} />
          {periodFields.error && <Failure companyId={companyId} error={periodFields.error} retry={refresh} />}
          {periods.data && !complete && <Notice tone="warning">The complete twelve-period calendar or required fields are unavailable. Status changes are disabled.</Notice>}
          <DataTable caption="Financial-year periods" columns={columns} rows={rows} rowId={row => row.id} rowLabel={row => row.code ?? 'Period'} loading={periods.loading}
            error={periods.error ? asErrorStatus(periods.error.status) : null} errorDetail={periods.error?.message} onRetry={refresh}
            emptyTitle="No periods available" rowActions={periodActions} onAction={(status, row) => {
              const action = transitions.find(item => item.from === row.status && item.to === status);
              if (action && !busy && !uncertain) { setCommand({ period: row, status: action.to, label: action.label }); setReviewing(true); setReason(''); setFailure(null); setReasonError(''); }
            }} />
        </Card>
      </>)}
    <ConfirmDialog open={!!command && reviewing} title={command ? `${command.label}: ${command.period.code ?? 'period'}?` : 'Change period status'}
      tone={command?.status === 'LOCKED' ? 'danger' : 'default'} confirmPhrase={command?.status === 'LOCKED' ? 'LOCK' : undefined}
      confirmLabel={uncertain ? 'Retry same period change' : command?.label ?? 'Confirm'} busy={busy} error={failure?.message} onCancel={() => { if (pending.current) return; setReviewing(false); if (!uncertain) { setCommand(null); setReason(''); setFailure(null); } }} onConfirm={() => void transition()}>
      <p>{command?.status === 'LOCKED' ? 'Locking is permanent. This period cannot be reopened through the application.' : 'This changes which transactions may post to this period. Accounting checks pending entries and preceding periods.'}</p>
      <TextField ref={reasonInput} label="Reason for status change" value={reason} maxLength={500} required disabled={busy || uncertain} error={reasonError || failure?.fields?.reason} onChange={event => { setReason(event.target.value); setReasonError(''); }} />
      {failure?.status === 409 && <Button variant="ghost" disabled={busy} onClick={() => { setCommand(null); setReviewing(false); setReason(''); setFailure(null); refresh(); }}>Reload periods</Button>}
    </ConfirmDialog>
    <ConfirmDialog open={discard !== null} title="Discard unsaved changes?" confirmLabel="Discard changes" onCancel={() => setDiscard(null)}
      onConfirm={() => { navigating.current = true; const target = discard; setDiscard(null); setStartYear(''); setReason(''); if (target) goTo(target); }}>
      Unsaved year settings or period-change reasons will be discarded.
    </ConfirmDialog>
  </div>;
}

function YearDirectory({ companyId, revision, returnTo, canManage, canReport }: { companyId: string; revision: number; returnTo: string; canManage: boolean; canReport: boolean }) {
  const base = '/companies/' + companyId + '/years';
  const [meta, setMeta] = useState<PageMeta | null>(null);
  const query = useListQuery({ meta });
  const params = new URLSearchParams({ limit: String(query.limit) });
  if (query.q) params.set('q', query.q); if (query.cursor) params.set('cursor', query.cursor);
  const [retry, setRetry] = useState(0);
  const data = useRead<accounting['schemas']['Page_FiscalYearListItem_']>('accounting', '/v1/companies/' + companyId + '/fiscal-years?' + params, revision + retry);
  useEffect(() => { setMeta(data.data ? { ...data.data.page, limit: query.limit } : null); }, [data.data, query.limit]);
  const columns: Column<Year>[] = [{ key: 'code', header: 'Financial year', type: 'custom', render: row => <a className="janso-link" href={administrationLink(base + '/' + row.id, returnTo)}>{row.code ?? 'Financial year'}</a> },
    { key: 'start_date', header: 'Starts', type: 'date' }, { key: 'end_date', header: 'Ends', type: 'date' }];
  return <Card><CardHeader title="Company financial years" subtitle="Each year has a unique company-specific code and date range." />
    <FilterBar><TableSearch label="Search financial years" placeholder="Year code, e.g. FY2026" value={query.q} onChange={query.setSearch} minLength={2} maxLength={100} busy={data.loading} /></FilterBar>
    <DataTable caption="Company financial years" columns={columns} rows={data.data?.items ?? []} rowId={row => row.id} rowLabel={row => row.code ?? 'Financial year'}
      loading={data.loading} error={data.error ? asErrorStatus(data.error.status) : null} errorDetail={data.error?.message} onRetry={() => setRetry(value => value + 1)}
      emptyTitle="No financial years found" emptyBody="Generate a year when permitted, or ask your accounting administrator." filtered={query.filtered} onClearFilters={query.clearFilters}
    rowActions={row => [
      { id: 'view', label: 'View year and manage periods', href: administrationLink(base + '/' + row.id, returnTo) },
      ...(canManage ? [{ id: 'next', label: 'Start next financial year', href: administrationLink(base + '/next?sourceYear=' + row.id, returnTo) }] : []),
      ...(canReport ? [{ id: 'continuity', label: 'Review opening balances', href: administrationLink(base + '/' + row.id + '/continuity', returnTo) }] : []),
    ]} />
    <Pager noun="year" count={data.data?.items.length ?? 0} from={query.page.from} limit={query.limit} hasPrevious={query.page.hasPrevious} hasNext={!data.loading && !data.error && query.page.hasNext}
      onPrevious={query.previousPage} onNext={query.nextPage} onLimitChange={query.setLimit} busy={data.loading} />
  </Card>;
}
