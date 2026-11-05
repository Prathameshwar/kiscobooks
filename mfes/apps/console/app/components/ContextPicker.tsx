'use client';

import { useEffect, useRef, useState } from 'react';
import { CalendarIcon, ContextSwitcher, PinIcon, PlusIcon, StoreIcon, formatDate, useDisplayConfig, type ContextAction, type ContextOption } from '@janso/ui';
import { companyCall, companyFailure, openCompany, setDefaultCompany } from '../lib/company-api';
import { SEARCH_MIN, companyChoices, sessionCompanyListPath, type CompanyChoice, type SessionCompanyPage } from '../lib/company-list';
import { goTo } from '../lib/navigate';
import type { CompanyContext } from '../lib/company-context';
import type { Session } from '../session';
import { organisationPermissions } from '../lib/session-authority';

const SEARCH_DEBOUNCE = 250;

/** What chose the open company, in the rail's words. Identity says which rule it was. */
const SOURCE_NOTE: Partial<Record<Session['companySource'], string>> = {
  // Never claim a stored default the user has not set: the last two are guesses the rail owns
  // up to, and saying which one it was is what makes "Set as my default" worth offering.
  membership: 'Opened the company you work in',
  first: 'Opened your first company',
};

/**
 * The rail's company and financial-year context.
 *
 * Two switchers, one state machine: both open a company through `openCompany` — the one place
 * that records a selection, sends a company wanting verification to auth, and re-renders the
 * page — and both report their failure in the same place.
 *
 * The search is **server-side**, because the rail shows the first fifty companies by code and a
 * tenant may have more. It is debounced and the in-flight request is dropped on the next
 * keystroke by the effect's own cleanup, so a slow answer cannot overwrite a newer one.
 */
