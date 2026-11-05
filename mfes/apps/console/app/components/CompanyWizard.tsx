'use client';

import { useEffect, useRef, useState, type FormEvent } from 'react';
import {
  Badge,
  businessToday,
  Button,
  Checkbox,
  ChoiceCard,
  customCondition,
  CustomFields,
  customValue,
  DEFAULT_DISPLAY_CONFIG,
  FieldGroup,
  FieldPair,
  formatDate,
  formatMoney,
  formatQuantity,
  Notice,
  PageNavigation,
  resolvedDisplay,
  ReviewList,
  Select,
  Skeleton,
  TextField,
  ThemeSwitcher,
  type StepperStep,
  type Tone,
  WizardLayout,
  Wordmark,
} from '@janso/ui';
import type { components } from '@janso/api-client/identity';
import { companyCall, companyFailure, openCompany } from '../lib/company-api';
import {
  DATE_FORMATS,
  DATETIME_FORMATS,
  DIGIT_GROUPINGS,
  ENTITY_TYPES,
  LOCALES,
  NEGATIVE_FORMATS,
  SEPARATORS,
  SYMBOL_POSITIONS,
  capabilityTree,
  supportedTimezones,
  ROUNDING_MODES,
  TAX_TREATMENTS,
  entityTypeLabel,
  roundingLabel,
  taxSystemLabel,
  taxSystemOptions,
  taxTreatmentLabel,
} from '../lib/company-labels';
import { FormatPreview } from './FormatPreview';
import { CompanyRegistrationFields, newTaxRegistration } from './CompanyRegistrationFields';
import { AutomaticCompanySetup } from './AutomaticCompanySetup';
import {
  NEUTRAL_SUGGESTION,
  codeSuffix,
  companyCode,
  companyShortName,
  dependsOn,
  featureLabel,
  fiscalYearLabel,
  fiscalYearSpan,
  fiscalYearStartYear,
  jurisdictionDraft,
  withDependencies,
  validFiscalAnchor,
  type Draft,
  type FeatureChoice,
} from '../lib/company-defaults';
import { goTo } from '../lib/navigate';
import type { Session } from '../session';
import { companyCustomFields, type CompanyField } from '../lib/company-form';
import { organisationPermissions } from '../lib/session-authority';
import { companyBootstrapAccess } from '../lib/company-bootstrap';
import { administrationBackLabel, administrationLink, administrationReturn } from '../lib/administration-navigation';
import { useUnsavedChanges } from '../lib/use-unsaved-changes';

type Country = components['schemas']['CountryChoice'];
type Currency = components['schemas']['CurrencyChoice'];
type State = components['schemas']['identity__schemas__reference__StateChoice'];
type Company = components['schemas']['CompanyDetail'];

/** Resolved once: the tz list does not change while a form is open. */
const TIMEZONES = supportedTimezones();
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const PRECISIONS = [0, 1, 2, 3, 4].map((value) => ({ value: String(value), label: String(value) }));

/** The required fields of each step, so a visited step can say what it is still missing. */
const STEPS: readonly { label: string; required: readonly (keyof Draft)[] }[] = [
  // No `code`: it is generated from the legal name rather than asked for (`companyCode`).
  { label: 'Business', required: ['legal_name', 'display_name', 'entity_type'] },
  { label: 'Location and tax', required: ['country_code', 'state_code', 'default_tax_system', 'tax_treatment_default'] },
  {
    label: 'Money and calendar',
    required: ['base_currency', 'fiscal_year_start_month', 'fiscal_year_start_day', 'books_begin_date', 'amount_precision', 'quantity_precision', 'rounding_mode'],
  },
  { label: 'What you track', required: [] },
  {
    label: 'Presentation',
    required: ['timezone', 'locale', 'date_format', 'datetime_format', 'digit_grouping', 'decimal_separator', 'negative_format', 'currency_symbol_position', 'default_payment_terms_days'],
  },
  { label: 'Review and create', required: [] },
];

type TaskState = 'pending' | 'running' | 'done' | 'failed' | 'skipped';
type Task = { id: string; label: string; state: TaskState; detail?: string };

/** Tone and wording per outcome, in one place: a new state is a type error, not a silent gap. */
const TASK_BADGE: Record<TaskState, { tone: Tone; label: string }> = {
  pending: { tone: 'neutral', label: 'Waiting' },
  running: { tone: 'info', label: 'Working' },
  done: { tone: 'success', label: 'Done' },
  failed: { tone: 'danger', label: 'Failed' },
  skipped: { tone: 'neutral', label: 'Not yours' },
};

function emptyDraft(today: string): Draft {
  // The neutral set until a country is chosen, which is when that jurisdiction's own
  // suggestions arrive with the country list.
  return {
    ...NEUTRAL_SUGGESTION,
    code: '',
    legal_name: '',
    display_name: '',
    entity_type: 'pvt_ltd',
    country_code: '',
    state_code: '',
    base_currency: '',
    books_begin_date: today,
    default_tax_system: '',
    show_amount_in_words: false,
    visibility: 'listed',
    requires_step_up: false,
  };
}

/**
 * The tax system a country decides on its own: one offered system is a decision, more than one
 * is a question for the operator. One expression, because the draft, the capability
 * suggestions and the cards all have to agree on the answer.
 */
function soleTaxSystem(country: Country | undefined): string {
  return country?.tax_systems?.length === 1 ? country.tax_systems[0] ?? '' : '';
}

/** Country selection and initial tenant suggestions follow the same jurisdiction rules. */
function countryDraft(current: Draft, code: string, country: Country | undefined, currencies: readonly Currency[], edited: ReadonlySet<string>): Draft {
  return {
    ...current,
    ...jurisdictionDraft(country?.setup_defaults ?? NEUTRAL_SUGGESTION),
    country_code: code,
    state_code: '',
    base_currency: country?.default_currency_code ?? current.base_currency,
    currency_symbol_override: edited.has('currency_symbol_override')
      ? current.currency_symbol_override
      : currencies.find(item => item.code === country?.default_currency_code)?.symbol,
    default_tax_system: soleTaxSystem(country),
    initial_tax_registration: newTaxRegistration(country?.tax_registration_options?.find(item => item.tax_system === soleTaxSystem(country))),
  };
}

/** Drops the fields the operator left empty: `extra="forbid"` accepts absence, not `''`. */
function body(draft: Draft): Draft {
  const value = { ...draft } as Record<string, unknown>;
  for (const [key, entry] of Object.entries(value)) {
    if (entry === '' || entry === undefined || entry === null) delete value[key];
  }
  // Required even when blank, so the server's own 422 names the field rather than "extra".
  for (const key of ['code', 'legal_name', 'display_name', 'country_code', 'state_code', 'base_currency', 'default_tax_system'] as const) {
    value[key] = draft[key];
  }
  return value as Draft;
}

