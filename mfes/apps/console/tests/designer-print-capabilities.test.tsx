/**
 * Designer plan P0/P3 (2026-11-03): a layout routed to Purchase is checked against the manifest
 * the Purchase printer publishes, and publishing one it would refuse is blocked with the reason.
 * The manifest is read from Vouchers' contract file — the exact document its service returns.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DesignerShell } from '../app/(editor)/invoice-designer/DesignerShell';
import type { CanvasDefinition, CanvasElement, DesignTemplate } from '../app/(editor)/invoice-designer/layout-model';
import {
  NO_PICTURE, WITHDRAWN_PICTURE, imageProblems, manifestFor, printProblems, verifyPrintCapabilities, type PrintCapabilities,
} from '../app/(editor)/invoice-designer/print-capabilities';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';
import { designRequest } from '../app/lib/design-api';

vi.mock('../app/lib/design-api', async (original) => ({
  ...(await original<typeof import('../app/lib/design-api')>()),
  designRequest: vi.fn(),
}));
beforeEach(() => { vi.mocked(designRequest).mockReset(); });

const CONTRACT = JSON.parse(readFileSync(resolve(__dirname, '../../../../apis/vouchers/contracts/print-capabilities-v2.json'), 'utf8')) as PrintCapabilities;
const PURCHASE = manifestFor(verifyPrintCapabilities(CONTRACT), 'PURCHASE')!;
const GST = SAMPLE_TEMPLATES.find((template) => template.id === 'tpl-gst-a4')!;
const at = (id: string, type: CanvasElement['type'], xMm: number, yMm: number, widthMm: number, heightMm: number, extra: Partial<CanvasElement> = {}): CanvasElement =>
  ({ id, type, xMm, yMm, widthMm, heightMm, ...extra });

/** A designed bill the Purchase printer prints as drawn: positioned, styled, boxed and signed. */
function designed(): CanvasDefinition {
  return {
    ...GST.layout,
    page: { ...GST.layout.page, size: 'A4', orientation: 'PORTRAIT' },
    sections: [
      { id: 'top', type: 'HEADER', xMm: 10, yMm: 10, widthMm: 190, heightMm: 30, elements: [
        at('title', 'TEXT', 0, 0, 80, 8, { content: 'Purchase bill', style: { fontWeight: 'bold' } }),
        at('supplier', 'FIELD_BINDING', 110, 0, 80, 6, { bindingPath: 'party.name' }),
        at('frame', 'SHAPE', 110, 8, 80, 18, { style: { borderWidthMm: 0.3, borderStyle: 'solid' } }),
      ] },
      { id: 'lines', type: 'ITEM_TABLE', xMm: 10, yMm: 45, widthMm: 190, heightMm: 120, elements: [at('table', 'ITEM_TABLE', 0, 0, 190, 100)] },
      { id: 'sum', type: 'TOTALS', xMm: 10, yMm: 170, widthMm: 190, heightMm: 40, elements: [
        at('totals', 'TOTALS_BLOCK', 110, 0, 80, 30), at('sign', 'SIGNATURE', 0, 20, 60, 18, { content: 'For the company' }),
      ] },
    ],
  };
}
const change = (patch: (layout: CanvasDefinition) => void) => { const layout = structuredClone(designed()); patch(layout); return layout; };
const element = (layout: CanvasDefinition, id: string) => layout.sections.flatMap((section) => section.elements).find((row) => row.id === id)!;

