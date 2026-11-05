'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Button, Card, CardBody, Checkbox, ConfirmDialog, DataTable, Disclosure, Notice, PageHeader, PageNavigation, ReviewList, SearchSelect, SectionHeader, Select, Skeleton, Stepper, Tabs, tabButtonId, TextField, Toggle, useFormatters, type Column } from '@janso/ui';
import { base, blockerLabel, declarationError, initialDeclaration, metadataRequest, newEntry, owned, request, sum, verifyWorkspace, type Access, type Declaration, type Entry, type Metadata, type Preview, type Readiness, type Reconciliation, type Workspace } from '../lib/financial-opening';
import { useServiceCommand, useServiceRead } from '../lib/service-resource';
import { lookup } from '../lib/voucher-fields';
import { useAccessDraft } from './AccessCommon';
import { AccountingFailure } from './AccountingConfigurationCommon';
import { FinancialOpeningEntry } from './FinancialOpeningEntry';
import { FinancialOpeningImports } from './FinancialOpeningImports';
import { FinancialOpeningHeldBalances } from './FinancialOpeningHeldBalances';
import { FinancialOpeningMasterBalances } from './FinancialOpeningMasterBalances';
import { FinancialOpeningHistory } from './FinancialOpeningHistory';
import { FinancialOpeningPosting } from './FinancialOpeningPosting';
import { FinancialOpeningAccounts, FinancialOpeningSelection } from './FinancialOpeningAccounts';
import { FinancialOpeningAutomatic } from './FinancialOpeningAutomatic';
import { FinancialOpeningDefaults } from './FinancialOpeningDefaults';
import { automaticSource, editedOpeningError, needsClearing, OFFSET_SOURCE, withOpeningOffset, type OpeningCategory } from '../lib/financial-opening-worksheet';
import { openingDefaultsRequest, verifyOpeningDefault, type OpeningDefaults, type OpeningDefaultAccount } from '../lib/financial-opening-defaults';
import { accountingRequest, assertAccountingRecord } from '../lib/accounting-configuration';
import type { AccountingRecord } from '../lib/accounting-configuration-resources';
import { FinancialOpeningAccount, FinancialOpeningMoney, FinancialOpeningFieldErrors } from './FinancialOpeningCommon';
import type { components } from '@janso/api-client/accounting';