/**
 * Creating a company, and its first financial year.
 *
 * Six steps rather than one long form, because four of the ten settings on step three are
 * **immutable once anything is posted** (docs/company.md §5.2) and deserve their own moment,
 * with a preview of what they will do to every printed figure.
 *
 * The finish saves one durable creation command. Server workers prepare the
 * company's capabilities and books; retries retain the original request and key.
 */
export function CompanyWizard({ session, canBootstrapBooks, returnTo }: { session: Session; canBootstrapBooks: boolean; returnTo?: string }) {
  const tenantCountry = session.organisation.defaultCountryCode;
  const tenantState = session.organisation.defaultStateCode;
  const back = administrationReturn('companies', returnTo);
  const canConfigureFeatures = organisationPermissions(session).some(key => key === 'company.create' || key === 'company.update');
  const bootstrap = companyBootstrapAccess(session, { creating: true });
  const canBootstrapChart = bootstrap.chart || canBootstrapBooks;
  const today = businessToday(session.display.timezone ?? DEFAULT_DISPLAY_CONFIG.timezone);
  const [step, setStep] = useState(0);
  const [reached, setReached] = useState(0);
  const [draft, setDraft] = useState<Draft>(() => emptyDraft(today));
  const [features, setFeatures] = useState<readonly string[]>(['inventory']);
  /** The capability catalogue, from the server: this form keeps no list of its own. */
  const [catalogue, setCatalogue] = useState<readonly FeatureChoice[]>([]);
  const [countries, setCountries] = useState<Country[] | null>(null);
  const [currencies, setCurrencies] = useState<Currency[]>([]);
  const [states, setStates] = useState<State[]>([]);
  const [loadFailure, setLoadFailure] = useState<string | null>(null);
  const [missing, setMissing] = useState<readonly string[]>([]);
  const [tasks, setTasks] = useState<readonly Task[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [fieldFailures, setFieldFailures] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const runningGuard = useRef(false);
  const openingCreatedCompany = useRef(false);
  const [formFields, setFormFields] = useState<CompanyField[]>([]);
  const created = useRef<string | null>(null);
  const [openingChoice, setOpeningChoice] = useState<'DECIDE_LATER' | 'ZERO_CONFIRMED' | 'IMPORT_EXISTING'>('ZERO_CONFIRMED');
  const [openingReason, setOpeningReason] = useState('New company; individual product openings will be entered during product creation');
  const [recovering, setRecovering] = useState(false);
  const savedCreation = useRef<{ key: string; body: Record<string, unknown> } | null>(null);
  const recoveryKey = session.user.id && session.organisation.id
    ? 'company-creation:' + session.organisation.id + ':' + session.user.id : null;
  useEffect(() => {
    if (!recoveryKey) return;
    try {
      const saved = JSON.parse(sessionStorage.getItem(recoveryKey) ?? 'null');
      if (saved && typeof saved.key === 'string' && saved.body && typeof saved.body === 'object') {
        savedCreation.current = saved; setRecovering(true);
      }
    } catch { /* Unavailable browser storage does not block company creation. */ }
  }, [recoveryKey]);
  /*
   * Which derived fields the operator has taken over. The short name and the code follow the
   * legal name while they are untouched — a suggestion that stops at the first keystroke is
   * worse than none, because it leaves "A" in the field the console will show forever.
   */
  const edited = useRef(new Set<string>());
  /*
   * The uniqueness suffix of the generated company code, drawn once per wizard and again on a
   * code conflict. A ref rather than state because nothing renders from it directly —
   * `draft.code` is what the review step reads, and it is set from here.
   *
   * Filled on first use, not in the `useRef` argument: that argument is evaluated on *every*
   * render and thrown away, which would run `crypto.getRandomValues` on every keystroke in
   * the form — and would do it during render, so a host without WebCrypto would throw while
   * rendering and take the page down instead of failing where a code is asked for.
   */
  const suffix = useRef<string | null>(null);
  /** The generated code for a legal name, against this wizard's one suffix. */
  const codeFor = (name: string) => companyCode(name, (suffix.current ??= codeSuffix()));
  const discarded = useRef(false);
  useUnsavedChanges(() => !discarded.current && !openingCreatedCompany.current && (runningGuard.current || !created.current && edited.current.size > 0));
  function leaveWizard(target = back) {
    if (runningGuard.current || !created.current && edited.current.size > 0 && !window.confirm('Discard your unsaved company setup?')) return;
    discarded.current = true; goTo(target);
  }
  /*
   * Breadcrumbs, and deliberately no `back` button.
   *
   * The console's page convention is a back button beside a breadcrumb trail, and in a wizard
   * that produces two different Backs on one screen: this one leaves the wizard, and the one
   * in the footer goes to the previous step. The trail already names every destination the
   * button offered, and the footer owns "Back" because that is where a wizard's Back lives.
   * Cancel, on the first step, is the explicit way out.
   */
  const navigation = (
    <PageNavigation
      breadcrumbs={[
        { label: 'Administration', href: '/organisation' },
        { label: 'Companies', href: back },
        { label: 'New company' },
      ]}
      onNavigate={event => {
        event.preventDefault();
        leaveWizard(event.currentTarget.href);
      }}
    />
  );

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      companyCall<Country[]>('identity', '/v1/reference/countries', { signal: controller.signal }),
      companyCall<Currency[]>('identity', '/v1/reference/currencies', { signal: controller.signal }),
      companyCall<{ items: FeatureChoice[] }>('identity', '/v1/company-features', { signal: controller.signal }),
      companyCall<components['schemas']['FieldSet']>('identity', '/v1/entities/identity.company/field-set', { signal: controller.signal }),
    ])
      .then(([foundCountries, foundCurrencies, foundFeatures, metadata]) => {
        if (controller.signal.aborted) return;
        // Only jurisdictions with an implemented profile: an ISO row alone cannot carry tax
        // (docs/company-setup.md).
        const supportedCountries = foundCountries.filter(country => country.jurisdiction_supported);
        setCountries(supportedCountries);
        setCurrencies(foundCurrencies);
        setCatalogue(foundFeatures.items);
        setFormFields(metadata.fields);
        // The tenant's own jurisdiction is adopted below; its suggested capabilities come
        // with it, from the catalogue just loaded rather than from the state it is about to
        // be put in. Nothing can have been edited yet — this is the first paint with a form.
        const adopted = supportedCountries.find(item => item.code === tenantCountry);
        if (adopted && !edited.current.has('country_code')) suggestFeatures(foundFeatures.items, adopted, soleTaxSystem(adopted));
        setDraft(current => {
          const country = supportedCountries.find(item => item.code === tenantCountry);
          const initial = country && !current.country_code && !edited.current.has('country_code')
            ? countryDraft(current, country.code, country, foundCurrencies, edited.current)
            : current;
          return { ...initial, custom_fields: {
            ...Object.fromEntries(companyCustomFields(metadata.fields).filter(field => field.writable && field.visible && field.custom?.default_value != null)
              .map(field => [field.key, field.custom?.default_value])), ...current.custom_fields,
          } };
        });
      })
      .catch((value) => {
        if (!controller.signal.aborted) setLoadFailure(companyFailure(value).message);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!draft.country_code) {
      setStates([]);
      return;
    }
    const controller = new AbortController();
    companyCall<State[]>('identity', `/v1/reference/countries/${draft.country_code}/states`, { signal: controller.signal })
      .then((found) => {
        if (controller.signal.aborted) return;
        setStates(found);
        setDraft(current => {
          if (current.country_code !== draft.country_code || current.country_code !== tenantCountry
            || current.state_code || edited.current.has('country_code') || edited.current.has('state_code')) return current;
          const state = found.find(item => item.code === tenantState && item.country_code === current.country_code);
          return state ? { ...current, state_code: state.code } : current;
        });
      })
      .catch((value) => {
        if (!controller.signal.aborted) setLoadFailure(companyFailure(value).message);
      });
    return () => controller.abort();
  }, [draft.country_code, tenantCountry, tenantState]);

  /** Drops whatever this field was last told off for — editing it is the answer to that. */
  function clearMessages(key: string): void {
    setMissing((current) => current.filter((name) => name !== key));
    setFieldFailures((current) => {
      if (!(key in current) && !('body.' + key in current)) return current;
      const next = { ...current };
      delete next[key];
      delete next['body.' + key];
      return next;
    });
  }

  function change<K extends keyof Draft>(key: K, value: Draft[K]): void {
    edited.current.add(key as string);
    setDraft((current) => ({ ...current, [key]: value }));
    clearMessages(key as string);
  }

  /**
   * The capabilities a jurisdiction suggests, and the ones it can no longer offer.
   *
   * Until the operator touches the capability step, the selection **is** the profile's
   * `default_features` — the server's list (docs/company-features.md §3), never one this
   * client keeps. A pre-selected capability is a suggestion like every other one on this
   * form: it is visible on step 4, it says what it does, and clearing it costs one click.
   *
   * Once they have touched that step their selection stands, minus whatever the new
   * jurisdiction cannot offer. That second half is not cosmetic: `e_waybill` chosen under
   * GST and carried into a UK company is a 422 from the enable call at the very end of the
   * run, after the company already exists.
   */
  function suggestFeatures(entries: readonly FeatureChoice[], country: Country | undefined, taxSystem: string): void {
    /*
     * Nothing is pre-selected where nothing can be toggled: the cards carry
     * `disabled={!canConfigureFeatures}`, and a selection that cannot be cleared is not a
     * suggestion. Tied to the same flag as the cards and the notice rather than restated,
     * so the three cannot disagree about who is choosing.
     */
    if (!canConfigureFeatures) return;
    /*
     * `taxSystem` is passed in rather than re-derived, so this filter and the card list
     * (`offeredFeatures`, which reads `draft.default_tax_system`) can only ever agree. A
     * jurisdiction offering two systems resolves to none until the operator picks one — and
     * picking one re-suggests, so a tax-gated default is never selected while its card is
     * hidden, and never missing once the card is there.
     */
    const offerable = (key: string) => {
      const feature = entries.find((entry) => entry.key === key);
      return !!feature && (feature.tax_systems.length === 0 || feature.tax_systems.includes(taxSystem));
    };
    setFeatures((current) =>
      withDependencies(
        entries,
        (edited.current.has('features') ? current : country?.default_features ?? []).filter(offerable),
      ),
    );
  }

  /** Picking a country re-suggests the jurisdiction's conventions, tax system and capabilities. */
  function chooseCountry(code: string): void {
    if (code === draft.country_code) return;
    edited.current.add('country_code');
    const country = countries?.find((item) => item.code === code);
    setStates([]);
    setDraft(current => countryDraft(current, code, country, currencies, edited.current));
    // The same tax system `countryDraft` just resolved, so the suggestion is filtered by
    // exactly what the cards will be filtered by.
    suggestFeatures(catalogue, country, soleTaxSystem(country));
    setMissing([]);
  }

  /**
   * Picking a currency also suggests its symbol. Identity stores only an *override* and falls
   * back to the currency code, so without this every document prints `INR 1,200.00` until
   * someone notices. It is an ordinary editable field, and clearing it restores the code.
   */
  function chooseCurrency(code: string): void {
    edited.current.add('base_currency');
    const previous = currencies.find((item) => item.code === draft.base_currency)?.symbol;
    const symbol = currencies.find((item) => item.code === code)?.symbol;
    setDraft((current) => ({
      ...current,
      base_currency: code,
      currency_symbol_override:
        !current.currency_symbol_override || current.currency_symbol_override === previous ? symbol : current.currency_symbol_override,
    }));
    clearMessages('base_currency');
  }

  function toggleFeature(key: string, on: boolean): void {
    // From here the selection is theirs: changing the country re-suggests the conventions
    // but must not quietly undo a capability decision someone has already made.
    edited.current.add('features');
    // Off drops every feature that needs this one, however deep the chain — otherwise the
    // server closes the dependency upward again and re-enables what was just turned off.
    setFeatures((current) =>
      on
        ? withDependencies(catalogue, [...current, key])
        : current.filter((entry) => entry !== key && !dependsOn(catalogue, entry, key)),
    );
  }

  const country = countries?.find((item) => item.code === draft.country_code);
  const registrationChoice = country?.tax_registration_options?.find(item => item.tax_system === draft.default_tax_system);
  const offeredFeatures = catalogue.filter(
    (feature) => feature.tax_systems.length === 0 || feature.tax_systems.includes(draft.default_tax_system),
  );
  /** Which of the jurisdiction's suggestions are actually still selected (see the step-4 notice). */
  const suggested = (country?.default_features ?? []).filter((key) => features.includes(key));
  const span = fiscalYearSpan(
    fiscalYearStartYear(draft.books_begin_date || today, draft.fiscal_year_start_month, draft.fiscal_year_start_day),
    draft.fiscal_year_start_month,
    draft.fiscal_year_start_day,
  );
  const preview = resolvedDisplay({
    base_currency: draft.base_currency || 'INR',
    amount_precision: draft.amount_precision,
    quantity_precision: draft.quantity_precision,
    rounding_mode: draft.rounding_mode,
    date_format: draft.date_format,
    datetime_format: draft.datetime_format,
    digit_grouping: draft.digit_grouping,
    currency_display: 'symbol',
    currency_symbol_override: draft.currency_symbol_override ?? null,
    currency_symbol_position: draft.currency_symbol_position,
    decimal_separator: draft.decimal_separator,
    thousands_separator: draft.thousands_separator,
    negative_format: draft.negative_format,
    timezone: draft.timezone,
    locale: draft.locale,
  }) as typeof DEFAULT_DISPLAY_CONFIG;

  function missingOf(index: number): readonly string[] {
    const gaps: string[] = STEPS[index].required.filter((key) => {
      const value = draft[key];
      return (typeof value === 'string' && !value.trim()) || value === undefined || value === null;
    });
    if (index === 1 && draft.initial_tax_registration) {
      for (const key of ['number', 'regime', 'valid_from'] as const) {
        if (!draft.initial_tax_registration[key].trim()) gaps.push('initial_tax_registration.' + key);
      }
    }
    return gaps;
  }

  const steps: StepperStep[] = STEPS.map((entry, index) => {
    const gaps = index <= reached && index !== step ? missingOf(index) : [];
    return {
      label: entry.label,
      complete: gaps.length === 0,
      note: gaps.length > 0 ? `${gaps.length} still needed` : undefined,
    };
  });

  function advance(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (step === 2 && !validFiscalAnchor(draft.fiscal_year_start_month, draft.fiscal_year_start_day)) {
      setFieldFailures({ fiscal_year_start_day: 'Choose a valid fiscal start month and day.' }); return;
    }
    const gaps = missingOf(step);
    if (gaps.length > 0) {
      setMissing(gaps);
      return;
    }
    setMissing([]);
    if (step === STEPS.length - 1) {
      const customErrors: Record<string, string> = {};
      const values = { ...(draft.custom_fields ?? {}) };
      for (const field of companyCustomFields(formFields)) {
        const definition = field.custom;
        if (!field.writable || !field.visible || !definition || definition.data_type === 'auto_number'
          || !customCondition(definition.visibility, { ...draft, ...values })) continue;
        const value = values[field.key];
        if (field.required && (value == null || value === '' || (Array.isArray(value) && !value.length))) customErrors['custom_fields.' + field.key] = `${field.label} is required.`;
        else try { if (field.key in values) values[field.key] = customValue(definition, value); }
        catch (error) { customErrors['custom_fields.' + field.key] = error instanceof Error ? error.message : 'Check this value.'; }
      }
      if (Object.keys(customErrors).length) { setFieldFailures(customErrors); return; }
      void run(values);
      return;
    }
    const next = step + 1;
    setStep(next);
    setReached((current) => Math.max(current, next));
  }

  function plan(): Task[] {
    return [
      { id: 'company', label: 'Save the company and automatic setup request', state: 'pending' },
      { id: 'open', label: 'Open this company', state: 'pending' },
    ];
  }

  async function create(customValues: Draft['custom_fields']): Promise<Company> {
    let code = draft.code || codeFor(draft.legal_name);
    for (let attempt = 1; ; attempt++) {
      if (!savedCreation.current) {
        savedCreation.current = {
          key: crypto.randomUUID(),
          body: { ...body({ ...draft, code, custom_fields: customValues }), setup: {
            features: withDependencies(catalogue, features), opening_choice: openingChoice,
            ...(openingChoice === 'ZERO_CONFIRMED' ? { opening_reason: openingReason.trim() } : {}),
          } },
        };
        if (recoveryKey) try { sessionStorage.setItem(recoveryKey, JSON.stringify(savedCreation.current)); } catch { /* Optional recovery storage. */ }
      }
      try {
        const result = await companyCall<Company>('identity', '/v1/companies', {
          method: 'POST', body: savedCreation.current.body, key: savedCreation.current.key,
        });
        if (recoveryKey) try { sessionStorage.removeItem(recoveryKey); } catch { /* Creation is already durable. */ }
        return result;
      } catch (value) {
        const failed = companyFailure(value);
        if (failed.status === 422 || (failed.status === 409 && failed.fields?.code)) {
          savedCreation.current = null;
          setRecovering(false);
          if (recoveryKey) try { sessionStorage.removeItem(recoveryKey); } catch { /* No command was accepted. */ }
        }
        if (attempt >= 3 || failed.status !== 409 || !failed.fields?.code || recovering) throw value;
        savedCreation.current = null;
        suffix.current = codeSuffix(); code = codeFor(draft.legal_name);
        setDraft(current => ({ ...current, code }));
      }
    }
  }

  function markTask(id: string, state: TaskState, detail?: string): void {
    setTasks(current => (current ?? []).map(task => task.id === id ? { ...task, state, detail } : task));
  }

  async function openCreatedCompany(): Promise<void> {
    if (!created.current || runningGuard.current || discarded.current) return;
    runningGuard.current = true; setRunning(true); setPreparing(false); setFailure(null);
    markTask('open', 'running');
    openingCreatedCompany.current = true;
    try {
      const refused = await openCompany(created.current, undefined, organisationPermissions(session).includes('company.read') ? 'company' : 'companies');
      if (refused) throw refused;
      markTask('open', 'done');
    } catch (value) {
      const failed = companyFailure(value);
      markTask('open', 'failed', failed.message); setFailure(failed.message);
    } finally { openingCreatedCompany.current = false; runningGuard.current = false; setRunning(false); }
  }

  async function run(customValues: Draft['custom_fields'] = draft.custom_fields): Promise<void> {
    if (runningGuard.current || preparing) return;
    if (!savedCreation.current && draft.initial_tax_registration && missingOf(1).length) {
      setMissing(missingOf(1)); setStep(1); return;
    }
    if (!savedCreation.current && openingChoice === 'ZERO_CONFIRMED' && openingReason.trim().length < 3) {
      setFailure('Explain why this company starts with no opening balances.'); return;
    }
    runningGuard.current = true; setRunning(true); setFailure(null);
    setTasks(plan());
    try {
      markTask('company', 'running');
      if (!created.current) created.current = (await create(customValues)).id as string;
      markTask('company', 'done', 'Setup continues automatically, including after you close this page.');
      setRecovering(false); setPreparing(true);
    } catch (value) {
      const failed = companyFailure(value);
      setTasks(current => (current ?? []).map(task => task.state === 'running' ? { ...task, state: 'failed', detail: failed.message } : task));
      setFailure(failed.message);
      if (failed.fields) setFieldFailures(failed.fields);
    } finally { runningGuard.current = false; setRunning(false); }
  }

  const label = (key: string) => (missing.includes(key) ? 'Required' : fieldFailures[key] ?? fieldFailures['body.' + key]);
  /**
   * What pressing "Create this company" actually does, and what it cannot do for this actor.
   *
   * Derived rather than written out as prose per branch: each line is the same shape whether
   * it is included or handed off, so the review step cannot grow a fourth paragraph with a
   * different voice.
   */
  const outcomes: readonly { label: string; detail?: string; included: boolean }[] = [
    { label: 'The company and your Company Administrator access', included: true },
    {
      label: 'Its books and first financial year, prepared automatically',
      detail: canBootstrapBooks ? undefined : 'Needs accounting permissions your role does not hold.',
      included: canBootstrapBooks,
    },
    {
      label: 'The starter accounting chart',
      detail: canBootstrapChart ? 'Standard account heads, groups and ledgers, plus applicable stock and tax accounts.' : undefined,
      included: canBootstrapChart,
    },
    {
      label: 'Main warehouse and internal transit',
      detail: bootstrap.warehouses ? 'Stock operations still need the inventory capability.' : undefined,
      included: bootstrap.warehouses,
    },
    { label: 'Default price levels', included: bootstrap.pricing },
    { label: 'Voucher types and common entry rules', included: true,
      detail: 'Account, Product and Mixed Sales/Purchase; stock types follow inventory and manufacturing follows BOM. Existing types are preserved.' },
    { label: withDependencies(catalogue, features).includes('inventory') ? 'Common units, conversions and pack types' : 'Count and service units', included: true,
      detail: 'Prepared from company capabilities. Existing definitions are preserved; pack quantities remain product-specific.' },
    ...(draft.country_code === 'IN' && draft.default_tax_system === 'gst_in' ? [{ label: 'Common GST categories, classifications, rules and rates', included: true,
      detail: 'Prepared for this company; existing records are preserved. Select the rule that matches each product.' }] : []),
    { label: 'The General product group', included: bootstrap.productGroup },
  ];

  /** Built where it is read — five formatter calls and four lookups, for one step of six. */
  const review = () => [
    { label: 'Legal name', value: draft.legal_name, step: 0 },
    ...(draft.trade_name ? [{ label: 'Trading name', value: draft.trade_name, step: 0 }] : []),
    { label: 'Opens as', value: draft.display_name, step: 0 },
    /*
     * No `step`, so no Edit: there is no field to send the reader to. It is here because the
     * value prints in every document number and freezes on the first posting — generated is
     * not the same as hidden.
     */
    {
      label: 'Company code',
      value: (
        <>
          {draft.code} <span className="janso-fine">Generated. It prints in document numbers and cannot be changed once anything is posted.</span>
        </>
      ),
    },
    { label: 'Entity type', value: entityTypeLabel(draft.entity_type), step: 0 },
    { label: 'Jurisdiction', value: `${country?.name ?? draft.country_code} · ${states.find((state) => state.code === draft.state_code)?.name ?? draft.state_code}`, step: 1 },
    { label: 'Tax', value: `${taxSystemLabel(draft.default_tax_system)} · ${taxTreatmentLabel(draft.tax_treatment_default).toLowerCase()}`, step: 1 },
    ...(draft.initial_tax_registration ? [{
      label: registrationChoice?.number_label ?? 'Tax registration', step: 1,
      value: `${draft.initial_tax_registration.number} · ${registrationChoice?.regimes.find(item => item.value === draft.initial_tax_registration?.regime)?.label ?? draft.initial_tax_registration.regime} · Effective ${formatDate(draft.initial_tax_registration.valid_from, preview)}`,
    }] : []),
    { label: 'Books currency', value: draft.base_currency + (draft.reporting_currency ? ` (reported in ${draft.reporting_currency})` : ''), step: 2 },
    { label: 'Books begin', value: formatDate(draft.books_begin_date, preview), step: 2 },
    { label: 'First financial year', value: `${fiscalYearLabel(span)} · ${formatDate(span.start, preview)} → ${formatDate(span.end, preview)}`, step: 2 },
    { label: 'Amounts', value: `${formatMoney('1234567.891', preview)} · rounded ${roundingLabel(draft.rounding_mode)}`, step: 2 },
    { label: 'Quantities', value: formatQuantity('1234.5678', preview), step: 2 },
    { label: 'Capabilities', value: features.length === 0 ? 'None yet' : withDependencies(catalogue, features).map((key) => featureLabel(catalogue, key)).join(', '), step: 3 },
  ];

  if (loadFailure && !countries) {
    return (
      <WizardLayout
        brand={<Wordmark size={28} nameSize="1.0625rem" />}
        headerEnd={<ThemeSwitcher />}
        steps={STEPS.map((entry) => entry.label)}
        current={0}
        title="Company setup is unavailable"
        actions={<Button type="submit">Try again</Button>}
        onSubmit={(event) => {
          event.preventDefault();
          goTo(administrationLink('/companies/new', back));
        }}
      >
        {navigation}<Notice tone="danger">{loadFailure}</Notice>
      </WizardLayout>
    );
  }

  if (recovering) return <div className="janso-page janso-flow">
    <Notice tone="info">A company creation request was interrupted. Resume it to recover the same company and its setup.</Notice>
    {failure && <Notice tone="danger">{failure}</Notice>}
    <Button disabled={running} onClick={() => void run()}>Resume company creation</Button>
  </div>;

  return (
    <WizardLayout
      brand={<Wordmark size={28} nameSize="1.0625rem" />}
      headerEnd={<ThemeSwitcher />}
      steps={steps}
      current={step}
      reached={reached}
      onStep={running || tasks ? undefined : (target) => setStep(target)}
      progress={`Step ${step + 1} of ${STEPS.length}`}
      title={tasks ? preparing ? 'Preparing your company' : 'Creating your company' : STEPS[step].label}
      subtitle={tasks ? created.current
        ? 'Company saved. We will open it when automatic preparation finishes.'
        : 'Waiting for confirmation that your company and setup request are saved.' : SUBTITLES[step]}
      notice={
        <>
          {navigation}
          {missing.length > 0 ? <Notice tone="warning">Fill in the highlighted fields to continue.</Notice> : null}
          {failure ? <Notice tone="danger">{failure}</Notice> : null}
          {loadFailure ? <Notice tone="warning">{loadFailure}</Notice> : null}
        </>
      }
      actions={
        tasks ? (
          <>
            {!created.current && !savedCreation.current && failure && <Button type="button" variant="ghost" disabled={running} onClick={() => { setTasks(null); setFailure(null); setStep(5); }}>Edit company details</Button>}
            <Button type="button" variant="ghost" disabled={running} onClick={() => leaveWizard()}>
              Leave for now
            </Button>
            {preparing ? (
              <Button type="button" variant="ghost" onClick={() => void openCreatedCompany()}>Open while setup continues</Button>
            ) : (
              <Button type="submit" loading={running} loadingLabel="Working…" disabled={!failure}>
                Retry the remaining steps
              </Button>
            )}
          </>
        ) : (
          <>
            <Button type="button" variant="ghost" onClick={() => (step === 0 ? leaveWizard() : setStep(step - 1))}>
              {step === 0 ? 'Cancel' : 'Back'}
            </Button>
            <Button type="submit">{step === STEPS.length - 1 ? 'Create this company' : 'Next'}</Button>
          </>
        )
      }
      onSubmit={tasks ? (event) => { event.preventDefault(); void run(); } : advance}
    >
      {tasks ? (
        <>
          {preparing && created.current && <AutomaticCompanySetup company={created.current} canRetry notifyInitialComplete onComplete={() => void openCreatedCompany()} />}
          <ol className="console-wizard__tasks">
            {tasks.map((task) => (
              <li key={task.id} data-state={task.state}>
                <Badge tone={TASK_BADGE[task.state].tone}>{TASK_BADGE[task.state].label}</Badge>
                <span>
                  <strong>{task.label}</strong>
                  {task.detail ? <span className="janso-fine">{task.detail}</span> : null}
                </span>
              </li>
            ))}
          </ol>
        </>
      ) : countries === null ? (
        <Skeleton />
      ) : (
        <>
          {step === 0 ? (
            <>
              <TextField
                label="Legal name"
                required
                maxLength={255}
                value={draft.legal_name}
                error={label('legal_name')}
                hint="Exactly as registered. It prints on every document."
                onChange={(event) => {
                  const value = event.target.value;
                  edited.current.add('legal_name');
                  setDraft((current) => ({
                    ...current,
                    legal_name: value,
                    trade_name: edited.current.has('trade_name') ? current.trade_name : value,
                    // A suggestion, replaceable: it follows along until the operator edits it.
                    display_name: edited.current.has('display_name') ? current.display_name : companyShortName(value),
                    // Not a suggestion — there is no field for it. It is shown on the review step.
                    code: codeFor(value),
                  }));
                  clearMessages('legal_name');
                }}
              />
              <TextField label="Trading name" maxLength={255} value={draft.trade_name ?? ''} hint="Follows the legal name until you change it. Use the name your customers know." onChange={(event) => change('trade_name', event.target.value)} />
              <TextField label="Short name" required maxLength={120} value={draft.display_name} error={label('display_name')} hint="Suggested initials for the company switcher, e.g. VEPL. You can change them; this name does not need to be unique." onChange={(event) => change('display_name', event.target.value)} />
              {/* Short fields pair up: a date and an entity type were each being given the
                * full width of the form. */}
              <FieldPair>
                <Select label="Entity type" required value={draft.entity_type} options={ENTITY_TYPES} onChange={(value) => change('entity_type', value)} error={label('entity_type')} />
                <TextField label="Incorporation date" type="date" value={draft.incorporation_date ?? ''} onChange={(event) => change('incorporation_date', event.target.value)} />
              </FieldPair>
            </>
          ) : null}
          {step === 1 ? (
            <>
              <FieldPair>
              <Select
                label="Country"
                required
                placeholder="Choose a country"
                value={draft.country_code}
                error={label('country_code')}
                hint="Starts with your tenant's country when available. You can change it. Only supported tax jurisdictions are listed."
                options={(countries ?? []).map((item) => ({ value: item.code, label: `${item.name} (${item.code})` }))}
                onChange={chooseCountry}
              />
              <Select
                label={country?.subdivision_label || 'State'}
                required
                placeholder={draft.country_code ? 'Choose one' : 'Choose a country first'}
                disabled={states.length === 0}
                value={draft.state_code}
                error={label('state_code')}
                hint="Starts with your tenant's state when available. You can change it. Decides the place of supply on your own documents."
                options={states.map((item) => ({ value: item.code, label: item.name }))}
                onChange={(value) => {
                  if (value !== draft.state_code && registrationChoice?.jurisdiction_scope === 'state' && draft.initial_tax_registration) {
                    change('initial_tax_registration', newTaxRegistration(registrationChoice));
                  }
                  change('state_code', value);
                }}
              />
              </FieldPair>
              <Select
                label="Tax system"
                required
                placeholder="Choose a tax system"
                value={draft.default_tax_system}
                error={label('default_tax_system')}
                hint="The form default. Each document still resolves its own tax by its posting date."
                options={taxSystemOptions(country?.tax_systems ?? [])}
                onChange={(value) => {
                  if (value !== draft.default_tax_system) {
                    change('initial_tax_registration', newTaxRegistration(country?.tax_registration_options?.find(item => item.tax_system === value)));
                  }
                  change('default_tax_system', value);
                  // Which capabilities are offerable moves with this, so the suggestion
                  // moves with it too. A no-op where the country decided it already.
                  suggestFeatures(catalogue, country, value);
                }}
              />
              {registrationChoice && <CompanyRegistrationFields
                choice={registrationChoice} value={draft.initial_tax_registration}
                error={key => label('initial_tax_registration.' + key)}
                onChange={value => {
                  change('initial_tax_registration', value);
                  for (const key of ['number', 'regime', 'valid_from']) clearMessages('initial_tax_registration.' + key);
                }}
              />}
              <Select
                label="Price convention"
                required
                value={draft.tax_treatment_default}
                options={TAX_TREATMENTS}
                onChange={(value) => change('tax_treatment_default', value)}
              />
            </>
          ) : null}
          {step === 2 ? (
            <>
              <Notice tone="warning" title="These settings are permanent once you post">
                Currency, financial-year start, books-begin date, precision and rounding reinterpret every figure ever filed, so they freeze on the first posting.
              </Notice>
              <Select
                label="Books currency"
                required
                placeholder="Choose a currency"
                value={draft.base_currency}
                error={label('base_currency')}
                options={currencies.map((item) => ({ value: item.code, label: `${item.code} — ${item.name}` }))}
                onChange={chooseCurrency}
              />
              <Select
                label="Reporting currency"
                placeholder="Same as the books currency"
                value={draft.reporting_currency ?? ''}
                hint="Presentation only. It does not enable foreign-currency billing."
                options={currencies.map((item) => ({ value: item.code, label: `${item.code} — ${item.name}` }))}
                onChange={(value) => change('reporting_currency', value || undefined)}
              />
              <Select
                label="Financial year starts in"
                required
                value={String(draft.fiscal_year_start_month)}
                options={MONTHS.map((month, index) => ({ value: String(index + 1), label: month }))}
                onChange={(value) => change('fiscal_year_start_month', Number(value))}
              />
              <TextField
                label="on day"
                type="number"
                required
                min={1}
                max={31}
                value={String(draft.fiscal_year_start_day)}
                onChange={(event) => change('fiscal_year_start_day', Number(event.target.value))}
              />
              <TextField
                label="Books begin on"
                type="date"
                required
                value={draft.books_begin_date}
                error={label('books_begin_date')}
                hint="The earliest date anything may be posted on."
                onChange={(event) => change('books_begin_date', event.target.value)}
              />
              <Select label="Amount decimals" required value={String(draft.amount_precision)} options={PRECISIONS} onChange={(value) => change('amount_precision', Number(value))} />
              <Select label="Quantity decimals" required value={String(draft.quantity_precision)} options={PRECISIONS} onChange={(value) => change('quantity_precision', Number(value))} />
              <Select label="Rounding" required value={draft.rounding_mode} options={ROUNDING_MODES} onChange={(value) => change('rounding_mode', value)} />
              <div className="console-wizard__preview">
                <p className="janso-fine">With these settings</p>
                <ReviewList
                  items={[
                    { label: 'An amount', value: formatMoney('1234567.891', preview) },
                    { label: 'A quantity', value: formatQuantity('1234.5678', preview) },
                    { label: 'A date', value: formatDate(today, preview) },
                    { label: 'First financial year', value: `${fiscalYearLabel(span)} · ${formatDate(span.start, preview)} → ${formatDate(span.end, preview)}` },
                  ]}
                />
                <p className="janso-fine">The financial year is generated by the accounting service; this is what it will cover.</p>
              </div>
            </>
          ) : null}
          {step === 3 ? (
            <>
              {!canConfigureFeatures && <Notice>You can create this company. Enabling optional features needs tenant-level company.update; an administrator can enable them later.</Notice>}
              <Notice tone="info">
                {/*
                  * Driven by the selection, not by the jurisdiction. Clearing every card
                  * left this claiming things were selected that no longer were — and the
                  * sentence is the only thing on the step that says who chose.
                  */}
                {suggested.length > 0 ? <>What most businesses in {country?.name ?? 'this jurisdiction'} use is already selected — clear anything this one does not do. </> : null}
                Turn on only what this business does. Anything here can be turned on later — but
                the ones marked <strong>Permanent</strong> cannot be turned back off once they
                have shaped posted data.
              </Notice>
              {/*
                * Cards in a dependency tree, not a flat checkbox list. The indent is the
                * `requires` chain, so "expiry dates need batches need stock" is structure
                * rather than three sentences; the whole card is the label, so the
                * description is part of the target that explains it.
                */}
              <div className="janso-choices">
                {capabilityTree(offeredFeatures).map(({ item: feature, depth }) => {
                  const on = features.includes(feature.key);
                  const pulledIn = feature.requires.filter((key) => features.includes(key));
                  return (
                    <ChoiceCard
                      key={feature.key}
                      depth={depth}
                      checked={on}
                      disabled={!canConfigureFeatures}
                      onChange={(next) => toggleFeature(feature.key, next)}
                      title={feature.label}
                      description={feature.description}
                      badges={
                        <>
                          {feature.locks ? <Badge tone="warn">Permanent</Badge> : null}
                          {feature.tax_systems.length > 0 ? (
                            <Badge tone="info">{taxSystemLabel(feature.tax_systems[0] ?? '')}</Badge>
                          ) : null}
                        </>
                      }
                      note={
                        on && pulledIn.length > 0
                          ? `Also on, because this needs it: ${pulledIn.map((key) => featureLabel(catalogue, key)).join(', ')}.`
                          : undefined
                      }
                    />
                  );
                })}
              </div>
            </>
          ) : null}
          {step === 4 ? (
            <>
              {/*
                * Grouped, because fifteen controls in one column is a list to get through
                * rather than a set of decisions to make. The four groups are the four
                * questions actually being asked: when, how many, how much, and who signs.
                * Short fields pair up — a decimal separator is one character and was being
                * given the full width of the form.
                */}
              <FieldGroup title="Dates and time">
                <TextField
                  label="Time zone"
                  required
                  maxLength={64}
                  list="tz-options"
                  value={draft.timezone}
                  error={label('timezone')}
                  hint="Decides what “today” means for this company."
                  onChange={(event) => change('timezone', event.target.value)}
                />
                {/* The real IANA list from the platform, not a hand-kept copy. Still a text
                  * field: the column is free-form and a zone this browser has not heard of
                  * must remain typeable. */}
                <datalist id="tz-options">
                  {TIMEZONES.map((zone) => (
                    <option key={zone} value={zone} />
                  ))}
                </datalist>
                <FieldPair>
                  <TextField
                    label="Date format"
                    required
                    maxLength={20}
                    list="date-format-options"
                    value={draft.date_format}
                    error={label('date_format')}
                    onChange={(event) => change('date_format', event.target.value)}
                  />
                  <TextField
                    label="Date and time format"
                    required
                    maxLength={30}
                    list="datetime-format-options"
                    value={draft.datetime_format}
                    error={label('datetime_format')}
                    onChange={(event) => change('datetime_format', event.target.value)}
                  />
                </FieldPair>
                {/*
                  * Suggestions, not a closed set. `formatDate` is a pattern formatter with a
                  * documented token vocabulary and support for quoted literals, which it
                  * handles on purpose, so turning this into a `Select` would remove a
                  * capability the platform offers deliberately. The preview below is what
                  * makes free entry safe: the pattern resolves as you type it.
                  */}
                <datalist id="date-format-options">
                  {DATE_FORMATS.map((pattern) => (
                    <option key={pattern} value={pattern} />
                  ))}
                </datalist>
                <datalist id="datetime-format-options">
                  {DATETIME_FORMATS.map((pattern) => (
                    <option key={pattern} value={pattern} />
                  ))}
                </datalist>
                <TextField
                  label="Language"
                  required
                  maxLength={8}
                  list="locale-options"
                  value={draft.locale}
                  error={label('locale')}
                  hint="A language tag, e.g. en, en-IN, hi."
                  onChange={(event) => change('locale', event.target.value)}
                />
                <datalist id="locale-options">
                  {LOCALES.map((tag) => (
                    <option key={tag} value={tag} />
                  ))}
                </datalist>
              </FieldGroup>

              <FieldGroup title="Numbers">
                <Select
                  label="Digit grouping"
                  required
                  value={draft.digit_grouping}
                  options={DIGIT_GROUPINGS}
                  onChange={(value) => change('digit_grouping', value)}
                />
                <FieldPair>
                  <TextField
                    label="Decimal separator"
                    required
                    maxLength={2}
                    list="separator-options"
                    value={draft.decimal_separator}
                    onChange={(event) => change('decimal_separator', event.target.value)}
                  />
                  <TextField
                    label="Thousands separator"
                    maxLength={2}
                    list="separator-options"
                    value={draft.thousands_separator ?? ''}
                    hint="Empty prints no separator."
                    onChange={(event) => change('thousands_separator', event.target.value)}
                  />
                </FieldPair>
                <datalist id="separator-options">
                  {SEPARATORS.map((mark) => (
                    <option key={mark} value={mark} />
                  ))}
                </datalist>
                <Select
                  label="Negative amounts"
                  required
                  value={draft.negative_format}
                  options={NEGATIVE_FORMATS}
                  onChange={(value) => change('negative_format', value)}
                />
              </FieldGroup>

              <FieldGroup title="Currency">
                <FieldPair>
                  {/* "Currency symbol" twice was two different fields under one visible name:
                    * confusing to read, and two identical labels for a screen reader. */}
                  <Select
                    label="Symbol position"
                    required
                    value={draft.currency_symbol_position}
                    options={SYMBOL_POSITIONS}
                    onChange={(value) => change('currency_symbol_position', value)}
                  />
                  <TextField
                    label="Currency symbol"
                    maxLength={8}
                    value={draft.currency_symbol_override ?? ''}
                    hint="Empty prints the currency code."
                    onChange={(event) => change('currency_symbol_override', event.target.value || undefined)}
                  />
                </FieldPair>
              </FieldGroup>

              {/* The live result of every control above. */}
              <FormatPreview display={preview} today={today} />

              <FieldGroup title="On printed documents">
                <TextField
                  label="Payment terms (days)"
                  type="number"
                  required
                  min={0}
                  max={3650}
                  value={String(draft.default_payment_terms_days)}
                  onChange={(event) => change('default_payment_terms_days', Number(event.target.value))}
                />
                <FieldPair>
                  <TextField label="Signatory name" maxLength={150} value={draft.signatory_name ?? ''} onChange={(event) => change('signatory_name', event.target.value)} />
                  <TextField label="Signatory designation" maxLength={100} value={draft.signatory_designation ?? ''} onChange={(event) => change('signatory_designation', event.target.value)} />
                </FieldPair>
                <TextField label="Jurisdiction note" maxLength={200} value={draft.jurisdiction_text ?? ''} hint="Printed on documents, e.g. “Subject to Mumbai jurisdiction”." onChange={(event) => change('jurisdiction_text', event.target.value)} />
                <Checkbox checked={draft.show_amount_in_words === true} onChange={(event) => change('show_amount_in_words', event.target.checked)}>
                  Print amounts in words
                </Checkbox>
              </FieldGroup>
            </>
          ) : null}
          {step === 5 ? (
            <>
              <ReviewList items={review()} onEdit={(target) => setStep(target)} />
              <FieldGroup title="Opening balances">
                <Select label="How does this company start?" value={openingChoice}
                  options={[{ value: 'DECIDE_LATER', label: 'Decide later' }, { value: 'ZERO_CONFIRMED', label: 'New business with no opening balances' }, { value: 'IMPORT_EXISTING', label: 'Existing business: import opening balances' }]}
                  onChange={value => setOpeningChoice(value as typeof openingChoice)} />
                {openingChoice === 'ZERO_CONFIRMED' && <TextField label="Reason for zero opening balances" required minLength={3} maxLength={500}
                  value={openingReason} onChange={event => setOpeningReason(event.target.value)}
                  hint="Confirm there are no opening cash, bank, customer, supplier, stock or other balances." />}
                <Notice tone="info">Books, starter masters and report preparation run automatically. Opening balances stay unconfirmed until you make an explicit choice.</Notice>
              </FieldGroup>
              <CustomFields fields={companyCustomFields(formFields)} values={draft.custom_fields ?? {}} nativeValues={draft}
                creating currencies={currencies.map(item => item.code)} errors={fieldFailures}
                onChange={values => change('custom_fields', values)} />
              {/*
                * One list, not three paragraphs.
                *
                * These were three stacked notices of dense prose, and two of them read as a
                * list of failures before anything had happened — "Warehouse settings will
                * need initialization by an authorized administrator. Default price levels
                * will need initialization by an authorized administrator." The facts are all
                * of one kind: here is what pressing the button does, and here is the part
                * somebody else has to finish. A line each, with the state as a badge, says
                * the same thing in a shape that can be scanned at the moment it matters.
                */}
              <FieldGroup title="What creating this will do">
                <ul className="janso-setup__checks">
                  {outcomes.map((outcome) => (
                    <li className="janso-setup__check" key={outcome.label}>
                      <span>
                        {outcome.label}
                        {outcome.detail ? <span className="janso-fine"> {outcome.detail}</span> : null}
                      </span>
                      <Badge tone={outcome.included ? 'success' : 'warn'}>
                        {outcome.included ? 'Included' : 'Needs an administrator'}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </FieldGroup>

              {/* Separate on purpose: these are not blocked on anyone, they are simply next. */}
              <Notice tone="info">
                Added separately afterwards: additional tax registrations, customers, suppliers, bank
                details and any opening balances you need to import.
              </Notice>
            </>
          ) : null}
        </>
      )}
    </WizardLayout>
  );
}

const SUBTITLES = [
  'Who issues the documents.',
  'Where the business is registered, and under which tax system.',
  'The settings that decide every figure. Four of them freeze on your first posting.',
  'What this business actually does. Everything here can be turned on later.',
  'How amounts, dates and documents are presented.',
  'Check it over. Nothing has been created yet.',
];
