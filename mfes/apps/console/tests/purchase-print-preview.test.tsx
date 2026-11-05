import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { PurchasePrintPreview } from '../app/components/PurchasePrintPreview';
import { purchasePrintRequest, verifiedPurchasePdf } from '../app/lib/purchase-print';

vi.mock('../app/lib/purchase-print', () => ({ purchasePrintRequest: vi.fn(), verifiedPurchasePdf: vi.fn() }));
const id = '01990000-0000-7000-8000-000000000001';
const input = { company: id, voucherId: id, revisionId: id, version: 2 };
const ready = { id, status: 'READY', revision_number: 3, document_status: 'DRAFT',
  layout_name: 'Standard Purchase', layout_version: 'purchase-a4@1', download_token: 'signed' };
const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } });

beforeEach(() => {
  vi.resetAllMocks();
  URL.createObjectURL = vi.fn(() => 'blob:purchase-pdf');
  URL.revokeObjectURL = vi.fn();
  vi.mocked(verifiedPurchasePdf).mockResolvedValue(new Blob(['%PDF-1.7'], { type: 'application/pdf' }));
});

it('previews the verified saved revision, gates printing until loaded, downloads and revokes on exit', async () => {
  vi.mocked(purchasePrintRequest).mockResolvedValueOnce(json(ready)).mockResolvedValueOnce(new Response('%PDF-1.7'));
  const view = render(<PurchasePrintPreview {...input} />);
  expect(screen.getByRole('status')).toHaveTextContent(/Checking the saved Purchase/);
  const frame = await screen.findByTitle('Purchase voucher PDF preview');
  expect(screen.getByText(/Saved revision 3 · DRAFT/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Print PDF' })).toBeDisabled();
  fireEvent.load(frame);
  expect(screen.getByRole('button', { name: 'Print PDF' })).toBeEnabled();
  expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('download', `purchase-${id}.pdf`);
  expect(vi.mocked(purchasePrintRequest).mock.calls[0]?.[3]).toEqual({ expected_version: 2, revision_id: id });
  expect(verifiedPurchasePdf).toHaveBeenCalledOnce();
  view.unmount();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:purchase-pdf');
});

it('reuses the same creation key after an uncertain network failure', async () => {
  vi.mocked(purchasePrintRequest).mockRejectedValueOnce(new Error('Connection unavailable'))
    .mockResolvedValueOnce(json(ready)).mockResolvedValueOnce(new Response('%PDF-1.7'));
  render(<PurchasePrintPreview {...input} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection unavailable');
  fireEvent.click(screen.getByRole('button', { name: 'Retry print' }));
  await screen.findByTitle('Purchase voucher PDF preview');
  expect(vi.mocked(purchasePrintRequest).mock.calls[0]?.[4]).toBe(vi.mocked(purchasePrintRequest).mock.calls[1]?.[4]);
});

it('generates a new job after a terminal worker failure', async () => {
  vi.mocked(purchasePrintRequest).mockResolvedValueOnce(json({ ...ready, status: 'FAILED', failure_code: 'RENDER_TIMEOUT' }))
    .mockResolvedValueOnce(json(ready)).mockResolvedValueOnce(new Response('%PDF-1.7'));
  render(<PurchasePrintPreview {...input} />);
  expect(await screen.findByRole('alert')).toHaveTextContent(/took too long/);
  fireEvent.click(screen.getByRole('button', { name: 'Retry print' }));
  await screen.findByTitle('Purchase voucher PDF preview');
  expect(vi.mocked(purchasePrintRequest).mock.calls[0]?.[4]).not.toBe(vi.mocked(purchasePrintRequest).mock.calls[1]?.[4]);
});

it('never previews a PDF whose integrity verification fails', async () => {
  vi.mocked(purchasePrintRequest).mockResolvedValueOnce(json(ready)).mockResolvedValueOnce(new Response('%PDF-1.7'));
  vi.mocked(verifiedPurchasePdf).mockRejectedValueOnce(new Error('Integrity check failed'));
  render(<PurchasePrintPreview {...input} />);
  expect(await screen.findByRole('alert')).toHaveTextContent(/Integrity/);
  expect(screen.queryByTitle('Purchase voucher PDF preview')).not.toBeInTheDocument();
  expect(URL.createObjectURL).not.toHaveBeenCalled();
});

it('polls the same queued identity until its PDF is ready', async () => {
  vi.mocked(purchasePrintRequest).mockResolvedValueOnce(json({ ...ready, status: 'PENDING' }))
    .mockResolvedValueOnce(json(ready)).mockResolvedValueOnce(new Response('%PDF-1.7'));
  render(<PurchasePrintPreview {...input} />);
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/Preparing your Purchase PDF/));
  await screen.findByTitle('Purchase voucher PDF preview', {}, { timeout: 3000 });
  expect(vi.mocked(purchasePrintRequest).mock.calls[1]?.[0]).toBe(`/v1/companies/${id}/voucher-print-jobs/${id}`);
});

/* ---- Layout preview (designer plan R4): the same print, on one saved design version. ---- */
const template = '01990000-0000-7000-8000-0000000000d1';
const designV2 = '01990000-0000-7000-8000-0000000000d2';
const designV3 = '01990000-0000-7000-8000-0000000000d3';
const layoutPreview = { templateId: template, versionId: designV2, templateName: 'Our purchase bill', versionNumber: 2 };

it('asks for the bill on the chosen design version, says it is a layout preview, and leads back to the designer', async () => {
  vi.mocked(purchasePrintRequest).mockResolvedValueOnce(json({ ...ready, layout_name: 'Our purchase bill', layout_version: '2' })).mockResolvedValueOnce(new Response('%PDF-1.7'));
  render(<PurchasePrintPreview {...input} layoutPreview={layoutPreview} />);
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Layout preview of “Our purchase bill version 2”');
  expect(screen.getByText(/It is not the bill’s print: every page is marked “Layout preview · not for use”/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /designer/i })).toHaveAttribute('href', `/invoice-designer/${template}`);
  await screen.findByTitle('Layout preview PDF');
  const [path, method, , body, key, purpose] = vi.mocked(purchasePrintRequest).mock.calls[0]!;
  expect([path, method]).toEqual([`/v1/companies/${id}/vouchers/${id}/print-jobs`, 'POST']);
  expect(body).toEqual({ expected_version: 2, revision_id: id, layout_preview: { template_id: template, version_id: designV2 } });
  expect(key).toEqual(expect.any(String));
  // Every request in the preview reports its refusals as a preview's.
  expect(vi.mocked(purchasePrintRequest).mock.calls.every((call) => call[5] === 'layout-preview')).toBe(true);
  expect(screen.getByRole('link', { name: 'Download PDF' })).toHaveAttribute('download', `layout-preview-${id}.pdf`);
});

