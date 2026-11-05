/**
 * Designer plan P1/P2 (2026-11-03): a design knows whether its lines are products, accounts or
 * both, and offers the tables that go with it — a product table, an accounts table, or one of
 * each — with columns that make sense for each.
 */
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import { templatePurpose } from '../app/(editor)/invoice-designer/TemplateGallery';
import { addableFor, availableColumns, placeElement } from '../app/(editor)/invoice-designer/layout-edit';
import type { CanvasElement, DesignTemplate, LineProfile } from '../app/(editor)/invoice-designer/layout-model';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';

const GST = SAMPLE_TEMPLATES.find((template) => template.id === 'tpl-gst-a4')!;
const designFor = (lineProfile?: LineProfile): DesignTemplate => ({ ...GST, id: 'tpl-ctx', isSystem: false, voucherKind: 'PURCHASE', ...(lineProfile ? { lineProfile } : {}) });
const table = (type: CanvasElement['type']): CanvasElement => ({ id: 't', type, xMm: 0, yMm: 0, widthMm: 190, heightMm: 30, columns: [] });

describe('which tables a design offers', () => {
  it.each<[LineProfile | undefined, string[]]>([
    ['ITEMS', ['ITEM_TABLE']],
    ['ACCOUNTS', ['ACCOUNT_TABLE']],
    ['MIXED', ['ITEM_TABLE', 'ACCOUNT_TABLE']],
    [undefined, ['ITEM_TABLE', 'ACCOUNT_TABLE']],
  ])('for %s lines, offers %j', (profile, tables) => {
    const offered = addableFor(profile);
    expect(offered.filter((kind) => kind.endsWith('_TABLE'))).toEqual(tables);
    expect(offered).toEqual(expect.arrayContaining(['TEXT', 'TOTALS_BLOCK', 'TAX_SUMMARY']));
  });

  it('shows only the accounts table in the palette of an accounts design, and adds it across its zone', async () => {
    render(<DesignerShell templates={[designFor('ACCOUNTS')]} initialTemplateId="tpl-ctx" />);
    expect(screen.queryByRole('button', { name: /Add product table/ })).toBeNull();
    const session = userEvent.setup();
    await session.click(within(screen.getByRole('tree', { name: 'Page structure' })).getByRole('treeitem', { name: /Footer/ }));
    await session.click(screen.getByRole('button', { name: 'Add accounts table to Footer' }));
    expect(screen.getByTestId('selection-readout').textContent).toMatch(/^account table · 10, [\d.]+ mm · 190 × 30 mm$/);
  });

  it('names what a design is for', () => {
    expect(templatePurpose({ voucherKind: 'PURCHASE', lineProfile: 'MIXED' })).toBe('Purchase · Products and accounts');
    expect(templatePurpose({})).toBe('Any voucher');
  });
});

describe('a placed table', () => {
  it('fills its zone with columns that fit it', () => {
    const zone = GST.layout.sections[0]!;
    for (const kind of ['ITEM_TABLE', 'ACCOUNT_TABLE'] as const) {
      const placed = placeElement(GST.layout, zone.id, kind);
      const element = placed.layout.sections[0]!.elements.at(-1)!;
      expect(element.widthMm).toBe(zone.widthMm);
      const used = (element.columns ?? []).reduce((sum, column) => sum + column.widthMm, 0);
      expect(used).toBeLessThanOrEqual(zone.widthMm);
      expect(used).toBeGreaterThan(zone.widthMm - 1);
    }
    const accounts = placeElement(GST.layout, zone.id, 'ACCOUNT_TABLE').layout.sections[0]!.elements.at(-1)!;
    expect(accounts.columns!.map((column) => column.key)).toEqual(['serial_no', 'account', 'description', 'taxable_value', 'amount']);
    const totals = placeElement(GST.layout, zone.id, 'TOTALS_BLOCK').layout.sections[0]!.elements.at(-1)!;
    expect(totals.totalsRows).toContain('grand_total');
  });

  it('offers each table only the columns its lines have', () => {
    expect(availableColumns(table('ACCOUNT_TABLE'))).toContain('account');
    expect(availableColumns(table('ACCOUNT_TABLE'))).not.toContain('quantity');
    expect(availableColumns(table('ITEM_TABLE'))).toContain('quantity');
    expect(availableColumns(table('ITEM_TABLE'))).not.toContain('account');
  });

  it('draws an accounts table with sample ledgers', async () => {
    const withAccounts = placeElement(GST.layout, GST.layout.sections[0]!.id, 'ACCOUNT_TABLE').layout;
    const { container } = render(<DesignerShell templates={[{ ...designFor('ACCOUNTS'), layout: withAccounts }]} initialTemplateId="tpl-ctx" />);
    const canvas = within(container.querySelector('[data-testid="design-canvas-paper"]') as HTMLElement);
    expect(canvas.getAllByText('Freight Inward').length).toBeGreaterThan(0);
    expect(canvas.getAllByText('Account').length).toBeGreaterThan(0);
  });
});
