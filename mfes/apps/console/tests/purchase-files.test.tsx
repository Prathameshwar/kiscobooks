import React, { useState } from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseSupportingFiles } from '../app/components/PurchaseSupportingFiles';
import { allowedPurchaseFileRequest } from '../app/lib/purchase-file-policy';
import { purchaseFileCall, verifyPurchaseFile, type PurchaseStoredFile } from '../app/lib/purchase-files';
vi.mock('../app/lib/purchase-files', async original => ({ ...await original<typeof import('../app/lib/purchase-files')>(), purchaseFileCall: vi.fn(), fileBase64: vi.fn().mockResolvedValue('JVBERi0xLjc=') }));
const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const company = id(1), voucher = id(2), revision = id(3), path = `/v1/companies/${company}/vouchers/${voucher}/supporting-files`;
const file: PurchaseStoredFile = { id: id(4), company_id: company, voucher_id: voucher, filename: 'Bill.pdf', object_key: `${id(5)}/${company}/purchase/${voucher}/${'a'.repeat(64)}`, content_hash: 'a'.repeat(64), media_type: 'application/pdf', size_bytes: 8, download_token: null };
beforeEach(() => { vi.mocked(purchaseFileCall).mockReset(); });
afterEach(cleanup);
describe('private file proxy allowlist', () => {
  it('admits only bounded exact upload/list/download routes', () => {
    expect(allowedPurchaseFileRequest('vouchers', 'POST', path)).toBe(true);
    expect(allowedPurchaseFileRequest('vouchers', 'GET', path + '?revision_id=' + revision)).toBe(true);
    expect(allowedPurchaseFileRequest('vouchers', 'GET', path + '/' + id(4) + '/download?token=abc.def&revision_id=' + revision)).toBe(true);
    for (const candidate of [path + '?unexpected=true', path + '?revision_id=' + revision + '&revision_id=' + revision, path + '/../post', path + '/%2e%2e/post', path + '/extra', '//evil.invalid' + path]) expect(allowedPurchaseFileRequest('vouchers', 'POST', candidate)).toBe(false);
    expect(allowedPurchaseFileRequest('accounting', 'POST', path)).toBe(false);
    expect(allowedPurchaseFileRequest('vouchers', 'DELETE', path)).toBe(false);
    expect(allowedPurchaseFileRequest('vouchers', 'GET', path + '/' + id(4) + '/download')).toBe(false);
  });
  it('verifies file scope, exact immutable identity and bounds', () => {
    expect(() => verifyPurchaseFile(file, company, voucher)).not.toThrow();
    for (const changed of [{ company_id: id(99) }, { voucher_id: id(99) }, { object_key: '../escape' }, { content_hash: 'wrong' }, { size_bytes: 0 }, { media_type: 'text/html' }]) expect(() => verifyPurchaseFile({ ...file, ...changed }, company, voucher)).toThrow(/verified/);
  });
});
function Editor({ saved = true, change = vi.fn(), busy = vi.fn() }: { saved?: boolean; change?: (files: PurchaseStoredFile[]) => void; busy?: (value: boolean) => void }) {
  const [files, setFiles] = useState<PurchaseStoredFile[]>([]);
  return <PurchaseSupportingFiles company={company} voucher={saved ? voucher : undefined} revision={revision} version={7} enabled editable disabled={false} files={files} onChange={next => { setFiles(next); change(next); }} onBusy={busy} />;
}
describe('staged Purchase evidence', () => {
  it('allows another file after abandoning a failed upload without linking the failed registration', async () => {
    vi.mocked(purchaseFileCall).mockRejectedValueOnce({ status: 422, message: 'The file format does not match its bytes' }).mockResolvedValueOnce(file);
    const change = vi.fn(), view = render(<Editor change={change} />);
    const input = view.container.querySelector('input[type=file]')!;
    fireEvent.change(input, { target: { files: [new File(['invalid'], 'Wrong.pdf', { type: 'application/pdf' })] } });
    fireEvent.click(await screen.findByRole('button', { name: 'Choose a different file' }));
    expect(change).not.toHaveBeenCalled(); expect(input).not.toBeDisabled();
    fireEvent.change(input, { target: { files: [new File(['%PDF-1.7'], 'Bill.pdf', { type: 'application/pdf' })] } });
    await waitFor(() => expect(change).toHaveBeenCalledWith([file]));
    expect(vi.mocked(purchaseFileCall).mock.calls[0]![0].key).not.toBe(vi.mocked(purchaseFileCall).mock.calls[1]![0].key);
  });
  it('requires a saved draft before offering upload', () => {
    const view = render(<Editor saved={false} />); expect(screen.getByText('Save the bill first')).toBeVisible(); expect(view.container.querySelector('input[type=file]')).toBeDisabled();
  });
  it('registers verified bytes and preserves the same request/key on retry', async () => {
    vi.mocked(purchaseFileCall).mockRejectedValueOnce({ status: 503, message: 'Storage unavailable' }).mockResolvedValueOnce(file);
    const change = vi.fn(), busy = vi.fn(), view = render(<Editor change={change} busy={busy} />);
    fireEvent.change(view.container.querySelector('input[type=file]')!, { target: { files: [new File(['%PDF-1.7'], 'Bill.pdf', { type: 'application/pdf' })] } });
    await screen.findByRole('button', { name: 'Retry same file upload' }); expect(change).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Retry same file upload' }));
    await waitFor(() => expect(change).toHaveBeenCalledWith([file]));
    expect(vi.mocked(purchaseFileCall).mock.calls[0]).toEqual(vi.mocked(purchaseFileCall).mock.calls[1]);
    expect(vi.mocked(purchaseFileCall).mock.calls[0]![0]).toMatchObject({ path, method: 'POST', body: { expected_version: 7, media_type: 'application/pdf' } });
    expect(screen.queryByRole('button', { name: 'Download Bill.pdf' })).toBeNull();
    expect(busy).toHaveBeenLastCalledWith(false);
  });
  it('does not accept an upload response from another company', async () => {
    vi.mocked(purchaseFileCall).mockResolvedValue({ ...file, company_id: id(99) }); const change = vi.fn(), view = render(<Editor change={change} />);
    fireEvent.change(view.container.querySelector('input[type=file]')!, { target: { files: [new File(['%PDF-1.7'], 'Bill.pdf', { type: 'application/pdf' })] } });
    await screen.findByText(/could not be verified/); expect(change).not.toHaveBeenCalled();
  });
});
