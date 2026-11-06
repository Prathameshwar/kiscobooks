/**
 * Plan R4 (2026-11-04): *Customize layout* for Purchase starts from a canvas of the standard
 * Purchase layout (`purchase-a4@7`) instead of an empty page.
 *
 * The starter is judged by the designer's own checks and by the manifest the Purchase printer
 * publishes (read from Vouchers' contract file, the exact document its service returns), for each
 * line profile — so the first thing a person sees when they customize is a layout that prints.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PermissionProvider } from '@janso/ui';
import { columnBudget } from '../app/(editor)/invoice-designer/layout-edit';
import { isLineTable, type LineProfile } from '../app/(editor)/invoice-designer/layout-model';
import { checkLayout } from '../app/(editor)/invoice-designer/layout-warnings';
import { manifestFor, printProblems, verifyPrintCapabilities, type PrintCapabilities } from '../app/(editor)/invoice-designer/print-capabilities';
import { sampleValue } from '../app/(editor)/invoice-designer/sample-document';
import {
  STANDARD_ACCOUNT_COLUMNS,
  STANDARD_PRODUCT_COLUMNS,
  standardPurchaseLayout,
  standardPurchaseStarter,
} from '../app/(editor)/invoice-designer/standard-purchase';
import { NewTemplateDialog } from '../app/(editor)/invoice-designer/NewTemplateDialog';
import { isEditableLayout, layoutToEditor, layoutToWire } from '../app/lib/design-canvas';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import { goTo } from '../app/lib/navigate';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

import { VoucherPrintKind } from '../app/components/VoucherPrintKind';

const CONTRACT = JSON.parse(readFileSync(resolve(__dirname, '../../../../apis/vouchers/contracts/print-capabilities-v2.json'), 'utf8')) as PrintCapabilities;
const PURCHASE = manifestFor(verifyPrintCapabilities(CONTRACT), 'PURCHASE')!;
const PROFILES: LineProfile[] = ['ITEMS', 'ACCOUNTS', 'MIXED'];
const A4 = { paper_size: 'A4', page_orientation: 'PORTRAIT' };

const tables = (profile: LineProfile) =>
  standardPurchaseLayout(profile).sections.flatMap((section) => section.elements.filter((element) => isLineTable(element.type)).map((element) => ({ section, element })));

describe('the standard Purchase layout, as a canvas', () => {
  it.each(PROFILES)('passes the designer’s own checks with nothing to fix, for %s lines', (profile) => {
    expect(checkLayout(standardPurchaseLayout(profile))).toEqual([]);
  });

  it.each(PROFILES)('is a layout the Purchase printer prints, for %s lines', (profile) => {
    expect(printProblems(standardPurchaseLayout(profile), PURCHASE)).toEqual([]);
  });

  it.each(PROFILES)('survives the trip to the service and back unchanged, for %s lines', (profile) => {
    const layout = standardPurchaseLayout(profile);
    const wire = layoutToWire(layout);
    expect(isEditableLayout(wire)).toBe(true);
    expect(layoutToEditor(wire, A4)).toEqual(layout);
  });

  it('carries the standard layout’s blocks, in its order, bound to what a Purchase prints', () => {
    const layout = standardPurchaseLayout('ITEMS');
    expect(layout.page).toMatchObject({ size: 'A4', orientation: 'PORTRAIT', margins: { top: 18, right: 15, bottom: 22, left: 15 } });
    expect(layout.sections.map((section) => section.id)).toEqual(['sec-header', 'sec-parties', 'sec-items', 'sec-totals', 'sec-narration']);
    const bound = layout.sections.flatMap((section) => section.elements).map((element) => element.bindingPath).filter(Boolean);
    expect(bound).toEqual([
      'company.name', 'voucher.status',
      'party.name', 'voucher.bill_reference', 'voucher.document_date',
      'voucher.document_number', 'voucher.posting_date', 'voucher.due_date', 'voucher.currency',
      'voucher.narration',
    ]);
    // Every binding is one the printer resolves, and one the canvas preview has a sample for.
    for (const path of bound) {
      expect(PURCHASE.bindings).toContain(path);
      expect(sampleValue(path!)).not.toBeNull();
    }
    const texts = layout.sections.flatMap((section) => section.elements).map((element) => element.content).filter(Boolean);
    expect(texts).toContain('Purchase voucher');
    const totals = layout.sections.flatMap((section) => section.elements).find((element) => element.type === 'TOTALS_BLOCK');
    expect(totals?.totalsRows).toEqual(['subtotal', 'cgst', 'sgst', 'igst', 'round_off', 'grand_total', 'amount_in_words']);
  });

  it('prints goods with HSN/SAC, quantity, unit and rate, and accounts with their ledger', () => {
    expect(STANDARD_PRODUCT_COLUMNS.map((column) => column.key)).toEqual(['serial_no', 'description', 'hsn_sac', 'quantity', 'unit', 'rate', 'taxable_value', 'amount']);
    expect(STANDARD_ACCOUNT_COLUMNS.map((column) => column.key)).toEqual(['serial_no', 'account', 'description', 'amount']);
    expect(tables('ITEMS').map(({ element }) => element.type)).toEqual(['ITEM_TABLE']);
    expect(tables('ACCOUNTS').map(({ element }) => element.type)).toEqual(['ACCOUNT_TABLE']);
    // Every table's columns fill it exactly: an overflow is the error a designer cannot see.
    for (const profile of PROFILES) {
      for (const { element } of tables(profile)) expect(columnBudget(element)).toEqual({ usedMm: 180, totalMm: 180 });
    }
  });

  it('gives a mixed bill both tables, products first, each in its own zone', () => {
    const both = tables('MIXED');
    expect(both.map(({ element }) => element.type)).toEqual(['ITEM_TABLE', 'ACCOUNT_TABLE']);
    expect(new Set(both.map(({ section }) => section.id)).size).toBe(2);
    expect(both[0]!.section.yMm).toBeLessThan(both[1]!.section.yMm);
  });

  it('starts a design that never said what its lines are with products', () => {
    expect(standardPurchaseLayout(undefined)).toEqual(standardPurchaseLayout('ITEMS'));
  });

  it('hands back a fresh tree each time, so editing one starter cannot change the next', () => {
    const first = standardPurchaseLayout('ITEMS');
    first.sections[2]!.elements[0]!.columns![0]!.widthMm = 99;
    expect(standardPurchaseLayout('ITEMS').sections[2]!.elements[0]!.columns![0]!.widthMm).toBe(8);
  });
});

describe('the starter on the paper a person chose', () => {
  it.each([
    ['A4 portrait', { paperSize: 'A4', orientation: 'PORTRAIT' }],
    ['Letter portrait', { paperSize: 'LETTER', orientation: 'PORTRAIT' }],
    ['a large custom sheet', { paperSize: 'CUSTOM', orientation: 'PORTRAIT', widthMm: '250', heightMm: '320' }],
  ])('fits %s, on that paper', (_, paper) => {
    const starter = standardPurchaseStarter('ITEMS', paper);
    expect(starter?.page.size).toBe(paper.paperSize);
    expect(checkLayout(starter!).filter((warning) => warning.severity === 'error')).toEqual([]);
  });

  it.each([
    ['an 80mm roll', { paperSize: 'THERMAL_80MM', orientation: 'PORTRAIT' }],
    ['a 58mm roll', { paperSize: 'THERMAL_58MM', orientation: 'PORTRAIT' }],
    ['A5', { paperSize: 'A5', orientation: 'PORTRAIT' }],
    ['A4 landscape', { paperSize: 'A4', orientation: 'LANDSCAPE' }],
    ['a small custom sheet', { paperSize: 'CUSTOM', orientation: 'PORTRAIT', widthMm: '150', heightMm: '200' }],
    ['a custom sheet with no size', { paperSize: 'CUSTOM', orientation: 'PORTRAIT' }],
  ])('does not fit %s, which opens empty instead', (_, paper) => {
    expect(standardPurchaseStarter('MIXED', paper)).toBeNull();
  });
});

/* ------------------------------------------------------------------ Customize */

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const FRESH = '01990000-0000-7000-8000-000000000007';
const FIRST_PAGE = { limit: 200, has_more: false, next_cursor: null };