describe('what Purchase prints, as its printer publishes it', () => {
  it('accepts a positioned, styled layout with boxes and signatures', () => {
    expect(printProblems(designed(), PURCHASE)).toEqual([]);
  });

  it.each<[string, (layout: CanvasDefinition) => void, string]>([
    ['a QR code', (layout) => layout.sections[2]!.elements.push(at('qr', 'QR_CODE', 70, 0, 20, 20)), 'QR codes'],
    ['a barcode', (layout) => layout.sections[2]!.elements.push(at('bar', 'BARCODE', 70, 0, 20, 20)), 'barcodes'],
    ['a field it cannot resolve', (layout) => { element(layout, 'supplier').bindingPath = 'party.gstin'; }, 'the field party.gstin'],
    // A Purchase bill records no batches, so batch, expiry and MRP stay unprintable (R1).
    ['a column it has no facts for', (layout) => { element(layout, 'table').columns = [{ key: 'batch', widthMm: 30, show: true }]; }, 'the Batch column'],
    ['the expiry column', (layout) => { element(layout, 'table').columns = [{ key: 'expiry', widthMm: 30, show: true }]; }, 'the Expiry column'],
    ['a total it cannot work out', (layout) => { element(layout, 'totals').totalsRows = ['outstanding_balance']; }, 'the outstanding balance total'],
    ['no item table', (layout) => { layout.sections[1]!.elements = []; }, 'without a line table'],
    ['a second item table', (layout) => layout.sections[1]!.elements.push(at('table-2', 'ITEM_TABLE', 0, 105, 190, 10)), 'more than one product table'],
    ['a tax summary by HSN', (layout) => layout.sections[2]!.elements.push(at('tax', 'TAX_SUMMARY', 0, 0, 100, 15, { taxGrouping: 'by_hsn' })), 'grouped by HSN'],
    ['a shared component', (layout) => { layout.sections[0]!.componentCode = 'TERMS'; }, 'shared components'],
  ])('refuses %s in the same words the printer uses', (_, patch, reason) => {
    const found = printProblems(change(patch), PURCHASE);
    const said = found.map((problem) => problem.message);
    expect(said.some((message) => message.startsWith('Purchase printing does not support') && message.includes(reason) && message.endsWith(' yet.'))).toBe(true);
    expect(found.every((problem) => problem.severity === 'error' && problem.code === 'print-unsupported')).toBe(true);
  });

  /*
   * Plan R1-R3 (2026-11-04): goods columns, amount in words, cess, pictures and rolls print now.
   * Nothing in the designer may still call them unprintable for Purchase.
   */
  it.each<[string, (layout: CanvasDefinition) => void]>([
    ['the HSN/SAC, quantity, unit and rate columns', (layout) => {
      element(layout, 'table').columns = (['hsn_sac', 'quantity', 'unit', 'rate'] as const).map((key) => ({ key, widthMm: 20, show: true }));
    }],
    ['the amount in words', (layout) => { element(layout, 'totals').totalsRows = ['grand_total', 'amount_in_words']; }],
    ['the cess and amount-in-words fields', (layout) => {
      layout.sections[2]!.elements.push(at('cess', 'FIELD_BINDING', 0, 0, 40, 5, { bindingPath: 'totals.cess' }), at('words', 'FIELD_BINDING', 0, 6, 100, 5, { bindingPath: 'totals.amount_in_words' }));
    }],
    ['an image with its picture chosen', (layout) => { layout.sections[0]!.elements.push(at('logo', 'IMAGE', 0, 10, 20, 10, { assetId: '01990000-0000-7000-8000-0000000000f1' })); }],
    ['a signature with a picture', (layout) => { element(layout, 'sign').assetId = '01990000-0000-7000-8000-0000000000f2'; }],
    ['an 80mm roll', (layout) => { layout.page.size = 'THERMAL_80MM'; }],
    ['a 58mm roll', (layout) => { layout.page.size = 'THERMAL_58MM'; }],
  ])('prints %s', (_, patch) => {
    expect(printProblems(change(patch), PURCHASE)).toEqual([]);
  });

  it('refuses an image with no picture chosen, in the printer’s words, on that image', () => {
    const found = printProblems(change((layout) => { layout.sections[0]!.elements.push(at('logo', 'IMAGE', 0, 10, 20, 10)); }), PURCHASE);
    expect(found).toEqual([{ code: 'print-unsupported', severity: 'error', targetId: 'logo', message: NO_PICTURE }]);
    expect(NO_PICTURE).toBe('An image on this layout has no picture chosen.');
  });

  it('accepts an accounts table in place of, or beside, the product table', () => {
    const accounts = change((layout) => { element(layout, 'table').type = 'ACCOUNT_TABLE'; element(layout, 'table').columns = [{ key: 'account', widthMm: 60, show: true }, { key: 'amount', widthMm: 40, show: true }]; });
    expect(printProblems(accounts, PURCHASE)).toEqual([]);
    const both = change((layout) => layout.sections.push({ id: 'acc', type: 'CUSTOM', xMm: 10, yMm: 215, widthMm: 190, heightMm: 20, elements: [at('accounts', 'ACCOUNT_TABLE', 0, 0, 190, 15)] }));
    expect(printProblems(both, PURCHASE)).toEqual([]);
    const crowded = change((layout) => layout.sections[1]!.elements.push(at('accounts', 'ACCOUNT_TABLE', 0, 105, 190, 10)));
    expect(printProblems(crowded, PURCHASE).map((problem) => problem.message)).toContain('Purchase printing does not support two line tables in the same zone yet.');
  });

  it('points each problem at what to fix', () => {
    const found = printProblems(change((layout) => { element(layout, 'supplier').bindingPath = 'party.gstin'; }), PURCHASE);
    expect(found.map((problem) => problem.targetId)).toEqual(['supplier']);
  });

  it('refuses a manifest that is not one, rather than trusting it', () => {
    expect(() => verifyPrintCapabilities({ version: '1', kinds: [{ kind: 'PURCHASE' }] } as never)).toThrow();
    // Image bounds, when stated, must be numbers the checks can compare against.
    expect(() => verifyPrintCapabilities({ ...CONTRACT, kinds: [{ ...PURCHASE, images: { max_bytes: 'big' } }] } as never)).toThrow();
    expect(PURCHASE.images).toEqual({ max_bytes: 524288, total_max_bytes: 655360, media_types: ['image/png', 'image/jpeg', 'image/webp'] });
  });
});

