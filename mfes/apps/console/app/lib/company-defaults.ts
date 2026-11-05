import type { components } from '@janso/api-client/identity';

export type Draft = components['schemas']['CompanyCreate'];

/**
 * The company settings a jurisdiction usually implies — a **suggestion**, never a decision.
 *
 * The table itself is `identity/domain/company_defaults.py` and arrives on each
 * `CountryChoice`, so web, mobile and every later client suggest the same thing. What is left
 * here is the one value a form needs *before* that response lands.
 *
 * `POST /v1/companies` still guesses nothing (docs/company-setup.md): country, currency and tax
 * system are explicit selections. A suggestion is keyed by the company's country, never by the
 * browser's locale — an Indian company opened from a laptop in Berlin still prints
 * `12,34,567.89` and `dd-MM-yyyy` (CLAUDE.md §4: display config comes from config).
 */
export type Suggestion = components['schemas']['CountrySetupDefaults'];

/**
 * What an empty form starts with, before the country list has loaded or a country is chosen.
 *
 * Kept deliberately neutral and *not* a second copy of any jurisdiction's conventions: every
 * real suggestion comes from the server, and the only job left here is to have something
 * well-formed in the fields while the first request is in flight.
 */
export const NEUTRAL_SUGGESTION: Suggestion = {
  fiscal_year_start_month: 1,
  fiscal_year_start_day: 1,
  timezone: 'UTC',
  locale: 'en',
  date_format: 'dd MMM yyyy',
  datetime_format: 'dd MMM yyyy HH:mm',
  digit_grouping: 'western',
  decimal_separator: '.',
  thousands_separator: ',',
  negative_format: 'minus',
  currency_symbol_position: 'prefix',
  amount_precision: 2,
  quantity_precision: 3,
  rounding_mode: 'half_up',
  tax_treatment_default: 'exclusive',
  default_payment_terms_days: 30,
};

/**
 * The draft fields that choosing a country re-suggests.
 *
 * Precision and rounding are **not** here on purpose: the operator meets them on the next step,
 * where the form explains that they freeze on the first posting, and a country change must not
 * quietly rewrite a number someone has already considered.
 */
const JURISDICTION_KEYS = [
  'fiscal_year_start_month',
  'fiscal_year_start_day',
  'timezone',
  'date_format',
  'datetime_format',
  'digit_grouping',
  'decimal_separator',
  'thousands_separator',
  'negative_format',
  'currency_symbol_position',
  'tax_treatment_default',
] as const satisfies readonly (keyof Suggestion & keyof Draft)[];

/** A country's suggestions as draft fields. The names match, so there is nothing to translate. */
export function jurisdictionDraft(suggestion: Suggestion): Partial<Draft> {
  return Object.fromEntries(JURISDICTION_KEYS.map((key) => [key, suggestion[key]])) as Partial<Draft>;
}

/** `company.code` is `VARCHAR(20)` (identity-schema.md), and the whole of it prints. */
export const CODE_MAX = 20;
/** Four characters of 32 is just over a million suffixes per stem. */
export const CODE_SUFFIX_LENGTH = 4;

/**
 * A company code derived from its name: embedded in document numbers, so it is short,
 * upper-case and has no characters a filename or a URL would argue with. It cannot be changed
 * after anything is posted (docs/company.md §5.2).
 *
 * `limit` is how much of the column this part may take — `companyCode` leaves room for the
 * uniqueness suffix.
 */
export function codeFrom(name: string, limit = CODE_MAX): string {
  const slug = name
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  let code = slug.slice(0, limit);
  // Cut at a word, not mid-word: `ACME-MANUFACTURING-P` reads like a typo, and this value is
  // printed on documents. A single long word is left truncated — there is nowhere to cut.
  if (slug.length > limit && slug[limit] !== '-' && code.includes('-')) code = code.slice(0, code.lastIndexOf('-'));
  return code.replace(/-+$/, '');
}

/*
 * No `I`, `O`, `0` or `1`. This value is on a printed invoice and gets read down a phone, and
 * a code nobody can transcribe is worse than a longer one.
 */
const SUFFIX_ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';

/**
 * A fresh uniqueness suffix. `crypto.getRandomValues` rather than `Math.random` because it is
 * one call and unbiased over a 32-character alphabet; this is uniqueness, not secrecy.
 */
export function codeSuffix(): string {
  const bytes = new Uint8Array(CODE_SUFFIX_LENGTH);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => SUFFIX_ALPHABET[byte % SUFFIX_ALPHABET.length]).join('');
}