function responder() {
  return async (_endpoint: string, request: ServiceRequest) => {
    const path = request.path.split('?')[0]!;
    const method = request.method ?? 'GET';
    if (path.endsWith('/assignments') && method === 'GET') return { items: [], page: FIRST_PAGE } as never;
    if (path.endsWith('/templates') && method === 'GET') return { items: [], page: FIRST_PAGE } as never;
    if (path.endsWith('/templates')) return { id: FRESH, company_id: COMPANY, initial_version_id: '01990000-0000-7000-8000-000000000008' } as never;
    return { id: '01990000-0000-7000-8000-0000000000a1', company_id: COMPANY, voucher_kind: 'PURCHASE', template_id: FRESH, priority: 100, is_active: true, created_at: '2026-11-04T00:00:00Z' } as never;
  };
}
const created = () =>
  vi.mocked(serviceCall).mock.calls.map(([, request]) => request).find((request) => request.method === 'POST' && request.path.endsWith('/templates'));

function mountKind(kind = 'PURCHASE') {
  return render(
    <PermissionProvider permissions={['design.template.read']}>
      <VoucherPrintKind company={COMPANY} kind={kind} canManageTemplates canReadRouting canManageRouting />
    </PermissionProvider>,
  );
}

async function openCustomize(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('button', { name: 'Customize layout' }));
  const dialog = await screen.findByRole('dialog', { name: 'Customize layout' });
  await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), 'Our purchase bill');
  await user.type(within(dialog).getByRole('textbox', { name: /Code/ }), 'our-purchase');
  return dialog;
}

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
  vi.mocked(serviceCall).mockImplementation(responder());
  vi.mocked(goTo).mockReset();
});

