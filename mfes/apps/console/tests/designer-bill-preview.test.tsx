/**
 * Plan R4 (2026-11-04): *Preview with a saved bill* — the real Purchase PDF of a saved design
 * version (published or not) for one saved Purchase, marked as a preview on every page.
 *
 *  - **A saved version only.** The canvas with unsaved edits is saved as a draft first, and the
 *    preview continues with the version that save made — never with what is merely on screen.
 *  - **The bill is one saved revision.** Choosing it reads the bill, and the preview names that
 *    revision and row version exactly as a print does.
 *  - **The print, plus `layout_preview`.** Same job, polling, token download and verification;
 *    only the body, the words on the page and Back differ. A preview's refusals are a preview's:
 *    403 is the design read right, 409 the version or the bill.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { getToken } from 'next-auth/jwt';
import { DesignerShell, type DesignerPersistence } from '../app/(editor)/invoice-designer/DesignerShell';
import type { DesignTemplate } from '../app/(editor)/invoice-designer/layout-model';
import { SAMPLE_TEMPLATES } from '../app/(editor)/invoice-designer/sample-templates';
import { SavedBillPicker } from '../app/(editor)/invoice-designer/SavedBillPicker';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';
import { sessionFetch } from '../app/lib/session-fetch';
import { layoutPreviewHref, purchasePrintRequest } from '../app/lib/purchase-print';
import { allowedPurchasePrintRequest } from '../app/lib/purchase-print-policy';
import { POST } from '../app/api/purchase-print/route';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/session-fetch', () => ({ sessionFetch: vi.fn() }));
vi.mock('next-auth/jwt', () => ({ getToken: vi.fn() }));

const COMPANY = '01990000-0000-7000-8000-00000000000c';
const OTHER = '01990000-0000-7000-8000-00000000000d';
const TEMPLATE = '01990000-0000-7000-8000-000000000001';
const V1 = '01990000-0000-7000-8000-000000000011';
const V2 = '01990000-0000-7000-8000-000000000012';
const V3 = '01990000-0000-7000-8000-000000000013';
const BILL = '01990000-0000-7000-8000-0000000000c1';
const REVISION = '01990000-0000-7000-8000-0000000000c2';
const PAGE = { limit: 25, has_more: false, next_cursor: null };

const GST = SAMPLE_TEMPLATES.find((template) => template.id === 'tpl-gst-a4')!;
const saved: DesignTemplate = {
  ...GST,
  id: TEMPLATE,
  isSystem: false,
  versions: [
    { id: V1, versionNumber: 1, createdAt: '2026-11-01T00:00:00Z' },
    { id: V2, versionNumber: 2, createdAt: '2026-11-02T00:00:00Z' },
  ],
};

function persistence(overrides: Partial<DesignerPersistence> = {}): DesignerPersistence {
  return {
    saveDraft: vi.fn(async () => ({ id: V3, versionNumber: 3 })),
    publish: vi.fn(async () => null),
    pending: false,
    failure: null,
    uncertain: false,
    reload: vi.fn(),
    ...overrides,
  };
}

async function edit(user: ReturnType<typeof userEvent.setup>) {
  const grid = screen.getByLabelText('Grid step');
  await user.clear(grid);
  await user.type(grid, '10{Enter}');
}

beforeEach(() => {
  vi.mocked(serviceCall).mockReset();
  vi.mocked(sessionFetch).mockReset();
});

/* ------------------------------------------------------------------ the designer's control */

