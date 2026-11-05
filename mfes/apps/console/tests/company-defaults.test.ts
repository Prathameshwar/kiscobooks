/**
 * The wizard's pure helpers: the neutral starting point, the fields a jurisdiction re-suggests,
 * the code suggestion, the financial-year preview and the feature dependency closure.
 *
 * The jurisdiction table itself is the server's (`identity/domain/company_defaults.py`), so
 * what is left to test here is the *shape* of what the client does with it. The year preview
 * matters most: it is a preview of Accounting's own generation, so it has to agree with it on
 * the awkward anchors — a 29 February start, a 31st-of-the-month start — or the operator
 * confirms one span and gets another.
 */
import { describe, expect, it } from 'vitest';
import {
  CODE_MAX,
  NEUTRAL_SUGGESTION,
  codeFrom,
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
  type FeatureChoice,
  type Suggestion,
} from '../app/lib/company-defaults';

/** As `GET /v1/reference/countries` carries India's suggestions. */
const INDIA: Suggestion = {
  ...NEUTRAL_SUGGESTION,
  fiscal_year_start_month: 4,
  fiscal_year_start_day: 1,
  timezone: 'Asia/Kolkata',
  date_format: 'dd-MM-yyyy',
  datetime_format: 'dd-MM-yyyy HH:mm',
  digit_grouping: 'indian',
};

const CATALOGUE: FeatureChoice[] = [
  { key: 'inventory', label: 'Stock and inventory', description: 'Track quantities.', requires: [], tax_systems: [], locks: true },
  { key: 'batch_tracking', label: 'Batches', description: 'Record a batch.', requires: ['inventory'], tax_systems: [], locks: true },
  { key: 'expiry_tracking', label: 'Expiry dates', description: 'Record expiry.', requires: ['batch_tracking'], tax_systems: [], locks: true },
  { key: 'multi_godown', label: 'Multiple warehouses', description: 'More than one location.', requires: ['inventory'], tax_systems: [], locks: true },
  { key: 'serial_tracking', label: 'Serial numbers', description: 'Identify units.', requires: ['inventory'], tax_systems: [], locks: true },
  { key: 'budgets', label: 'Budgets', description: 'Set budgets.', requires: [], tax_systems: [], locks: false },
];

describe('the neutral starting point', () => {
  it('is neutral, and not a second copy of any jurisdiction', () => {
    // January, UTC, western grouping: a form showing this has not guessed at a country.
    expect(NEUTRAL_SUGGESTION.fiscal_year_start_month).toBe(1);
    expect(NEUTRAL_SUGGESTION.timezone).toBe('UTC');
    expect(NEUTRAL_SUGGESTION.digit_grouping).toBe('western');
    expect(NEUTRAL_SUGGESTION.tax_treatment_default).toBe('exclusive');
  });
});

describe('jurisdictionDraft', () => {
  it('carries the country’s conventions straight through, by matching field names', () => {
    expect(jurisdictionDraft(INDIA)).toMatchObject({
      fiscal_year_start_month: 4,
      fiscal_year_start_day: 1,
      timezone: 'Asia/Kolkata',
      date_format: 'dd-MM-yyyy',
      digit_grouping: 'indian',
      tax_treatment_default: 'exclusive',
    });
  });

  it('leaves precision and rounding alone, since the operator meets them on the next step', () => {
    const draft = jurisdictionDraft({ ...INDIA, amount_precision: 0, quantity_precision: 0, rounding_mode: 'down' });
    expect(draft).not.toHaveProperty('amount_precision');
    expect(draft).not.toHaveProperty('quantity_precision');
    expect(draft).not.toHaveProperty('rounding_mode');
    // Nor the payment terms or the locale, which are the operator's commercial choices.
    expect(draft).not.toHaveProperty('default_payment_terms_days');
    expect(draft).not.toHaveProperty('locale');
  });
});

