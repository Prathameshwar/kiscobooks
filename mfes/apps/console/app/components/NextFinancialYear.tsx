'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Badge, Button, Card, CardBody, CardHeader, Checkbox, ConfirmDialog, FieldGrid,
  FormActions, Notice, PageHeader, PageNavigation, ReviewList, Skeleton, Stepper, TextField,
  useFormatters } from '@janso/ui';
import type { components } from '@janso/api-client/accounting';
import type { Session } from '../session';
import { companyCall, companyFailure, openCompany, type CompanyFailure } from '../lib/company-api';
import { companyPermission } from '../lib/company-permissions';
import { administrationBackLabel, administrationLink, administrationReturn } from '../lib/administration-navigation';
import { completeFiscalCalendar } from '../lib/fiscal-calendar';
import { goTo, stepUpUrl } from '../lib/navigate';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';

type Preview = components['schemas']['NextYearPreview'];
type Readiness = components['schemas']['FiscalReadiness'];
type Period = components['schemas']['FiscalPeriodListItem'];
type Fields = components['schemas']['FieldSet'];
export const fiscalBlockerText: Record<string, string> = {
  INCOMPLETE_CALENDAR: 'The twelve monthly periods are incomplete. Review the year calendar.',
  OPENING_NOT_FINALIZED: 'Finalise the original company opening balances before proceeding.',
  CONFIGURATION_CHANGED: 'Reconcile the accounting books with company configuration.',
  COMPANY_INACTIVE: 'Activate the company before opening periods.',
  SOURCE_CALENDAR_MISMATCH: 'The source year does not match the company calendar.',
  TARGET_CALENDAR_MISMATCH: 'The existing next year does not match the company calendar.',
  OVERLAPPING_CALENDAR: 'Another financial year overlaps these dates.',
};

