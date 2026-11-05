'use client';

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Notice,
  Select,
  Skeleton,
  asErrorStatus,
  businessToday,
  useDisplayConfig,
  useFormatters,
} from '@janso/ui';
import * as D from '../lib/fixed-decimal';
import { companyPath, salesCall } from '../lib/sales-entry-api';
import { bindingFrom, policyFromConfiguration, type SalesBinding } from '../lib/sales-entry-connection';
import type { SalesDraft } from '../lib/sales-entry-draft';
import {
  addressLoader,
  advanceLoader,
  customerLoader,
  loadBookAccounts,
  loadCompany,
  loadConfiguration,
  loadPriceLevels,
  loadSalesTypes,
  resolveCustomer,
  resolveSubject,
  subjectLoader,
  type BookAccounts,
  type CompanyFacts,
  type CustomerFacts,
  type Item,
  type SalesType,
} from '../lib/sales-entry-lookups';
import { SAMPLE_SALES_POLICY, type EntryMode, type SalesEntryPolicy } from '../lib/sales-entry-policy';
import type { InvoicePreview } from '../lib/sales-entry-preview';
import { toVoucherInput, type SubjectRef } from '../lib/sales-entry-wire';
import type { RequestFailure } from '../lib/service-call';
import { SalesEntryPage, type SaveOutcome } from './SalesEntryPage';

/**
 * The sales bill, connected to Vouchers, Accounting and Catalog.
 *
 * The page is unchanged: this supplies what it reads from — the effective Sales policy, the
 * masters, the company's facts — and what it hands over to: a draft created, then edited as
 * revisions, then calculated, accepted and submitted by the service. Issue stays absent: the
 * service refuses Sales issuance until the statutory profile is released (open question 1).
 */

type Voucher = { id: string; row_version: number; status: string; revision_number: number };
type Calculation = {
  calculation_hash: string;
  currency: string;
  commercial_total: string;
  tax_total: string;
  rounding: string;
  payable: string;
};

type Ready = {
  readonly company: CompanyFacts;
  readonly type: SalesType;
  readonly policy: SalesEntryPolicy;
  readonly binding: SalesBinding;
  readonly accounts: BookAccounts;
  readonly priceLevels: readonly { value: string; label: string }[];
};

type Load =
  | { readonly state: 'loading' }
  | { readonly state: 'failed'; readonly failure: RequestFailure }
  | { readonly state: 'none' }
  | { readonly state: 'choose'; readonly types: readonly SalesType[] }
  | { readonly state: 'ready'; readonly ready: Ready };

const failureOf = (error: unknown): RequestFailure =>
  error && typeof error === 'object' && 'status' in error
    ? (error as RequestFailure)
    : { status: 500, message: error instanceof Error ? error.message : 'The sales bill could not be loaded. Try again.' };

/** A failed call, as the sentence the reader needs: what happened and what to do. */
export function sayFailure(failure: RequestFailure): string {
  if (failure.status === 409) return 'This draft was changed elsewhere since it was opened. Reload it before saving again.';
  if (failure.status === 403) return 'You do not have access to do this for this company.';
  if (failure.status === 401) return 'Your session has ended. Sign in again to continue.';
  const fields = failure.fields ? Object.values(failure.fields).join(' ') : '';
  return [failure.message, fields].filter(Boolean).join(' ');
}

