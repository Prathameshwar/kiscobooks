'use client';

import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from 'react';
import {
  Button,
  ConfirmDialog,
  Notice,
  PageHeader,
  PageNavigation,
  SectionHeader,
  useDisplayConfig,
  useFormatters,
  useGranted,
} from '@janso/ui';
import type { SearchSelectLoader } from '@janso/ui';
import type { EntryMode, SalesEntryPolicy } from '../lib/sales-entry-policy';
import {
  draftProblems,
  initialDraft,
  problemTarget,
  reduceDraft,
  sameAmount,
  type CustomerCredit,
  type DraftAction,
  type DraftLine,
  type DraftProblem,
  type ProblemTarget,
  type SalesDraft,
} from '../lib/sales-entry-draft';
import type { SubjectResolver } from '../lib/sales-entry-columns';
import { previewInvoice, previewProblems, type InvoicePreview } from '../lib/sales-entry-preview';
import { SalesEntryHeader } from './SalesEntryHeader';
import { SalesLineGrid, enteredLineCount } from './SalesLineGrid';
import { SalesEntryTotals } from './SalesEntryTotals';
import { SalesComponentsDrawer } from './SalesComponentsDrawer';
import { SalesSettlementDrawer, type AdvanceLoader } from './SalesSettlementDrawer';
import { SalesReviewDialog } from './SalesReviewDialog';
import { SalesShortcutsDialog } from './SalesShortcutsDialog';

/**
 * Raising a sales bill.
 *
 * Three regions, and the shape is the decision: a sticky document bar, a scrolling line grid and
 * a sticky totals rail, on one page. Not a wizard — `Stepper` and `WizardLayout` both exist and
 * are right for company onboarding, where a reader passes through once. A billing clerk raises
 * dozens of these a day, and a wizard turns one dense screen into four pages of waiting. Tally's
 * speed comes from exactly that single screen and it costs nothing to match.
 *
 * Inside `ConsoleShell`, not the designer's full-bleed group. The invoice designer renders
 * outside the shell because a canvas needs the viewport; a money document is the opposite case —
 * the company chip and the financial-year chip are what a reader must not lose sight of while
 * entering one, and the rail is how they switch away deliberately instead of by accident.
 *
 * Everything that changes the bill goes through one reducer (`sales-entry-draft`), everything it
 * computes comes from one pure preview (`sales-entry-preview`), and this component only arranges
 * them. Two side panels hold the components and the payment, so the main surface stays the lines.
 */

type Panel = 'components' | 'payment' | 'review' | 'shortcuts' | null;

/** What a connected save reports: stored, or why not, in a sentence. */
export type SaveOutcome = { readonly stored: true } | { readonly stored: false; readonly message: string };

/** The control inside a cell or a field wrapper — the wrapper itself may not take focus. */
function focusWithin(host: HTMLElement | null): boolean {
  const control = host?.matches('input, select, textarea, button')
    ? host
    : host?.querySelector<HTMLElement>('input, select, textarea, button');
  if (!control) return false;
  control.scrollIntoView?.({ block: 'center' });
  control.focus();
  return true;
}

