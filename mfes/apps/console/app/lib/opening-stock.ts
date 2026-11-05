'use client';
import type { components as Accounting } from '@janso/api-client/accounting';
import type { components as Vouchers } from '@janso/api-client/vouchers';
import { serviceCall, type ServiceRequest } from './service-call';
import { sessionFetch } from './session-fetch';
import { trackingId } from './stock-tracking-resources';
export type Readiness = Accounting['schemas']['OpeningReadiness'];
export type Control = Accounting['schemas']['OpeningControlDetail'];
export type Manifest = Accounting['schemas']['OpeningManifest-Input'];
export type Allocation = Accounting['schemas']['StockLine-Input'];
export type Calculation = Accounting['schemas']['OpeningCalculated'];
export type Capture = Accounting['schemas']['OpeningCapture-Input'];
export type ImportJob = Vouchers['schemas']['OpeningImportDetail'];
export type ImportStage = Vouchers['schemas']['OpeningImportStage'];
export type OpeningAccess = {
  manage: boolean;
  draft: boolean;
  importRead: boolean;
  commit: boolean;
  zero: boolean;
  export: boolean;
};
export const openingBase = (company: string) =>
  `/v1/companies/${company}/stock/openings`;
export const importBase = (company: string) =>
  `/v1/companies/${company}/stock-opening-imports`;
export const openingRequest = <T>(request: ServiceRequest) =>
  serviceCall<T>(
    '/api/opening-stock',
    { service: 'accounting', ...request },
    'opening stock',
  );
export const openingImportRequest = <T>(request: ServiceRequest) =>
  openingRequest<T>({ ...request, service: 'vouchers' });
export const openingCatalogRequest = <T>(request: ServiceRequest) =>
  openingRequest<T>({ ...request, service: 'catalog' });
