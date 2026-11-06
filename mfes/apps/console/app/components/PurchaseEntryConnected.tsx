'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { AmountField, Button, Checkbox, CustomFields, Drawer, Modal, Notice, PageHeader, SearchSelect, Select, Skeleton, SplitButton, TextField, businessToday, customPatch, useDisplayConfig, useFormatters, type SearchSelectLoader } from '@janso/ui';
import { PurchaseWorkspace } from './PurchaseWorkspace';
import { ExpenseAccountQuickCreate, SupplierQuickCreate } from './PurchaseQuickCreate';
import { PurchaseSupportingFiles } from './PurchaseSupportingFiles';
import { PurchasePageHeader } from './PurchasePageHeader';
import { PurchaseDraftsDrawer } from './PurchaseDraftsDrawer';
import { PurchaseTermsCard, TAX_CONFIRMATION_NAME } from './PurchaseTermsCard';
import { PurchaseTaxSection, type TaxAccount } from './PurchaseTaxSection';
import { PurchaseCalculationCard } from './PurchaseCalculationCard';
import { PurchaseLifecycle } from './PurchaseLifecycle';
import { DuplicateBillModal } from './PurchaseDuplicateBill';
import { VoucherSummary } from './VoucherSummary';
import { purchaseFileBase, purchaseFileCall, verifyPurchaseFile, type PurchaseStoredFile } from '../lib/purchase-files';
import { nativeProperties, PURCHASE_GOODS_UNAVAILABLE, purchaseAvailability, purchaseGoodsAllowed, purchaseGoodsType, purchaseLookup, purchaseModes, purchaseSource, supplierPayables } from '../lib/purchase-entry';
import { purchaseGoodsContext, purchaseItem, purchaseItemLookup } from '../lib/purchase-goods';
import { customFields, type FieldSet } from '../lib/voucher-fields';
import { serviceCall, requestFailure, type ServiceRequest } from '../lib/service-call';
import { useDraftNavigation } from '../lib/use-draft-navigation';
import { purchaseStatusView } from '../lib/purchase-page';
import { isTaxed, registrationsInForce, resolvePurchaseTax, type PurchaseTaxDraft } from '../lib/purchase-tax';
import { usePurchaseTaxFacts } from '../lib/use-purchase-tax-facts';
import type { PurchaseQuickCreate, QuickCreated, QuickCreateTarget } from '../lib/purchase-quick-create';
import { purchasePrintAction } from '../lib/purchase-print-action';
import { blankPurchaseLine, isBlankPurchaseLine, newPurchaseWorkspace, purchaseWorkspaceReducer, withPairedQuantity, type PurchaseWorkspaceAction, type PurchaseWorkspaceDraft, type PurchaseWorkspacePolicy } from '../lib/purchase-workspace';
import { purchaseDueDate } from '../lib/purchase-workspace-details';
import { DUPLICATE_BILL_CODE, PURCHASE_BROADER_CAPTURE, duplicateBillQuery, duplicateBillsFromFields, verifyDuplicateBills, type DuplicateBill, verifyPurchaseFieldSet, livePurchasePolicy, purchaseAdvancePage, purchaseBase, purchaseFromVoucher, purchaseInput, purchasePaymentAccount, purchasePendingKey, purchaseWireKey, readPurchasePending, verifyPurchaseCalculation, verifyPurchaseOperation, verifyPurchaseVoucher, type PurchaseAdvance, type PurchaseBinding, type PurchaseCalculation, type PurchaseCapabilities, type PurchaseOperation, type PurchaseOperationTarget, type PurchasePending, type PurchaseVoucher } from '../lib/purchase-api';
import { SUPPLIER_BALANCE_PERMISSION, SUPPLIER_BALANCE_TIMEOUT_MS, balanceDate, readSupplierBalance, type SupplierBalance } from '../lib/purchase-supplier-balance';
import { trackingId } from '../lib/stock-tracking-resources';
import { purchaseTracking, type PurchaseTracking } from '../lib/purchase-stock';
import { typeHref, TYPES_ROOT } from '../lib/voucher-type-routes';
import { offeredPurchaseTypes } from '../lib/voucher-types';
import * as D from '../lib/fixed-decimal';

const call = <T,>(request: ServiceRequest) => serviceCall<T>('/api/product-fields', { service: 'vouchers', ...request }, 'Purchase');
type Props = { company: string; currency: string; actor: string; year: string; canCreate: boolean; permissions: readonly string[]; initialVoucherId?: string; initialTypeId?: string; navigation?: ReactNode;
  /** The company's country: the default for a supplier created from the bill. */ companyCountry?: string };
type PurchaseType = { id: string; company_id: string; kind: string; profile: string; status?: string; name?: string; code?: string };
type Ready = { metadata: FieldSet; type: PurchaseType; capabilities: PurchaseCapabilities };
type PurchaseMutation = { kind: 'voucher'; value: PurchaseVoucher } | { kind: 'operation'; value: PurchaseOperation };