type Tab = 'worksheet' | 'imports' | 'completion' | 'history';
type Action = 'save' | 'automatic' | 'resume-automatic' | 'prepare-drafts' | 'finalize' | 'void';
export function FinancialOpeningWorkspace({ company, access, initialAccountId, initialPartyId, initialBatchId }: {
  company: string; access: Access; initialAccountId?: string; initialPartyId?: string; initialBatchId?: string;
}) {
  const format = useFormatters();
  const root = base(company);
  const ready = useServiceRead<Readiness>(root + '/readiness', request, owned(company));
  const metadata = useServiceRead<Metadata>(root + '/workspaces/field-set', metadataRequest);
  const defaults = useServiceRead<OpeningDefaults>(`/v1/companies/${company}`, openingDefaultsRequest);
  const [selected, setSelected] = useState<string | null>(initialBatchId ?? null), [tab, setTab] = useState<Tab>('worksheet'), [step, setStep] = useState(0),
    [draft, setDraft] = useState<Declaration | null>(null), [entry, setEntry] = useState<{ index: number | null; value: Entry } | null>(null),
    [preview, setPreview] = useState<Preview | null>(null), [previewing, setPreviewing] = useState(false), [previewError, setPreviewError] = useState(''),
    [error, setError] = useState(''), [message, setMessage] = useState(''), [confirm, setConfirm] = useState<Action | null>(null),
    [reason, setReason] = useState(''), [page, setPage] = useState(0), [childDirty, setChildDirty] = useState(false);
  const [creating, setCreating] = useState(false);
  const [category, setCategory] = useState<OpeningCategory>('BUYER'), [group, setGroup] = useState<string | null>(null);
  const [automatic, setAutomatic] = useState(true), [reviewed, setReviewed] = useState(false);
  const [offset, setOffset] = useState<string | null | undefined>(undefined);
  const [autoWorkspace, setAutoWorkspace] = useState<Workspace | null>(null);
  const panel = useRef<HTMLElement>(null), previousStep = useRef(step);
  useEffect(() => {
    if (previousStep.current !== step && tab === 'worksheet') {
      const heading = panel.current?.querySelector<HTMLElement>('h2');
      if (heading) { heading.tabIndex = -1; heading.focus(); }
    }
    previousStep.current = step;
  }, [step, tab]);
  const automaticRequested = useRef(false);
  const automaticReason = useRef('');
  const [masterDirty,setMasterDirty]=useState(false);
  const baseline = useRef<{ id: string | null; version?: number; hash?: string } | undefined>(undefined);
  const id = creating ? undefined : selected ?? ready.data?.batch_id;
  const path = id ? root + '/workspaces/' + id : undefined;
  const control = useServiceRead<Workspace>(path, request, value => {
    verifyWorkspace(company)(value);
    if (value.id !== id) throw { status: 502, message: 'The selected opening workspace could not be verified.' };
  });
  const isLegacy = control.failure?.status === 409 && control.failure.message === 'use the legacy opening workflow for this batch';
  const legacy = useServiceRead<components['schemas']['OpeningBatchDetail']>(isLegacy && id ? root + '/' + id : undefined, request, owned(company));
  // Read the immutable revision named by the versioned header. Separate mutable
  // reads can otherwise combine an old declaration with a newer edit baseline.
  const savedPath = path && ready.data && control.data && control.data.id === id
    ? path + '/revisions/' + control.data.revision_id : undefined;
  const saved = useServiceRead<Declaration>(savedPath, request, value => {
    if (value.posting_date !== ready.data?.books_begin_date || !Array.isArray(value.entries)) throw { status: 502, message: 'The saved opening worksheet could not be verified.' };
  });
  const reconcile = useServiceRead<Reconciliation>(path && tab === 'completion' && !autoWorkspace ? path + '/reconciliation' : undefined, request, value => {
    if (value.batch_id !== id || !Array.isArray(value.blockers)) throw { status: 502, message: 'Opening reconciliation could not be verified.' };
  });
  const seed = useMemo(() => ready.data ? initialDeclaration(ready.data) : null, [ready.data]);
  const value = draft ?? saved.data ?? seed;
  const command = useServiceCommand(request, 'account and party opening');
  const setupCommand = useServiceCommand(accountingRequest, 'opening account setup');
  const frozen = useRef<Parameters<typeof command.execute>[0] | null>(null), previewGeneration = useRef(0), busy = useRef(false);
  const locked = command.pending || command.uncertain || setupCommand.pending || setupCommand.uncertain || previewing || childDirty || masterDirty || !!autoWorkspace;
  const guard = useAccessDraft(!!draft || !!entry || childDirty || masterDirty || command.uncertain || setupCommand.uncertain || !!autoWorkspace, command.pending || setupCommand.pending || previewing || !!autoWorkspace);
  const protectedRead = [ready.failure, metadata.failure, control.failure, saved.failure].some(failure => failure?.status === 403);
  const windowBlocked = !ready.data || !!ready.failure || ready.loading || access.period === false || ready.data.blockers.some(code => ['ACCOUNTING_NOT_INITIALIZED', 'FINANCIAL_SETUP_NOT_INITIALIZED', 'BOOKS_BEGIN_PERIOD_NOT_OPEN', 'LATER_BOOKS_CLOSED', 'LEGACY_ACTIVITY_REQUIRES_REVIEW'].includes(code));
  const editable = !windowBlocked && access.manage && !!metadata.data && !!value && (!id || !!control.data && !!saved.data) && !protectedRead && !locked && !control.loading && !saved.loading && !control.failure && !saved.failure &&
    (!id ? ready.data?.can_prepare : control.data?.status === 'DRAFT' && !control.data.posted_journals);
  function refresh() { ready.refresh(); control.refresh(); saved.refresh(); reconcile.refresh(); defaults.refresh(); }
  function pinBaseline() {
    if (!baseline.current) baseline.current = { id: id ?? null, version: control.data?.expected_version, hash: control.data?.manifest_hash };
  }
  function beginEntry(index: number | null, value: Entry) { pinBaseline(); setEntry({ index, value }); }
  function patch(change: Partial<Declaration>) {
    if (!value || !editable) return;
    pinBaseline(); setDraft({ ...value, ...change }); setPreview(null); setReviewed(false); setError(''); setPreviewError(''); previewGeneration.current++;
  }
  async function run(payload: Parameters<typeof command.execute>[0]) {
    frozen.current = payload;
    const result = await command.execute<Workspace>(payload, receipt => {
      verifyWorkspace(company)(receipt);
      if (automaticRequested.current && (payload.path.endsWith('/workspaces') || payload.path.endsWith('/replace')) &&
          (!preview || receipt.manifest_hash !== preview.manifest_hash || receipt.posting_date !== preview.posting_date ||
           receipt.entry_count !== preview.entry_count || receipt.document_count !== preview.document_count || (id && receipt.id !== id)))
        throw { status: 502, message: 'The saved opening does not match the reviewed preview. Retry the same request before posting.' };
    });
    if (result) {
      setCreating(false); baseline.current = undefined; setSelected(result.id); setDraft(null); setEntry(null); setPreview(null); setConfirm(null); setReason(''); command.clear();
      setMessage(result.status === 'FINALIZED' ? 'Opening finalized. The company can use its posted starting balances.' : result.status === 'VOID' || result.status === 'REVERSED' ? 'The unposted opening plan is closed. Financial evidence is retained.' : payload.path.endsWith('/prepare-drafts') ? 'Native opening drafts prepared. Review and post them in Posting and completion.' : 'Opening worksheet saved. No balances have been posted.');
      refresh();
      if (automaticRequested.current && (payload.path.endsWith('/workspaces') || payload.path.endsWith('/replace'))) { automaticRequested.current = false; setMessage(''); setAutoWorkspace(result); setTab('completion'); }
      if (payload.path.endsWith('/prepare-drafts') || payload.path.endsWith('/finalize')) setTab('completion');
    }
  }
  async function apply() {
    if (command.uncertain && frozen.current) { await run(frozen.current); return; }
    if (!confirm || !value || !access.manage || command.pending) return;
    if (confirm === 'resume-automatic') {
      if (!access.post || windowBlocked || locked || draft || !saved.data || control.data?.status !== 'DRAFT') return;
      automaticReason.current = saved.data.reason;
      setConfirm(null); setAutoWorkspace(control.data); setTab('completion');
    } else if (confirm === 'save' || confirm === 'automatic') {
      if (!preview || windowBlocked || draft && declarationError(draft)) return;
      if (confirm === 'automatic' && (!access.post || !reviewed)) return;
      if (confirm === 'automatic') automaticReason.current = value.reason;
      const original = baseline.current;
      if (draft && original && (original.id !== (id ?? null) || original.version !== control.data?.expected_version || original.hash !== control.data?.manifest_hash)) {
        setError('The worksheet changed while you were editing. Discard local changes, reload and review the current declaration before saving.'); setConfirm(null); return;
      }
      const body = id && control.data ? { expected_version: control.data.expected_version, manifest_hash: control.data.manifest_hash, reason: value.reason, declaration: value } : value;
      if (confirm === 'automatic' && id && !draft && control.data) {
        if (control.data.manifest_hash !== preview.manifest_hash) { setError('The saved opening changed. Refresh and review it again before posting.'); setConfirm(null); return; }
        setConfirm(null); setAutoWorkspace(control.data); setTab('completion'); return;
      }
      automaticRequested.current = confirm === 'automatic';
      await run({ path: id ? path + '/replace' : root + '/workspaces', method: 'POST', body });
    } else if (path && control.data) {
      if (reason.trim().length < 3) { setError('Explain this action using at least three characters.'); return; }
      await run({ path: path + '/' + confirm, method: 'POST', body: { expected_version: control.data.expected_version, manifest_hash: control.data.manifest_hash, reason } });
    }
  }
  function reviewAction(action: Exclude<Action, 'save' | 'automatic' | 'resume-automatic'>) {
    automaticRequested.current = false;
    if (reason.trim().length < 3) { setError('Explain this action using at least three characters.'); document.getElementById('financial-opening-action-reason')?.focus(); return; }
    setError(''); setConfirm(action);
  }
  async function review() {
    if (!value || !access.manage || windowBlocked || busy.current || locked && !setupCommand.uncertain) return;
    busy.current = true; setPreviewing(true); setPreviewError(''); setError('');
    try {
      let reviewedValue = value;
      // Bootstrap only from this explicit review action. A timeout is replayed before
      // reading defaults, so the same initialization cannot acquire a second key.
      const initializeAccounts = () => setupCommand.execute<AccountingRecord>({ path: `/v1/companies/${company}/accounting-setup/initialize`, method: 'POST', body: {} }, result => { assertAccountingRecord(result, company); });
      if (setupCommand.uncertain && !await initializeAccounts()) return;
      if (automatic) {
        reviewedValue = withOpeningOffset(automaticSource(value), offsetId);
        const unbalanced = sum(reviewedValue.entries.filter(row => row.side === 'DEBIT').map(row => row.base_amount!)) !== sum(reviewedValue.entries.filter(row => row.side === 'CREDIT').map(row => row.base_amount!));
        if (unbalanced || needsClearing(reviewedValue) && !reviewedValue.clearing_account_id) {
          let configured = await openingDefaultsRequest<OpeningDefaults>({ path: `/v1/companies/${company}` });
          if ((unbalanced && !offsetId && !configured.offset) || (needsClearing(reviewedValue) && !reviewedValue.clearing_account_id && !configured.clearing)) {
            if (!await initializeAccounts()) return;
            configured = await openingDefaultsRequest<OpeningDefaults>({ path: `/v1/companies/${company}` });
          }
          reviewedValue = withOpeningOffset(reviewedValue, offsetId ?? configured.offset?.id ?? null);
          if (needsClearing(reviewedValue) && !reviewedValue.clearing_account_id) {
            if (!configured.clearing) throw new Error('The migration clearing account is unavailable. Retry setup or select an eligible account in manual mode on this page.');
            reviewedValue = { ...reviewedValue, clearing_account_id: configured.clearing.id };
          }
          defaults.refresh();
        }
        if (JSON.stringify(reviewedValue) !== JSON.stringify(value)) {
          pinBaseline(); setDraft(reviewedValue); setPreview(null); setReviewed(false);
        }
      }
      const problem = declarationError(reviewedValue); if (problem) { setError(problem); return; }
      const generation = ++previewGeneration.current;
      const offsetEntry = reviewedValue.entries.find(row => row.source_key === OFFSET_SOURCE);
      if (offsetEntry) {
        const account = await accountingRequest<OpeningDefaultAccount>({ path: `/v1/companies/${company}/accounts/${offsetEntry.account_id}` });
        if (account.id !== offsetEntry.account_id) throw new Error('The opening offset account could not be verified.');
        await verifyOpeningDefault(`/v1/companies/${company}`, account, 'offset');
      }
      const result = await request<Preview>({ path: root + '/workspaces/preview', method: 'POST', body: reviewedValue });
      owned(company)(result);
      if (!/^[a-f0-9]{64}$/.test(result.manifest_hash) || result.entry_count !== reviewedValue.entries.length || result.posting_date !== reviewedValue.posting_date) throw new Error('Invalid preview');
      if (generation === previewGeneration.current) setPreview(result);
    } catch (failure) { setPreview(null); setPreviewError(failure && typeof failure === 'object' && 'message' in failure ? String(failure.message) : 'Preview could not be verified. Reload and review before saving.'); }
    finally { busy.current = false; setPreviewing(false); }
  }
  const offsetId = offset === undefined ? value?.entries.find(row => row.source_key === OFFSET_SOURCE)?.account_id ?? defaults.data?.offset?.id ?? null : offset;
  function changeStep(next: number) {
    if (locked || entry || !value || !metadata.data) return;
    if (next > 0 && category === 'OTHER' && !group) { setError('Select one account group before continuing.'); setStep(0); return; }
    if (next === 2) {
      const problem = editedOpeningError(value, metadata.data);
      if (problem) { setError(problem); setStep(1); return; }
      if (editable) {
        try {
          const prepared = automatic ? automaticSource(value) : value;
          const balanced = withOpeningOffset(prepared, offsetId);
          const nextValue = !balanced.clearing_account_id && needsClearing(balanced) && defaults.data?.clearing
            ? { ...balanced, clearing_account_id: defaults.data.clearing.id } : balanced;
          if (JSON.stringify(nextValue) !== JSON.stringify(value)) patch(nextValue);
        } catch (failure) { setError((failure as Error).message); setStep(1); return; }
      }
    }
    setError(''); setStep(next);
  }
  function changeTab(next: Tab) {
    if (locked || entry || draft) { setError('Save or discard your worksheet changes before changing sections.'); return; }
    setTab(next); setError(''); setMessage('');
  }
  function finishAutomatic(completed: boolean) {
    setAutoWorkspace(null); setChildDirty(false); setTab('completion'); setReason(automaticReason.current);
    setMessage(completed ? 'Opening posted, reconciled and finalized. Your starting balances are ready; no further financial opening action is required.' : 'Automatic completion paused. Confirmed progress is retained. Continue automatic completion from this page when ready.');
    refresh();
  }
  const rows = protectedRead ? [] : (value?.entries ?? []);
  const pageRows = rows.slice(page * 25, (page + 1) * 25);
  const field = (key: string) => !!metadata.data?.capture.properties?.[key];
  const total = (side: string) => { try { return sum(rows.filter(row => row.side === side).map(row => row.base_amount ?? '')); } catch { return 'Incomplete'; } };
  const columns: Column<Entry>[] = [
    { type: 'custom', key: 'account', header: 'Ledger / source', render: row => <><FinancialOpeningAccount company={company} id={row.account_id} onLeave={guard.leave} /><div className="janso-caption">{row.source_key}</div></> },
    { type: 'custom', key: 'side', header: 'Side', render: row => row.side === 'DEBIT' ? 'Debit' : 'Credit' },
    { type: 'custom', key: 'amount', header: 'Opening amount', render: row => <FinancialOpeningMoney value={row.amount} currency={row.currency} /> },
    { type: 'custom', key: 'base', header: `Base value (${value?.currency ?? ''})`, render: row => row.base_amount ? <FinancialOpeningMoney value={row.base_amount} /> : 'Incomplete' },
    { type: 'custom', key: 'documents', header: 'Documents', render: row => String(row.documents?.length ?? 0) },
    { type: 'custom', key: 'actions', header: 'Actions', render: row => <div className="janso-form-actions"><Button variant="ghost" disabled={!editable || !!entry} onClick={() => beginEntry(rows.indexOf(row), row)}>Edit {row.source_key}</Button><Button variant="ghost" disabled={!editable || !!entry} onClick={() => { patch({ entries: rows.filter(item => item !== row) }); setPage(0); }}>Remove {row.source_key}</Button></div> },
  ];
  return <div className="janso-page janso-opening-page">
    <PageNavigation back={{ href: initialPartyId ? '/accounting/parties/' + initialPartyId : initialAccountId ? '/accounting/accounts/' + initialAccountId : '/masters', label: initialPartyId ? 'Party' : initialAccountId ? 'Account' : 'Masters' }} breadcrumbs={[{ label: 'Masters', href: '/masters' }, { label: 'Account and party openings' }]} onNavigate={guard.leave} />
    <PageHeader title="Account and party openings" lede="Choose accounts, enter openings, then review and post." actions={<Button variant="ghost" disabled={locked || !!draft || !!entry} onClick={refresh}>Refresh status</Button>} />
    <Tabs label="Opening sections" panelId="financial-opening-panel" tabs={[{ id: 'worksheet', label: 'Balances and bills' }, { id: 'imports', label: 'Import' }, { id: 'completion', label: 'Posting and completion' }, { id: 'history', label: 'History' }]} active={tab} onChange={value => changeTab(value as Tab)} />
    {message && <Notice tone="success"><span role="status">{message}</span></Notice>}
    {error && <Notice tone="danger">{error}</Notice>}
    {[ready, metadata, ...(isLegacy ? [legacy] : [control, saved])].map((read, i) => <AccountingFailure key={i} failure={read.failure} retry={read.refresh} />)}
    {isLegacy && legacy.data && <Notice>This opening was recorded through the earlier company setup flow. It is retained with status {legacy.data.status ?? 'restricted'} at {legacy.data.posting_date ? format.date(legacy.data.posting_date) : 'the original cutover'}. <a className="janso-link" href="/settings/readiness" onClick={guard.leave}>Review company readiness</a>. Its posted facts cannot be overwritten by a new worksheet.</Notice>}
    <AccountingFailure failure={command.failure} retry={refresh} write />
    <FinancialOpeningFieldErrors failure={command.failure} />
    <AccountingFailure failure={setupCommand.failure} write />
    {setupCommand.uncertain && <Notice tone="warning">Opening account setup is unconfirmed. The same request will be retried before preview.<Button disabled={setupCommand.pending || previewing} onClick={() => void review()}>Retry opening account setup</Button></Notice>}
    {command.uncertain && <Notice tone="warning">The outcome is unconfirmed. Your exact request is retained.<Button disabled={command.pending} onClick={() => frozen.current && void run(frozen.current)}>Retry the same request</Button></Notice>}
    {autoWorkspace && <FinancialOpeningAutomatic company={company} initial={autoWorkspace} access={access} reason={automaticReason.current} onDirty={setChildDirty} onDone={finishAutomatic} />}
    {ready.loading || metadata.loading ? <Skeleton width="100%" lines={5} /> : !protectedRead && ready.data && metadata.data && <>
      <div className="janso-opening-context" aria-label="Company opening context"><span>Books begin <strong>{format.date(ready.data.books_begin_date)}</strong></span><span>Currency <strong>{ready.data.currency}</strong></span><span>Status <strong>{(control.data?.status ?? ready.data.status).replaceAll('_', ' ').toLowerCase()}</strong></span><span>Posted journals <strong>{control.data?.posted_journals ?? 0}</strong></span></div>
        {ready.data.blockers.length > 0 && <Notice>{ready.data.blockers.map(code => <p key={code}>{blockerLabel(code)}</p>)}</Notice>}
        {!access.manage && <Notice>You have read access. A user with finance management access must save, prepare and finalize the opening.</Notice>}
      <section ref={panel} id="financial-opening-panel" role="tabpanel" aria-labelledby={tabButtonId(tab)} tabIndex={0} className="janso-flow">
      {tab === 'worksheet' && value && (!id || !!control.data && !!saved.data) && !control.loading && !saved.loading && !control.failure && !saved.failure && <div className="janso-flow">
        {(initialAccountId || initialPartyId) && <Notice>This is the balanced opening for the whole company. {initialPartyId ? <a className="janso-link" href={`/accounting/accounts?party_id=${initialPartyId}`} onClick={guard.leave}>Find this party’s customer or supplier ledger</a> : 'The selected account can be added below; its opposite entry must also be recorded.'}</Notice>}
        <Stepper orientation="horizontal" allowFuture steps={['Choose accounts', 'Enter openings', 'Review and post']} current={step} reached={step} onStep={locked || entry ? undefined : changeStep} />
        {step === 0 && <FinancialOpeningSelection company={company} category={category} group={group} disabled={locked} onCategory={setCategory} onGroup={setGroup} />}
        {!id && !value.entries.length && step === 0 && <p className="janso-caption">Starting with no balances? <a className="janso-link" href="/settings/readiness" onClick={guard.leave}>Confirm a zero opening in company readiness</a>.</p>}
        {step === 2 && <Card><CardBody><div className="janso-opening-mode"><div><strong>Prepare and post automatically</strong><p className="janso-caption">{automatic ? 'Review the balances once. This action prepares, posts, reconciles and finalizes the opening here.' : 'Edit the source details, then save and post using the individual controls.'}</p></div><Toggle label="Prepare and post automatically" checked={automatic} disabled={!editable} onChange={enabled => { setAutomatic(enabled); setReviewed(false); if (enabled) patch(automaticSource(value)); }} /></div></CardBody></Card>}
        {step === 2 && <Card><CardBody><div className="janso-flow"><SectionHeader title="Opening source and settings" description={automatic ? "Source details are filled for you. Choose how historical activity appears in reports." : "Set the source details for this opening."} />
          <div className="janso-form-grid">
            {field('coverage_mode') && <Select label="Historical reporting" value={value.coverage_mode ?? 'POST_CUTOVER_ONLY'} disabled={!editable} options={[{ value: 'POST_CUTOVER_ONLY', label: 'Report from cutover only' }, { value: 'YTD_SUMMARY', label: 'Import an explicit year-to-date summary' }]} onChange={mode => patch({ coverage_mode: mode as Declaration['coverage_mode'], ytd_summary: mode === 'YTD_SUMMARY' ? [] : null })} />}
            {value.coverage_mode === 'YTD_SUMMARY' && field('originating_year_start') && <TextField label="Originating financial year start" type="date" value={value.originating_year_start ?? ''} disabled={!editable} onChange={event => patch({ originating_year_start: event.target.value })} />}
          </div>
          <p className="janso-caption">{value.coverage_mode === 'YTD_SUMMARY' ? 'The imported summary supports full-year totals. Historical monthly transactions remain unavailable.' : 'Reports start from your books-begin date. Earlier transaction history is not included.'}</p>
          <Disclosure key={automatic ? 'automatic-source' : 'manual-source'} summary={automatic ? 'View automatically filled source details' : 'Edit source details'} defaultOpen={!automatic}>
          <div className="janso-form-grid">
            {field('posting_date') && <TextField label="Opening date" type="date" value={value.posting_date} readOnly />}
            {field('covered_through') && <TextField label="Source covered through" type="date" max={value.posting_date} value={value.covered_through} disabled={!editable} readOnly={automatic} onChange={event => patch({ covered_through: event.target.value })} />}
            {field('source_system') && <TextField label="Source system" value={value.source_system} maxLength={60} disabled={!editable} readOnly={automatic} hint={automatic ? undefined : 'For example, manual, tally or quickbooks.'} onChange={event => patch({ source_system: event.target.value })} />}
            {field('source_id') && <TextField label="Migration reference" value={value.source_id} maxLength={100} disabled={!editable} readOnly={automatic} onChange={event => patch({ source_id: event.target.value })} />}
            {field('reason') && <TextField label="Opening source and reason" value={value.reason} maxLength={500} required disabled={!editable} readOnly={automatic} onChange={event => patch({ reason: event.target.value })} />}
            {field('clearing_account_id') && (automatic ? <TextField label="Migration clearing account" value={value.clearing_account_id ? defaults.data?.clearing?.id === value.clearing_account_id ? defaults.data.clearing.name ?? "Configured migration clearing" : "Configured migration clearing" : needsClearing(value) ? "Not configured" : "Not required for this opening"} readOnly /> : <SearchSelect label="Migration clearing account" hint="For large openings only. Must be separately configured, unused in the declaration, and reconcile to zero." loadOptions={lookup(company, 'accounts')} scopeKey={company + ':clearing'} value={value.clearing_account_id ?? null} disabled={!editable} onChange={id => patch({ clearing_account_id: id })} />)}
            <FinancialOpeningDefaults company={company} automatic={automatic} offset={offsetId} disabled={!editable} onBusy={setChildDirty} onOffset={id => { try { const next = withOpeningOffset(value, id); setOffset(id); patch(next); } catch (failure) { setError((failure as Error).message); } }} />
          </div>
          </Disclosure>
          {automatic && (defaults.failure || !offsetId || needsClearing(value) && !value.clearing_account_id) && <Notice>Validate and preview loads the opening accounts and adds missing company starter defaults when needed. You can also select eligible accounts here in manual mode. A balanced opening does not need an offset.</Notice>}
          <div className="janso-opening-reviews">
          {field('same_day_reviewed') && <Checkbox checked={value.same_day_reviewed ?? false} disabled={!editable} onChange={event => patch({ same_day_reviewed: event.target.checked })}>I reviewed same-day source overlap</Checkbox>}
          {field('credit_cash_reviewed') && <Checkbox checked={value.credit_cash_reviewed ?? false} disabled={!editable} onChange={event => patch({ credit_cash_reviewed: event.target.checked, ...(automatic && event.target.checked ? { credit_cash_reason: value.credit_cash_reason || 'User reviewed the credit cash opening in this worksheet.' } : {}) })}>I reviewed a credit cash opening</Checkbox>}
          </div>
          {value.credit_cash_reviewed && <TextField label="Credit cash explanation" readOnly={automatic} value={value.credit_cash_reason ?? ''} maxLength={500} disabled={!editable} onChange={event => patch({ credit_cash_reason: event.target.value })} />}
        </div></CardBody></Card>}
        {step === 1 && <>
          <FinancialOpeningAccounts company={company} category={category} group={group} value={value} metadata={metadata.data} disabled={!editable || !!entry} onChange={entries => patch({ entries })} onDetails={(account, row) => beginEntry(row ? rows.indexOf(row) : null, row ?? { ...newEntry(account.currency_mode === 'FIXED' ? account.currency ?? value.currency : value.currency, account.id), side: account.party_role === 'SUPPLIER' ? 'CREDIT' : 'DEBIT' })} />
          <Disclosure summary={`Entered lines and bill details · ${rows.length} lines`}>
          <FinancialOpeningHeldBalances company={company} rows={rows} access={access} editable={!!editable} onAdd={added => { patch({ entries: [...rows, ...added] }); setPage(0); }} onDirty={setChildDirty} onLeave={guard.leave} />
          <FinancialOpeningMasterBalances company={company} rows={rows} date={value.posting_date} access={access} editable={!!editable} onAdd={added=>{patch({entries:[...rows,...added]});setPage(0);}} onDirty={setMasterDirty} onLeave={guard.leave}/>
          <Card><CardBody><div className="janso-flow"><SectionHeader title="Ledger balances and outstanding bills" description="Enter debit and credit balances separately. Party documents must equal their ledger line, including the historical base value." />
            <ReviewList items={[{ label: 'Debit base total', value: total('DEBIT') }, { label: 'Credit base total', value: total('CREDIT') }, { label: 'Account lines', value: String(rows.length) }]} />
            <DataTable caption="Opening account balances" columns={columns} rows={pageRows} rowId={row => row.source_key} rowLabel={row => row.description ?? row.source_key} emptyTitle="No opening account lines" emptyBody="Add ledger balances or use Import to prepare a reviewed migration file." />
            <div className="janso-form-actions"><Button variant="ghost" disabled={page === 0 || locked || !!entry} onClick={() => setPage(n => n - 1)}>Previous lines</Button><span className="janso-caption">Page {page + 1} of {Math.max(1, Math.ceil(rows.length / 25))}</span><Button variant="ghost" disabled={(page + 1) * 25 >= rows.length || locked || !!entry} onClick={() => setPage(n => n + 1)}>Next lines</Button><Button disabled={!editable || !!entry || rows.length >= 10000} onClick={() => beginEntry(null, newEntry(value.currency, initialAccountId))}>Add account balance</Button></div>
          </div></CardBody></Card>
          </Disclosure>
          {entry && <FinancialOpeningEntry key={entry.value.source_key} company={company} declaration={value} initial={entry.value} metadata={metadata.data} native={metadata.data.native} disabled={locked} onDirty={() => { setPreview(null); }} onCancel={() => { setEntry(null); if (!draft) baseline.current = undefined; }} onSave={line => { const next = [...rows]; if (entry.index === null) next.push(line); else next[entry.index] = line; patch({ entries: next }); setEntry(null); }} />}

        </>}
        {step === 2 && value.coverage_mode === 'YTD_SUMMARY' && <FinancialOpeningYtd company={company} value={value} disabled={!editable || !!entry} onChange={patch} />}
        {step === 2 && <Card><CardBody><div className="janso-flow"><SectionHeader title="Review the opening declaration" description={`Check the totals in ${value.currency}, validate the opening, then confirm posting.`} />
          <div className="janso-opening-metrics"><ReviewList items={[{ label: 'Debit base total', value: total('DEBIT') }, { label: 'Credit base total', value: total('CREDIT') }, { label: 'Account lines', value: String(rows.length) }]} /></div>
          <p className="janso-caption">Source covered through <time dateTime={value.covered_through}>{format.date(value.covered_through)}</time> · {value.coverage_mode === 'YTD_SUMMARY' ? 'Imported year-to-date summary' : 'Post-cutover only'}</p>
          {value.entries.find(row => row.source_key === OFFSET_SOURCE) && <Notice>The difference is balanced by a visible opening offset: <strong>{value.entries.find(row => row.source_key === OFFSET_SOURCE)!.amount} {value.currency} {value.entries.find(row => row.source_key === OFFSET_SOURCE)!.side === 'DEBIT' ? 'Dr' : 'Cr'}</strong>. This entry is included in the totals and will be posted.</Notice>}
          {automatic && <Checkbox checked={reviewed} disabled={!editable} onChange={event => setReviewed(event.target.checked)}>I reviewed the opening amounts, Dr/Cr types, offset and any on-account balances with unknown bill dates</Checkbox>}
          {automatic && !access.post && <Notice>Automatic posting requires journal posting and period access. Turn off automatic mode to save a reviewed worksheet.</Notice>}
          {previewError && <Notice tone="danger"><span role="alert">{previewError}</span></Notice>}
          {preview && <Notice tone="success"><span role="status">Preview passed: {preview.entry_count} account lines, {preview.document_count} {preview.document_count === 1 ? 'document' : 'documents'}, {preview.journal_count} {preview.journal_count === 1 ? 'journal' : 'journals'}. {automatic ? 'Ready for your posting confirmation.' : 'Saving keeps the reviewed balances without posting.'}</span></Notice>}
          <div className="janso-form-actions"><Button variant="ghost" loading={previewing} disabled={!editable || !!entry} onClick={() => void review()}>Validate and preview</Button>{automatic ? <Button disabled={!editable || !preview || !reviewed || !access.post || !!entry} onClick={() => setConfirm('automatic')}>Prepare and post opening</Button> : <Button disabled={!editable || !preview || !!entry || (!!id && !draft)} onClick={() => setConfirm('save')}>{id ? 'Save reviewed revision' : 'Save reviewed opening'}</Button>}</div>
        </div></CardBody></Card>}
        <div className="janso-opening-navigation"><span className="janso-caption">Step {step + 1} of 3</span><div className="janso-form-actions">{draft && <Button variant="ghost" disabled={locked || !!entry} onClick={() => { baseline.current = undefined; setDraft(null); setPreview(null); setReviewed(false); setOffset(undefined); setError(''); setCreating(false); setStep(0); }}>Discard worksheet changes</Button>}{step > 0 && <Button variant="ghost" disabled={locked || !!entry} onClick={() => changeStep(step - 1)}>Previous step</Button>}{step < 2 && <Button disabled={locked || !!entry || automatic && defaults.loading} onClick={() => changeStep(step + 1)}>Next step</Button>}</div></div>
      </div>}
      {tab === 'imports' && <FinancialOpeningImports company={company} access={access} onDirty={setChildDirty} onChanged={batch => { if (batch) { setCreating(false); setSelected(batch); control.refresh(); saved.refresh(); reconcile.refresh(); } }} />}
      {tab === 'completion' && !autoWorkspace && <div className="janso-flow janso-opening-completion" data-complete={control.data?.status === 'FINALIZED'}>
        {!control.data ? <Notice>Save a reviewed worksheet or commit an import before preparing native journals.</Notice> : <>
          <Card><CardBody><div className="janso-flow"><SectionHeader title={control.data.status === 'FINALIZED' ? 'Financial opening complete' : 'Prepare, post and reconcile'} description={control.data.status === 'FINALIZED' ? 'The reviewed starting balances have been posted and finalized.' : 'Complete the saved opening automatically, or use the individual controls below.'} />
            {['VOID', 'REVERSED'].includes(control.data.status) && saved.data && <Button disabled={!access.manage || locked || windowBlocked || !ready.data?.can_prepare} onClick={() => { baseline.current = { id: null }; setCreating(true); setDraft({ ...saved.data!, source_id: crypto.randomUUID(), replacement_of_id: control.data!.status === 'REVERSED' ? control.data!.id : null }); setSelected(null); setTab('worksheet'); setStep(0); ready.refresh(); }}>Prepare a replacement opening</Button>}
            <div className="janso-opening-metrics"><ReviewList items={[{ label: 'Captured account lines', value: String(control.data.entry_count) }, { label: 'Prepared journals', value: String(control.data.journal_ids.length) }, { label: 'Posted journals', value: String(control.data.posted_journals) }, { label: 'Effect', value: control.data.effect_kind.replaceAll('_', ' ') }]} /></div>
            {control.data.status === 'DRAFT' && <Button disabled={!access.manage || !access.post || windowBlocked || locked || !!draft || !saved.data} onClick={() => setConfirm('resume-automatic')}>Complete opening automatically</Button>}
            {control.data.status !== 'FINALIZED' && <><Notice>{control.data.blockers.includes('OPENING_DRAFTS_NOT_PREPARED') ? 'More journal drafts remain. Automatic completion prepares all remaining drafts.' : 'All journal drafts are prepared.'} {control.data.posted_journals} of {control.data.journal_ids.length} prepared journals posted.</Notice>
            <TextField id="financial-opening-action-reason" label="Action review reason" value={reason} maxLength={500} disabled={locked || !access.manage} onChange={event => setReason(event.target.value)} />
            <div className="janso-form-actions"><Button disabled={!access.manage || windowBlocked || locked || !!draft || control.data.status !== 'DRAFT'} onClick={() => reviewAction('prepare-drafts')}>Prepare remaining drafts</Button>
            <Button variant="ghost" disabled={!access.manage || windowBlocked || locked || !!draft || control.data.status !== 'DRAFT'} onClick={() => reviewAction('void')}>Close unposted opening plan</Button></div></>}
          </div></CardBody></Card>
          <FinancialOpeningPosting company={company} workspace={control.data} access={access} blocked={windowBlocked} onDirty={setChildDirty} onChanged={refresh} />
          <AccountingFailure failure={reconcile.failure} retry={reconcile.refresh} />
          {reconcile.loading ? <Skeleton lines={4} width="100%" /> : reconcile.data && <Card><CardBody><div className="janso-flow"><SectionHeader title="Opening reconciliation" />
            <ReviewList items={[{ label: 'Declared debit / credit', value: reconcile.data.expected_debit + ' / ' + reconcile.data.expected_credit }, { label: 'Posted debit / credit', value: reconcile.data.posted_debit + ' / ' + reconcile.data.posted_credit }, { label: 'Posted / declared documents', value: reconcile.data.posted_documents + ' / ' + reconcile.data.declared_documents }, { label: 'Ledger agreement', value: reconcile.data.gl_matches ? 'Matches' : 'Pending or different' }, { label: 'Outstanding agreement', value: reconcile.data.party_items_match ? 'Matches' : 'Pending or different' }, { label: 'Clearing balance', value: reconcile.data.clearing_balance }, { label: 'Confirmation', value: reconcile.data.confirmation_pending ? 'Awaiting delivery' : 'Complete' }]} />
            {reconcile.data.blockers.length > 0 && <Notice tone="warning">{reconcile.data.blockers.map(code => <p key={code}>{blockerLabel(code)}</p>)}</Notice>}
            <Disclosure summary="Related bank and inventory workflows"><p>Bank statement opening items and physical stock have separate records. These do not post the bank balance again. <a className="janso-link" href="/accounting/bank-reconciliation" onClick={guard.leave}>Review bank opening items</a>. <a className="janso-link" href="/inventory/stock/opening" onClick={guard.leave}>Review opening stock</a></p></Disclosure>
            {control.data.status !== 'FINALIZED' && <Button disabled={!access.manage || windowBlocked || reconcile.loading || !!reconcile.failure || locked || !!draft || !reconcile.data.ready_to_finalize || control.data.status !== 'DRAFT'} onClick={() => reviewAction('finalize')}>Finalize financial opening</Button>}
          </div></CardBody></Card>}
        </>}
      </div>}
      {tab === 'history' && <FinancialOpeningHistory company={company} workspace={control.data} access={access} initialAccountId={initialAccountId} initialPartyId={initialPartyId} onDirty={setChildDirty} />}
      </section>
    </>}
    <ConfirmDialog open={!!confirm} busy={command.pending} title={confirm === 'automatic' || confirm === 'resume-automatic' ? 'Post and complete this opening?' : confirm === 'save' ? 'Save the reviewed opening?' : confirm === 'finalize' ? 'Finalize the financial opening?' : confirm === 'void' ? 'Close the unposted plan?' : 'Prepare native journal drafts?'} confirmLabel={command.uncertain ? 'Retry the same request' : confirm === 'automatic' || confirm === 'resume-automatic' ? 'Prepare and post' : confirm === 'save' ? 'Save opening' : confirm === 'finalize' ? 'Finalize opening' : confirm === 'void' ? 'Close plan' : 'Prepare drafts'} onCancel={() => { if (!command.uncertain) setConfirm(null); }} onConfirm={() => void apply()}>
      {command.failure && <p role="alert">{command.failure.message}{command.uncertain ? ' Retry preserves the exact request and idempotency key.' : ''}</p>}
      {confirm === 'automatic' || confirm === 'resume-automatic' ? 'This prepares and posts the reviewed balances, including the displayed opening offset, waits for confirmation, reconciles and finalizes the financial opening automatically. Confirmed progress is retained when resuming. Finalization enables ordinary posting. Posted balances require a reversal to correct.' : confirm === 'save' ? 'This stores the reviewed declaration and its immutable source evidence. No money is posted.' : confirm === 'finalize' ? 'Completion requires every journal and outstanding document to agree with the declaration, confirmations delivered and clearing zero. It enables ordinary posting under existing permissions.' : confirm === 'void' ? 'Only unposted drafts can be closed. Posted amounts require the native reversal process; evidence is retained.' : 'This creates at most two missing opening journal drafts. Posting remains a separate, explicit action. Continue preparation if more are required.'}
    </ConfirmDialog>
    {guard.confirmation}
  </div>;
}

