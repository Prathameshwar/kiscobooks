import type { components } from '@janso/api-client/vouchers';
import { serviceCall, type ServiceRequest } from './service-call';
import { sessionFetch } from './session-fetch';
import { purchaseBase } from './purchase-api';
import { trackingId } from './stock-tracking-resources';

export type PurchaseStoredFile = components['schemas']['SupportingFileDetail'];
export const purchaseFileCall = <T,>(request: ServiceRequest) => serviceCall<T>('/api/purchase-files', { service: 'vouchers', ...request }, 'Purchase supporting file');
export function verifyPurchaseFile(value: unknown, company: string, voucher: string): asserts value is PurchaseStoredFile {
  const file = value as PurchaseStoredFile | null;
  if (!file || !trackingId.test(file.id) || file.company_id !== company || file.voucher_id !== voucher || !/^[a-f0-9]{64}$/.test(file.content_hash) || !Number.isInteger(file.size_bytes) || file.size_bytes < 1 || file.size_bytes > 10 * 1024 * 1024 || !['application/pdf', 'image/png', 'image/jpeg', 'text/plain'].includes(file.media_type) || typeof file.filename !== 'string' || file.filename.length > 160 || typeof file.object_key !== 'string' || !file.object_key.endsWith('/purchase/' + voucher + '/' + file.content_hash) || file.object_key.split('/')[1] !== company) throw Error('The supporting-file response could not be verified for this Purchase.');
}
export function purchaseFileBase(company: string, voucher: string): string {
  if (!trackingId.test(voucher)) throw Error('Save this Purchase before uploading files.');
  return purchaseBase(company) + '/vouchers/' + voucher + '/supporting-files';
}
export function fileBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onerror = () => reject(Error('The file could not be read. Select it again.'));
    reader.onload = () => { const value = reader.result; if (typeof value !== 'string' || !value.includes(',')) reject(Error('The file could not be read.')); else resolve(value.slice(value.indexOf(',') + 1)); };
    reader.readAsDataURL(file);
  });
}
export async function downloadPurchaseFile(company: string, voucher: string, revision: string, file: PurchaseStoredFile): Promise<void> {
  // Obtain a fresh short-lived ticket under current field and document authority.
  const rows = await purchaseFileCall<PurchaseStoredFile[]>({ path: purchaseFileBase(company, voucher) + '?revision_id=' + revision });
  const current = rows.find(row => row.id === file.id); if (!current?.download_token) throw Error('This file is no longer available for this revision.');
  verifyPurchaseFile(current, company, voucher);
  const path = purchaseFileBase(company, voucher) + '/' + current.id + '/download?' + new URLSearchParams({ revision_id: revision, token: current.download_token });
  const response = await sessionFetch('/api/purchase-files', { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ service: 'vouchers', method: 'GET', path }) }, true);
  if (!response.ok) throw Error('Download is unavailable or your access changed. Refresh and try again.');
  const blob = await response.blob();
  if (blob.size !== current.size_bytes || !crypto.subtle || Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', await blob.arrayBuffer())), byte => byte.toString(16).padStart(2, '0')).join('') !== current.content_hash) throw Error('The downloaded file failed integrity verification.');
  const href = URL.createObjectURL(blob), anchor = document.createElement('a'); anchor.href = href; anchor.download = current.filename; anchor.click(); setTimeout(() => URL.revokeObjectURL(href), 1000);
}