describe('the designer’s Preview with a saved bill', () => {
  it('is not offered without the print rights the route checks', () => {
    render(<DesignerShell templates={[saved]} initialTemplateId={TEMPLATE} persistence={persistence()} />);
    expect(screen.queryByRole('button', { name: 'Preview with a saved bill' })).toBeNull();
  });

  it('previews the newest saved version straight away when nothing is unsaved', async () => {
    const onPreview = vi.fn();
    const user = userEvent.setup();
    render(<DesignerShell templates={[saved]} initialTemplateId={TEMPLATE} persistence={persistence()} onPreviewWithBill={onPreview} />);
    expect(screen.getByTestId('bill-preview-state')).toHaveTextContent('Prints version 2 on a saved bill you choose');
    await user.click(screen.getByRole('button', { name: 'Preview with a saved bill' }));
    expect(onPreview).toHaveBeenCalledWith({ id: V2, versionNumber: 2 });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('asks to save unsaved edits first, saves a draft, then previews the version that save made', { timeout: 20000 }, async () => {
    const onPreview = vi.fn();
    const writes = persistence();
    const user = userEvent.setup();
    render(<DesignerShell templates={[saved]} initialTemplateId={TEMPLATE} persistence={writes} onPreviewWithBill={onPreview} />);
    await edit(user);
    expect(screen.getByTestId('bill-preview-state')).toHaveTextContent('Your changes are saved as a draft version first');

    await user.click(screen.getByRole('button', { name: 'Preview with a saved bill' }));
    const ask = await screen.findByRole('dialog', { name: 'Save this design first?' });
    expect(onPreview).not.toHaveBeenCalled();
    await user.click(within(ask).getByRole('button', { name: 'Save a draft' }));

    const draft = await screen.findByRole('dialog', { name: /as a draft\?/ });
    await user.type(within(draft).getByLabelText('What changed'), 'Logo moved left');
    await user.click(within(draft).getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(writes.saveDraft).toHaveBeenCalledOnce());
    await waitFor(() => expect(onPreview).toHaveBeenCalledWith({ id: V3, versionNumber: 3 }));
  });

  // Three dialogs and a rerender: slower than the default five seconds under a loaded runner.
  it('does not preview when the save is cancelled or fails, nor on a later ordinary save', { timeout: 30000 }, async () => {
    const onPreview = vi.fn();
    const writes = persistence({ saveDraft: vi.fn(async () => null), failure: 'The design service is unavailable.' });
    const user = userEvent.setup();
    const view = render(<DesignerShell templates={[saved]} initialTemplateId={TEMPLATE} persistence={writes} onPreviewWithBill={onPreview} />);
    await edit(user);

    await user.click(screen.getByRole('button', { name: 'Preview with a saved bill' }));
    await user.click(within(await screen.findByRole('dialog', { name: 'Save this design first?' })).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog')).toBeNull();

    await user.click(screen.getByRole('button', { name: 'Preview with a saved bill' }));
    await user.click(within(await screen.findByRole('dialog', { name: 'Save this design first?' })).getByRole('button', { name: 'Save a draft' }));
    const draft = await screen.findByRole('dialog', { name: /as a draft\?/ });
    await user.type(within(draft).getByLabelText('What changed'), 'Try');
    await user.click(within(draft).getByRole('button', { name: 'Save draft' }));
    expect(await within(draft).findByText('The design service is unavailable.')).toBeInTheDocument();
    await user.click(within(draft).getByRole('button', { name: 'Cancel' }));
    expect(onPreview).not.toHaveBeenCalled();

    // A plain Save draft afterwards is only a save.
    const works = persistence();
    view.rerender(<DesignerShell templates={[saved]} initialTemplateId={TEMPLATE} persistence={works} onPreviewWithBill={onPreview} />);
    await user.click(screen.getByRole('button', { name: /Save version .* as a draft/ }));
    const plain = await screen.findByRole('dialog', { name: /as a draft\?/ });
    await user.type(within(plain).getByLabelText('What changed'), 'Plain save');
    await user.click(within(plain).getByRole('button', { name: 'Save draft' }));
    await waitFor(() => expect(works.saveDraft).toHaveBeenCalledOnce());
    expect(onPreview).not.toHaveBeenCalled();
  });

  it('is held, and says why, on a read-only design with no saved version', () => {
    render(<DesignerShell templates={[{ ...saved, versions: [] }]} initialTemplateId={TEMPLATE} readOnlyReason="Read only." onPreviewWithBill={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Preview with a saved bill' })).toBeDisabled();
    expect(screen.getByTestId('bill-preview-state')).toHaveTextContent('This design has no saved version to preview yet.');
  });

  it('shows the Used for panel the route hands it, inside the editor rail', () => {
    render(<DesignerShell templates={[saved]} initialTemplateId={TEMPLATE} usage={<p>Used for: Purchase · all types</p>} />);
    expect(within(screen.getByRole('navigation')).getByText('Used for: Purchase · all types')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ choosing the bill */

function voucherRow(overrides: Record<string, unknown> = {}) {
  return { id: BILL, company_id: COMPANY, kind: 'PURCHASE', profile: 'STANDARD', status: 'POSTED', issue_number: 'PUR/26-27/0041', document_date: '2026-10-25', type_code: 'PURCHASE_GOODS', row_version: 3, ...overrides };
}
function voucherDetail(overrides: Record<string, unknown> = {}) {
  return { ...voucherRow(), revision_id: REVISION, revision_number: 2, type_revision_id: OTHER, invoice: { bill_reference: 'SUP/26-27/0418' }, ...overrides };
}
function bills(options: { rows?: unknown[]; listFailure?: { status: number; message: string }; detail?: unknown; detailFailure?: { status: number; message: string } } = {}) {
  return async (_endpoint: string, request: ServiceRequest) => {
    const path = request.path.split('?')[0]!;
    if (path.endsWith('/vouchers')) {
      if (options.listFailure) throw options.listFailure;
      return { items: options.rows ?? [voucherRow()], page: PAGE } as never;
    }
    if (path.endsWith(`/vouchers/${BILL}`)) {
      if (options.detailFailure) throw options.detailFailure;
      return (options.detail ?? voucherDetail()) as never;
    }
    throw new Error('unexpected ' + request.path);
  };
}
const picker = (onClose = vi.fn()) =>
  render(<SavedBillPicker company={COMPANY} templateId={TEMPLATE} version={{ id: V2, versionNumber: 2 }} open onClose={onClose} />);

describe('choosing the saved bill', () => {
  it('lists the company’s Purchase vouchers through the voucher boundary', async () => {
    vi.mocked(serviceCall).mockImplementation(bills());
    picker();
    expect(await screen.findByRole('dialog', { name: 'Preview version 2 with a saved bill' })).toBeInTheDocument();
    expect(await screen.findByText('PUR/26-27/0041')).toBeInTheDocument();
    const [list] = vi.mocked(serviceCall).mock.calls.map(([, request]) => request);
    expect(list!.service).toBe('vouchers');
    expect(list!.path).toMatch(new RegExp(`^/v1/companies/${COMPANY}/vouchers\\?kind=PURCHASE&`));
  });

  it('reads the chosen bill and shows its supplier bill number, date and status, then links the preview of that revision', async () => {
    vi.mocked(serviceCall).mockImplementation(bills());
    const user = userEvent.setup();
    picker();
    await user.click(await screen.findByRole('button', { name: /Choose the Purchase dated .*number PUR\/26-27\/0041/ }));
    const chosen = await screen.findByLabelText('Chosen bill');
    expect(chosen).toHaveTextContent('SUP/26-27/0418');
    expect(chosen).toHaveTextContent('posted');
    expect(screen.getByRole('link', { name: 'Open the preview' })).toHaveAttribute(
      'href',
      layoutPreviewHref({ templateId: TEMPLATE, designVersionId: V2, voucherId: BILL, revisionId: REVISION, version: 3 }),
    );
    await user.click(screen.getByRole('button', { name: 'Choose another bill' }));
    expect(await screen.findByText('PUR/26-27/0041')).toBeInTheDocument();
  });

  it('refuses a bill read that is not this company’s Purchase', async () => {
    vi.mocked(serviceCall).mockImplementation(bills({ detail: voucherDetail({ company_id: OTHER }) }));
    const user = userEvent.setup();
    picker();
    await user.click(await screen.findByRole('button', { name: /Choose the Purchase/ }));
    expect(await screen.findByText('The saved Purchase could not be verified for this company.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open the preview' })).toBeNull();
  });

  it.each([
    [403, 'You do not have access to read this Purchase.'],
    [401, 'Your session has expired. Sign in again, then choose the bill.'],
    [500, 'The voucher service is unavailable.'],
  ])('says a %s on reading the bill plainly', async (status, message) => {
    vi.mocked(serviceCall).mockImplementation(bills({ detailFailure: { status, message: 'The voucher service is unavailable.' } }));
    const user = userEvent.setup();
    picker();
    await user.click(await screen.findByRole('button', { name: /Choose the Purchase/ }));
    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it('shows the list’s own refusal state rather than an empty list', async () => {
    vi.mocked(serviceCall).mockImplementation(bills({ listFailure: { status: 403, message: 'denied' } }));
    picker();
    expect(await screen.findByText(/permission|access/i)).toBeInTheDocument();
    expect(screen.queryByText('No saved Purchase bills match')).toBeNull();
  });

  it('says when there is no saved Purchase to choose', async () => {
    vi.mocked(serviceCall).mockImplementation(bills({ rows: [] }));
    picker();
    expect(await screen.findByText('No saved Purchase bills match')).toBeInTheDocument();
  });

  it('refuses a list row of another kind', async () => {
    vi.mocked(serviceCall).mockImplementation(bills({ rows: [voucherRow({ kind: 'SALES' })] }));
    picker();
    await waitFor(() => expect(screen.queryByText('PUR/26-27/0041')).toBeNull());
    expect(await screen.findByRole('button', { name: /Retry|Try again/ })).toBeInTheDocument();
  });

  it('closes on Cancel', async () => {
    vi.mocked(serviceCall).mockImplementation(bills());
    const onClose = vi.fn();
    picker(onClose);
    await userEvent.setup().click(await screen.findByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});

/* ------------------------------------------------------------------ the request */

const failing = (status: number) => new Response(JSON.stringify({ error: { message: 'service words' } }), { status, headers: { 'Content-Type': 'application/json' } });

describe('a preview’s refusals', () => {
  const signal = new AbortController().signal;
  it.each([
    [403, 'You need permission to read designs (and their pictures, when the layout has any) to preview a layout with a saved bill'],
    [409, 'This design version cannot be previewed with this bill'],
    [422, 'This design version or the saved bill cannot be printed'],
    [401, 'Your session has expired'],
  ])('says a %s as a preview’s', async (status, words) => {
    vi.mocked(sessionFetch).mockResolvedValue(failing(status));
    await expect(purchasePrintRequest('/x', 'POST', signal, {}, 'key', 'layout-preview')).rejects.toThrow(words);
  });

  it('keeps an ordinary print’s words for an ordinary print', async () => {
    vi.mocked(sessionFetch).mockResolvedValue(failing(403));
    await expect(purchasePrintRequest('/x', 'POST', signal)).rejects.toThrow('Your access to this Purchase print has changed.');
    vi.mocked(sessionFetch).mockResolvedValue(failing(500));
    await expect(purchasePrintRequest('/x', 'POST', signal, {}, 'key', 'layout-preview')).rejects.toThrow('service words');
  });

  it('builds the preview link from identities only', () => {
    expect(layoutPreviewHref({ templateId: TEMPLATE, designVersionId: V2, voucherId: BILL, revisionId: REVISION, version: 3 }))
      .toBe(`/invoice-designer/${TEMPLATE}/preview?design_version=${V2}&voucher=${BILL}&revision=${REVISION}&version=3`);
  });
});

describe('the print boundary', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

  it('allows the print-job POST whatever its body carries: the path is policed, the body is the service’s to check', () => {
    expect(allowedPurchasePrintRequest('vouchers', 'POST', `/v1/companies/${COMPANY}/vouchers/${BILL}/print-jobs`)).toBe(true);
    expect(allowedPurchasePrintRequest('design', 'POST', `/v1/companies/${COMPANY}/vouchers/${BILL}/print-jobs`)).toBe(false);
  });

  it('forwards layout_preview to Vouchers unchanged, with the creation key', async () => {
    vi.stubEnv('NEXTAUTH_SECRET', 'test-runtime-only'); vi.stubEnv('AUTH_URL', 'http://localhost:4310');
    vi.stubEnv('VOUCHERS_GATEWAY_URL', 'http://gateway.test/vouchers');
    vi.mocked(getToken).mockResolvedValue({ accessToken: 'test-access', accessTokenExpires: Date.now() + 60000 } as never);
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: BILL, status: 'PENDING' }), { headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetcher);
    const body = { expected_version: 3, revision_id: REVISION, layout_preview: { template_id: TEMPLATE, version_id: V2 } };
    const path = `/v1/companies/${COMPANY}/vouchers/${BILL}/print-jobs`;
    const result = await POST(new NextRequest('http://localhost:4320/api/purchase-print', {
      method: 'POST', headers: { Origin: 'http://localhost:4320', 'Content-Type': 'application/json' },
      body: JSON.stringify({ service: 'vouchers', method: 'POST', path, body, key: 'preview-key' }),
    }));
    expect(result.status).toBe(200);
    const [url, init] = fetcher.mock.calls[0]!;
    expect(url).toBe(`http://gateway.test/vouchers${path}`);
    expect(JSON.parse(init.body)).toEqual(body);
    expect(init.headers).toMatchObject({ 'Idempotency-Key': 'preview-key' });
  });
});