describe('Customize layout for Purchase', () => {
  it('says it starts from the standard layout, and creates the template with it as the first version', async () => {
    const user = userEvent.setup();
    mountKind();
    const dialog = await openCustomize(user);
    expect(within(dialog).getByText(/It opens in the designer on a copy of the standard layout/)).toBeInTheDocument();
    expect(within(dialog).getByTestId('template-starter')).toHaveTextContent('settlements and adjustments that this design cannot yet reproduce');

    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));
    await waitFor(() => expect(goTo).toHaveBeenCalledWith('/invoice-designer/' + FRESH));
    const body = created()!.body as Record<string, unknown>;
    expect(body).toMatchObject({ voucher_kind: 'PURCHASE', line_profile: 'ITEMS', paper_size: 'A4', page_orientation: 'PORTRAIT' });
    expect(body.initial_canvas).toEqual(layoutToWire(standardPurchaseLayout('ITEMS')));
  });

  it.each<[string, LineProfile]>([
    ['Products and accounts', 'MIXED'],
    ['Accounts and expenses', 'ACCOUNTS'],
  ])('starts a design for %s from that profile’s standard layout', async (label, profile) => {
    const user = userEvent.setup();
    mountKind();
    const dialog = await openCustomize(user);
    await user.selectOptions(within(dialog).getByRole('combobox', { name: /Lines/ }), label);
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));
    await waitFor(() => expect(created()).toBeDefined());
    const body = created()!.body as Record<string, unknown>;
    expect(body.line_profile).toBe(profile);
    expect(body.initial_canvas).toEqual(layoutToWire(standardPurchaseLayout(profile)));
  });

  it('opens on an empty page, and says so, on paper the standard layout does not fit', async () => {
    const user = userEvent.setup();
    mountKind();
    const dialog = await openCustomize(user);
    await user.selectOptions(within(dialog).getByRole('combobox', { name: /Paper/ }), '80mm roll');
    expect(within(dialog).getByTestId('template-starter')).toHaveTextContent('on this paper the design starts on an empty page');
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));
    await waitFor(() => expect(created()).toBeDefined());
    expect(created()!.body).not.toHaveProperty('initial_canvas');
  });

  it('keeps an empty page for kinds with no standard canvas yet', async () => {
    const user = userEvent.setup();
    mountKind('SALES');
    const dialog = await openCustomize(user);
    expect(within(dialog).getByText(/It opens in the designer on an empty page/)).toBeInTheDocument();
    expect(within(dialog).queryByTestId('template-starter')).toBeNull();
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));
    await waitFor(() => expect(created()).toBeDefined());
    expect(created()!.body).not.toHaveProperty('initial_canvas');
  });

  it('keeps the gallery’s plain New template empty, even when Purchase is chosen', async () => {
    const user = userEvent.setup();
    render(<NewTemplateDialog company={COMPANY} open onClose={() => undefined} />);
    const dialog = await screen.findByRole('dialog', { name: 'New template' });
    await user.type(within(dialog).getByRole('textbox', { name: /Name/ }), 'Purchase A4');
    await user.type(within(dialog).getByRole('textbox', { name: /Code/ }), 'purchase-a4');
    await user.selectOptions(within(dialog).getByRole('combobox', { name: /Prints/ }), 'Purchase');
    expect(within(dialog).queryByTestId('template-starter')).toBeNull();
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));
    await waitFor(() => expect(created()).toBeDefined());
    expect(created()!.body).toMatchObject({ voucher_kind: 'PURCHASE' });
    expect(created()!.body).not.toHaveProperty('initial_canvas');
  });

  it('keeps the form and says why when the service refuses the starter', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if (request.method === 'POST' && request.path.endsWith('/templates')) {
        throw { status: 422, message: 'the layout does not fit the paper this template prints on' };
      }
      return responder()(endpoint, request);
    });
    const user = userEvent.setup();
    mountKind();
    const dialog = await openCustomize(user);
    await user.click(within(dialog).getByRole('button', { name: /Create and open/ }));
    expect(await within(dialog).findByText('the layout does not fit the paper this template prints on')).toBeInTheDocument();
    expect(goTo).not.toHaveBeenCalled();
    expect(within(dialog).getByRole('textbox', { name: /Name/ })).toHaveValue('Our purchase bill');
  });
});