describe('codeFrom', () => {
  it.each([
    ['Acme Manufacturing Private Limited', 'ACME-MANUFACTURING'],
    ['Søren & Co.', 'S-REN-CO'],
    ['   spaced   out   ', 'SPACED-OUT'],
    ['A', 'A'],
    ['!!!', ''],
  ])('suggests a document-safe code from %s', (name, code) => {
    expect(codeFrom(name)).toBe(code);
  });

  it('never exceeds the column, and never ends mid-separator', () => {
    const code = codeFrom('Northwind Overseas Trading and Manufacturing Private Limited');
    expect(code.length).toBeLessThanOrEqual(20);
    expect(code).not.toMatch(/-$/);
  });
});

describe('companyShortName', () => {
  it.each([
    ['Visva Enterprises Private Limited', 'VEPL'],
    ['visva enterprises pvt. ltd.', 'VEPL'],
    ['Acme Manufacturing Private Limited', 'AMPL'],
    ['Sharma Traders Pvt. Ltd.', 'STPL'],
    ['Acme, LLC', 'AL'],
    ['Acme L.L.P.', 'ALLP'],
    ['Acme Inc.', 'AI'],
    ['  Acme   Traders  ', 'AT'],
    ['Limited Edition Stores', 'LES'],
    ['A & B Traders', 'ABT'],
    ['Acme', 'Acme'],
    ['शर्मा ट्रेडर्स Pvt Ltd', 'शटPL'],
    ['', ''],
  ])('suggests a readable short name for %s', (name, expected) => {
    expect(companyShortName(name)).toBe(expected);
  });
  it('uses initials including the legal suffix for a long name', () => {
    expect(companyShortName('Acme International Manufacturing Distribution and Export Private Limited'))
      .toBe('AIMDAEPL');
  });
  it('bounds single long names without splitting Unicode characters', () => {
    expect(companyShortName('A'.repeat(60))).toBe('A'.repeat(40));
    expect(companyShortName('😀'.repeat(45))).toBe('😀'.repeat(40));
  });
});

describe('companyCode', () => {
  /** No `I`, `O`, `0` or `1`: the value is read off a printed document. */
  const SUFFIX = /^[2-9A-HJ-NP-Z]{4}$/;

  it('draws a four-character suffix from the unambiguous alphabet', () => {
    for (let i = 0; i < 200; i += 1) expect(codeSuffix()).toMatch(SUFFIX);
  });

  it('does not repeat itself', () => {
    // Not a distribution test — it catches a generator that returns a constant, which is the
    // way this fails in practice and the way `uq_company_tenant_id_code` would find out.
    expect(new Set(Array.from({ length: 50 }, codeSuffix)).size).toBeGreaterThan(1);
  });

  it('keeps the name readable and leaves room for the suffix', () => {
    expect(companyCode('Acme Manufacturing Private Limited', 'K7Q2')).toBe('ACME-K7Q2');
    expect(companyCode('Acme', 'K7Q2')).toBe('ACME-K7Q2');
  });

  it.each([
    'Northwind Overseas Trading and Manufacturing Private Limited',
    'Abcdefghijklmnopqrstuvwxyz',
    'Søren & Co.',
    'A',
  ])('fits the column for %s', (name) => {
    const code = companyCode(name, codeSuffix());
    expect(code.length).toBeLessThanOrEqual(CODE_MAX);
    expect(code).toMatch(/^[A-Z0-9-]+$/);
  });

  it('still produces a code for a name with nothing usable in it', () => {
    // `company.code` is NOT NULL and this value is never asked for, so there is no one to
    // fall back to.
    expect(companyCode('!!!', 'K7Q2')).toBe('CO-K7Q2');
  });
});