describe('pictures the printer would refuse, judged from the asset list (R2)', () => {
  const LOGO = '01990000-0000-7000-8000-0000000000f1';
  const SEAL = '01990000-0000-7000-8000-0000000000f2';
  const KB = 1024;
  const withPictures = (...ids: string[]) => change((layout) => ids.forEach((id, index) => layout.sections[0]!.elements.push(at(`pic-${index}`, 'IMAGE', 0, 10, 20, 10, { assetId: id }))));

  it('passes pictures inside both limits', () => {
    expect(imageProblems(withPictures(LOGO, SEAL), PURCHASE, [
      { id: LOGO, file_size_bytes: 300 * KB, is_active: true },
      { id: SEAL, file_size_bytes: 300 * KB, is_active: true },
    ])).toEqual([]);
  });

  it('refuses a picture over 512 KB on each element showing it', () => {
    const found = imageProblems(withPictures(LOGO, LOGO), PURCHASE, [{ id: LOGO, file_size_bytes: 512 * KB + 1, is_active: true }]);
    expect(found.map((problem) => [problem.targetId, problem.message])).toEqual([
      ['pic-0', 'An image on this layout is larger than 512 KB; upload a smaller picture.'],
      ['pic-1', 'An image on this layout is larger than 512 KB; upload a smaller picture.'],
    ]);
    expect(found.every((problem) => problem.severity === 'error')).toBe(true);
  });

  it('counts a picture placed twice once against the 640 KB budget', () => {
    expect(imageProblems(withPictures(LOGO, LOGO, LOGO), PURCHASE, [{ id: LOGO, file_size_bytes: 500 * KB, is_active: true }])).toEqual([]);
    const over = imageProblems(withPictures(LOGO, SEAL, LOGO), PURCHASE, [
      { id: LOGO, file_size_bytes: 400 * KB, is_active: true },
      { id: SEAL, file_size_bytes: 300 * KB, is_active: true },
    ]);
    expect(over).toEqual([{ code: 'print-unsupported', severity: 'error', targetId: 'pic-0', message: 'The images on this layout are larger than 640 KB together; use smaller pictures.' }]);
  });

  it('refuses a withdrawn picture', () => {
    expect(imageProblems(withPictures(LOGO), PURCHASE, [{ id: LOGO, file_size_bytes: KB, is_active: false }]).map((problem) => problem.message)).toEqual([WITHDRAWN_PICTURE]);
  });

  it('leaves a picture the list does not hold to the printer, and judges nothing for a kind without images', () => {
    expect(imageProblems(withPictures(LOGO), PURCHASE, [])).toEqual([]);
    const noImages = { ...PURCHASE, options: { ...PURCHASE.options, images: false } };
    expect(imageProblems(withPictures(LOGO), noImages, [{ id: LOGO, file_size_bytes: 10_000 * KB, is_active: false }])).toEqual([]);
    const { images: _unstated, ...unbounded } = PURCHASE;
    expect(imageProblems(withPictures(LOGO), unbounded, [{ id: LOGO, file_size_bytes: 10_000 * KB, is_active: true }])).toEqual([]);
  });
});

