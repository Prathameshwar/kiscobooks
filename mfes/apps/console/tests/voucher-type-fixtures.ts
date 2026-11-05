/** Shared fixtures for the voucher type screens: the wire shapes, and a service double that speaks them. */
import { vi } from 'vitest';
import { serviceCall, type ServiceRequest } from '../app/lib/service-call';

export const COMPANY = '01990000-0000-7000-8000-00000000000c';
export const OTHER = '01990000-0000-7000-8000-00000000000d';
export const RETAIL = '01990000-0000-7000-8000-0000000000a1';
export const EXPORT = '01990000-0000-7000-8000-0000000000a2';
export const NEW_TYPE = '01990000-0000-7000-8000-0000000000a9';
export const REVISION = '01990000-0000-7000-8000-0000000000b1';
export const page = { limit: 25, has_more: false, next_cursor: null };

export const fullPolicy = {
  schema_version: 1,
  allowed_modes: ['ACCOUNTS', 'ITEMS', 'MIXED'],
  required_sections: [],
  forbidden_sections: [],
  max_lines: 200,
  max_parties: 20,
  narration_required: false,
  line_description_required: false,
  approval_required: true,
  self_approval_allowed: false,
  backdate_days: 3650,
  future_days: 365,
  supplier_reference_required: false,
  allowed_party_roles: ['CARRIER', 'CONSIGNEE', 'CUSTOMER', 'OTHER', 'PRINCIPAL', 'SUPPLIER', 'WORKER'],
  default_mode: 'ACCOUNTS',
  default_narration: '',
};

export function item(overrides: Record<string, unknown> = {}) {
  return {
    id: RETAIL,
    company_id: COMPANY,
    row_version: 3,
    status: 'ACTIVE',
    code: 'RETAIL',
    name: 'Retail sales',
    kind: 'SALES',
    profile: 'STANDARD',
    current_revision: 2,
    ...overrides,
  };
}

export function detail(overrides: Record<string, unknown> = {}) {
  return { ...item(), revision_id: REVISION, policy: fullPolicy, ...overrides };
}

export const capabilities = {
  registry_version: 1,
  kinds: [
    {
      kind: 'SALES',
      family: 'ACCOUNTING',
      profiles: ['STANDARD', 'PRO_FORMA'],
      planned_sections: ['ACCOUNTS', 'ATTACHMENTS', 'BILL_ALLOCATIONS', 'CHARGES', 'INVENTORY', 'ITEMS', 'PARTIES', 'REFERENCES', 'TAX', 'TENDERS'],
    },
    {
      kind: 'RECEIPT',
      family: 'ACCOUNTING',
      profiles: ['STANDARD', 'ADVANCE'],
      planned_sections: ['ACCOUNTS', 'ATTACHMENTS', 'BILL_ALLOCATIONS', 'PARTIES', 'REFERENCES', 'TENDERS'],
    },
    { kind: 'PHYSICAL_STOCK', family: 'INVENTORY', profiles: ['STANDARD'], planned_sections: ['ATTACHMENTS', 'INVENTORY', 'ITEMS', 'PARTIES', 'REFERENCES'] },
  ],
};

type Answers = {
  list?: unknown[];
  listPage?: unknown;
  one?: unknown;
  /** What a successful write returns. */
  written?: unknown;
  /** Throw this for a write instead. */
  writeFailure?: unknown;
  capabilities?: unknown;
};

/** The reads and writes the voucher type screens make, answered from `answers`. */
export function service(answers: Answers = {}) {
  return async (_endpoint: string, request: ServiceRequest) => {
    const method = request.method ?? 'GET';
    const path = request.path.split('?')[0]!;
    if (method !== 'GET') {
      if (answers.writeFailure) throw answers.writeFailure;
      // A revision or a retirement answers with the type it was sent to; a creation with a new one.
      const target = request.path.match(/voucher-types\/([0-9a-f-]{36})\//)?.[1];
      return (answers.written ?? detail({ id: target ?? NEW_TYPE })) as never;
    }
    if (path.endsWith('/voucher-capabilities')) return (answers.capabilities ?? capabilities) as never;
    if (path.endsWith('/voucher-types')) return { items: answers.list ?? [item()], page: answers.listPage ?? page } as never;
    return (answers.one ?? detail()) as never;
  };
}

export const calls = () => vi.mocked(serviceCall).mock.calls;
export const writes = () => calls().filter(([, request]) => (request.method ?? 'GET') !== 'GET');
export const reads = (suffix: string) =>
  calls().filter(([, request]) => (request.method ?? 'GET') === 'GET' && request.path.split('?')[0]!.endsWith(suffix));
export const lastRead = (suffix: string) => reads(suffix).at(-1)![1].path;
