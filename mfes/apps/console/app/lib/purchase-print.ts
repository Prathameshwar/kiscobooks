import type { components } from '@janso/api-client/vouchers';
import { sessionFetch } from './session-fetch';

export type PurchasePrintJob = components['schemas']['PrintJobDetail'];
/**
 * A saved design version to print the bill on once, to check the design (plan R4). The PDF is
 * marked as a layout preview on every page; it is never the bill's print.
 */
export type LayoutPreview = { templateId: string; versionId: string };
export type SavedPurchasePrint = { company: string; voucherId: string; revisionId: string; version: number; layoutPreview?: LayoutPreview };

export function purchasePrintHref(input: Omit<SavedPurchasePrint, 'company' | 'layoutPreview'>): string {
  return `/vouchers/${encodeURIComponent(input.voucherId)}/print?revision=${encodeURIComponent(input.revisionId)}&version=${input.version}`;
}

/** The designer's preview of one saved design version on one saved Purchase revision. */
export function layoutPreviewHref(input: { templateId: string; designVersionId: string; voucherId: string; revisionId: string; version: number }): string {
  const query = new URLSearchParams({
    design_version: input.designVersionId,
    voucher: input.voucherId,
    revision: input.revisionId,
    version: String(input.version),
  });
  return `/invoice-designer/${encodeURIComponent(input.templateId)}/preview?${query}`;
}

const MESSAGES: Record<number, string> = {
  401: 'Your session has expired. Sign in again, then retry this print.',
  403: 'Your access to this Purchase print has changed. Return to the voucher and check your access.',
  409: 'The Purchase or its print configuration has changed. Return to the saved voucher and try again.',
  422: 'The saved Purchase or its layout cannot be printed. Check its details and print settings.',
};

/** A preview is refused for its own reasons, and the person is told those rather than a print's. */
const PREVIEW_MESSAGES: Record<number, string> = {
  ...MESSAGES,
  403: 'You need permission to read designs (and their pictures, when the layout has any) to preview a layout with a saved bill, as well as permission to print Purchase bills.',
  409: 'This design version cannot be previewed with this bill: the version is not one this company can use, or the bill cannot print as saved. Go back to the designer, save the design, and choose the bill again.',
  422: 'This design version or the saved bill cannot be printed. Check the problems listed in the designer, then try again.',
};

export async function purchasePrintRequest(path: string, method: 'GET' | 'POST',
  signal: AbortSignal, body?: unknown, key?: string, purpose: 'print' | 'layout-preview' = 'print'): Promise<Response> {
  const response = await sessionFetch('/api/purchase-print', {
    method: 'POST', credentials: 'same-origin', cache: 'no-store', signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ service: 'vouchers', path, method, ...(body ? { body } : {}), ...(key ? { key } : {}) }),
  });
  if (!response.ok) {
    const value = await response.json().catch(() => null);
    const messages = purpose === 'layout-preview' ? PREVIEW_MESSAGES : MESSAGES;
    throw new Error(messages[response.status] ?? value?.error?.message ?? 'Purchase printing is unavailable. Retry shortly.');
  }
  return response;
}

export async function verifiedPurchasePdf(response: Response, job: PurchasePrintJob): Promise<Blob> {
  if (response.headers.get('content-type')?.split(';')[0] !== 'application/pdf') throw new Error('Unexpected Purchase print format.');
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Purchase PDF is empty. Retry the download.');
  const parts: Uint8Array<ArrayBuffer>[] = [];
  let size = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 10 * 1024 * 1024) throw new Error('Purchase PDF exceeds the supported size.');
      parts.push(new Uint8Array(value));
    }
  } finally { await reader.cancel(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), (n) => n.toString(16).padStart(2, '0')).join('');
  if (size !== job.size_bytes || digest !== job.content_hash || new TextDecoder().decode(bytes.slice(0, 5)) !== '%PDF-') {
    throw new Error('Purchase PDF integrity check failed. Reload the preview before using this copy.');
  }
  return new Blob([bytes], { type: 'application/pdf' });
}