export function SalesEntryConnected({ company, canCreate, initialTypeId, navigation }: { company: string; canCreate: boolean; initialTypeId?: string; navigation?: ReactNode }) {
  const { timezone } = useDisplayConfig();
  const today = useMemo(() => businessToday(timezone), [timezone]);
  const [load, setLoad] = useState<Load>({ state: 'loading' });
  const [chosen, setChosen] = useState<string | null>(initialTypeId ?? null);
  const [attempt, setAttempt] = useState(0);

  /* ---- the bill type and its policy ---- */
  useEffect(() => {
    let live = true;
    setLoad({ state: 'loading' });
    (async () => {
      const [facts, types] = await Promise.all([loadCompany(company, today), loadSalesTypes(company, initialTypeId)]);
      if (types.length === 0) return { state: 'none' } as const;
      const type = types.length === 1 ? types[0]! : types.find((row) => row.id === chosen);
      if (!type) return { state: 'choose', types } as const;
      const evidence = await loadConfiguration(company, type.id, today);
      const binding = bindingFrom(evidence, type);
      const [accounts, priceLevels] = await Promise.all([
        loadBookAccounts(company, binding),
        loadPriceLevels(company).catch(() => []),
      ]);
      return {
        state: 'ready',
        ready: {
          company: facts,
          type,
          // What the service does not decide yet comes from the page's defaults; see the adapter.
          policy: policyFromConfiguration(evidence, SAMPLE_SALES_POLICY),
          binding,
          accounts,
          priceLevels,
        },
      } as const;
    })().then(
      (next) => live && setLoad(next),
      (error) => live && setLoad({ state: 'failed', failure: failureOf(error) }),
    );
    return () => {
      live = false;
    };
  }, [attempt, chosen, company, today, initialTypeId]);

  if (load.state === 'loading') {
    // The skeleton is hidden from assistive tech; the status says what is happening.
    return (
      <>
        {navigation}
        <p className="janso-visually-hidden" role="status">
          Loading the sales bill
        </p>
        <Skeleton lines={8} />
      </>
    );
  }
  if (load.state === 'failed') {
    return (
      <>{navigation}<ErrorState
        status={asErrorStatus(load.failure.status)}
        detail={sayFailure(load.failure)}
        action={
          <Button variant="ghost" onClick={() => setAttempt((count) => count + 1)}>
            Try again
          </Button>
        }
      /></>
    );
  }
  if (load.state === 'none') {
    return (
      <>{navigation}<EmptyState
        title="No Sales bill type is set up"
        body="A sales bill is raised under an active Sales voucher type. Set one up in voucher configuration, then come back."
      /></>
    );
  }
  if (load.state === 'choose') {
    return (
      <>{navigation}<Select
        label="Bill type"
        value=""
        options={[
          { value: '', label: 'Choose a bill type' },
          ...load.types.map((type) => ({ value: type.id, label: type.name ?? type.code ?? 'Sales' })),
        ]}
        onChange={(id) => setChosen(id || null)}
      /></>
    );
  }
  return <ConnectedBill key={load.ready.type.id} company={company} canCreate={canCreate} today={today} ready={load.ready} navigation={navigation} />;
}