export function ContextPicker({ session, context }: { session: Session; context: CompanyContext }) {
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<CompanyChoice[] | null>(null);
  /*
   * Two failures, two places. A failed *search* belongs in the open panel beside the box that
   * caused it; a failed *switch* cannot, because choosing an option closes the panel — so it
   * belongs in the rail, where it survives long enough to be read.
   */
  const [searchFailure, setSearchFailure] = useState<string | null>(null);
  const [switchFailure, setSwitchFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const switching = useRef(false);
  /** Set once "Set as my default" has succeeded, so the rail stops offering it mid-page. */
  const [defaulted, setDefaulted] = useState<string | null>(null);
  const display = useDisplayConfig();

  useEffect(() => {
    const term = query.trim();
    if (term.length < SEARCH_MIN) {
      setFound(null);
      setSearchFailure(null);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setSearchFailure(null);
      companyCall<SessionCompanyPage>('identity', sessionCompanyListPath({ q: term, limit: 20 }), { signal: controller.signal })
        .then((page) => { if (!controller.signal.aborted) setFound(companyChoices(page)); })
        .catch((error) => {
          if (controller.signal.aborted) return;
          setFound([]);
          setSearchFailure(companyFailure(error).message);
        });
    }, SEARCH_DEBOUNCE);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  async function open(company: string, fiscalYear?: string): Promise<void> {
    if (switching.current) return;
    switching.current = true;
    setPending(true);
    setSwitchFailure(null);
    const failure = await openCompany(company, fiscalYear);
    if (!failure) return;
    setSwitchFailure(failure.message);
    switching.current = false;
    setPending(false);
  }

  /**
   * Stores the open company as this user's default (`PATCH /v1/session/preferences`).
   *
   * Nothing is re-rendered on success: the page is already showing that company, and the only
   * thing that changed is which one opens next time. Reloading to move a badge would throw away
   * whatever the operator was in the middle of.
   */
  async function makeDefault(company: string): Promise<void> {
    if (switching.current) return;
    switching.current = true;
    setPending(true);
    setSwitchFailure(null);
    try {
      await setDefaultCompany(company);
      setDefaulted(company);
    } catch (value) {
      setSwitchFailure(companyFailure(value).message);
    }
    setPending(false);
    switching.current = false;
  }

  const companies = found ?? context.companies;
  const openId = session.company.id;
  const isDefault = (id: string) => (defaulted ? defaulted === id : companies.some((item) => item.id === id && item.isDefault));
  const companyOptions: ContextOption[] = companies.map((item) => ({
    id: item.id,
    name: item.name,
    code: item.code || undefined,
    // Said before the row is chosen, not after the switch appears to have failed.
    note: item.requiresStepUp ? 'Asks you to sign in again' : undefined,
    badge: isDefault(item.id) ? 'Default' : undefined,
  }));
  const actions: ContextAction[] = [
    ...(openId && !isDefault(openId) ? [{ id: 'default', label: 'Set as my default', icon: <PinIcon /> }] : []),
    ...(organisationPermissions(session).includes('company.create') ? [{ id: 'create', label: 'Create company', icon: <PlusIcon /> }] : []),
    { id: 'manage', label: 'Manage companies', icon: <StoreIcon />, permission: 'company.read' },
  ];

  function act(id: string): void {
    if (id === 'default') {
      if (openId) void makeDefault(openId);
      return;
    }
    goTo(id === 'create' ? '/companies/new' : '/companies');
  }

  // The span in the company's own date format, like every other date on the page.
  const years: ContextOption[] = context.fiscalYears.map((year) => ({
    id: year.id,
    name: year.code || formatDate(year.startDate, display),
    code: `${formatDate(year.startDate, display)} → ${formatDate(year.endDate, display)}`,
    note: year.current ? 'Contains today' : year.open ? 'Has an open period' : undefined,
  }));

  return (
    <div className="janso-switcher">
      <ContextSwitcher
        label="Switch company"
        overline={session.company.code ?? session.organisation.code}
        name={session.company.name}
        options={companyOptions}
        selectedId={session.company.id}
        onSelect={(id) => void open(id)}
        search={{ label: 'Search companies', value: query, onChange: setQuery, placeholder: 'Search companies' }}
        status={{
          loading: pending,
          error: searchFailure ?? undefined,
          empty: query.trim().length >= SEARCH_MIN ? 'No company matches that search.' : context.companiesNote ?? undefined,
        }}
        actions={actions}
        onAction={act}
      />
      {/*
        * Present only for an actor who can read the fiscal calendar (`period.read`). This is
        * display and filter context — it never becomes a posting date (CLAUDE.md invariant 4).
        */}
      {session.permissions.includes('period.read') && context.fiscalYears.length > 0 && session.company.id ? (
        <ContextSwitcher
          compact
          icon={<CalendarIcon />}
          label="Switch financial year"
          overline="Financial year"
          name={context.fiscalYear?.code ?? 'Select a year'}
          options={years}
          selectedId={context.fiscalYear?.id}
          onSelect={(id) => void open(session.company.id as string, id)}
          status={{ loading: pending, empty: context.fiscalNote ?? undefined }}
        />
      ) : null}
      {switchFailure ? (
        <p className="console-context__error" role="alert">
          {switchFailure}
        </p>
      ) : null}
      {/*
        * A company that exists and is simply locked behind a fresh sign-in. Routed through the
        * same `openCompany` as every other switch, which is the one place that recognises
        * `step_up_required` and hands the browser to auth.
        */}
      {session.stepUpCompanyId && !session.company.id ? (
        <p className="console-context__note">
          Your company needs you to sign in again.{' '}
          <button type="button" className="janso-link" disabled={pending} onClick={() => void open(session.stepUpCompanyId as string)}>
            Verify to open it
          </button>
        </p>
      ) : null}
      {SOURCE_NOTE[session.companySource] ? (
        <p className="console-context__note">{SOURCE_NOTE[session.companySource]}</p>
      ) : null}
    </div>
  );
}