/** Production boundary. The synthetic review adapter is never used by this screen. */
export function PurchaseEntryConnected(props: Props) {
  if (!trackingId.test(props.company) || !trackingId.test(props.actor) || !/^[A-Z]{3}$/.test(props.currency)) return <Notice tone="danger" title="Purchase context is unavailable">Refresh your session and select a company with a valid base currency before preparing Purchase.</Notice>;
  return <PurchaseConnection key={JSON.stringify([props.actor, props.company, props.year])} {...props} />;
}
function PurchaseConnection(props: Props) {
  const { company } = props, display = useDisplayConfig();
  const today = useMemo(() => businessToday(display.timezone), [display.timezone]);
  const [types, setTypes] = useState<PurchaseType[]>([]), [chosen, setChosen] = useState(props.initialTypeId ?? '');
  const [ready, setReady] = useState<Ready | null>(null), [failure, setFailure] = useState(''), [loading, setLoading] = useState(true), [attempt, setAttempt] = useState(0);
  const [goods, setGoods] = useState(false);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setFailure(''); setGoods(false); setReady(null);
    const read = <T,>(path: string) => call<T>({ path, signal: controller.signal });
    void (async () => {
      const base = purchaseBase(company);
      if (props.initialVoucherId) {
        const saved = await read<PurchaseVoucher>(base + '/vouchers/' + props.initialVoucherId);
        verifyPurchaseVoucher(saved, company, { id: props.initialVoucherId });
        const [metadata, capabilities] = await Promise.all([
          read<FieldSet>(base + '/vouchers/' + saved.id + '/field-set?revision_id=' + saved.revision_id), read<PurchaseCapabilities>(base + '/voucher-capabilities'),
        ]);
        verifyPurchaseFieldSet(metadata);
        if (!controller.signal.aborted) setReady({ metadata, capabilities, type: { id: metadata.configuration.type_revision_id, company_id: company, kind: 'PURCHASE', profile: 'STANDARD' } });
        return;
      }
      const [page, capabilities] = await Promise.all([
        props.initialTypeId ? read<PurchaseType>(base + '/voucher-types/' + props.initialTypeId).then(row => ({ items: [row], page: { next_cursor: null } })) : read<{ items: PurchaseType[]; page: { next_cursor: string | null } }>(base + '/voucher-types?kind=PURCHASE&status=ACTIVE&limit=200'),
        read<PurchaseCapabilities>(base + '/voucher-capabilities'),
      ]);
      if (!Array.isArray(page.items) || page.items.some(row => !trackingId.test(row.id) || row.company_id !== company || row.kind !== 'PURCHASE') || page.page?.next_cursor || typeof capabilities.invoice_execution !== 'boolean' || !Array.isArray(capabilities.kinds)) throw Error('Purchase configuration could not be verified.');
      if (props.initialTypeId && page.items.some(row => row.id !== props.initialTypeId || row.status !== 'ACTIVE')) throw Error('The selected purchase type is unavailable for this company.');
      if (controller.signal.aborted) return;
      const offered = offeredPurchaseTypes(page.items);
      setTypes(offered);
      const selected = offered.find(row => row.id === chosen) ?? (offered.length === 1 ? offered[0] : undefined);
      if (!selected) return;
      const metadata = await read<FieldSet>(base + '/voucher-types/' + selected.id + '/field-set?date=' + today + '&posting_date=' + today);
      if (!metadata?.native || !Array.isArray(metadata.custom) || !trackingId.test(metadata.configuration?.type_revision_id ?? '')) throw Error('Purchase field access could not be verified.');
      // A product or mixed type whose rules do not allow goods supplies cannot take its item lines here.
      if (purchaseGoodsType(metadata) && !purchaseGoodsAllowed(metadata)) { if (!controller.signal.aborted) setGoods(true); return; }
      const unavailable = purchaseAvailability(metadata); if (unavailable) throw Error(unavailable);
      if (!controller.signal.aborted) setReady({ metadata, type: selected, capabilities });
    })().catch(error => { if (!controller.signal.aborted) setFailure(error instanceof Error ? error.message : requestFailure(error, 'Purchase').message); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [company, chosen, today, attempt, props.initialVoucherId, props.initialTypeId]);
  if (loading) return <section className="janso-page" aria-busy="true">{props.navigation}<PageHeader title="New purchase" />
    <div className="janso-purchase-loading"><p role="status">Loading Purchase configuration and access…</p><Skeleton lines={4} /></div></section>;
  const selected = types.find(row => row.id === chosen) ?? (types.length === 1 ? types[0] : undefined);
  if (!ready) return <section className="janso-page">{props.navigation}<PageHeader overline={<a className="janso-link" href="/vouchers">Purchases</a>} title="New purchase" lede="Record a supplier’s bill for goods, expenses or services. Choose a Purchase voucher type to begin." />
    <div className="janso-entry-workspace__panel janso-purchase-setup">
      {goods ? <Notice title="This Purchase type cannot take products">{PURCHASE_GOODS_UNAVAILABLE}</Notice> : failure ? <Notice tone="danger" title="Purchase needs configuration">{failure}</Notice> : !types.length ? <Notice title="No active Purchase type">Set up an active Purchase voucher type for this company to begin.</Notice> : null}
      {!!types.length && <Select label="Purchase voucher type" value={selected?.id ?? ''} options={[{ value: '', label: 'Choose a Purchase type' }, ...types.map(row => ({ value: row.id, label: row.name ?? row.code ?? row.id }))]} onChange={setChosen} />}
      <div className="janso-purchase-setup__links">{selected ? <><a className="janso-link" href={typeHref(selected.id)}>Review Purchase voucher type</a>{props.permissions.includes('vouchers.type.manage') && !goods && <a className="janso-link" href={typeHref(selected.id) + '/edit'}>Edit Purchase entry rules</a>}</> : <a className="janso-link" href={TYPES_ROOT}>Open voucher types</a>}</div>
      <div><Button variant="ghost" onClick={() => setAttempt(value => value + 1)}>Refresh Purchase setup</Button></div>
    </div></section>;
  return <PurchaseSession key={ready.type.id} {...props} today={today} ready={ready} />;
}

function PurchaseSession({ company, currency, actor, year, permissions, canCreate, initialVoucherId, navigation, companyCountry, today, ready }: Props & { today: string; ready: Ready }) {
  const base = purchaseBase(company), scope = JSON.stringify([actor, company, year]);
  const format = useFormatters();
  const allowed = (action: string) => permissions.includes('vouchers.' + action);
  const binding = useRef<PurchaseBinding>({ company, currency, metadata: ready.metadata, sources: new Map(), keys: new Map(), partyKey: crypto.randomUUID() });
  const goodsAllowed = purchaseGoodsAllowed(ready.metadata);
  const display = useDisplayConfig();
  // A new bill opens in the type's own default mode when this screen offers it, otherwise in the first one it does.
  const [draft, setDraft] = useState<PurchaseWorkspaceDraft>(() => {
    const modes = purchaseModes(ready.metadata), preferred = ready.metadata.configuration.policy.default_mode;
    const mode = modes.find(entry => entry === preferred) ?? modes[0] ?? 'ACCOUNTS';
    return { ...newPurchaseWorkspace(today), mode, lines: [blankPurchaseLine('p1', mode === 'ACCOUNTS' ? 'ACCOUNT' : 'ITEM')] };
  });
  const [baseline, setBaseline] = useState(() => JSON.stringify(draft));
  const [duplicate, setDuplicate] = useState<{ request: ServiceRequest; matches: DuplicateBill[]; incomplete: boolean } | null>(null), [similar, setSimilar] = useState<DuplicateBill[]>([]);
  const [record, setRecord] = useState<PurchaseVoucher | null>(null), [policy, setPolicy] = useState<PurchaseWorkspacePolicy>(() => livePurchasePolicy(currency, ready.metadata, company));
  const [calculation, setCalculation] = useState<{ value: PurchaseCalculation; revision: string } | null>(null);
  const [pending, setPending] = useState(false), [completing, setCompleting] = useState(false), [retained, setRetained] = useState<PurchasePending | null>(null), [failure, setFailure] = useState(''), [notice, setNotice] = useState('');
  /** A saved bill (for example a product bill) that only voucher review can show. */
  const [elsewhere, setElsewhere] = useState<string | null>(null);
  const [recoveryBlocked, setRecoveryBlocked] = useState(false);
  const [operationBlocked, setOperationBlocked] = useState(false), [operationAttempt, setOperationAttempt] = useState(0);
  const [readbackBlocked, setReadbackBlocked] = useState(false);
  const [operation, setOperation] = useState<PurchaseOperation | null>(null);
  const operationKey = 'purchase-api-operation:' + scope;
  const [details, setDetails] = useState(false), [reason, setReason] = useState(''), [taxError, setTaxError] = useState(false);
  const [draftsOpen, setDraftsOpen] = useState(false), [draftsLoaded, setDraftsLoaded] = useState(false), [draftsFailure, setDraftsFailure] = useState(''), [restoreFocus, setRestoreFocus] = useState(false);
  const [filePending, setFilePending] = useState(false);
  const [detailEdit, setDetailEdit] = useState(draft.details), [detailRaw, setDetailRaw] = useState<Record<string, string>>({}), [detailIssue, setDetailIssue] = useState(''), [detailDiscard, setDetailDiscard] = useState(false);
  const [advances, setAdvances] = useState<PurchaseAdvance[]>([]), [advanceCursor, setAdvanceCursor] = useState<string | null>(null);
  const [resume, setResume] = useState(initialVoucherId ?? ''), [drafts, setDrafts] = useState<{ id: string; status: string; document_date?: string | null }[]>([]), [cursor, setCursor] = useState<string | null>(null);
  const [history, setHistory] = useState<{ id: string; action: string; from_status: string; to_status: string; revision_id?: string }[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null), [historyLoaded, setHistoryLoaded] = useState(false), [snapshot, setSnapshot] = useState<PurchaseVoucher | null>(null), [snapshotFiles, setSnapshotFiles] = useState<PurchaseStoredFile[]>([]);
  const [transient, setTransient] = useState(false), [confirmation, setConfirmation] = useState<(() => void) | null>(null);
  const [loaded, setLoaded] = useState(!initialVoucherId);
  const [replacementSource, setReplacementSource] = useState<string | null>(null);
  const [creating, setCreating] = useState<{ kind: 'supplier' } | { kind: 'account'; target: QuickCreateTarget } | null>(null), [focusAfter, setFocusAfter] = useState<readonly string[] | null>(null);
  const [balance, setBalance] = useState<SupplierBalance | null>(null);
  const [batchPrompt, setBatchPrompt] = useState<{ lineKey: string; itemId: string; profile: PurchaseTracking } | null>(null);
  const busy = useRef(false), completeRun = useRef(false), alive = useRef(true), balanceRun = useRef<AbortController | null>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; balanceRun.current?.abort(); }; }, []);
  useEffect(() => {
    try { setRetained(readPurchasePending(sessionStorage, scope, company)); }
    catch (error) { setRecoveryBlocked(true); setFailure((error as Error).message); }
  }, [company, scope]);
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(operationKey); if (!raw) return;
      setOperationBlocked(true);
      const ticket = JSON.parse(raw) as { id: string; voucherId: string; revisionId: string };
      if (![ticket.id, ticket.voucherId, ticket.revisionId].every(value => trackingId.test(value))) throw Error('The saved execution reference could not be verified.');
      void readAction(async () => {
        const value = await call<PurchaseOperation>({ path: base + '/voucher-operations/' + ticket.id });
        verifyPurchaseOperation(value, ticket); if (value.id !== ticket.id) throw Error('The saved execution identity changed.');
        if (!alive.current) return;
        setOperation(value); settleOperation(value, await reopen(ticket.voucherId)); setOperationBlocked(false);
      });
    } catch { setRecoveryBlocked(true); setFailure('The retained Purchase execution reference could not be verified. Review the saved voucher before continuing.'); }
  }, [operationKey, operationAttempt]);
  const dirty = JSON.stringify(draft) !== baseline;
  const locked = pending || completing || !!retained || recoveryBlocked || operationBlocked || readbackBlocked;
  // An execution belongs to the bill it was requested for: one that finished for another bill must not lock this one.
  const running = operation && record && operation.voucher_id === record.id ? operation : null;
  const executing = running?.status === 'PENDING' || running?.status === 'COMMITTED' && !['POSTED', 'REVERSED'].includes(record?.status ?? '');
  const editable = !executing && (!record ? canCreate : ['DRAFT', 'REJECTED', 'SUBMITTED', 'APPROVED'].includes(record.status) && allowed('edit'));
  const currentCalculation = !dirty && calculation && calculation.revision === record?.revision_id ? calculation.value : null;
  const acceptedHash = (record?.invoice as { accepted_calculation_hash?: string | null } | null | undefined)?.accepted_calculation_hash ?? null;
  // A fresh calculation that is not the accepted one means the bill was accepted for something Accounting no longer works out.
  const differs = !!currentCalculation && !!acceptedHash && acceptedHash !== currentCalculation.calculation_hash;
  const accepted = !dirty && !!acceptedHash && !differs;
  useDraftNavigation({ atRisk: dirty, blocked: locked || transient || details || !!snapshot || !!creating, requestLeave: proceed => setConfirmation(() => proceed), onBlocked: () => setNotice('Finish the open detail editor or resolve the pending request before leaving.') });
  const transientChanged = useCallback((value: boolean) => setTransient(value), []);
  const sourcePolicy = (next: PurchaseWorkspaceDraft, current: PurchaseWorkspacePolicy): PurchaseWorkspacePolicy => {
    const party = binding.current.sources.get(next.supplier), payable = binding.current.sources.get(next.payable);
    return { ...current, live: true, discountsAllowed: !!binding.current.metadata.configuration.policy.invoice?.manual_discounts_allowed, suppliers: party ? [{ id: party.id, label: party.label, meta: 'Supplier', payables: payable ? [{ value: payable.id, label: payable.label }] : [] }] : [], subjects: next.lines.filter(line => !!line.subject).map(line => ({ id: line.subject, label: line.label, meta: 'Captured expense account', kind: line.kind, unit: line.unit })) };
  };
  async function readAction(work: () => Promise<unknown>) {
    if (busy.current) return;
    busy.current = true; setPending(true); setFailure(''); setNotice('');
    try { await work(); } catch (error) { if (alive.current) setFailure(error instanceof Error ? error.message : requestFailure(error, 'Purchase').message); }
    finally { busy.current = false; if (alive.current) setPending(false); }
  }
  /**
   * The chosen supplier's balance, read once in the background. It takes no part in the busy guard: nothing is disabled while it
   * loads, a newer choice (or leaving the page) cancels the read, and a read that fails or runs long shows "not available" and
   * leaves the bill alone. Without the ledger read key nothing is requested.
   */
  const loadBalance = (supplier: string, payables: readonly string[], posting: string) => {
    balanceRun.current?.abort(); balanceRun.current = null;
    if (!permissions.includes(SUPPLIER_BALANCE_PERMISSION) || !payables.length) { setBalance(null); return; }
    const controller = new AbortController(); balanceRun.current = controller;
    const current = () => balanceRun.current === controller && alive.current;
    const timer = setTimeout(() => { if (current()) { controller.abort(); setBalance({ supplier, status: 'unavailable' }); } }, SUPPLIER_BALANCE_TIMEOUT_MS);
    setBalance({ supplier, status: 'loading' });
    readSupplierBalance(call, { base, supplier, payables, asOf: balanceDate(posting, today), currency, signal: controller.signal })
      .then(value => { if (current()) setBalance(value); })
      .catch(() => { if (current()) setBalance({ supplier, status: 'unavailable' }); })
      .finally(() => clearTimeout(timer));
  };
  const balanceSupplier = policy.suppliers.find(row => row.id === draft.supplier);
  const balanceActive = !record || ['DRAFT', 'REJECTED', 'SUBMITTED', 'APPROVED'].includes(record.status);
  const balanceKey = balanceActive && balanceSupplier ? [draft.supplier, draft.postingDate, ...balanceSupplier.payables.map(row => row.value)].join('|') : '';
  useEffect(() => {
    if (!balanceKey || !balanceSupplier) { balanceRun.current?.abort(); balanceRun.current = null; setBalance(null); return; }
    balanceRun.current?.abort(); balanceRun.current = null; setBalance(null);
    const timer = setTimeout(() => loadBalance(balanceSupplier.id, balanceSupplier.payables.map(row => row.value), draft.postingDate), 150);
    return () => clearTimeout(timer);
  }, [balanceKey]);
  /** Returns whether the change was taken; `announce` is said once a supplier or account has been verified and chosen. */
  const dispatch = (action: PurchaseWorkspaceAction, announce?: string): boolean => {
    if (locked || !editable || busy.current) return false;
    setFailure(''); setNotice('');
    if (action.type === 'supplier' && action.value) {
      void readAction(async () => {
        const supplier = await purchaseSource(company, 'suppliers', action.value);
        // The supplier's payable account is chosen with the supplier: it has exactly one (a supplier that has none, or several, says so on the bill).
        const verified = await supplierPayables(company, supplier.id);
        if (!alive.current) return;
        binding.current.sources.set(supplier.id, supplier); verified.forEach(row => binding.current.sources.set(row.id, row));
        const next = { ...policy, live: true, suppliers: [{ id: supplier.id, label: supplier.label, meta: 'Active supplier', payables: verified.map(row => ({ value: row.id, label: row.label })) }] };
        setPolicy(next); setDraft(current => purchaseWorkspaceReducer(current, { ...action, policy: next }));
        if (announce) setNotice(announce);
      }); return true;
    }
    // A cleared supplier leaves no balance behind, and cancels one still being read.
    if (action.type === 'supplier' && !action.value) { balanceRun.current?.abort(); balanceRun.current = null; setBalance(null); }
    const subjectId = action.type === 'subject' ? action.subject?.id : action.type === 'line' ? action.patch.subject : undefined;
    const subjectKind = action.type === 'subject' ? action.subject?.kind : action.type === 'line' ? action.patch.kind ?? draft.lines.find(line => line.key === action.key)?.kind : undefined;
    if (subjectId && subjectKind === 'ITEM') {
      // A product is checked with Catalog before the line takes it: active, purchasable, in this company, with its unit.
      void readAction(async () => {
        const item = await purchaseItem(company, subjectId);
        if (!alive.current) return;
        (binding.current.items ??= new Map()).set(item.id, item);
        const subject = { id: item.id, label: item.label, meta: item.sku ?? 'Verified product', kind: 'ITEM' as const, unit: item.unit };
        setPolicy(current => ({ ...current, subjects: [...current.subjects.filter(row => row.id !== item.id || row.kind !== 'ITEM'), subject] }));
        setDraft(current => purchaseWorkspaceReducer(current, action.type === 'subject' ? { ...action, subject } : action.type === 'line' ? { ...action, patch: { ...action.patch, label: item.label, unit: item.unit } } : action));
        if (action.type === 'subject') {
          setBatchPrompt(null);
          const tracking = await purchaseTracking(company, item.id);
          if (!alive.current) return;
          const retainedBatch = draft.lines.find(line => line.key === action.key && line.subject === item.id)?.stock?.lotId;
          if (tracking.lotTracking && !retainedBatch && policy.stockAccess?.batch && permissions.includes('accounting.batch.read')) setBatchPrompt({ lineKey: action.key, itemId: item.id, profile: tracking });
          else if (tracking.lotTracking) setNotice('This product requires a batch. Batch read and Purchase stock-line access are needed to choose one.');
        }
        if (announce) setNotice(announce);
      }); return true;
    }
    if (action.type === 'subject') setBatchPrompt(null);
    if (subjectId) {
      void readAction(async () => {
        const account = await purchaseSource(company, 'expenses', subjectId);
        if (!alive.current) return;
        binding.current.sources.set(account.id, account);
        setPolicy(current => ({ ...current, subjects: [...current.subjects.filter(row => row.id !== account.id), { id: account.id, label: account.label, meta: 'Verified expense account', kind: 'ACCOUNT', unit: '' }] }));
        setDraft(current => purchaseWorkspaceReducer(current, action.type === 'subject' ? { ...action, subject: { id: account.id, label: account.label, meta: '', kind: 'ACCOUNT', unit: '' } } : action));
        if (announce) setNotice(announce);
      }); return true;
    }
    setDraft(current => {
      const line = action.type === 'line' ? current.lines.find(entry => entry.key === action.key) : undefined;
      return purchaseWorkspaceReducer(current, line && action.type === 'line' ? { ...action, patch: withPairedQuantity(line, action.patch) } : action);
    });
    return true;
  };
  // GST is recorded only where the actor may read tax masters and the type takes service supplies; otherwise no tax master is read at all.
  const serviceAllowed = !!ready.metadata.configuration.policy.invoice?.allowed_supply_kinds?.includes('SERVICE');
  const taxEnabled = permissions.includes('accounting.tax.read') && (serviceAllowed || goodsAllowed);
  const taxedBill = isTaxed(draft.tax);
  const taxAccounts = useMemo<TaxAccount[]>(() => {
    const found = new Map<string, { id: string; label: string; lines: number[] }>();
    draft.lines.forEach((line, index) => {
      if (line.kind !== 'ACCOUNT' || !line.subject) return;
      const entry = found.get(line.subject) ?? { id: line.subject, label: line.label || line.subject, lines: [] };
      entry.lines.push(index + 1); found.set(line.subject, entry);
    });
    return [...found.values()];
  }, [draft.lines]);
  const taxFacts = usePurchaseTaxFacts({ enabled: taxEnabled && (editable || taxedBill), active: taxedBill, read: call, company, supplier: draft.supplier, accounts: taxAccounts.map(account => account.id), on: draft.tax.completionDate || draft.invoiceDate });
  const inForce = registrationsInForce(taxFacts.facts, draft.invoiceDate);
  const taxAvailable = taxEnabled && !taxFacts.failures.companies && (taxFacts.facts.companies === null || inForce.length > 0);
  const taxResolution = resolvePurchaseTax({ tax: draft.tax, invoiceDate: draft.invoiceDate, supplier: draft.supplier, facts: taxFacts.facts });
  // Where GST can be recorded a new bill starts as one that carries it — the box unticked, the tax section to fill — once the
  // company's registrations are known, and never over a choice already made. A bill that has not been touched stays untouched.
  useEffect(() => {
    if (!editable || draft.tax.choice !== '' || !taxEnabled || taxFacts.facts.companies === null || !inForce.length) return;
    const next = { ...draft, tax: { ...draft.tax, choice: 'FORWARD' as const } };
    if (!dirty) setBaseline(JSON.stringify(next));
    setDraft(current => current.tax.choice === '' ? { ...current, tax: { ...current.tax, choice: 'FORWARD' } } : current);
  }, [editable, draft.tax.choice, taxEnabled, taxFacts.facts.companies, inForce.length]);
  const taxReason = !permissions.includes('accounting.tax.read') ? 'You need access to tax masters to record GST on a bill.'
    : !serviceAllowed && !goodsAllowed ? 'This voucher type does not allow service purchase lines, which GST is recorded on. An administrator can allow them in the type’s purchase rules.'
    : taxFacts.failures.companies ? 'The company’s GST registrations could not be read: ' + taxFacts.failures.companies
    : taxFacts.facts.companies !== null && !inForce.length ? 'This company has no GST registration in force on the invoice date, so this bill can only be recorded without tax.' : undefined;
  const taxHint = taxAvailable ? (taxedBill ? 'Tick this if the bill carries no GST.' : draft.tax.choice === 'NONE' ? 'Untick this if the bill includes GST.' : 'Required before saving.') : taxReason ? 'Required before saving. ' + taxReason : undefined;
  const changeTax = (patch: Partial<PurchaseTaxDraft>) => { setTaxError(false); dispatch({ type: 'tax', patch }); };
  const focusTax = (field: string) => (document.querySelector<HTMLElement>('[data-purchase-field="' + field + '"] :is(input,select,button)') ?? document.querySelector<HTMLElement>('[data-purchase-field="taxChoice"] :is(input,select,button)'))?.focus();
  const supplierLookup = useMemo(() => purchaseLookup(company, 'suppliers'), [company]);
  const subjectLookup: SearchSelectLoader = useMemo(() => purchaseLookup(company, 'expenses'), [company]);
  const itemLookup = useMemo(() => goodsAllowed ? purchaseItemLookup(company) : undefined, [company, goodsAllowed]);
  const paymentLookup: SearchSelectLoader = useMemo(() => async ({ q, cursor, signal }) => {
    const query = new URLSearchParams({ kind: detailEdit.payment.method, status: 'ACTIVE', limit: '50', ...(q ? { q } : {}), ...(cursor ? { cursor } : {}) });
    const page = await call<{ items: { id: string; company_id: string; name?: string; code?: string }[]; page: { next_cursor: string | null } }>({ service: 'accounting', path: base + '/accounts?' + query, signal });
    if (!Array.isArray(page.items) || page.items.length > 50 || !page.page || page.items.some(row => row.company_id !== company || !trackingId.test(row.id))) throw Error('Payment accounts could not be verified.');
    return { items: page.items.map(row => ({ id: row.id, label: row.name ?? row.code ?? row.id })), nextCursor: page.page.next_cursor };
  }, [base, company, detailEdit.payment.method]);
  // The balance is "before this bill", so it is shown only while the bill can still be changed, and only for the supplier it was read for.
  const supplierBalance = balance && balance.supplier === draft.supplier && (balance.status !== 'ready' || balance.asOf === balanceDate(draft.postingDate, today)) && (!record || !executing && ['DRAFT', 'REJECTED', 'SUBMITTED', 'APPROVED'].includes(record.status)) ? balance : undefined;
  const balanceAccess = useMemo(() => ({ ledger: permissions.includes(SUPPLIER_BALANCE_PERMISSION), stock: permissions.includes('accounting.stock.read') }), [permissions]);
  const livePolicy = useMemo(() => ({ ...policy, live: true, subjectLookup, itemLookup, supplierBalance, balanceAccess,
    canReadBatch: permissions.includes('accounting.batch.read'),
    canPrepareBatch: permissions.includes('accounting.batch.read') && permissions.includes('accounting.batch.manage'),
    supplierHistoryAccess: permissions.includes('vouchers.read') }), [policy, subjectLookup, itemLookup, supplierBalance, balanceAccess, permissions]);
  // Presentation only: Accounting authorizes each create. A supplier needs its payable account too; an expense account needs the groups to choose from.
  const canQuickSupplier = permissions.includes('accounting.party.manage') && permissions.includes('accounting.account.manage');
  const canQuickTax = permissions.includes('accounting.tax.manage') && permissions.includes('accounting.tax.read');
  const canQuickAccount = permissions.includes('accounting.account.manage') && permissions.includes('accounting.group.read') && permissions.includes('accounting.head.read');
  const canQuickProduct = goodsAllowed && permissions.includes('item.create');
  const quickCreate = useMemo<PurchaseQuickCreate | undefined>(() => editable && (canQuickSupplier || canQuickAccount || canQuickProduct) ? {
    ...(canQuickSupplier ? { supplier: () => setCreating({ kind: 'supplier' }) } : {}),
    ...(canQuickAccount ? { account: (target: QuickCreateTarget) => setCreating({ kind: 'account', target }) } : {}),
    ...(canQuickProduct ? { product: true } : {}),
  } : undefined, [editable, canQuickSupplier, canQuickAccount, canQuickProduct]);
  // What was created is chosen through the bill's own paths, so Accounting re-reads and verifies it exactly as for a pick from the list.
  function createdSupplier(created: QuickCreated) {
    setCreating(null);
    const taken = dispatch({ type: 'supplier', value: created.id, policy }, 'Supplier ' + created.label + ' was created and selected.');
    if (!taken) setNotice('Supplier ' + created.label + ' was created. Choose it in the Supplier field when this bill is ready.');
    setFocusAfter(['[data-purchase-field="invoice"] input', '[data-purchase-field="supplier"] input']);
  }
  function createdAccount(target: QuickCreateTarget, created: QuickCreated) {
    setCreating(null);
    // A staged line editor keeps the account until its line is applied; the bill is not touched before then. It is
    // verified now so the editor accepts it like any other pick, and again with the line when that is applied.
    if (target.apply) {
      void readAction(async () => {
        const account = await purchaseSource(company, 'expenses', created.id);
        if (!alive.current) return;
        binding.current.sources.set(account.id, account);
        setPolicy(current => ({ ...current, subjects: [...current.subjects.filter(row => row.id !== account.id), { id: account.id, label: account.label, meta: 'Verified expense account', kind: 'ACCOUNT', unit: '' }] }));
        target.apply!({ ...created, label: account.label });
      });
      return;
    }
    const row = '[data-entry-row="' + target.lineKey + '"]';
    const taken = dispatch({ type: 'subject', key: target.lineKey, subject: { id: created.id, label: created.label, meta: created.meta ?? '', kind: 'ACCOUNT', unit: '' } }, 'Expense account ' + created.label + ' was created and selected.');
    if (!taken) setNotice('Expense account ' + created.label + ' was created. Choose it on its line when this bill is ready.');
    setFocusAfter([row + '[data-entry-col="amount"]', row + '[data-entry-col="subject"] input']);
  }
  // Focus waits for the bill to finish verifying the choice: a field that is still disabled cannot take it.
  useEffect(() => {
    if (!focusAfter || pending) return;
    for (const selector of focusAfter) {
      const target = document.querySelector<HTMLElement>(selector);
      if (target && !(target as HTMLInputElement).disabled) { target.focus(); break; }
    }
    setFocusAfter(null);
  }, [focusAfter, pending]);
  async function reopen(id: string) {
    if (!trackingId.test(id)) throw Error('Enter a valid saved Purchase ID.');
    const value = await call<PurchaseVoucher>({ path: base + '/vouchers/' + id }); verifyPurchaseVoucher(value, company, { id });
    const metadata = await call<FieldSet>({ path: base + '/vouchers/' + id + '/field-set?revision_id=' + value.revision_id });
    let result: ReturnType<typeof purchaseFromVoucher>;
    try { result = purchaseFromVoucher(value, company, metadata); setElsewhere(null); }
    catch (error) { setElsewhere(error instanceof Error && error.message === PURCHASE_BROADER_CAPTURE ? id : null); throw error; }
    if (value.attachments?.length && ready.capabilities.purchase_supporting_files) {
      const files = await purchaseFileCall<PurchaseStoredFile[]>({ path: purchaseFileBase(company, id) + '?revision_id=' + value.revision_id });
      if (!Array.isArray(files) || files.length > 20) throw Error('Supporting-file metadata could not be verified.');
      files.forEach(file => verifyPurchaseFile(file, company, id));
      result.draft.details.supportingFiles = result.draft.details.supportingFiles?.map(saved => files.find(file => file.object_key === saved.object_key && file.content_hash === saved.content_hash && file.size_bytes === saved.size_bytes && file.media_type === saved.media_type) ?? saved);
    }
    // Current labels supplement immutable capture; the stored source versions are retained.
    const sources = [...result.binding.sources.values()];
    for (let offset = 0; offset < sources.length; offset += 5) await Promise.all(sources.slice(offset, offset + 5).map(async source => {
      try {
        const row = await call<{ id: string; company_id: string; name?: string; code?: string }>({ service: 'accounting', path: base + (source.id === result.draft.supplier ? '/parties/' : '/accounts/') + source.id });
        if (row.id === source.id && row.company_id === company) source.label = row.name ?? row.code ?? source.label;
      } catch { /* Unavailable current labels never replace the saved source identity/version. */ }
    }));
    // Products are read again for their current name, unit and version; one that is no longer active keeps its saved capture.
    const items = [...result.binding.items?.values() ?? []];
    for (let offset = 0; offset < items.length; offset += 5) await Promise.all(items.slice(offset, offset + 5).map(async saved => {
      try { result.binding.items!.set(saved.id, await purchaseItem(company, saved.id)); } catch { /* Saved identity and version stay. */ }
    }));
    if (!alive.current) return;
    result.draft.lines = result.draft.lines.map(line => {
      const item = line.kind === 'ITEM' ? result.binding.items?.get(line.subject) : undefined;
      return item ? { ...line, label: item.label, unit: item.unit } : { ...line, label: result.binding.sources.get(line.subject)?.label ?? line.label };
    });
    binding.current = result.binding;
    setPolicy(sourcePolicy(result.draft, livePurchasePolicy(currency, metadata, company)));
    setDraft(result.draft); setBaseline(JSON.stringify(result.draft)); setRecord(value); setReplacementSource(null); setOperation(current => current && current.voucher_id === value.id ? current : null); setCalculation(null); setTaxError(false); setReason(''); setHistory([]); setHistoryLoaded(false); setLoaded(true);
    setAdvances([]); setAdvanceCursor(null); setHistoryCursor(null);
    setReadbackBlocked(false);
    setNotice('Loaded saved Purchase revision ' + value.revision_number + '. Captured source versions are preserved.' + (result.typeRevised ? ' The voucher type has been revised since this bill was saved; saving it uses the current rules.' : ''));
    if (window.location.pathname === '/vouchers/new/purchase') {
      const url = new URL(window.location.href); url.searchParams.set('voucher_id', value.id);
      // Preserve Next's history state and replace this entry, so reload reopens the server record.
      window.history.replaceState(window.history.state, '', url);
    }
    return value;
  }
  // A finished execution is not a reference to keep: left in the tab it would pin every later visit to that bill.
  const settleOperation = (current: PurchaseOperation, voucher: PurchaseVoucher | undefined) => {
    const finished = current.status === 'REJECTED' || current.status === 'CANCELLED' || current.status === 'COMMITTED' && ['POSTED', 'REVERSED'].includes(voucher?.status ?? '');
    if (!finished) return;
    try { sessionStorage.removeItem(operationKey); } catch { /* The page still works; the reference simply stays. */ }
  };
  // The bill in the address is opened once any retained execution has been followed: that first read takes the busy guard, and a
  // reference for another bill must not leave the one the address names unopened.
  useEffect(() => { if (initialVoucherId && !replacementSource && !operationBlocked && record?.id !== initialVoucherId) void readAction(() => reopen(initialVoucherId)); }, [initialVoucherId, replacementSource, operationBlocked]);
  // Advice only: the service refuses a repeat at submit. A lookup that fails shows nothing rather than an error.
  useEffect(() => {
    setSimilar([]);
    const supplier = (record?.parties as { role: string; party_id: string }[] | undefined)?.find(row => row.role === 'SUPPLIER')?.party_id;
    const invoice = record?.invoice as { bill_reference?: string; party_account_id?: string } | null | undefined;
    const reference = invoice?.bill_reference?.trim(), payable = invoice?.party_account_id;
    if (!record || !record.document_date || !(supplier || payable) || !reference || !allowed('read') || !['DRAFT', 'REJECTED'].includes(record.status)) return;
    let current = true;
    call<unknown>({ path: duplicateBillQuery(base, { partyId: supplier, payableId: payable, billReference: reference, documentDate: record.document_date, excludeVoucherId: record.id }) })
      .then(value => { if (current && alive.current) setSimilar(verifyDuplicateBills(value)); }).catch(() => undefined);
    return () => { current = false; };
  }, [record?.id, record?.revision_id]);
  const confirmDuplicate = () => {
    const pending = duplicate; if (!pending) return;
    setDuplicate(null);
    // A new key: this is a different command from the refused one, and the service records the acknowledgement.
    void send({ ...pending.request, body: { ...(pending.request.body as object), acknowledge_duplicate_bill: true } });
  };

  async function send(request: ServiceRequest, operationTarget?: PurchaseOperationTarget): Promise<PurchaseMutation | null> {
    if (busy.current || retained || recoveryBlocked || operationBlocked || readbackBlocked) return null;
    const command: PurchasePending = { schema: 1, scope, request: { ...request, service: 'vouchers', key: crypto.randomUUID() }, createdAt: new Date().toISOString(), ...(operationTarget ? { operation: operationTarget } : {}) };
    try { sessionStorage.setItem(purchasePendingKey(scope), JSON.stringify(command)); }
    catch { setFailure('Recovery storage is unavailable. Enable session storage before saving this bill.'); return null; }
    return perform(command);
  }
  async function perform(command: PurchasePending): Promise<PurchaseMutation | null> {
    if (busy.current) return null;
    busy.current = true; setPending(true); setFailure(''); setNotice(''); setRetained(command);
    let confirmed = false;
    try {
      if (command.operation) {
        const receipt = await call<PurchaseOperation & { operation_id?: string }>(command.request);
        const operationId = receipt.operation_id ?? receipt.id;
        if (!trackingId.test(operationId)) throw Error('The execution receipt identity could not be verified.');
        const pathOperation = command.request.path.match(/\/voucher-operations\/([a-f0-9-]{36})\//i)?.[1];
        if (pathOperation && operationId !== pathOperation) throw Error('The execution receipt does not match the requested operation.');
        // Recovery receipts carry references only. Read actual lineage under live authority.
        const value = await call<PurchaseOperation>({ path: base + '/voucher-operations/' + operationId });
        verifyPurchaseOperation(value, command.operation);
        if (value.id !== operationId) throw Error('The execution receipt identity changed.');
        sessionStorage.setItem(operationKey, JSON.stringify({ id: value.id, ...command.operation }));
        sessionStorage.removeItem(purchasePendingKey(scope));
        confirmed = true;
        if (!alive.current) return null;
        setReason(''); setRetained(null); setOperation(value); setNotice('Execution request received. Financial effects are not confirmed until the owner operation commits and the voucher reconciles.');
        await reopen(command.operation.voucherId);
        setNotice('Execution request received. Refresh execution to confirm its owner result and reconciliation.');
        return { kind: 'operation', value };
      }
      const value = await call<PurchaseVoucher>(command.request);
      const body = command.request.body as { expected_version?: number; calculation_hash?: string; content?: { type_revision_id: string }; type_revision_id?: string };
      const pathId = command.request.path.match(/\/vouchers\/([a-f0-9-]{36})(?:\/|$)/i)?.[1];
      verifyPurchaseVoucher(value, company, { id: pathId, type: body.type_revision_id ?? body.content?.type_revision_id, version: body.expected_version });
      if (body.calculation_hash && (value.invoice as { accepted_calculation_hash?: string } | null)?.accepted_calculation_hash !== body.calculation_hash) throw Error('The accepted calculation does not match the requested evidence.');
      if (!alive.current) return null;
      sessionStorage.removeItem(purchasePendingKey(scope)); setRetained(null); setRecord(value); setReason('');
      confirmed = true;
      // Re-read the actual returned capture, including the new acceptance revision/version.
      const refreshed = await reopen(value.id);
      setNotice(body.calculation_hash ? 'Accounting calculation accepted in revision ' + value.revision_number + '.' : value.status === 'DRAFT'
        ? 'Purchase saved as a draft. It has not been submitted or posted.' : value.status === 'SUBMITTED'
          ? 'Purchase submitted for approval. It has not been posted.' : value.status === 'APPROVED'
            ? command.request.path.endsWith('/submit') ? 'Purchase submitted and approved automatically. It is ready to post.' : 'Purchase approved. It is ready to post.'
            : 'Purchase saved. Status: ' + value.status + '.');
      return refreshed ? { kind: 'voucher', value: refreshed } : null;
    } catch (error) {
      if (!alive.current) return null;
      const problem = requestFailure(error, 'Purchase');
      if (confirmed) { setReadbackBlocked(true); setFailure('The request succeeded, but its saved details could not be refreshed. Load the saved revision before continuing.'); return null; }
      const uncertain = problem.status >= 500 || problem.status === 409 && problem.message === 'request is busy; retry with the same idempotency key';
      if (!uncertain) { sessionStorage.removeItem(purchasePendingKey(scope)); setRetained(null); }
      if (problem.status === 409 && problem.code === DUPLICATE_BILL_CODE && !command.operation && command.request.path.endsWith('/submit')) { setDuplicate({ request: command.request, matches: duplicateBillsFromFields(problem.fields), incomplete: /incomplete/i.test(problem.message) }); return null; }
      setFailure(error instanceof Error ? error.message : problem.status === 409 && /version changed/i.test(problem.message) ? 'This Purchase changed elsewhere. Your entries are retained. Load its latest revision before continuing.' : problem.message);
      return null;
    } finally { busy.current = false; if (alive.current) setPending(false); }
  }
  async function save(): Promise<PurchaseVoucher | null> {
    if (locked && !completeRun.current || !editable) return null;
    try {
      if (draft.tax.choice === '') { setTaxError(true); document.querySelector<HTMLInputElement>('[name="' + TAX_CONFIRMATION_NAME + '"]')?.focus(); return null; }
      if (taxedBill) {
        if (!taxEnabled) { setFailure('This bill carries GST, and changing it needs access to tax masters. Ask an administrator for tax read access.'); return null; }
        const found = taxResolution.problems[0];
        if (found) { setTaxError(true); focusTax(found.field); return null; }
      }
      const fields = customFields(binding.current.metadata, 'vouchers.voucher');
      const proposal = { ...draft, details: { ...draft.details, custom: customPatch(fields, draft.details.custom, binding.current.previous?.custom_fields ?? {}) } };
      if (draft.lines.some(line => line.kind === 'ITEM' && !isBlankPurchaseLine(line))) {
        // Verify current tracking requirements before preparing the draft; posting checks them again.
        if (busy.current) return null;
        busy.current = true; setPending(true);
        try {
          const context = await purchaseGoodsContext(company, draft.postingDate);
          binding.current.goods = context;
          binding.current.rounding = { places: display.amountPrecision, mode: display.roundingMode };
          const products = [...new Set(draft.lines.filter(line => line.kind === 'ITEM' && !isBlankPurchaseLine(line)).map(line => line.subject))];
          const tracking = new Map();
          for (let offset = 0; offset < products.length; offset += 5) {
            const verified = await Promise.all(products.slice(offset, offset + 5).map(item => purchaseTracking(company, item)));
            verified.forEach(profile => tracking.set(profile.itemId, profile));
          }
          binding.current.tracking = tracking;
        } finally { busy.current = false; if (alive.current) setPending(false); }
      }
      const content = purchaseInput(proposal, binding.current, taxFacts.facts);
      const result = await send(record ? { path: base + '/vouchers/' + record.id, method: 'PUT', body: { expected_version: record.row_version, content, ...(reason.trim() ? { reason: reason.trim() } : {}) } } : { path: base + '/vouchers', method: 'POST', body: content });
      return result?.kind === 'voucher' ? result.value : null;
    } catch (error) { setFailure((error as Error).message); return null; }
  }
  async function completePurchase() {
    if (completeRun.current || locked || !editable) return;
    const approvalRequired = binding.current.metadata.configuration.policy.approval_required !== false;
    const executionReady = ready.capabilities.invoice_execution && ready.capabilities.kinds.some(row => row.kind === 'PURCHASE' && row.execution_ready);
    if (!approvalRequired && (!executionReady || !allowed('post') || !allowed('operation.read'))) {
      setFailure('Purchase posting is not ready for this company. Your bill has not been submitted or posted.');
      return;
    }
    completeRun.current = true; setCompleting(true);
    try {
      // Saving a rejected or approved revision reopens it as a draft. Every later command
      // uses the confirmed version returned by the owner, never a pending React render.
      const saved = !record || dirty || record.status !== 'DRAFT' ? await save() : record;
      if (!saved) return;
      if (saved.status !== 'DRAFT') throw Error('The saved Purchase is not a draft. Load its latest revision before submitting.');
      const calculated = await call<PurchaseCalculation>({ path: base + '/vouchers/' + saved.id + '/invoice-preview', method: 'POST', body: { expected_version: saved.row_version } });
      verifyPurchaseCalculation(calculated, currency);
      const allocated = draft.details.advances.reduce((sum, row) => sum + (D.parse(row.amount) ?? 0n), 0n) + (D.parse(draft.details.payment.amount) ?? 0n);
      if (allocated > D.parse(calculated.payable)!) throw Error('The proposed settlements exceed Accounting’s calculated supplier payable. Reduce them and save again.');
      if (!alive.current) return;
      setCalculation({ value: calculated, revision: saved.revision_id });
      const acceptance = await send({ path: base + '/vouchers/' + saved.id + '/invoice-acceptance', method: 'POST', body: { expected_version: saved.row_version, calculation_hash: calculated.calculation_hash } });
      if (acceptance?.kind !== 'voucher') return;
      const acceptedVoucher = acceptance.value;
      if ((acceptedVoucher.invoice as { accepted_calculation_hash?: string } | null)?.accepted_calculation_hash !== calculated.calculation_hash) throw Error('The saved Purchase did not retain the accepted calculation.');
      const submission = await send({ path: base + '/vouchers/' + saved.id + '/submit', method: 'POST', body: { expected_version: acceptedVoucher.row_version } });
      if (submission?.kind !== 'voucher') return;
      if (approvalRequired) {
        if (submission.value.status !== 'SUBMITTED') throw Error('The Purchase did not enter the required approval workflow.');
        setNotice('Purchase submitted for approval. It has not been posted.');
        return;
      }
      if (submission.value.status !== 'APPROVED') throw Error('The Purchase was not approved by its no-approval configuration. It has not been posted.');
      const target = { voucherId: saved.id, revisionId: submission.value.revision_id };
      const posted = await send({ path: base + '/vouchers/' + saved.id + '/post', method: 'POST', body: { expected_version: submission.value.row_version } }, target);
      if (posted?.kind !== 'operation') return;
      for (let attempt = 0; attempt < 20 && alive.current; attempt++) {
        const value = await call<PurchaseOperation>({ path: base + '/voucher-operations/' + posted.value.id });
        verifyPurchaseOperation(value, target);
        if (value.id !== posted.value.id) throw Error('The posting operation identity changed.');
        setOperation(value);
        if (value.status === 'REJECTED' || value.status === 'CANCELLED') {
          settleOperation(value, submission.value);
          throw Error('Accounting refused this Purchase posting: ' + (value.rejection_code ?? 'review the operation and saved bill.'));
        }
        if (value.status === 'COMMITTED') {
          const voucher = await reopen(saved.id);
          settleOperation(value, voucher);
          if (voucher?.status === 'POSTED') { setNotice('Purchase posted and confirmed.'); return; }
        }
        await new Promise<void>(resolve => setTimeout(resolve, 1500));
      }
      if (alive.current) setNotice('Posting is still in progress. Refresh the execution before treating this Purchase as posted.');
    } catch (error) {
      if (alive.current) setFailure(error instanceof Error ? error.message : 'Purchase completion could not be confirmed. Review its saved status before trying again.');
    } finally { completeRun.current = false; if (alive.current) setCompleting(false); }
  }
  function startReplacement(source: PurchaseVoucher) {
    if (source.status !== 'REVERSED' || !canCreate || !allowed('create')) { setFailure('A reversed Purchase and create access are required for a replacement draft.'); return; }
    try {
      const result = purchaseFromVoucher(source, company, binding.current.metadata);
      const clean = newPurchaseWorkspace(today);
      const next = { ...result.draft, postingDate: today, details: { ...result.draft.details, supportingFiles: [], advances: [], payment: clean.details.payment } };
      result.binding.previous = { ...result.binding.previous!, attachments: [], links: [...(result.binding.previous?.links ?? []), { purpose: 'CORRECTION', source_voucher_id: source.id, source_revision_id: source.revision_id }] };
      binding.current = result.binding;
      setPolicy(sourcePolicy(next, livePurchasePolicy(currency, result.binding.metadata, company)));
      setDraft(next); setBaseline(JSON.stringify(next)); setRecord(null); setReplacementSource(source.id);
      setOperation(null); setCalculation(null); setReason(''); setHistory([]); setHistoryLoaded(false);
      setNotice('The original Purchase is reversed. Review this linked replacement draft, its current posting date, and any payment or supporting files before creating it.');
      const url = new URL(window.location.href); url.searchParams.delete('voucher_id'); window.history.replaceState(window.history.state, '', url);
    } catch (error) { setFailure(error instanceof Error ? error.message : 'The replacement could not be prepared.'); }
  }
  async function reversePurchase(mode: 'EDIT' | 'CANCEL', postingDate: string) {
    const source = record;
    if (!source || source.status !== 'POSTED' || !allowed('reverse') || reason.trim().length < 3) return;
    if (mode === 'EDIT' && !canCreate) { setFailure('Purchase create access is required to prepare a replacement bill.'); return; }
    try {
      // A reversal must not strand the user with a replacement this editor cannot faithfully load.
      if (mode === 'EDIT') purchaseFromVoucher(source, company, binding.current.metadata);
      const target = { voucherId: source.id, revisionId: source.revision_id };
      const requested = await send({ path: base + '/vouchers/' + source.id + '/reverse', method: 'POST', body: { expected_version: source.row_version, posting_date: postingDate, reason: reason.trim() } }, target);
      if (requested?.kind !== 'operation') return;
      for (let attempt = 0; attempt < 20 && alive.current; attempt++) {
        const operation = await call<PurchaseOperation>({ path: base + '/voucher-operations/' + requested.value.id });
        verifyPurchaseOperation(operation, target);
        setOperation(operation);
        if (operation.status === 'REJECTED' || operation.status === 'CANCELLED') { setFailure('Accounting refused this correction: ' + (operation.rejection_code ?? 'review settlements, stock and statutory dependencies.')); return; }
        if (operation.status === 'COMMITTED') {
          const original = await reopen(source.id);
          settleOperation(operation, original);
          if (original?.status === 'REVERSED') {
            if (mode === 'EDIT') startReplacement(original);
            else setNotice('Posted Purchase reversed and confirmed. The original bill and print remain in history.');
            return;
          }
        }
        await new Promise<void>(resolve => setTimeout(resolve, 1500));
      }
      setNotice('Correction is still in progress. Refresh its operation before preparing a replacement.');
    } catch (error) {
      if (alive.current) setFailure(error instanceof Error ? error.message : 'Purchase correction could not be verified. Refresh the saved operation before continuing.');
    }
  }
  async function preview() {
    if (!record || dirty || locked) return;
    await readAction(async () => {
      const value = await call<PurchaseCalculation>({ path: base + '/vouchers/' + record.id + '/invoice-preview', method: 'POST', body: { expected_version: record.row_version } });
      verifyPurchaseCalculation(value, currency);
      const allocated = draft.details.advances.reduce((sum, row) => sum + (D.parse(row.amount) ?? 0n), 0n) + (D.parse(draft.details.payment.amount) ?? 0n);
      if (allocated > D.parse(value.payable)!) throw Error('The proposed settlements exceed Accounting’s calculated supplier payable. Reduce them and save again.');
      if (alive.current) { setCalculation({ value, revision: record.revision_id }); setNotice('Accounting calculation is ready to review.'); }
    });
  }
  const askReopen = (id: string) => {
    if (locked || transient || details) return;
    if (executing) { setNotice('Resolve the pending Purchase execution before opening another bill.'); return; }
    const work = () => void readAction(() => reopen(id));
    if (dirty) setConfirmation(() => work); else work();
  };
  async function listDrafts(next?: string) {
    if (!next) { setDraftsLoaded(false); setDraftsFailure(''); setDrafts([]); setCursor(null); }
    let ran = false;
    await readAction(async () => {
      ran = true;
      try {
        const page = await call<{ items: { id: string; company_id: string; kind: string; status: string; document_date?: string | null }[]; page: { next_cursor: string | null } }>({ path: base + '/vouchers?kind=PURCHASE&status=DRAFT&limit=25' + (next ? '&cursor=' + encodeURIComponent(next) : '') });
        if (!Array.isArray(page.items) || page.items.some(row => row.company_id !== company || row.kind !== 'PURCHASE' || !trackingId.test(row.id)) || !page.page) throw Error('The saved Purchase list could not be verified.');
        if (alive.current) { setDrafts(current => next ? [...current, ...page.items] : page.items); setCursor(page.page.next_cursor); }
      } catch (error) {
        // Shown in the drawer, not as a page-wide failure that would outlive it.
        if (alive.current) setDraftsFailure(error instanceof Error ? error.message : requestFailure(error, 'Purchase').message);
      }
    });
    if (!alive.current) return;
    if (!ran) setDraftsFailure('Another request is still running. Try again in a moment.');
    setDraftsLoaded(true);
  }
  // Read on every open: a bill saved, submitted or cancelled since the last time is not in an old list.
  const openDrafts = () => { setDraftsOpen(true); void listDrafts(); };
  async function refreshExecution() {
    if (!operation || !record) return;
    await readAction(async () => {
      const value = await call<PurchaseOperation>({ path: base + '/voucher-operations/' + operation.id });
      verifyPurchaseOperation(value, { voucherId: record.id, revisionId: record.revision_id });
      if (value.id !== operation.id) throw Error('Execution identity changed. Review the saved voucher.');
      if (alive.current) setOperation(value);
      if (value.status === 'COMMITTED') { settleOperation(value, await reopen(record.id)); setNotice('Execution committed. Review the reconciled voucher and owner reports for its recorded effects.'); }
      else settleOperation(value, record);
    });
  }
  const transitions = record?.status === 'DRAFT' ? ['submit', 'cancel'] : record?.status === 'SUBMITTED' ? ['approve', 'reject', 'cancel'] : record?.status === 'APPROVED' ? ['cancel'] : record?.status === 'REJECTED' ? ['submit', 'cancel'] : [];
  async function loadHistory(next?: string) {
    if (!record) return;
    await readAction(async () => {
      const page = await call<{ items: typeof history; page: { next_cursor: string | null } }>({ path: base + '/vouchers/' + record.id + '/history?limit=50' + (next ? '&cursor=' + encodeURIComponent(next) : '') });
      if (!Array.isArray(page.items) || page.items.length > 50 || !page.page || page.page.next_cursor !== null && typeof page.page.next_cursor !== 'string' || page.items.some(row => !trackingId.test(row.id) || !trackingId.test(row.revision_id ?? ''))) throw Error('History could not be verified.');
      if (alive.current) { setHistory(current => next ? [...current, ...page.items] : page.items); setHistoryCursor(page.page.next_cursor); setHistoryLoaded(true); }
    });
  }
  async function viewRevision(revision: string) {
    if (!record || !trackingId.test(revision)) return;
    await readAction(async () => {
      const value = await call<PurchaseVoucher>({ path: base + '/vouchers/' + record.id + '/revisions/' + revision });
      verifyPurchaseVoucher(value, company, { id: record.id });
      if (value.revision_id !== revision) throw Error('The saved revision identity changed.');
      const files = ready.capabilities.purchase_supporting_files && value.attachments?.length ? await purchaseFileCall<PurchaseStoredFile[]>({ path: purchaseFileBase(company, value.id) + '?revision_id=' + revision }) : [];
      if (!Array.isArray(files) || files.length > 20) throw Error('Historical files could not be verified.'); files.forEach(file => verifyPurchaseFile(file, company, value.id));
      if (alive.current) { setSnapshotFiles(files); setSnapshot(value); }
    });
  }
  const detailsFields = customFields(binding.current.metadata, 'vouchers.voucher');
  const openDetails = () => { setDetailEdit(draft.details); setDetailRaw({}); setDetailIssue(''); setDetails(true); };
  const setDetail = (patch: Partial<PurchaseWorkspaceDraft['details']>) => setDetailEdit(current => ({ ...current, ...patch }));
  const reportDetailRaw = (field: string, message: string | null) => setDetailRaw(current => { const next = { ...current }; if (message) next[field] = message; else delete next[field]; return next; });
  const closeDetails = () => { if (filePending) return; JSON.stringify(detailEdit) !== JSON.stringify(draft.details) || Object.keys(detailRaw).length ? setDetailDiscard(true) : setDetails(false); };
  const applyDetails = () => {
    if (!editable || locked || Object.keys(detailRaw).length) return;
    if (!purchaseDueDate({ ...draft, details: detailEdit })) { setDetailIssue('Enter valid credit days, from 0 to 3650.'); return; }
    dispatch({ type: 'details', details: detailEdit }); setDetails(false);
  };
  async function refreshAdvances(next?: string) {
    await readAction(async () => {
      const page = await purchaseAdvancePage(call, company, draft.supplier, draft.payable, currency, draft.postingDate, next);
      if (!alive.current) return;
      const entries = next ? [...advances, ...page.items] : page.items;
      binding.current.advances = new Map(entries.map(row => [row.id, row]));
      setAdvances(entries); setAdvanceCursor(page.nextCursor);
      setNotice('Eligible advance balances refreshed. Accounting rechecks balances when the bill executes.');
    });
  }
  const statusView = purchaseStatusView(record?.status);
  const approvalRequired = binding.current.metadata.configuration.policy.approval_required !== false;
  const executionReady = ready.capabilities.invoice_execution && ready.capabilities.kinds.some(row => row.kind === 'PURCHASE' && row.execution_ready);
  useEffect(() => {
    if (!restoreFocus || pending) return;
    document.querySelector<HTMLElement>('[data-purchase-drafts-trigger]')?.focus();
    setRestoreFocus(false);
  }, [restoreFocus, pending]);
  // What stays in view in the action bar on a long bill: which bill, from whom, and where it stands.
  const identity = [draft.invoice.trim(), binding.current.sources.get(draft.supplier)?.label].filter(Boolean).join(' · ');
  const state = pending ? 'Contacting the service…' : retained ? 'Request outcome needs confirmation' : dirty ? 'Unsaved changes' : record ? statusView.label + ' · saved' : 'Not saved yet';
  // A finished bill cannot be edited by anyone, which is a different thing to say than "you may not create vouchers".
  const finished = !!record && ['POSTED', 'CANCELLED', 'REVERSED'].includes(record.status);
  // Printing is of the last confirmed save: its identifiers, never the editor's provisional values.
  const print = purchasePrintAction({ saved: record ? { id: record.id, revisionId: record.revision_id, version: record.row_version } : null, permitted: permission => permissions.includes(permission), dirty,
    uncertain: !!retained || recoveryBlocked || operationBlocked || readbackBlocked, busy: pending, executing: !!executing, editorOpen: details || !!snapshot || transient });
  const header = <PurchasePageHeader title={record ? 'Purchase bill · revision ' + record.revision_number : 'New purchase'} status={record?.status ?? null} typeName={ready.type.name ?? ready.type.code} currency={currency} canStartNew={!!record && canCreate} locked={locked} onDrafts={openDrafts} print={print} />;
  return <section className="janso-page" aria-label="Purchase voucher">
    {navigation}
    {!loaded ? <>{header}<p role="status">Opening saved Purchase…</p></> : <PurchaseWorkspace today={today} canCreate={editable} policy={livePolicy} supplierLookup={supplierLookup} controller={{ live: true, draft, dispatch, readOnly: !editable || locked, pending, dirty, title: record ? 'Purchase bill · revision ' + record.revision_number : 'New purchase', note: identity ? identity + ' · ' + state : state, onTransientChange: transientChanged,
      batchPrompt, closeBatchPrompt: () => setBatchPrompt(null),
      reviewNotice: finished ? <Notice tone="info" title="Review only">This purchase is {statusView.label.toLowerCase()} and can no longer be edited here.</Notice>
        : executing ? <Notice tone="info" title="Posting in progress">This purchase is being posted, so it cannot be changed until that finishes.</Notice>
        : record && !allowed('edit') ? <Notice tone="info" title="Review only">You can review this purchase, but changing it needs edit access to vouchers.</Notice> : undefined,
      total: currentCalculation?.payable, linesLabel: taxedBill ? 'Lines before GST' : undefined, header, quickCreate,
      banner: () => <>
        {record && editable && ['SUBMITTED', 'APPROVED'].includes(record.status) ? <Notice tone="info" title="Editing a submitted bill">Saving changes opens a new draft revision. Submit the revised bill again to post it.</Notice> : null}
        {failure ? <Notice tone="danger" title="Purchase needs attention"><p>{failure}</p>{elsewhere && failure === PURCHASE_BROADER_CAPTURE ? <a className="janso-link" href={'/vouchers/' + elsewhere}>Open it in voucher review</a> : null}{record && !retained ? <Button variant="ghost" disabled={pending} onClick={() => readbackBlocked ? void readAction(() => reopen(record.id)) : askReopen(record.id)}>Load latest saved revision</Button> : null}</Notice> : null}
        {operationBlocked ? <Notice title="Execution recovery needs verification">Writes stay locked until the retained execution is verified.<Button variant="ghost" disabled={pending} onClick={() => setOperationAttempt(value => value + 1)}>Retry execution recovery</Button></Notice> : null}
        {notice ? <div role="status"><Notice title="Purchase status">{notice}</Notice></div> : null}
        {retained ? <Notice tone="warning" title="Confirm the previous request"><p>The outcome is not confirmed. Your exact request and idempotency key are retained for this actor, company and year. Retry the same request before making another change.</p><Button disabled={pending} onClick={() => void perform(retained)}>Retry previous request</Button></Notice> : null}
      </>,
      sections: <>
        <PurchaseTermsCard draft={draft} taxConfirmed={draft.tax.choice === 'NONE'} taxError={taxError && !taxedBill} editable={editable} locked={locked} onEdit={openDetails} taxHint={taxHint}
          onTaxConfirmed={confirmed => changeTax({ choice: confirmed ? 'NONE' : taxAvailable && taxFacts.facts.companies !== null ? 'FORWARD' : '' })}>
          {taxedBill ? taxEnabled
            ? <PurchaseTaxSection company={company} tax={draft.tax} resolution={taxResolution} facts={taxFacts.facts} failures={taxFacts.failures} loading={taxFacts.loading} accounts={taxAccounts} supplierId={draft.supplier}
              editable={editable} locked={locked} showProblems={taxError} canManage={permissions.includes('accounting.tax.manage')} onChange={changeTax} onReload={taxFacts.reload} />
            : <Notice tone="info" title="This bill carries GST">{draft.tax.choice === 'REVERSE' ? 'The GST is charged under reverse charge.' : 'The supplier charged the GST.'} Its registrations are not shown because your access does not include tax masters.</Notice>
            : null}
        </PurchaseTermsCard>
        {record && currentCalculation ? <PurchaseCalculationCard calculation={currentCalculation} accepted={accepted} differs={differs} revision={record.revision_number}
          lines={draft.lines.filter(line => !isBlankPurchaseLine(line)).map(line => ({ key: purchaseWireKey(binding.current, line.key), label: line.label || line.description }))} /> : null}
        {record && !retained ? <PurchaseLifecycle duplicates={similar} record={record} accepted={accepted} locked={locked} dirty={dirty} editable={editable} approvalRequired={approvalRequired} allowed={allowed} reason={reason} onReason={setReason} transitions={transitions}
          today={today} onReverse={(mode, postingDate) => void reversePurchase(mode, postingDate)} onReplacement={() => startReplacement(record)}
          onTransition={action => void send({ path: base + '/vouchers/' + record.id + '/' + action, method: 'POST', body: { expected_version: record.row_version, ...(reason.trim() ? { reason: reason.trim() } : {}) } })}
          executionReady={executionReady} executing={!!executing}
          onPost={() => void send({ path: base + '/vouchers/' + record.id + '/post', method: 'POST', body: { expected_version: record.row_version } }, { voucherId: record.id, revisionId: record.revision_id })}
          history={history} historyLoaded={historyLoaded} historyCursor={historyCursor} onHistory={next => void loadHistory(next)} onRevision={revision => void viewRevision(revision)} operation={operation}
          onRefresh={() => void refreshExecution()} onRecover={() => { if (operation) void send({ path: base + '/voucher-operations/' + operation.id + '/recover', method: 'POST', body: { expected_version: operation.row_version } }, { voucherId: record.id, revisionId: record.revision_id }); }} /> : null}
      </>,
      actions: ({ validate, review }) => <>
        <Button variant="ghost" disabled={locked} onClick={review}>Review bill</Button>
        {editable ? <SplitButton label="Purchase actions" variant="primary"
          primary={{ id: 'save', label: record ? 'Update' : 'Create', disabledReason: !dirty && record ? 'No changes to save.' : undefined }}
          items={[{ id: 'complete', label: record ? 'Update and Submit' : 'Create and Submit', disabledReason: !allowed('edit') || !allowed('submit') || !allowed('read') ? 'Purchase edit, read and submit access is required.' : !approvalRequired && !executionReady ? 'Purchase invoice posting is not active.' : !approvalRequired && (!allowed('operation.read') || !allowed('post')) ? 'Purchase posting and operation read access is required.' : undefined }]}
          disabledReason={locked ? 'Wait for the current Purchase action to finish.' : undefined}
          loading={pending || completing} loadingLabel="Completing Purchase…"
          onSelect={action => { if (!validate()) return; if (action === 'complete') void completePurchase(); else if (action === 'save') void save(); }} /> : null}
        {record && ['DRAFT', 'REJECTED', 'SUBMITTED', 'APPROVED'].includes(record.status) && allowed('read') ? <Button variant="ghost" disabled={locked || dirty} onClick={() => void preview()}>Calculate saved bill</Button> : null}
        {currentCalculation && allowed('edit') && record?.status === 'DRAFT' ? <Button disabled={locked} onClick={() => void send({ path: base + '/vouchers/' + record.id + '/invoice-acceptance', method: 'POST', body: { expected_version: record.row_version, calculation_hash: currentCalculation.calculation_hash } })}>Accept Accounting calculation</Button> : null}
      </> }} />}
    {!loaded && failure ? <Notice tone="danger" title="Saved Purchase could not be opened">{failure}{elsewhere && failure === PURCHASE_BROADER_CAPTURE ? <a className="janso-link" href={'/vouchers/' + elsewhere}>Open it in voucher review</a> : null}<Button variant="ghost" disabled={locked} onClick={() => void readAction(() => reopen(resume))}>Try opening again</Button>{operationBlocked ? <Button variant="ghost" disabled={pending} onClick={() => setOperationAttempt(value => value + 1)}>Retry execution recovery</Button> : null}</Notice> : null}
    {creating?.kind === 'supplier' ? <SupplierQuickCreate company={company} companyCountry={companyCountry ?? 'IN'} canTax={canQuickTax} onCreated={createdSupplier} onClose={() => setCreating(null)} /> : null}
    {creating?.kind === 'account' ? <ExpenseAccountQuickCreate company={company} onCreated={created => createdAccount(creating.target, created)} onClose={() => setCreating(null)} /> : null}
    <PurchaseDraftsDrawer open={draftsOpen} onClose={() => setDraftsOpen(false)} drafts={drafts} loaded={draftsLoaded} cursor={cursor} locked={locked} failure={draftsFailure} resume={resume} onResume={setResume} onOpen={id => { setDraftsOpen(false); setRestoreFocus(true); askReopen(id); }} onMore={next => void listDrafts(next)} onRetry={() => void listDrafts()} />
    <Drawer open={details} title="Bill details & terms" onClose={closeDetails} footer={<><Button variant="ghost" disabled={filePending} onClick={closeDetails}>{editable ? 'Cancel' : 'Done'}</Button>{editable ? <Button disabled={locked || filePending || !!Object.keys(detailRaw).length} onClick={applyDetails}>Apply bill details</Button> : null}</>}><div className="janso-entry-detail janso-flow"><p>Apply these details to the bill, then save its next draft revision.</p>
      {failure ? <Notice tone="danger" title="Details need attention">{failure}</Notice> : null}
      <TextField label="Credit days" inputMode="numeric" maxLength={4} value={detailEdit.termsDays} error={detailIssue || undefined} disabled={!editable || locked} onChange={event => { setDetailIssue(''); setDetail({ termsDays: event.target.value }); }} />
      <Select label="Credit terms basis" value={detailEdit.termsBasis} disabled={!editable || locked} options={[{ value: 'INVOICE_DATE', label: 'Supplier invoice date' }, ...(binding.current.metadata.native.properties?.credit_terms_date ? [{ value: 'POSTING_DATE', label: 'Posting date' }] : [])]} onChange={value => setDetail({ termsBasis: value as 'INVOICE_DATE' | 'POSTING_DATE' })} />
      <AmountField label="Supplier-declared total" value={detailEdit.declaredTotal} precision={4} error={detailRaw.total} disabled={!editable || locked || !nativeProperties(binding.current.metadata.native.properties?.invoice).supplier_declared_total || !!nativeProperties(binding.current.metadata.native.properties?.invoice).supplier_declared_total?.readOnly} onUnstorable={message => reportDetailRaw('total', message)} onChange={value => setDetail({ declaredTotal: value })} />
      {nativeProperties(binding.current.metadata.native.properties?.invoice).supplier_difference_reason ? <TextField label="Supplier total difference reason" value={detailEdit.comparisonReason} maxLength={500} disabled={!editable || locked || !!nativeProperties(binding.current.metadata.native.properties?.invoice).supplier_difference_reason?.readOnly} hint={'Accounting permits a difference up to ' + format.money(binding.current.metadata.configuration.policy.invoice?.supplier_difference_limit ?? '0') + ', with a reason. This does not change the calculated tax or payable.'} onChange={event => setDetail({ comparisonReason: event.target.value })} /> : null}
      {nativeProperties(binding.current.metadata.native.properties?.invoice).rounding_account_id ? <SearchSelect label="Rounding difference account" value={detailEdit.roundingAccount || null} loadOptions={subjectLookup} scopeKey={company + ':rounding'} selected={detailEdit.roundingAccount ? { id: detailEdit.roundingAccount, label: binding.current.sources.get(detailEdit.roundingAccount)?.label ?? detailEdit.roundingAccount } : null} disabled={!editable || locked || !!nativeProperties(binding.current.metadata.native.properties?.invoice).rounding_account_id?.readOnly || !!nativeProperties(binding.current.metadata.native.properties?.invoice).rounding_account_version?.readOnly} onChange={id => { if (!id) { setDetail({ roundingAccount: '' }); return; } void readAction(async () => { const account = await purchaseSource(company, 'expenses', id); if (!alive.current) return; binding.current.sources.set(account.id, account); setDetailEdit(current => ({ ...current, roundingAccount: account.id })); }); }} /> : null}
      {nativeProperties(binding.current.metadata.native.properties?.invoice).allocations ? <fieldset className="janso-entry-detail__group"><legend>Supplier advances to apply</legend><p>Proposed allocations are saved with the bill. Balances are checked again by Accounting when it executes.</p>
        <Button variant="ghost" disabled={locked || !draft.supplier || !draft.payable} onClick={() => void refreshAdvances()}>Refresh eligible supplier advances</Button>
        {advances.filter(row => row.supplier === draft.supplier && row.payable === draft.payable && row.asOf === draft.postingDate).map(advance => { const selected = detailEdit.advances.find(row => row.id === advance.id); return <div key={advance.id} className="janso-entry-detail__group"><Checkbox checked={!!selected} disabled={!editable || locked} hint={'Available ' + format.money(advance.remaining)} onChange={event => setDetail({ advances: event.target.checked ? [...detailEdit.advances, { id: advance.id, amount: advance.remaining }] : detailEdit.advances.filter(row => row.id !== advance.id) })}>{advance.label}</Checkbox>
          {selected ? <AmountField label={'Advance allocation · ' + advance.label} value={selected.amount} error={detailRaw['advance:' + advance.id]} disabled={!editable || locked} precision={4} onUnstorable={message => reportDetailRaw('advance:' + advance.id, message)} onChange={amount => setDetail({ advances: detailEdit.advances.map(row => row.id === advance.id ? { ...row, amount } : row) })} /> : null}</div>; })}
        {detailEdit.advances.filter(selected => !advances.some(row => row.id === selected.id && row.supplier === draft.supplier && row.payable === draft.payable && row.asOf === draft.postingDate)).map(selected => <div key={selected.id}><p>Saved allocation {format.money(selected.amount)} · {selected.id}. Refresh its eligible balance before saving changes.</p><Button variant="ghost" disabled={!editable || locked} onClick={() => setDetail({ advances: detailEdit.advances.filter(row => row.id !== selected.id) })}>Remove retained allocation</Button></div>)}
        {advanceCursor ? <Button variant="ghost" disabled={locked} onClick={() => void refreshAdvances(advanceCursor)}>More supplier advances</Button> : null}
      </fieldset> : null}
      {nativeProperties(binding.current.metadata.native.properties?.invoice).tenders ? <fieldset className="janso-entry-detail__group"><legend>Proposed payment instruction</legend><p>This instruction is saved with the bill. It does not send a bank transfer, confirm payment or establish clearance.</p>
        <AmountField label="Proposed payment amount" value={detailEdit.payment.amount} precision={4} error={detailRaw.payment} disabled={!editable || locked} onUnstorable={message => reportDetailRaw('payment', message)} onChange={amount => setDetail({ payment: { ...detailEdit.payment, amount } })} />
        <Select label="Proposed payment method" value={detailEdit.payment.method} disabled={!editable || locked} options={[{ value: 'BANK', label: 'Bank transfer instruction' }, { value: 'CASH', label: 'Cash' }]} onChange={method => setDetail({ payment: { ...detailEdit.payment, method: method as 'BANK' | 'CASH', account: '' } })} />
        <SearchSelect label="Proposed payment account" value={detailEdit.payment.account || null} disabled={!editable || locked} scopeKey={company + ':' + detailEdit.payment.method} loadOptions={paymentLookup} selected={detailEdit.payment.account ? { id: detailEdit.payment.account, label: binding.current.paymentAccounts?.get(detailEdit.payment.account)?.label ?? detailEdit.payment.account } : null} onChange={id => { if (!id) { setDetail({ payment: { ...detailEdit.payment, account: '' } }); return; } void readAction(async () => { const account = await purchasePaymentAccount(call, company, currency, id); if (!alive.current) return; binding.current.paymentAccounts ??= new Map(); binding.current.paymentAccounts.set(account.id, account); setDetailEdit(current => ({ ...current, payment: { ...current.payment, account: account.id } })); }); }} />
        <TextField label="Proposed payment reference" value={detailEdit.payment.reference} disabled={!editable || locked} maxLength={120} onChange={event => setDetail({ payment: { ...detailEdit.payment, reference: event.target.value } })} />
      </fieldset> : null}
      <TextField label="Purchase notes" value={detailEdit.notes} disabled={!editable || locked || !binding.current.metadata.native.properties?.narration || !!binding.current.metadata.native.properties?.narration?.readOnly} maxLength={2000} onChange={event => setDetail({ notes: event.target.value })} />
      <CustomFields fields={detailsFields} values={detailEdit.custom} disabled={!editable || locked} onChange={custom => setDetail({ custom })} />
      <PurchaseSupportingFiles key={record?.id ?? 'new'} company={company} voucher={record?.id} revision={record?.revision_id} version={record?.row_version} enabled={!!ready.capabilities.purchase_supporting_files} editable={editable && !!binding.current.metadata.native.properties?.attachments && !binding.current.metadata.native.properties?.attachments?.readOnly} disabled={locked} files={detailEdit.supportingFiles ?? []} linkedKeys={binding.current.previous?.attachments?.map(file => file.object_key)} onChange={supportingFiles => setDetail({ supportingFiles })} onBusy={setFilePending} />
    </div></Drawer>
    <Drawer open={!!snapshot} title={snapshot ? 'Purchase revision ' + snapshot.revision_number : 'Saved Purchase revision'} onClose={() => { if (!filePending) setSnapshot(null); }} footer={<Button disabled={filePending} onClick={() => setSnapshot(null)}>Done reviewing revision</Button>}>
      {snapshot ? <div className="janso-entry-detail janso-flow"><p>Read-only saved capture. The current bill and your unsaved entries stay open behind this review.</p><VoucherSummary company={company} voucher={snapshot} />
        <PurchaseSupportingFiles key={snapshot.revision_id} company={company} voucher={snapshot.id} revision={snapshot.revision_id} enabled={!!ready.capabilities.purchase_supporting_files} editable={false} disabled={false} files={snapshotFiles} linkedKeys={snapshotFiles.map(file => file.object_key)} onChange={() => undefined} onBusy={setFilePending} />
      </div> : null}
    </Drawer>
    <DuplicateBillModal matches={duplicate?.matches ?? null} incomplete={duplicate?.incomplete} busy={pending} onCancel={() => setDuplicate(null)} onConfirm={confirmDuplicate} />
    <Modal open={detailDiscard} title="Discard bill detail changes?" onClose={() => setDetailDiscard(false)} footer={<><Button variant="ghost" onClick={() => setDetailDiscard(false)}>Keep editing details</Button><Button onClick={() => { setDetailDiscard(false); setDetails(false); }}>Discard detail changes</Button></>}><p>The bill will keep its previously applied details.</p></Modal>
    <Modal open={!!confirmation} title="Leave unsaved Purchase entries?" onClose={() => setConfirmation(null)} footer={<><Button variant="ghost" onClick={() => setConfirmation(null)}>Keep editing</Button><Button onClick={() => { const proceed = confirmation; setConfirmation(null); proceed?.(); }}>Discard unsaved entries</Button></>}><p>The saved revision will remain on the server. Unsaved entries on this page will be discarded.</p></Modal>
  </section>;
}
