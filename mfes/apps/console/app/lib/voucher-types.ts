'use client';
import { useCallback, useMemo } from 'react';
import type { components } from '@janso/api-client/vouchers';
import { serviceCall, type ServiceRequest } from './service-call';
import { useServiceCommand, useServiceList, useServiceRead } from './service-resource';

type Wire = components['schemas'];

export type VoucherTypeItem = Wire['ResourceItem'];
export type VoucherTypeDetail = Wire['ResourceDetail'];

/**
 * The browser's one way to reach voucher types: the `vouchers` service, through the same proxy
 * boundary as every other call, so `lib/voucher-request-policy` decides whether a method and path
 * exist at all and the service then authorizes each against the actor's grants and the company
 * (`vouchers.read` to look, `vouchers.type.manage` to create, revise or retire).
 */
export const voucherTypeRequest = <T,>(request: ServiceRequest) =>
  serviceCall<T>('/api/product-fields', { service: 'vouchers', ...request }, 'voucher service');

export const typesPath = (company: string, rest = '') => `/v1/companies/${company}/voucher-types${rest}`;

import { isTypeId } from './voucher-type-routes';

export { TYPES_ROOT, isTypeId, typeHref } from './voucher-type-routes';

const mismatch = () => ({ status: 502, message: 'The voucher type response did not match this company. Reload before continuing.' });

/**
 * That a row is this company's. Not a permission check — the service made that. It is the
 * mismatch check for the company switcher: a reply can arrive for the company the reader has just
 * left and paint one company's type under another's name.
 */
export function assertTypeRow(row: { id?: string; company_id?: string } | null | undefined, company: string, id?: string): void {
  if (!row || !row.id || !isTypeId(row.id) || row.company_id !== company || (id !== undefined && row.id !== id)) throw mismatch();
}

export type TypeFilters = { q: string; kind: string; status: string };

/**
 * The catch-all "Purchase voucher" / "All Purchase vouchers" type some companies define by hand.
 * The company defaults provision the specific bill types (account, product, mixed), and the catch-all
 * does the same job as the account bill — so it is not offered beside them, by Operate or by the
 * New → Purchase chooser. One rule, so the two screens cannot disagree about it again.
 */
export const GENERIC_PURCHASE_TYPE = /^(?:all\s+)?purchase\s+vouchers?$/i;

/**
 * The Purchase types to offer. The catch-all is dropped only when a specific type remains: a
 * company whose one and only Purchase type is the catch-all must still be able to raise a bill.
 */
export function offeredPurchaseTypes<T extends { name?: string | null }>(types: readonly T[]): T[] {
  const specific = types.filter(row => !GENERIC_PURCHASE_TYPE.test((row.name ?? '').trim()));
  return specific.length ? specific : [...types];
}

/**
 * The types for a company, newest first, one page at a time.
 *
 * `q` is the service's own code-prefix search — a voucher type has no full-text index — so the
 * screen says "code starts with" rather than promising a name search it cannot do.
 */
export function useVoucherTypes(company: string, filters: TypeFilters) {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set('q', filters.q.trim());
  if (filters.kind) params.set('kind', filters.kind);
  if (filters.status) params.set('status', filters.status);
  return useServiceList<VoucherTypeItem>(
    typesPath(company),
    params.toString(),
    voucherTypeRequest,
    (row) => {
      assertTypeRow(row, company);
      // A row of another kind or status in a filtered list is the same breach as another company's.
      if ((filters.kind && row.kind !== filters.kind) || (filters.status && row.status !== filters.status)) throw mismatch();
    },
  );
}

/** One type with its current revision's policy. */
export function useVoucherType(company: string, id: string | undefined) {
  return useServiceRead<VoucherTypeDetail>(
    id ? typesPath(company, '/' + id) : undefined,
    voucherTypeRequest,
    (row) => assertTypeRow(row, company, id),
    'voucher service',
  );
}

/** `planned_sections` is every section the kind can ever carry — what a policy may require of it. */
export type KindCapability = { kind: string; family: string; profiles: string[]; planned_sections?: string[] };