function FinancialOpeningYtd({ company, value, disabled, onChange }: { company: string; value: Declaration; disabled: boolean; onChange: (change: Partial<Declaration>) => void }) {
  const rows = value.ytd_summary ?? [];
  const [account, setAccount] = useState<string | null>(null), [side, setSide] = useState<'DEBIT' | 'CREDIT'>('CREDIT'), [currency, setCurrency] = useState(value.currency), [amount, setAmount] = useState(''), [baseAmount, setBaseAmount] = useState('');
  return <Card><CardBody><div className="janso-flow"><SectionHeader title="Imported year-to-date nominal summary" description="Add only income and expense account totals for the originating financial year through the day before cutover. Leaving the list empty explicitly declares zero imported activity." />
    {rows.map((row, i) => <ReviewList key={i} items={[{ label: `${row.account_id} · ${row.side}`, value: <span>{row.amount} {row.currency} / {row.base_amount} {value.currency} <Button variant="ghost" disabled={disabled} onClick={() => onChange({ ytd_summary: rows.filter((_, index) => i !== index) })}>Remove summary {i + 1}</Button></span> }]} />)}
    <div className="janso-form-grid"><SearchSelect label="Nominal account" loadOptions={lookup(company, 'accounts')} scopeKey={company + ':nominal'} value={account} disabled={disabled} onChange={setAccount} /><Select label="YTD side" value={side} disabled={disabled} options={[{ value: 'DEBIT', label: 'Debit' }, { value: 'CREDIT', label: 'Credit' }]} onChange={side => setSide(side as 'DEBIT' | 'CREDIT')} /><TextField label="YTD currency" value={currency} maxLength={3} disabled={disabled} onChange={event => setCurrency(event.target.value.toUpperCase())} /><TextField label="YTD amount" inputMode="decimal" value={amount} disabled={disabled} onChange={event => { setAmount(event.target.value); if (currency === value.currency) setBaseAmount(event.target.value); }} /><TextField label="YTD base value" inputMode="decimal" value={baseAmount} disabled={disabled || currency === value.currency} onChange={event => setBaseAmount(event.target.value)} /></div>
    <Button variant="ghost" disabled={disabled || !account || !amount || !baseAmount || rows.length >= 10000} onClick={() => { if (account) { onChange({ ytd_summary: [...rows, { account_id: account, side, currency, amount, base_amount: baseAmount }] }); setAmount(''); setBaseAmount(''); setAccount(null); } }}>Add YTD summary</Button>
  </div></CardBody></Card>;
}