export function NextFinancialYear({ session, companyId, companyName, sourceYearId, returnTo }: {
  session: Session; companyId: string; companyName: string; sourceYearId?: string; returnTo?: string;
}) {
  const has = (key: string) => companyPermission(session, key, companyId), format = useFormatters();
  const base = '/companies/' + companyId + '/years', api = '/v1/companies/' + companyId;
  const back = returnTo ? administrationReturn('companies', returnTo) : base;
  const [preview, setPreview] = useState<Preview | null>(null), [loading, setLoading] = useState(true);
  const [step, setStep] = useState(0), [year, setYear] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null), [periods, setPeriods] = useState<Period[]>([]);
  const [fields, setFields] = useState<Fields | null>(null), [selected, setSelected] = useState<string[]>([]);
  const [reason, setReason] = useState(''), [reasonError, setReasonError] = useState('');
  const [failure, setFailure] = useState<CompanyFailure | null>(null), [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(''), [revision, setRevision] = useState(0), [discard, setDiscard] = useState<string | null>(null);
  const pending = useRef(false), leaving = useRef(false), keys = useRef(new Map<string, string>());
  const heading = useRef<HTMLHeadingElement>(null), reasonInput = useRef<HTMLInputElement>(null);
  const uncertain = !!failure && failure.status >= 500;
  const canAssess = ['period.read', 'accounting.finance.read', 'ledger.read'].every(has);
  const dirty = selected.length > 0 && step === 1 || !!reason || busy || uncertain;
  useUnsavedChanges(useCallback(() => !leaving.current && (dirty || pending.current), [dirty]));
  useEffect(() => { heading.current?.focus(); }, [step]);
  useEffect(() => {
    if (!has('accounting.finance.read')) { setLoading(false); return; }
    const controller = new AbortController(); setLoading(true); setFailure(null);
    companyCall<Preview>('accounting', api + '/fiscal-years/next-preview' + (sourceYearId ? '?source_year_id=' + sourceYearId : ''), { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) {
        if (data.company_id !== companyId || sourceYearId && data.source_year?.id !== sourceYearId) throw new Error('Financial-year scope mismatch.');
        setPreview(data); setLoading(false);
      } }).catch(error => { if (!controller.signal.aborted) { setFailure(companyFailure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [api, companyId, sourceYearId, revision]); // permissions are resolved when the company page loads
  function key(body: unknown): string {
    const payload = JSON.stringify(body); let value = keys.current.get(payload);
    if (!value) { value = crypto.randomUUID(); keys.current.set(payload, value); } return value;
  }
  async function inspect(id: string, selectFirst = false): Promise<Readiness> {
    const [check, calendar, policy] = await Promise.all([
      companyCall<Readiness>('accounting', api + '/fiscal-years/' + id + '/readiness'),
      companyCall<components['schemas']['Page_FiscalPeriodListItem_']>('accounting', api + '/fiscal-periods?fiscal_year_id=' + id + '&limit=13'),
      companyCall<Fields>('accounting', api + '/finance/field-sets/fiscal-periods'),
    ]);
    if (check.fiscal_year_id !== id || !completeFiscalCalendar(companyId, id, preview?.start_date, preview?.end_date, calendar.items, calendar.page.has_more))
      throw { status: 409, message: 'The complete next-year calendar could not be verified. Review the year details.' };
    const rows = [...calendar.items].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
    setReadiness(check); setPeriods(rows); setFields(policy);
    if (selectFirst) setSelected(rows.find(row => row.status === 'FUTURE')?.id ? [rows.find(row => row.status === 'FUTURE')!.id] : []);
    return check;
  }
  async function generate() {
    if (pending.current || !preview || preview.blockers.length || !preview.existing_year_id && !preview.can_generate) return;
    pending.current = true; setBusy(true); setFailure(null); setMessage('Checking the next financial year…');
    try {
      let id = year ?? preview.existing_year_id;
      if (!id) {
        const body = { start_year: preview.start_year };
        const created = await companyCall<components['schemas']['FiscalYearDetail']>('accounting', api + '/fiscal-years/generate', { method: 'POST', body, key: key(body) });
        if (created.company_id !== companyId || created.start_date !== preview.start_date || created.end_date !== preview.end_date) throw new Error('The generated year does not match the reviewed calendar.');
        id = created.id;
      }
      setYear(id);
      if (canAssess) await inspect(id, true);
      setStep(1); setMessage('Financial year is available. Review its prerequisites and choose the periods to open.');
    } catch (error) { setFailure(companyFailure(error)); setMessage(''); }
    finally { pending.current = false; setBusy(false); }
  }
  async function refreshChecks() {
    if (!year || pending.current) return;
    pending.current = true; setBusy(true); setFailure(null);
    try { await inspect(year); setMessage('Prerequisites and period statuses refreshed.'); }
    catch (error) { setFailure(companyFailure(error)); }
    finally { pending.current = false; setBusy(false); }
  }
  const writable = ['status', 'reason', 'expected_version'].every(name => fields?.fields.some(field => field.key === name && field.readable && field.writable && field.visible));
  async function openPeriods() {
    if (pending.current || !year || !readiness || readiness.blockers.length || !writable || !has('period.manage')) return;
    if (!selected.length) {
      if (readiness.ready_for_posting) { setStep(2); setReason(''); }
      else { setReasonError('Select at least one future period to open.'); }
      return;
    }
    if (reason.trim().length < 3 || reason.trim().length > 500) { setReasonError('Give a reason using 3 to 500 characters.'); reasonInput.current?.focus(); return; }
    pending.current = true; setBusy(true); setFailure(null); setReasonError('');
    try {
      let completed = 0;
      for (const id of selected) {
        const period = periods.find(row => row.id === id);
        if (!period || period.status !== 'FUTURE' || !period.row_version) continue;
        const body = { status: 'OPEN', reason: reason.trim(), expected_version: period.row_version };
        setMessage(`Opening ${period.code}: ${completed + 1} of ${selected.length}…`);
        const changed = await companyCall<components['schemas']['FiscalPeriodDetail']>('accounting', api + '/fiscal-periods/' + id + '/transition', { method: 'POST', body, key: key({ id, ...body }) });
        if (changed.id !== id || changed.company_id !== companyId || changed.fiscal_year_id !== year || changed.status !== 'OPEN') throw new Error('The period result does not match this financial year.');
        completed += 1;
        setPeriods(rows => rows.map(row => row.id === id ? changed : row));
      }
      const check = await inspect(year);
      if (!check.ready_for_posting) throw { status: 409, message: 'Year prerequisites changed. Refresh the checks before proceeding.' };
      setSelected([]); setReason(''); setStep(2); setMessage('Selected periods are open. Choose Use this year to switch your working context.');
    } catch (error) { setFailure(companyFailure(error)); setMessage('Completed period changes are preserved. Retry the unconfirmed operation or refresh confirmed statuses.'); }
    finally { pending.current = false; setBusy(false); }
  }
  async function useYear() {
    if (!year || pending.current) return;
    pending.current = true; leaving.current = true; setBusy(true); setFailure(null);
    const error = await openCompany(companyId, year);
    if (error) { leaving.current = false; pending.current = false; setBusy(false); setFailure(error); }
  }
  const details = year ? administrationLink(base + '/' + year, back) : base;
  return <div className="janso-page" onClickCapture={event => {
    const link = (event.target as HTMLElement).closest('a[href]');
    if (link instanceof HTMLAnchorElement && dirty && !leaving.current) { event.preventDefault(); event.stopPropagation(); if (!busy) setDiscard(link.href); }
  }}>
    <PageNavigation back={{ href: back, label: administrationBackLabel(back) }} breadcrumbs={[{ label: 'Companies', href: '/companies' }, { label: 'Financial years', href: base }, { label: 'Start next year' }]}
      onNavigate={event => { if (dirty) { event.preventDefault(); if (!busy) setDiscard(event.currentTarget.href); } }} />
    <PageHeader title="Start next financial year" lede={'Company: ' + companyName} />
    <Stepper steps={['Review next year', 'Check and open periods', 'Ready to use']} current={step} />
    {message && <Notice tone={step === 2 ? 'success' : 'info'}><span role="status">{message}</span></Notice>}
    {failure && <Notice tone="danger">{failure.message}{failure.code === 'step_up_required' && <a className="janso-link" href={stepUpUrl(companyId)}>Verify sign-in</a>}</Notice>}
    {uncertain && <Notice tone="warning">The last result is unconfirmed. Retry the same operation to recover it; the request identity is retained.</Notice>}
    {loading ? <div role="status" aria-label="Checking next financial year"><Skeleton /></div> : !has('accounting.finance.read') ? <Notice>Calendar preview needs accounting books read access. Ask your accounting administrator, or use the existing year generator with your permitted access. <a className="janso-link" href={base + '/new'}>Generate a year</a></Notice>
      : !preview ? <Card><CardBody><p>Check the company books before continuing.</p><a className="janso-link" href={base + '/new'}>Review books and year setup</a><Button variant="ghost" onClick={() => setRevision(value => value + 1)}>Retry preview</Button></CardBody></Card>
      : <Card><CardHeader title={preview.code} subtitle="A new year continues the existing company books." /><CardBody>
        <h2 tabIndex={-1} ref={heading}>{['Review the calendar', 'Check prerequisites and opening periods', 'Your next year is ready'][step]}</h2>
        <ReviewList items={[{ label: 'Source year', value: preview.source_year?.code ?? 'Initial company year' }, { label: 'Starts', value: format.date(preview.start_date) }, { label: 'Ends', value: format.date(preview.end_date) }]} />
        {step === 0 && <>
          <Notice>The previous year can remain open. Generating this year creates twelve future periods. Your selected year changes only when you choose Use this year.</Notice>
          {preview.existing_year_id && <Notice tone="success">This next year already exists. Continue to review its current periods.</Notice>}
          {preview.blockers.map(code => <Notice key={code} tone="warning">{fiscalBlockerText[code] ?? code.replaceAll('_', ' ')}</Notice>)}
          <FormActions><Button loading={busy} loadingLabel="Preparing year…" disabled={!!preview.blockers.length || !preview.existing_year_id && !preview.can_generate} onClick={() => void generate()}>{uncertain ? 'Retry year preparation' : preview.existing_year_id ? 'Review existing year' : 'Generate and check year'}</Button></FormActions>
        </>}
        {step === 1 && <>
          {!canAssess ? <Notice tone="warning">The year is available. Posting prerequisite checks need period.read, accounting.finance.read and ledger.read. Ask an authorised accountant to check and open its periods. <a className="janso-link" href={details}>View year and manage periods</a></Notice>
            : <>
              <Button variant="ghost" disabled={busy || uncertain} onClick={() => void refreshChecks()}>Refresh checks</Button>
              {readiness?.blockers.map(code => <Notice key={code} tone="warning">{fiscalBlockerText[code] ?? code.replaceAll('_', ' ')}</Notice>)}
              <Notice>Balances continue from retained posted history. Confirm account mappings, document numbering and applicable tax settings before entering transactions.</Notice>
              <form onSubmit={event => { event.preventDefault(); void openPeriods(); }} noValidate>
                <FieldGrid disabled={busy || uncertain}>
                  <div className="janso-form-grid janso-form-grid--pair">
                  {periods.map(period => <div key={period.id} className="janso-flow">
                    {period.status === 'FUTURE' ? <Checkbox checked={selected.includes(period.id)} disabled={!writable || !!readiness?.blockers.length} onChange={event => setSelected(values => event.target.checked ? [...values, period.id] : values.filter(id => id !== period.id))}
                      hint={format.date(period.start_date) + ' to ' + format.date(period.end_date)}>Open {period.code}</Checkbox>
                      : <p>{period.code} <Badge tone={period.status === 'OPEN' ? 'success' : 'neutral'}>{period.status?.replaceAll('_', ' ')}</Badge></p>}
                  </div>)}
                  </div>
                  <TextField ref={reasonInput} label="Reason for opening periods" value={reason} maxLength={500} disabled={!writable} required={selected.length > 0} error={reasonError || failure?.fields?.reason} onChange={event => { setReason(event.target.value); setReasonError(''); }} />
                </FieldGrid>
                {!writable && <Notice>Your field policy does not allow period opening through this form.</Notice>}
                <FormActions><a className="janso-link" href={details}>View year details</a><Button type="submit" loading={busy} loadingLabel="Opening periods…" disabled={!readiness || !!readiness.blockers.length || !writable || !has('period.manage')}>{uncertain ? 'Retry period opening' : selected.length ? `Open ${selected.length} selected period${selected.length === 1 ? '' : 's'}` : 'Continue with open periods'}</Button></FormActions>
              </form>
            </>}
        </>}
        {step === 2 && <>
          <Notice tone="success">The checked year has an open posting period. Each transaction will still validate its own posting date and configuration.</Notice>
          <FormActions><a className="janso-link" href={details}>View year</a>{has('report.read') && <a className="janso-link" href={administrationLink(base + '/' + year + '/continuity', back)}>Review opening balances</a>}<Button loading={busy} loadingLabel="Switching year…" onClick={() => void useYear()}>Use this year</Button></FormActions>
        </>}
      </CardBody></Card>}
    <ConfirmDialog open={discard !== null} title="Leave financial-year setup?" confirmLabel="Leave setup" onCancel={() => setDiscard(null)} onConfirm={() => { leaving.current = true; if (discard) goTo(discard); }}>
      Unsaved period choices and reasons will be discarded. Any year or periods already created remain available from Financial years.
    </ConfirmDialog>
  </div>;
}