export function SalesEntryPage({
  policy,
  today,
  loadCustomers,
  loadSubjects,
  resolveSubject,
  resolveCustomerState,
  resolveCustomerCredit,
  resolveCustomer,
  loadAddresses,
  resolveAddressState,
  priceLevels,
  rail,
  actions,
  status,
  onDraftChange,
  loadAdvances,
  companyState,
  canCreate,
  onSaveDraft,
  navigation,
}: {
  policy: SalesEntryPolicy;
  navigation?: ReactNode;
  /** Injected, never `new Date()` inside render: a date that changes between two renders of the
   * same form is how a document acquires a different posting date than the one shown. */
  today: string;
  loadCustomers: SearchSelectLoader;
  /**
   * A loader *factory*, taking the mode.
   *
   * The mode lives in the draft, which lives here, so the route cannot know it — and the real
   * lookup will ask two different services depending on it. A factory keeps that decision at
   * the one place that has the answer.
   */
  loadSubjects: (mode: EntryMode) => SearchSelectLoader;
  /** What choosing a master supplies: price, unit, classification, resolved tax rate. */
  resolveSubject?: SubjectResolver;
  /** The chosen customer's state, which decides intra- or inter-state supply. */
  resolveCustomerState?: (customerId: string) => string;
  /** The chosen customer's credit limit and open balance, as the party master projects them. */
  resolveCustomerCredit?: (customerId: string) => CustomerCredit | null;
  /**
   * The chosen customer's state and credit, from the masters, answered later. The draft takes
   * them only if the customer is still the one they were asked for.
   */
  resolveCustomer?: (customerId: string) => Promise<{ customerState: string; customerCredit: CustomerCredit | null } | null>;
  /** The company's price levels, for the header. */
  priceLevels?: readonly { value: string; label: string }[];
  /** More of the totals rail — the service's own calculation, once there is one. */
  rail?: ReactNode;
  /** More of the action bar, before Save — calculate, accept, submit. */
  actions?: (state: { draft: SalesDraft; savable: boolean; stored: boolean }) => ReactNode;
  /** A sentence about where the bill stands with the service, above the form. */
  status?: ReactNode;
  /** Told after each change — a connected page prices against the customer the draft now has. */
  onDraftChange?: (draft: SalesDraft, preview: InvoicePreview) => void;
  /** The chosen customer's addresses, for bill-to and ship-to. */
  loadAddresses?: (customerId: string) => SearchSelectLoader;
  /** An address's state: a ship-to's is the place of supply. */
  resolveAddressState?: (addressId: string) => string;
  /** A customer's open advances, as Accounting projects them. */
  loadAdvances?: AdvanceLoader;
  /** The issuing company's registered state. */
  companyState: string;
  /** `vouchers.create` for the open company. Presentation only; the service decides. */
  canCreate: boolean;
  /**
   * Hands a checked draft to the vouchers write path. **Absent today**, and the page says so:
   * Save then checks the bill and stores nothing, so the leave guard stays on — a "saved"
   * that only meant "checked" would let someone close the tab on a bill that exists nowhere.
   */
  onSaveDraft?: (draft: SalesDraft) => void | Promise<SaveOutcome>;
}) {
  const [draft, dispatch] = useReducer(reduceDraft, undefined, () => initialDraft(policy, today));
  const [panel, setPanel] = useState<Panel>(null);
  /** The revision last "saved" — so the leave guard and the footer know what is unsaved. */
  const [savedAt, setSavedAt] = useState<number | null>(null);
  /** A save in flight, and why the last one failed. */
  const [saving, setSaving] = useState(false);
  const [saveFailure, setSaveFailure] = useState<string | null>(null);
  const config = useDisplayConfig();
  const { money, date } = useFormatters();
  const [openLine, setOpenLine] = useState<string | null>(null);
  /**
   * Figure fields holding text that cannot be stored, by `lineKey|field`.
   *
   * Such text stays on screen while the draft keeps the last storable value, so without this a
   * cell could show `2450.12345` while Save handed over `2450`. Each becomes a problem, which
   * blocks Save and names the place like any other.
   */
  const [unstorable, setUnstorable] = useState<ReadonlyMap<string, DraftProblem>>(() => new Map());
  const reportUnstorable = useCallback((lineKey: string | null, field: string, message: string | null) => {
    const id = `${lineKey ?? ''}|${field}`;
    setUnstorable((current) => {
      if (message === null && !current.has(id)) return current;
      if (message !== null && current.get(id)?.message === message) return current;
      const next = new Map(current);
      if (message === null) next.delete(id);
      else next.set(id, { severity: 'error', lineKey, field, message });
      return next;
    });
  }, []);

  /*
   * The provisional preview, recomputed on every change. Exact and cheap — a fifty-line bill is
   * a few hundred bigint operations — so there is no debounce to make a total lag behind what
   * was just typed.
   */
  const preview = useMemo(
    () =>
      previewInvoice(draft, policy, {
        companyState,
        places: config.amountPrecision,
        formatMoney: (value) => money(value, { display: 'none' }),
      }),
    [companyState, config.amountPrecision, draft, money, policy],
  );

  /**
   * Everything wrong, from both places that can find it: the draft's own rules, and the ones
   * only arithmetic reveals — more received than the bill, say.
   */
  const granted = useGranted();
  const told = useRef(onDraftChange);
  told.current = onDraftChange;
  useEffect(() => {
    told.current?.(draft, preview);
  }, [draft, preview]);
  const problems = useMemo(
    () => [
      ...unstorable.values(),
      // The reader's grants, for the checks the policy ties to one — overriding a list price.
      ...draftProblems(draft, policy, {
        granted: (key) => granted(key),
        formatMoney: (value) => money(value, { display: 'none' }),
        formatDate: date,
      }),
      ...previewProblems(preview),
    ],
    [date, draft, granted, money, policy, preview, unstorable],
  );
  const firstError = problems.find((problem) => problem.severity === 'error');

  /*
   * A drawer holding a figure that cannot be stored stays open.
   *
   * Its field keeps the text while the bill keeps the last storable prefix — `12..5` typed, `12`
   * held. Closing unmounted the field, which took its problem with it, so the bill silently went
   * on holding 12. Refusing the close keeps the field, its error and the blocked Save together
   * until the reader fixes or clears it. Document-level figures (no line) only live in drawers.
   */
  const [closeRefused, setCloseRefused] = useState(0);
  const panelHoldsUnstorable = [...unstorable.values()].some((problem) => problem.lineKey === null);
  const closePanel = useCallback(() => {
    if (panelHoldsUnstorable) {
      setCloseRefused((count) => count + 1);
      document.querySelector<HTMLElement>('[role="dialog"] [aria-invalid="true"]')?.focus();
      return;
    }
    setCloseRefused(0);
    setPanel(null);
  }, [panelHoldsUnstorable]);
  const savable = canCreate && !firstError;
  const entered = enteredLineCount(draft);
  const checked = savedAt !== null && savedAt === draft.revision;
  /* Stored only once something stores it; until then every change is unsaved work. */
  const unsaved = draft.revision > 0 && !(checked && onSaveDraft !== undefined);
  /*
   * What is *shown* as wrong. Nothing, until the reader has done something: a form that opens
   * with "Choose the customer" in red and "Add at least one line" in the rail is scolding someone
   * for not having started. Save stays disabled either way — this only governs the shouting.
   */
  const shown: readonly DraftProblem[] = draft.revision === 0 ? [] : problems;

  /*
   * A chosen customer brings its state with it, which is what decides CGST + SGST against IGST.
   * Wrapped here rather than in the header so the header stays a form of fields and the party
   * master's facts arrive in one place.
   */
  const dispatchWithParty = useCallback(
    (action: DraftAction) => {
      if (action.type === 'header' && 'customerId' in action.patch) {
        const id = action.patch.customerId;
        dispatch({
          ...action,
          patch: {
            ...action.patch,
            ...(resolveCustomerState ? { customerState: id ? resolveCustomerState(id) : '' } : {}),
            customerCredit: id && resolveCustomerCredit ? resolveCustomerCredit(id) : null,
          },
        });
        if (id && resolveCustomer) {
          void resolveCustomer(id).then((facts) => {
            if (facts) dispatch({ type: 'resolveCustomer', customerId: id, patch: facts });
          });
        }
        return;
      }
      dispatch(action);
    },
    [resolveCustomer, resolveCustomerCredit, resolveCustomerState],
  );

  /*
   * A different price level re-prices the lines whose price came from the list. A rate the
   * reader typed stays theirs, but it is now measured against the new list — an override is a
   * departure from the price in force, not from one that used to be.
   */
  const reprice = useCallback(
    async (priceLevel: string) => {
      if (!resolveSubject) return;
      const patches: Record<string, Partial<DraftLine>> = {};
      for (const line of draft.lines) {
        if (!line.subjectId) continue;
        // A tier or last-sold price came from somewhere else; the price level does not own it.
        if (line.rateSource === 'QUANTITY_TIER' || line.rateSource === 'LAST_SOLD') continue;
        const listed = (await resolveSubject(line.subjectId, priceLevel))?.rate ?? '';
        if (line.rateSource === 'PRICE_LEVEL') {
          // No price at the new level: the old level's figure stays, but it is no longer "List".
          patches[line.key] = listed
            ? { rate: listed, resolvedRate: listed, rateSource: 'PRICE_LEVEL' }
            : { resolvedRate: '', rateSource: 'MANUAL' };
        } else if (line.resolvedRate !== '') {
          // A typed rate is measured against the new list — and is no override if it now *is* it.
          patches[line.key] =
            listed && sameAmount(line.rate, listed)
              ? { resolvedRate: listed, rateSource: 'PRICE_LEVEL', rateReason: '' }
              : { resolvedRate: listed };
        }
      }
      if (Object.keys(patches).length > 0) dispatch({ type: 'patchLines', patches });
    },
    [draft.lines, resolveSubject],
  );

  /**
   * A change that reinterprets every line already entered asks first.
   *
   * Switching to tax-inclusive turns a 1,000 rate from "1,000 plus tax" into "1,000 with tax
   * inside", and switching mode re-reads which lines are items and which accounts — one stray
   * arrow key on the mode used to do either to a fifty-line bill without a word.
   */
  const [pending, setPending] = useState<{ title: string; body: string; action: DraftAction } | null>(null);
  const headerDispatch = useCallback(
    (action: DraftAction) => {
      const lines = enteredLineCount(draft);
      if (lines > 0 && action.type === 'mode' && action.mode !== draft.mode) {
        setPending({
          title: `Switch this bill to ${action.mode === 'ACCOUNTS' ? 'accounts' : action.mode === 'MIXED' ? 'mixed' : 'items'}?`,
          body: `The ${lines} ${lines === 1 ? 'line' : 'lines'} already entered stay, but a line that does not fit the new mode is marked and left out of the totals until it is changed.`,
          action,
        });
        return;
      }
      if (
        lines > 0 &&
        action.type === 'header' &&
        'taxInclusive' in action.patch &&
        action.patch.taxInclusive !== draft.taxInclusive
      ) {
        setPending({
          title: action.patch.taxInclusive ? 'Treat the rates as including tax?' : 'Treat the rates as before tax?',
          body: action.patch.taxInclusive
            ? 'Every rate already entered is then read as tax-inclusive: tax is taken out of it, so the taxable value of each line falls and the total stays the rate.'
            : 'Every rate already entered is then read as before tax: tax is added to it, so each line and the total go up.',
          action,
        });
        return;
      }
      dispatchWithParty(action);
      if (action.type === 'header' && action.patch.priceLevel !== undefined && action.patch.priceLevel !== draft.priceLevel) {
        void reprice(action.patch.priceLevel);
      }
    },
    [dispatchWithParty, draft, reprice],
  );

  const onSave = useCallback(async () => {
    if (!savable || saving) return;
    setPanel(null);
    setSaveFailure(null);
    const outcome = onSaveDraft?.(draft);
    if (!(outcome instanceof Promise)) {
      // Not connected, and it says so rather than appearing to work: the revision is recorded as
      // *checked*, and the leave guard stays on.
      setSavedAt(draft.revision);
      return;
    }
    /*
     * Connected: the revision counts as saved only once the service has stored it. A failure is
     * said beside Save, and the bill stays exactly as it was typed.
     */
    setSaving(true);
    try {
      const result = await outcome;
      if (result.stored) setSavedAt(draft.revision);
      else setSaveFailure(result.message);
    } finally {
      setSaving(false);
    }
  }, [draft, onSaveDraft, savable, saving]);

  /*
   * Ctrl+S saves the draft. The browser's own "save page" on that chord is useless on a form and
   * every desktop accounting product binds it; a clerk's hand is already there.
   */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 's') {
        event.preventDefault();
        onSave();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onSave]);

  /*
   * Leaving with unsaved work asks first. A fifty-line bill lost to a stray back-swipe is the
   * single most expensive accident this page can have, and the browser's prompt is the only one
   * that fires on a tab close.
   */
  useEffect(() => {
    if (!unsaved) return;
    const onLeave = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      // Legacy browsers need a value set; modern ones show their own wording regardless.
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', onLeave);
    /*
     * The back link and the breadcrumbs navigate inside the app, where `beforeunload` never
     * fires — the easiest way to lose a bill was the link at the top of it. A capture listener on
     * the document runs before the router's own click handler and can stop it.
     */
    const onClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = (event.target as Element | null)?.closest?.('a[href]');
      if (!(link instanceof HTMLAnchorElement)) return;
      if (link.target === '_blank' || link.hasAttribute('download')) return;
      const url = new URL(link.href, window.location.href);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      if (!window.confirm('Leave this bill? What you have entered is not saved.')) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    document.addEventListener('click', onClick, true);
    return () => {
      window.removeEventListener('beforeunload', onLeave);
      document.removeEventListener('click', onClick, true);
    };
  }, [unsaved]);

  /**
   * Take the reader to where a problem is fixed: a line's first cell, a field of the document
   * bar, or the drawer the problem lives in.
   *
   * A cell is either the control itself or a host wrapping one (the item lookup). One selector
   * list would return the host first, in document order, and a span takes no focus — so the
   * host is found first, then the control at or inside it.
   */
  const goTo = useCallback((target: ProblemTarget, field?: string) => {
    if (target.kind === 'panel') {
      // The drawers edit; a reader without create access has nothing to do in one.
      if (canCreate) setPanel(target.panel);
      return;
    }
    if (target.kind === 'detail') {
      // A missing reason is answered in the line's detail, not in a cell.
      setOpenLine(target.lineKey);
      return;
    }
    if (target.kind === 'field') {
      focusWithin(document.querySelector<HTMLElement>(`[data-entry-field="${CSS.escape(target.field)}"]`));
      return;
    }
    // The cell the problem is in when it is one — "Enter a billed quantity" lands on Billed,
    // not on the item — and the row's first cell otherwise.
    const row = `[data-entry-row="${CSS.escape(target.lineKey)}"]`;
    const cell = field ? document.querySelector<HTMLElement>(`${row}[data-entry-col="${CSS.escape(field)}"]`) : null;
    focusWithin(cell ?? document.querySelector<HTMLElement>(row));
  }, [canCreate]);

  const targetOf = useCallback((problem: DraftProblem) => problemTarget(problem, draft), [draft]);
  const blockedAt = firstError ? problemTarget(firstError, draft) : null;

  /*
   * A new bill starts at the customer, as Tally's voucher screen starts at the party: it is the
   * first thing every bill needs, and the one the tax split depends on. Once, on arrival — never
   * again, which would steal focus from wherever the reader went next.
   */
  const arrived = useRef(false);
  useEffect(() => {
    if (arrived.current) return;
    arrived.current = true;
    focusWithin(document.querySelector<HTMLElement>('[data-entry-field="customerId"]'));
  }, []);

  /*
   * Ctrl+/ lists every key, where Google's and GitHub's products put the same list. Not over an
   * open drawer or dialog: a modal stacked on a drawer leaves two focus traps, and closing the
   * top one returned focus to a page the drawer still covered.
   */
  const overlayOpen = panel !== null || openLine !== null;
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === '/') {
        event.preventDefault();
        if (!overlayOpen) setPanel('shortcuts');
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [overlayOpen]);

  /*
   * The document bar's height, for the totals rail's sticky offset: both are sticky, the bar is
   * drawn above, and at `top: 0` it covered the first three totals. Measured because the bar
   * wraps with the window and grows with a warning; a fixed guess would be wrong at every other
   * width. Set as a custom property on the page — computed geometry, like the designer's.
   */
  const pageRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const page = pageRef.current;
    const bar = page?.querySelector<HTMLElement>('.janso-entry__bar');
    if (!page || !bar || typeof ResizeObserver === 'undefined') return;
    const sync = () => {
      const sticky = getComputedStyle(bar).position === 'sticky';
      page.style.setProperty('--janso-entry-bar-h', sticky ? `${bar.offsetHeight}px` : '0px');
    };
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(bar);
    // A short window unsticks the bar (entry.css) without changing its size.
    window.addEventListener('resize', sync);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', sync);
    };
  }, []);

  const note =
    draft.revision === 0
      ? 'Nothing entered yet.'
      : `${entered} line${entered === 1 ? '' : 's'} · ${
          !checked ? 'not saved yet' : onSaveDraft ? 'saved' : 'checked, not stored'
        }`;

  return (
    <div className="janso-page" ref={pageRef}>
      {navigation ?? <PageNavigation
        back={{ href: '/vouchers', label: 'voucher drafts' }}
        breadcrumbs={[{ label: 'Voucher drafts', href: '/vouchers' }, { label: 'New sales bill' }]}
      />}
      <PageHeader
        title="New sales bill"
        lede="Bill a customer for goods or services. Nothing is posted until the invoice is accepted."
      />

      {!canCreate ? (
        <Notice tone="warning">
          You can see this form but not raise a bill with it. Raising one needs voucher create
          access for this company.
        </Notice>
      ) : null}

      {status}
      {saveFailure ? (
        <Notice tone="danger" title="The draft was not saved">
          {saveFailure}
        </Notice>
      ) : null}

      {savedAt !== null && !onSaveDraft ? (
        <Notice tone="info">
          This form is not connected to the vouchers service yet, so nothing was stored. The entry
          surface is being built first, on purpose.
        </Notice>
      ) : null}

      <SalesEntryHeader
        draft={draft}
        policy={policy}
        problems={shown}
        dispatch={headerDispatch}
        loadCustomers={loadCustomers}
        {...(priceLevels ? { priceLevels } : {})}
        {...(loadAddresses ? { loadAddresses } : {})}
        {...(resolveAddressState ? { resolveAddressState } : {})}
        canEdit={canCreate}
      />

      {/* The frame is the size container the layout answers to: the rail goes under the lines
        * when the *content* is narrow, whatever the window — a collapsed or expanded app rail
        * changes this width by 200px at the same viewport. */}
      <div className="janso-entry-frame">
        <div className="janso-entry">
          <section className="janso-entry__lines" aria-label="Invoice lines">
            <SectionHeader
              title="Lines"
              description={
                draft.mode === 'ACCOUNTS'
                  ? 'Account and service amounts. No stock moves on an accounts-only bill.'
                  : 'Items, what moves and what is charged for. They are separate quantities.'
              }
            />
            {entered === 0 && canCreate ? (
              /* Said once, where entry starts, and gone as soon as a line exists: the keys are what
               * make this page fast, and nobody discovers a key by looking at a blank row. */
              <p className="janso-entry__hint">
                Find an item to start. Tab moves across, Enter moves down and Ctrl+Enter adds a
                line; Ctrl+/ lists every key.
              </p>
            ) : null}
            <SalesLineGrid
              draft={draft}
              policy={policy}
              problems={problems}
              dispatch={dispatch}
              loadSubjects={loadSubjects(draft.mode)}
              canEdit={canCreate}
              preview={preview}
              openLine={openLine}
              onOpenLine={setOpenLine}
              onCellUnstorable={reportUnstorable}
              {...(resolveSubject ? { resolveSubject } : {})}
            />
          </section>

          <SalesEntryTotals
            preview={preview}
            policy={policy}
            problems={shown}
            targetOf={targetOf}
            onGoTo={goTo}
            {...(canCreate
              ? {
                  onEditComponents: () => setPanel('components'),
                  onEditPayment: () => setPanel('payment'),
                }
              : {})}
          >
            {rail}
          </SalesEntryTotals>
        </div>
      </div>

      {panel === 'components' ? (
        <SalesComponentsDrawer
          draft={draft}
          policy={policy}
          problems={problems}
          dispatch={dispatch}
          onUnstorable={(field, message) => reportUnstorable(null, field, message)}
          onClose={closePanel}
        />
      ) : null}

      {panel === 'payment' ? (
        <SalesSettlementDrawer
          draft={draft}
          policy={policy}
          preview={preview}
          problems={problems}
          dispatch={dispatch}
          {...(loadAdvances ? { loadAdvances } : {})}
          onUnstorable={(field, message) => reportUnstorable(null, field, message)}
          onClose={closePanel}
        />
      ) : null}

      {panel === 'shortcuts' ? <SalesShortcutsDialog onClose={() => setPanel(null)} /> : null}

      <ConfirmDialog
        open={pending !== null}
        title={pending?.title ?? ''}
        confirmLabel="Change it"
        cancelLabel="Keep as it is"
        onConfirm={() => {
          if (pending) dispatchWithParty(pending.action);
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      >
        {pending?.body}
      </ConfirmDialog>

      {panel === 'review' ? (
        <SalesReviewDialog
          draft={draft}
          preview={preview}
          policy={policy}
          problems={problems}
          canSave={savable}
          onSave={onSave}
          onClose={() => setPanel(null)}
        />
      ) : null}

      <div className="janso-entry__actions">
        {/* The total, always in view. Under the lines on a laptop the rail scrolls away with a
          * long bill, and "what does this come to" is the question asked most while typing. */}
        {entered > 0 ? (
          <span className="janso-entry__actions-total">
            <span className="janso-entry__total-label">Total</span>{' '}
            <span className="janso-entry__total-value">
              {preview.total === null ? '—' : money(preview.total)}
            </span>
          </span>
        ) : null}
        <span className="janso-entry__actions-note">
          {note}
          {/* Always a sentence beside a disabled button, never the button alone: "why can I not
            * press this" is the question a disabled control asks and must answer. */}
          {canCreate && firstError && draft.revision > 0 ? (
            <span className="janso-entry__blocked">
              {' · Before saving: '}
              {blockedAt ? (
                <>
                  <button
                    type="button"
                    className="janso-entry__goto"
                    onClick={() => goTo(blockedAt, firstError.field)}
                  >
                    {blockedAt.label}
                  </button>{' '}
                </>
              ) : null}
              {firstError.message}
            </span>
          ) : null}
        </span>
        {/* Announced, because a save that only changes a word in a footer is a save a
          * screen-reader user cannot tell happened. Empty until the current revision is saved,
          * so each save is a fresh announcement. */}
        <span className="janso-visually-hidden" role="alert">
          {closeRefused > 0 && panelHoldsUnstorable
            ? 'A figure in this panel cannot be stored. Correct or clear it before closing.'
            : ''}
        </span>
        <span className="janso-visually-hidden" role="status">
          {checked ? (onSaveDraft ? 'Draft saved.' : 'Checked. Nothing was stored; this form is not connected yet.') : ''}
        </span>
        {/* The buttons as one group that never splits: a long "Before saving" sentence used to
          * push Preview and Save onto a row of their own, away from Keys. */}
        <span className="janso-entry__actions-buttons">
          <Button variant="ghost" onClick={() => setPanel('shortcuts')}>
            Keys <kbd className="janso-command__kbd" aria-hidden="true">Ctrl /</kbd>
          </Button>
          {/* No Issue action, and the rail says why: issuing a sales invoice needs the statutory
            * numbering profile, which is not released, and the legal allocator belongs to
            * Accounting. A button that 400s is worse than an absent one. */}
          <Button variant="ghost" disabled={draft.revision === 0} onClick={() => setPanel('review')}>
            Preview
          </Button>
          {actions?.({ draft, savable, stored: checked && onSaveDraft !== undefined })}
          <Button disabled={!savable || saving} aria-busy={saving || undefined} onClick={onSave}>
            {/* The overlay keycap, not `Kbd`: that one is styled in `designer.css`, which only the
              * editor route group loads, and would render here as bare text. */}
            Save draft <kbd className="janso-command__kbd" aria-hidden="true">Ctrl S</kbd>
          </Button>
        </span>
      </div>
    </div>
  );
}