/**
 * The code a new company is created with — the legal name, then a random suffix.
 *
 * **Why it is generated rather than asked for.** It is one more required field on the first
 * step, and the operator has no way to know what is already taken inside the tenant: a typed
 * code either duplicates an existing one, which is a 409 they can do nothing useful about, or
 * it is unique by luck. The stem keeps the value readable on a document, and the suffix is
 * what makes `uq_company_tenant_id_code` a formality rather than a guess. A company with no
 * usable letters in its name still gets a code, because the column is `NOT NULL`.
 */
export function companyCode(name: string, suffix: string): string {
  const stem = codeFrom(name, CODE_MAX - suffix.length - 1) || 'CO';
  return `${stem}-${suffix}`;
}

/** Editable initials for multiword names; display labels do not need to be unique. */
export function companyShortName(name: string): string {
  const clean = name.trim().replace(/\s+/gu, ' ');
  const words = clean.match(/[\p{L}\p{N}][\p{L}\p{M}\p{N}]*/gu) ?? [];
  const short = words.length > 1 ? words.map(word => [...word][0]).join('').toUpperCase() : clean;
  return [...short].slice(0, 40).join('');
}

/** The last day of a month, with February's leap year — the clamp an anchor day needs. */
export function validFiscalAnchor(month: number, day: number): boolean {
  return Number.isInteger(month) && Number.isInteger(day) && month >= 1 && month <= 12
    && day >= 1 && day <= new Date(Date.UTC(2000, month, 0)).getUTCDate();
}

function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

function anchor(year: number, month: number, day: number): string {
  const clamped = Math.min(day, daysInMonth(year, month));
  return `${year}-${String(month).padStart(2, '0')}-${String(clamped).padStart(2, '0')}`;
}

/**
 * The span a financial year starting in `startYear` would cover — **a preview of Accounting's
 * own calculation, not a second implementation of it.**
 *
 * Accounting generates the real spans (`accounting/domain/fiscal.py`): twelve contiguous
 * monthly periods from the anchor, with short months clamped. This reproduces only the outer
 * bounds so the form can show "01-04-2026 → 31-03-2027" before anything is created. The server
 * remains the authority, and the created year is read back from it.
 */
export function fiscalYearSpan(startYear: number, month: number, day: number): { start: string; end: string } {
  if (!validFiscalAnchor(month, day) || !Number.isInteger(startYear) || startYear < 1900 || startYear > 9997) return { start: '', end: '' };
  const start = anchor(startYear, month, day);
  const next = anchor(startYear + 1, month, day);
  const end = new Date(next + 'T00:00:00Z');
  end.setUTCDate(end.getUTCDate() - 1);
  return { start, end: end.toISOString().slice(0, 10) };
}

/** `FY2026-2027` — the code Accounting assigns, previewed. */
export function fiscalYearLabel(span: { start: string; end: string }): string {
  return `FY${span.start.slice(0, 4)}-${span.end.slice(0, 4)}`;
}

/** The financial year containing a business date, given the company's anchor. */
export function fiscalYearStartYear(today: string, month: number, day: number): number {
  const year = Number(today.slice(0, 4));
  if (!validFiscalAnchor(month, day)) return year;
  return today >= anchor(year, month, day) ? year : year - 1;
}

/** One capability, as `GET /v1/company-features` carries it. */
export type FeatureChoice = components['schemas']['FeatureCatalogueItem'];

/**
 * Whether `key` needs `target`, however deep the chain. The server reasons the same way
 * (`billing_platform.features.required_closure`); this exists so the form can *show* it.
 *
 * The catalogue is passed in rather than imported: it is the server's answer now, so a copy
 * in this file could only disagree with it.
 */
export function dependsOn(catalogue: readonly FeatureChoice[], key: string, target: string): boolean {
  const requires = catalogue.find((feature) => feature.key === key)?.requires ?? [];
  return requires.some((required) => required === target || dependsOn(catalogue, required, target));
}

/** Every feature that must be on for these to be on, transitively — the server does this too. */
export function withDependencies(catalogue: readonly FeatureChoice[], keys: readonly string[]): string[] {
  const byKey = new Map(catalogue.map((feature) => [feature.key, feature]));
  const closed = new Set<string>();
  const add = (key: string) => {
    if (closed.has(key)) return;
    closed.add(key);
    for (const dependency of byKey.get(key)?.requires ?? []) add(dependency);
  };
  for (const key of keys) add(key);
  // Ordered so a dependency is enabled before the feature that needs it.
  return catalogue.filter((feature) => closed.has(feature.key)).map((feature) => feature.key);
}

/** A feature's name for a sentence, falling back to its key if the catalogue lacks it. */
export function featureLabel(catalogue: readonly FeatureChoice[], key: string): string {
  return catalogue.find((feature) => feature.key === key)?.label ?? key;
}