function ConnectedBill({
  company,
  canCreate,
  today,
  ready,
  navigation,
}: {
  company: string;
  canCreate: boolean;
  today: string;
  ready: Ready;
  navigation?: ReactNode;
}) {
  const { money } = useFormatters();
  const { binding, accounts, policy } = ready;
  const currency = ready.company.currency;

  /* ---- what the masters said, by id, for the save ---- */
  const subjects = useRef(new Map<string, SubjectRef>());
  const sources = useRef(new Map<string, 'ITEM' | 'ACCOUNT'>());
  const items = useRef(new Map<string, Item>());
  const customers = useRef(new Map<string, CustomerFacts>());
  const addressStates = useRef(new Map<string, string>());
  /** Stable UUIDs for the page's keys, across every save of this draft. */
  const keys = useRef(new Map<string, string>());
  const keyFor = useCallback((pageKey: string) => {
    const existing = keys.current.get(pageKey);
    if (existing) return existing;
    const made = crypto.randomUUID();
    keys.current.set(pageKey, made);
    return made;
  }, []);
  const latest = useRef<{ draft: SalesDraft | null; preview: InvoicePreview | null }>({ draft: null, preview: null });

  /* ---- the voucher, once saved; its calculation, once asked for ---- */
  const [voucher, setVoucher] = useState<Voucher | null>(null);
  const [calculation, setCalculation] = useState<{ value: Calculation; version: number } | null>(null);
  const [workflowFailure, setWorkflowFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState<'calculate' | 'accept' | 'submit' | null>(null);
  /** One idempotency key per distinct request, reused if that same request is retried. */
  const receipt = useRef<{ signature: string; key: string } | null>(null);
  const keyForRequest = (signature: string) => {
    if (receipt.current?.signature !== signature) receipt.current = { signature, key: crypto.randomUUID() };
    return receipt.current.key;
  };

  const loadCustomers = useMemo(() => customerLoader(company), [company]);
  const loadSubjects = useCallback(
    (mode: EntryMode) => subjectLoader(company, mode, binding, sources.current, items.current),
    [binding, company],
  );
  const resolve = useCallback(
    async (id: string, priceLevel?: string) => {
      const kind = sources.current.get(id) ?? 'ITEM';
      const resolved = await resolveSubject(
        company,
        id,
        kind,
        {
          date: latest.current.draft?.documentDate || today,
          currency,
          partyId: latest.current.draft?.customerId ?? null,
          priceLevelId: priceLevel || null,
          accounts,
        },
        items.current,
      ).catch(() => null);
      if (!resolved) return null;
      subjects.current.set(id, resolved.ref);
      return resolved.patch;
    },
    [accounts, company, currency, today],
  );
  const resolveParty = useCallback(
    async (id: string) => {
      const facts = await resolveCustomer(company, id, { binding, currency, date: today }, addressStates.current).catch(() => null);
      if (!facts) return null;
      customers.current.set(id, facts);
      return { customerState: facts.state, customerCredit: facts.credit };
    },
    [binding, company, currency, today],
  );
  const loadAddresses = useCallback(
    (customerId: string) => addressLoader(company, customerId, addressStates.current),
    [company],
  );
  const resolveAddressState = useCallback((id: string) => addressStates.current.get(id) ?? '', []);
  const loadAdvances = useMemo(() => advanceLoader(company, today), [company, today]);

  /* ---- save: create, then revise ---- */
  const onSaveDraft = useCallback(
    async (draft: SalesDraft): Promise<SaveOutcome> => {
      const customer = draft.customerId ? customers.current.get(draft.customerId) : undefined;
      // Goods: ship-to, then bill-to, then the customer. A services bill: bill-to, then the customer.
      const place = draft.shipToState || draft.billToState || draft.customerState || null;
      const wire = toVoucherInput(draft, {
        binding,
        currency,
        customer: customer?.ref ?? null,
        subjects: subjects.current,
        tenderAccounts: accounts.tenders,
        rounding: accounts.rounding,
        companyRegistrationId: ready.company.registrationId,
        placeOfSupply: place && /^IN-[A-Z0-9]{1,3}$/.test(place) ? place : null,
        partyLineKey: keyFor('party-line'),
        billReference: `SB-${keyFor('bill-reference').slice(0, 8).toUpperCase()}`,
        keyFor,
        roundOff: latest.current.preview?.roundOff ?? null,
      });
      if (!wire.ok) return { stored: false, message: wire.problems.join(' ') };
      const body = voucher
        ? { expected_version: voucher.row_version, reason: 'Edited on the sales bill', content: wire.body }
        : wire.body;
      const path = voucher ? companyPath(company, `/vouchers/${voucher.id}`) : companyPath(company, '/vouchers');
      const method = voucher ? 'PUT' : 'POST';
      try {
        const saved = await salesCall<Voucher>('vouchers', {
          path,
          method,
          body,
          key: keyForRequest(JSON.stringify({ path, method, body })),
        });
        receipt.current = null;
        setVoucher(saved);
        // A new revision is a new bill to the calculator: an earlier result no longer applies.
        setCalculation(null);
        setWorkflowFailure(null);
        return { stored: true };
      } catch (error) {
        const failure = failureOf(error);
        // A server failure keeps the key, so pressing Save again replays rather than duplicates.
        if (failure.status < 500) receipt.current = null;
        return { stored: false, message: sayFailure(failure) };
      }
    },
    [accounts, binding, company, currency, keyFor, ready.company.registrationId, voucher],
  );

  /* ---- calculate, accept, submit ---- */
  const command = useCallback(
    async <T,>(name: 'calculate' | 'accept' | 'submit', path: string, body: unknown, keyed: boolean): Promise<T | null> => {
      setBusy(name);
      setWorkflowFailure(null);
      try {
        const result = await salesCall<T>('vouchers', {
          path,
          method: 'POST',
          body,
          ...(keyed ? { key: keyForRequest(JSON.stringify({ path, body })) } : {}),
        });
        receipt.current = null;
        return result;
      } catch (error) {
        const failure = failureOf(error);
        if (failure.status < 500) receipt.current = null;
        setWorkflowFailure(sayFailure(failure));
        return null;
      } finally {
        setBusy(null);
      }
    },
    [],
  );
  const calculate = async () => {
    if (!voucher) return;
    const result = await command<Calculation>(
      'calculate',
      companyPath(company, `/vouchers/${voucher.id}/invoice-preview`),
      { expected_version: voucher.row_version },
      false,
    );
    if (result) setCalculation({ value: result, version: voucher.row_version });
  };
  const accept = async () => {
    if (!voucher || !calculation) return;
    const result = await command<Voucher>(
      'accept',
      companyPath(company, `/vouchers/${voucher.id}/invoice-acceptance`),
      { expected_version: voucher.row_version, calculation_hash: calculation.value.calculation_hash },
      true,
    );
    if (result) setVoucher(result);
  };
  const submit = async () => {
    if (!voucher) return;
    const result = await command<Voucher>(
      'submit',
      companyPath(company, `/vouchers/${voucher.id}/submit`),
      { expected_version: voucher.row_version },
      true,
    );
    if (result) setVoucher(result);
  };

  const current = calculation && voucher && calculation.version === voucher.row_version ? calculation.value : null;
  const accepted = Boolean(calculation && voucher && voucher.row_version > calculation.version && voucher.status === 'DRAFT');
  const submitted = voucher?.status === 'SUBMITTED' || voucher?.status === 'APPROVED';
  const provisional = latest.current.preview?.total ?? null;
  const differs = current && provisional !== null && D.parse(current.payable) !== D.parse(provisional);

  return (
    <SalesEntryPage
      navigation={navigation}
      policy={policy}
      today={today}
      loadCustomers={loadCustomers}
      loadSubjects={loadSubjects}
      resolveSubject={resolve}
      resolveCustomer={resolveParty}
      loadAddresses={loadAddresses}
      resolveAddressState={resolveAddressState}
      loadAdvances={loadAdvances}
      priceLevels={ready.priceLevels}
      companyState={ready.company.state}
      canCreate={canCreate}
      onSaveDraft={onSaveDraft}
      onDraftChange={(draft, preview) => {
        latest.current = { draft, preview };
      }}
      status={
        <>
          {voucher ? (
            <Notice tone={submitted ? 'success' : 'info'}>
              {submitted
                ? `Submitted for approval as revision ${voucher.revision_number}. Issuing waits for the statutory numbering profile.`
                : `Saved as a draft, revision ${voucher.revision_number}${accepted ? ', with its calculation accepted' : ''}.`}
            </Notice>
          ) : null}
          {workflowFailure ? (
            <Notice tone="danger" title="The service did not take this step">
              {workflowFailure}
            </Notice>
          ) : null}
        </>
      }
      rail={
        current ? (
          <div className="janso-entry__rail-card" role="group" aria-label="Service calculation">
            <p className="janso-entry__rail-heading">
              <Badge tone="success">Service</Badge>
              Calculated by the service
            </p>
            <p className="janso-entry__total">
              <span className="janso-entry__total-label">Taxable value</span>
              <span className="janso-entry__total-value">{money(current.commercial_total, { display: 'none' })}</span>
            </p>
            <p className="janso-entry__total">
              <span className="janso-entry__total-label">Tax</span>
              <span className="janso-entry__total-value">{money(current.tax_total, { display: 'none' })}</span>
            </p>
            <p className="janso-entry__total">
              <span className="janso-entry__total-label">Round off</span>
              <span className="janso-entry__total-value">{money(current.rounding, { display: 'none' })}</span>
            </p>
            <p className="janso-entry__total janso-entry__total--grand">
              <span className="janso-entry__total-label">Payable</span>
              <span className="janso-entry__total-value">{money(current.payable)}</span>
            </p>
            {differs ? (
              <p className="janso-entry__number-note">
                The page estimated {money(provisional!)}. The service’s figure is the one the bill is accepted at.
              </p>
            ) : null}
          </div>
        ) : null
      }
      actions={({ stored }) =>
        voucher && stored && !submitted ? (
          <>
            {!current && !accepted ? (
              <Button variant="ghost" aria-busy={busy === 'calculate' || undefined} disabled={busy !== null} onClick={calculate}>
                Calculate
              </Button>
            ) : null}
            {current && !accepted ? (
              <Button variant="ghost" aria-busy={busy === 'accept' || undefined} disabled={busy !== null} onClick={accept}>
                Accept calculation
              </Button>
            ) : null}
            {accepted ? (
              <Button aria-busy={busy === 'submit' || undefined} disabled={busy !== null} onClick={submit}>
                Submit
              </Button>
            ) : null}
          </>
        ) : null
      }
    />
  );
}