/** Which profiles each kind supports — owned by the service's registry, so read, not restated. */
export function useKindCapabilities(company: string) {
  const read = useServiceRead<{ kinds: KindCapability[] }>(
    `/v1/companies/${company}/voucher-capabilities`,
    voucherTypeRequest,
    (value) => {
      if (!Array.isArray(value.kinds)) throw { status: 502, message: 'The voucher kinds could not be verified.' };
    },
    'voucher service',
  );
  return { kinds: read.data?.kinds ?? [], loading: read.loading, failure: read.failure, refresh: read.refresh };
}

export type CreateDraft = {
  code: string;
  name: string;
  kind: string;
  profile: string;
  /** The revision a type is derived from. Absent for a type started from scratch. */
  derivedFromRevisionId?: string;
  /**
   * The original's policy, for a copy. Without it the service intersects the original with the *default*
   * policy and the copy comes back on the defaults — approval, starting mode and narration reset — and an
   * original that is items-only cannot be copied at all.
   */
  policy?: Record<string, unknown>;
};

export const CODE = /^[A-Z][A-Z0-9_-]{0,39}$/;
export const NAME_MAX = 120;

/** The code as the service stores it. Upper-cased on the way out rather than refused for being typed in lower case. */
export const normaliseCode = (code: string) => code.trim().toUpperCase();

export function validateCreate(draft: CreateDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  const code = normaliseCode(draft.code);
  if (!code) errors.code = 'Enter a code.';
  else if (!CODE.test(code)) {
    errors.code = 'Start with a letter, then use letters, digits, hyphen or underscore — up to 40 characters.';
  }
  const name = draft.name.trim();
  if (!name) errors.name = 'Enter a name.';
  else if (name.length > NAME_MAX) errors.name = `Keep the name within ${NAME_MAX} characters.`;
  if (!draft.kind) errors.kind = 'Choose the kind of voucher this type is for.';
  if (draft.kind && !draft.profile) errors.profile = 'Choose a profile.';
  return errors;
}

export type TypeWrites = {
  create: (draft: CreateDraft) => Promise<VoucherTypeDetail | null>;
  revise: (id: string, input: { expectedVersion: number; policy: Record<string, unknown> }) => Promise<VoucherTypeDetail | null>;
  retire: (id: string, input: { expectedVersion: number }) => Promise<VoucherTypeDetail | null>;
  pending: boolean;
  uncertain: boolean;
  failure: string | null;
  /** The refusal's HTTP status, so a screen can tell a conflict from a validation failure. */
  status: number | null;
  fields: Record<string, string> | null;
  clear: () => void;
};

/**
 * The three writes. A retry of a write whose outcome is unknown replays the same key — the
 * service treats it as the same command, so a lost response never becomes a second type.
 */
export function useVoucherTypeWrites(company: string): TypeWrites {
  const command = useServiceCommand(voucherTypeRequest, 'voucher service');

  const run = useCallback(
    (path: string, body: unknown, id?: string) =>
      command.execute<VoucherTypeDetail>({ path, method: 'POST', body }, (value) => assertTypeRow(value, company, id)),
    [command, company],
  );

  const create = useCallback(
    (draft: CreateDraft) =>
      run(typesPath(company), {
        code: normaliseCode(draft.code),
        name: draft.name.trim(),
        kind: draft.kind,
        profile: draft.profile,
        ...(draft.derivedFromRevisionId ? { derived_from_revision_id: draft.derivedFromRevisionId } : {}),
        ...(draft.policy ? { policy: draft.policy } : {}),
      }),
    [company, run],
  );
  const revise = useCallback(
    (id: string, input: { expectedVersion: number; policy: Record<string, unknown> }) =>
      // No reason is sent: the service accepts one and records it nowhere, so asking for it would promise an audit trail it does not keep.
      run(typesPath(company, `/${id}/revisions`), { expected_version: input.expectedVersion, policy: input.policy }, id),
    [company, run],
  );
  const retire = useCallback(
    (id: string, input: { expectedVersion: number }) =>
      run(typesPath(company, `/${id}/retire`), { expected_version: input.expectedVersion }, id),
    [company, run],
  );

  return useMemo(
    () => ({
      create,
      revise,
      retire,
      pending: command.pending,
      uncertain: command.uncertain,
      failure: command.failure?.message ?? null,
      status: command.failure?.status ?? null,
      fields: command.failure?.fields ?? null,
      clear: command.clear,
    }),
    [command.clear, command.failure, command.pending, command.uncertain, create, retire, revise],
  );
}
