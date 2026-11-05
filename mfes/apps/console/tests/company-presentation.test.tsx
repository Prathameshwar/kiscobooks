/**
 * The company wizard's presentation layer: the labels that reach the user, the capability
 * chain, and the live preview of the formatting choices.
 *
 * These exist because the review step was printing `gst_in` and `half_up` to the person about
 * to create a company, and because the preview that made those choices legible was being
 * rendered one step after they were made.
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { resolvedDisplay } from '@janso/ui';
import { FormatPreview } from '../app/components/FormatPreview';
import {
  DATE_FORMATS,
  capabilityTree,
  entityTypeLabel,
  roundingLabel,
  supportedTimezones,
  taxSystemLabel,
  taxSystemOptions,
  taxTreatmentLabel,
} from '../app/lib/company-labels';

describe('stored values never reach the screen as themselves', () => {
  it('names a tax system', () => {
    expect(taxSystemLabel('gst_in')).toBe('GST (India)');
    expect(taxSystemLabel('vat_gb')).toBe('VAT (United Kingdom)');
  });

  it('renders an unknown code as words rather than as a code', () => {
    // The countries endpoint sends bare codes, so a jurisdiction nobody has written a label
    // for is a question of when, not if. "GST SG" is wrong-ish; `gst_sg` is just wrong.
    expect(taxSystemLabel('gst_sg')).toBe('GST SG');
    expect(taxSystemLabel('')).toBe('');
  });

  it('builds select options from a country’s codes', () => {
    expect(taxSystemOptions(['gst_in'])).toEqual([{ value: 'gst_in', label: 'GST (India)' }]);
  });

  it('names an entity type, a rounding mode and a price convention', () => {
    expect(entityTypeLabel('pvt_ltd')).toBe('Private limited company');
    expect(taxTreatmentLabel('exclusive')).toBe('Prices exclude tax');
    // The worked example belongs in the select, where the choice is made — not in a review
    // line, where "rounded Half up — 0.005 becomes 0.01" is the explanation arriving twice.
    expect(roundingLabel('half_up')).toBe('half up');
    expect(roundingLabel('half_even')).toBe("banker's rounding");
  });

  it('falls back to words for a rounding mode it has not been taught', () => {
    expect(roundingLabel('half_down')).toBe('Half Down');
  });
});

describe('the capability chain', () => {
  const CATALOGUE = [
    { key: 'inventory', requires: [] },
    { key: 'multi_godown', requires: ['inventory'] },
    { key: 'batch_tracking', requires: ['inventory'] },
    { key: 'expiry_tracking', requires: ['batch_tracking'] },
    { key: 'budgets', requires: [] },
    { key: 'e_waybill', requires: ['inventory'] },
  ];

  it('puts each dependent directly after its parent, at its own depth', () => {
    expect(capabilityTree(CATALOGUE).map((entry) => [entry.item.key, entry.depth])).toEqual([
      ['inventory', 0],
      ['multi_godown', 1],
      ['batch_tracking', 1],
      ['expiry_tracking', 2],
      ['e_waybill', 1],
      ['budgets', 0],
    ]);
  });

  it('includes everything exactly once, whatever the order it arrives in', () => {
    const shuffled = [...CATALOGUE].reverse();
    const keys = capabilityTree(shuffled).map((entry) => entry.item.key);
    expect(new Set(keys).size).toBe(CATALOGUE.length);
    expect(keys).toHaveLength(CATALOGUE.length);
  });

  it('shows a capability whose requirement is not offered, rather than dropping it', () => {
    // The step filters the catalogue by tax system, so a dependent can outlive its parent in
    // the offered set. Hiding it would be a capability the operator can never reach.
    const orphan = capabilityTree([{ key: 'expiry_tracking', requires: ['batch_tracking'] }]);
    expect(orphan.map((entry) => [entry.item.key, entry.depth])).toEqual([['expiry_tracking', 0]]);
  });

  it('survives a cycle rather than recursing for ever', () => {
    const cyclic = [
      { key: 'a', requires: ['b'] },
      { key: 'b', requires: ['a'] },
    ];
    expect(capabilityTree(cyclic)).toHaveLength(2);
  });

  it('caps the indent rather than mis-indenting a deeper chain', () => {
    const deep = [
      { key: 'one', requires: [] },
      { key: 'two', requires: ['one'] },
      { key: 'three', requires: ['two'] },
      { key: 'four', requires: ['three'] },
    ];
    expect(capabilityTree(deep).map((entry) => entry.depth)).toEqual([0, 1, 2, 2]);
  });
});

describe('the format preview', () => {
  const display = (overrides: Record<string, unknown> = {}) =>
    resolvedDisplay({
      base_currency: 'INR',
      amount_precision: 2,
      quantity_precision: 3,
      rounding_mode: 'half_up',
      date_format: 'dd-MM-yyyy',
      datetime_format: 'dd-MM-yyyy HH:mm',
      digit_grouping: 'indian',
      currency_display: 'symbol',
      currency_symbol_override: '₹',
      currency_symbol_position: 'prefix',
      decimal_separator: '.',
      thousands_separator: ',',
      negative_format: 'minus',
      timezone: 'UTC',
      locale: 'en',
      ...overrides,
    } as never) as never;

  it('shows the choices as output, including the two a positive number hides', () => {
    render(<FormatPreview display={display()} today="2026-10-26" />);
    const panel = screen.getByTestId('format-preview');
    expect(panel).toHaveTextContent('26-10-2026');
    // Indian grouping, which is the whole reason this preview is worth having.
    expect(panel).toHaveTextContent('₹12,34,567.89');
    // Negative and zero: `negative_format` is invisible until a negative number is on screen.
    expect(panel).toHaveTextContent('-₹98,765.40');
    expect(panel).toHaveTextContent('₹0.00');
    expect(panel).toHaveTextContent('1,234.568');
  });

  it('follows the settings, so a change is visible as a change', () => {
    render(
      <FormatPreview
        display={display({
          digit_grouping: 'western',
          negative_format: 'parentheses',
          decimal_separator: ',',
          thousands_separator: '.',
          date_format: 'yyyy-MM-dd',
        })}
        today="2026-10-26"
      />,
    );
    const panel = screen.getByTestId('format-preview');
    expect(panel).toHaveTextContent('2026-10-26');
    expect(panel).toHaveTextContent('₹1.234.567,89');
    expect(panel).toHaveTextContent('(₹98.765,40)');
  });

  it('is output, so nothing in it is a tab stop', () => {
    render(<FormatPreview display={display()} today="2026-10-26" />);
    const panel = screen.getByTestId('format-preview');
    expect(panel.querySelectorAll('button, input, a, select')).toHaveLength(0);
  });
});

describe('presentation suggestions', () => {
  it('offers date patterns without closing the set', () => {
    // A `Select` here would remove the quoted-literal patterns `formatDate` handles on
    // purpose, so these are suggestions behind a text field.
    expect(DATE_FORMATS).toContain('dd-MM-yyyy');
    expect(DATE_FORMATS).toContain('yyyy-MM-dd');
  });

  it('offers the runtime zones and the canonical ones, so the field value is always listed', () => {
    const zones = supportedTimezones();
    expect(zones.length).toBeGreaterThan(0);
    // This runtime reports Asia/Calcutta; the company default is Asia/Kolkata. Both are
    // valid IANA names and both have to be offered, or opening the list hides the value
    // already in the field.
    expect(zones).toContain('Asia/Kolkata');
    expect(zones).toContain('UTC');
    expect(new Set(zones).size).toBe(zones.length);
  });
});