describe('the designer, for a template Purchase prints on', () => {
  const template = (layout: CanvasDefinition): DesignTemplate => ({ ...GST, id: 'tpl-purchase', isSystem: false, layout });

  it('lists the printing problems and blocks publishing', () => {
    render(<DesignerShell templates={[template(change((layout) => layout.sections[0]!.elements.push(at('qr', 'QR_CODE', 0, 10, 10, 10))))]} initialTemplateId="tpl-purchase" printManifest={PURCHASE} />);
    expect(screen.getAllByText(/Purchase printing does not support QR codes yet/).length).toBeGreaterThan(0);
  });

  it('shows no printing problems when the layout is one Purchase prints', () => {
    render(<DesignerShell templates={[template(designed())]} initialTemplateId="tpl-purchase" printManifest={PURCHASE} />);
    expect(screen.queryByText(/Purchase printing does not support/)).toBeNull();
  });

  it('blocks publishing a picture the printer would refuse, once the company’s assets are read', async () => {
    const LOGO = '01990000-0000-7000-8000-0000000000f1';
    const company = '01990000-0000-7000-8000-000000000001';
    vi.mocked(designRequest).mockResolvedValue({ items: [
      { id: LOGO, company_id: company, asset_name: 'Logo', asset_type: 'LOGO', file_name: 'logo.png', mime_type: 'image/png', file_size_bytes: 600 * 1024, is_active: true, created_at: '2026-11-01T00:00:00Z' },
    ] } as never);
    const layout = change((value) => { value.sections[0]!.elements.push(at('logo', 'IMAGE', 0, 10, 20, 10, { assetId: LOGO })); });
    render(<DesignerShell templates={[template(layout)]} initialTemplateId="tpl-purchase" printManifest={PURCHASE} company={company} />);
    expect(await screen.findAllByText('An image on this layout is larger than 512 KB; upload a smaller picture.')).not.toHaveLength(0);
    // Asked with withdrawn assets included, so a withdrawn picture can be named as one.
    await waitFor(() => expect(designRequest).toHaveBeenCalledWith(expect.objectContaining({ path: `/v1/companies/${company}/assets?limit=200&include_inactive=true` })));
    // A real company's picture is the company's, not "an asset this template does not carry".
    expect(screen.queryByText(/names an asset this template does not carry/)).toBeNull();
    expect(screen.getByRole('button', { name: /^Publish version/ })).toBeDisabled();
  });

  it('says an image without a picture once, as the printer’s error rather than also as a layout warning', () => {
    render(<DesignerShell templates={[template(change((layout) => { layout.sections[0]!.elements.push(at('logo', 'IMAGE', 0, 10, 20, 10)); }))]} initialTemplateId="tpl-purchase" printManifest={PURCHASE} />);
    expect(screen.getAllByText(NO_PICTURE).length).toBeGreaterThan(0);
    expect(screen.queryByText(/has no image assigned and prints as an empty frame/)).toBeNull();
  });

  it('does not judge a template no Purchase rule prints on', () => {
    render(<DesignerShell templates={[template(change((layout) => { layout.sections[1]!.elements = []; }))]} initialTemplateId="tpl-purchase" />);
    expect(screen.queryByText(/Purchase printing does not support/)).toBeNull();
  });
});