it('never sends layout_preview on an ordinary print', async () => {
  vi.mocked(purchasePrintRequest).mockResolvedValueOnce(json(ready)).mockResolvedValueOnce(new Response('%PDF-1.7'));
  render(<PurchasePrintPreview {...input} />);
  await screen.findByTitle('Purchase voucher PDF preview');
  expect(vi.mocked(purchasePrintRequest).mock.calls[0]?.[3]).not.toHaveProperty('layout_preview');
  expect(vi.mocked(purchasePrintRequest).mock.calls[0]?.[5]).toBe('print');
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Purchase print');
});

it('makes a new creation key when the previewed version changes, and keeps it for a retry of the same one', async () => {
  vi.mocked(purchasePrintRequest).mockRejectedValueOnce(new Error('Connection unavailable'))
    .mockResolvedValueOnce(json(ready)).mockResolvedValueOnce(new Response('%PDF-1.7'))
    .mockResolvedValueOnce(json(ready)).mockResolvedValueOnce(new Response('%PDF-1.7'));
  const view = render(<PurchasePrintPreview {...input} layoutPreview={layoutPreview} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection unavailable');
  fireEvent.click(screen.getByRole('button', { name: 'Retry print' }));
  await screen.findByTitle('Layout preview PDF');
  view.rerender(<PurchasePrintPreview {...input} layoutPreview={{ ...layoutPreview, versionId: designV3, versionNumber: 3 }} />);
  await waitFor(() => expect(vi.mocked(purchasePrintRequest).mock.calls.filter((call) => call[1] === 'POST')).toHaveLength(3));
  const posts = vi.mocked(purchasePrintRequest).mock.calls.filter((call) => call[1] === 'POST');
  expect(posts[0]?.[4]).toBe(posts[1]?.[4]);
  expect(posts[2]?.[4]).not.toBe(posts[1]?.[4]);
  expect(posts[2]?.[3]).toMatchObject({ layout_preview: { version_id: designV3 } });
});

it.each([
  ['403', 'You need permission to read designs (and their pictures, when the layout has any) to preview a layout with a saved bill, as well as permission to print Purchase bills.'],
  ['409', 'This design version cannot be previewed with this bill: the version is not one this company can use, or the bill cannot print as saved. Go back to the designer, save the design, and choose the bill again.'],
])('shows a preview %s refusal as the message it carries, with a retry', async (_, message) => {
  vi.mocked(purchasePrintRequest).mockRejectedValueOnce(new Error(message));
  render(<PurchasePrintPreview {...input} layoutPreview={layoutPreview} />);
  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  expect(screen.getByRole('button', { name: 'Retry print' })).toBeEnabled();
  expect(screen.queryByTitle('Layout preview PDF')).not.toBeInTheDocument();
});