export function owned<T extends { company_id: string }>(company: string) {
  return (row: T) => {
    if (row.company_id !== company)
      throw {
        status: 502,
        message:
          'Opening ownership could not be verified. Reload the current company.',
      };
  };
}
export function verifyControl(company: string) {
  return (row: Control) => {
    owned(company)(row);
    if (
      !trackingId.test(row.id) ||
      !Number.isSafeInteger(row.expected_version) ||
      row.expected_version < 1 ||
      !Array.isArray(row.blockers) ||
      !/^[a-f0-9]{64}$/.test(row.manifest_hash) ||
      !Array.isArray(row.missing_source_keys) ||
      !['OPEN', 'FINALIZED'].includes(row.status) ||
      !Number.isSafeInteger(row.expected_cohorts) ||
      !Number.isSafeInteger(row.applied_cohorts) ||
      !decimal(row.expected_value) ||
      !decimal(row.applied_value)
    )
      throw {
        status: 502,
        message:
          'The opening confirmation could not be verified. Retry the same request.',
      };
  };
}
export function verifyJob(company: string) {
  return (row: ImportJob) => {
    owned(company)(row);
    if (
      !trackingId.test(row.id) ||
      !Number.isSafeInteger(row.row_version) ||
      row.row_version < 1 ||
      !Array.isArray(row.effects) ||
      !Array.isArray(row.errors) ||
      [...row.effects, ...row.errors].some(
        (value) => !value || typeof value !== 'object',
      ) ||
      ![row.chunk_count, row.created_chunks, row.validated_chunks].every(
        (value) => Number.isSafeInteger(value) && value >= 0 && value <= 100,
      ) ||
      row.created_chunks > row.chunk_count ||
      row.validated_chunks > row.chunk_count
    )
      throw {
        status: 502,
        message:
          'The draft job confirmation could not be verified. Retry the same request.',
      };
  };
}
/** Exact DECIMAL(19,4), including the storage precision fence. */
export function decimal(value: string, positive = false): boolean {
  return (
    /^(?:0|[1-9]\d{0,14})(?:\.\d{1,4})?$/.test(value) &&
    (!positive || /[1-9]/.test(value))
  );
}
export function sum(values: string[]): string {
  let total = 0n;
  for (const value of values) {
    if (!decimal(value))
      throw new Error('An exact carrying value is required.');
    const [whole, fraction = ''] = value.split('.');
    total += BigInt(whole!) * 10000n + BigInt(fraction.padEnd(4, '0'));
  }
  return `${total / 10000n}.${String(total % 10000n).padStart(4, '0')}`;
}
export function validateAllocation(
  line: Allocation,
  mode: Manifest['opening_mode'],
): string | null {
  if (
    ![
      line.line_id,
      line.item_id,
      line.warehouse_id,
      line.opening?.entered_unit_id,
      line.opening?.unit_revision_id,
    ].every((id) => trackingId.test(id ?? ''))
  )
    return 'Select the product, warehouse and effective unit.';
  if (
    !decimal(line.quantity, true) ||
    !decimal(line.opening!.entered_quantity, true) ||
    !decimal(line.received_value ?? '')
  )
    return 'Calculate a positive quantity and an explicit carrying value.';
  if (
    !/[1-9]/.test(line.received_value!) &&
    (line.zero_value_reason ?? '').trim().length < 3
  )
    return 'Explain why this stock has zero carrying value.';
  if (
    mode === 'LINKED_GL' &&
    /[1-9]/.test(line.received_value!) &&
    !trackingId.test(line.opening_journal_line_id ?? '')
  )
    return 'Select the posted inventory opening line.';
  if (new Set(line.unit_ids ?? []).size !== (line.unit_ids ?? []).length)
    return 'Each serial can be selected only once.';
  return null;
}
export const blockers: Record<string, { label: string; href?: string }> = {
  STOCK_POSTING_NOT_ENABLED: {
    label:
      'Stock posting awaits installation activation. You can prepare and review drafts.',
  },
  STOCK_ACCOUNTS_NOT_CONFIGURED: {
    label:
      'Configure inventory and opening-offset accounts effective at books begin.',
    href: '/inventory/stock?view=account-policies',
  },
  ACCOUNTING_NOT_INITIALIZED: {
    label: 'Initialize company accounting.',
    href: '/accounting/setup',
  },
  BOOKS_BEGIN_PERIOD_NOT_OPEN: {
    label: 'Open the financial period containing books begin.',
    href: '/financial-periods',
  },
  LATER_BOOKS_CLOSED: {
    label: 'Later books are closed. A controller must review the period locks.',
    href: '/financial-periods',
  },
  FINANCIAL_OPENING_NOT_FINALIZED: {
    label: 'Finalize the separate financial opening balances.',
    href: '/accounting',
  },
  LEGACY_ACTIVITY_REQUIRES_REVIEW: {
    label:
      'Existing stock history needs a controller-reviewed adoption. Do not declare it as zero stock.',
  },
  EXECUTION_UNCONFIRMED: {
    label:
      'A stock execution is awaiting confirmation. Resolve its native voucher before changing the worksheet.',
  },
  OPENING_NOT_FINALIZED: { label: 'Company opening is not finalized.' },
};
export async function openingDownload(
  service: 'accounting' | 'vouchers',
  ticketPath: string,
  company: string,
) {
  const ticket = await openingRequest<{ download_path: string }>({
    service,
    path: ticketPath,
  });
  const prefix =
    service === 'accounting' ? openingBase(company) : importBase(company);
  if (!ticket.download_path.startsWith(prefix + '/'))
    throw new Error('The export destination could not be verified.');
  const response = await sessionFetch(
    '/api/opening-stock',
    {
      method: 'POST',
      cache: 'no-store',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        service,
        method: 'GET',
        path: ticket.download_path,
      }),
    },
    true,
  );
  if (
    !response.ok ||
    !response.headers.get('content-type')?.startsWith('text/csv')
  )
    throw new Error(
      'Export is unavailable or access has changed. Reload and try again.',
    );
  const url = URL.createObjectURL(await response.blob()),
    anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'opening-stock.csv';
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