describe('fiscalYearSpan', () => {
  it('covers a full year ending the day before the next anchor', () => {
    expect(fiscalYearSpan(2026, 4, 1)).toEqual({ start: '2026-04-01', end: '2027-03-31' });
    expect(fiscalYearSpan(2026, 1, 1)).toEqual({ start: '2026-01-01', end: '2026-12-31' });
    expect(fiscalYearSpan(2026, 4, 6)).toEqual({ start: '2026-04-06', end: '2027-04-05' });
  });

  it('clamps a short month, the way the generator does', () => {
    // 31 January 2026 → the next anchor clamps to 31 January 2027, so the year ends on the 30th.
    expect(fiscalYearSpan(2026, 1, 31)).toEqual({ start: '2026-01-31', end: '2027-01-30' });
    // An impossible configured anchor must not look like a valid preview.
    expect(fiscalYearSpan(2026, 4, 31)).toEqual({ start: '', end: '' });
  });

  it('handles a leap-year anchor without inventing a 29 February', () => {
    expect(fiscalYearSpan(2024, 2, 29)).toEqual({ start: '2024-02-29', end: '2025-02-27' });
    expect(fiscalYearSpan(2023, 2, 29)).toEqual({ start: '2023-02-28', end: '2024-02-28' });
  });

  it('labels the span the way Accounting codes it', () => {
    expect(fiscalYearLabel(fiscalYearSpan(2026, 4, 1))).toBe('FY2026-2027');
    expect(fiscalYearLabel(fiscalYearSpan(2026, 1, 1))).toBe('FY2026-2026');
  });
});

describe('fiscalYearStartYear', () => {
  it('picks the year whose span contains the date', () => {
    expect(fiscalYearStartYear('2026-04-01', 4, 1)).toBe(2026);
    expect(fiscalYearStartYear('2026-03-31', 4, 1)).toBe(2025);
    expect(fiscalYearStartYear('2026-12-31', 1, 1)).toBe(2026);
    // A 6 April start: 1 April is still the previous year.
    expect(fiscalYearStartYear('2026-04-01', 4, 6)).toBe(2025);
  });
});

describe('withDependencies', () => {
  it('closes upward, so expiry brings batches and stock with it', () => {
    expect(withDependencies(CATALOGUE, ['expiry_tracking'])).toEqual(['inventory', 'batch_tracking', 'expiry_tracking']);
  });

  it('orders dependencies before the feature that needs them', () => {
    const chosen = withDependencies(CATALOGUE, ['multi_godown', 'serial_tracking']);
    expect(chosen.indexOf('inventory')).toBeLessThan(chosen.indexOf('multi_godown'));
    expect(chosen.indexOf('inventory')).toBeLessThan(chosen.indexOf('serial_tracking'));
  });

  it('de-duplicates and leaves an independent feature alone', () => {
    expect(withDependencies(CATALOGUE, ['budgets', 'budgets'])).toEqual(['budgets']);
  });

  it('answers nothing for a catalogue it has not received yet', () => {
    // The first render happens before the catalogue request lands; an empty answer offers no
    // capability rather than inventing one the server would reject.
    expect(withDependencies([], ['expiry_tracking'])).toEqual([]);
    expect(dependsOn([], 'expiry_tracking', 'inventory')).toBe(false);
  });
});

describe('dependsOn', () => {
  it('follows the chain however deep, so turning stock off drops expiry too', () => {
    expect(dependsOn(CATALOGUE, 'expiry_tracking', 'inventory')).toBe(true);
    expect(dependsOn(CATALOGUE, 'expiry_tracking', 'batch_tracking')).toBe(true);
    expect(dependsOn(CATALOGUE, 'batch_tracking', 'expiry_tracking')).toBe(false);
    expect(dependsOn(CATALOGUE, 'budgets', 'inventory')).toBe(false);
  });
});

describe('featureLabel', () => {
  it('names a feature, and falls back to its key rather than rendering nothing', () => {
    expect(featureLabel(CATALOGUE, 'batch_tracking')).toBe('Batches');
    expect(featureLabel(CATALOGUE, 'point_of_sale')).toBe('point_of_sale');
  });
});
