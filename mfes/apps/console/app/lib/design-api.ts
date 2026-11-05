'use client';
import { serviceCall, type ServiceRequest } from './service-call';

/**
 * The browser's one way to reach the `design` service.
 *
 * Through the same proxy boundary as every other service call: the browser names a service, a
 * method and a path, never a URL and never a token, and `lib/design-request-policy` decides
 * whether that triple exists at all. The service then authorizes it again on arrival against
 * the actor's grants and the object's own company (docs/invoice-design.md §6.1).
 */
export const designRequest = <T,>(request: ServiceRequest) =>
  serviceCall<T>('/api/product-fields', { service: 'design', ...request }, 'design service');

export const designBase = (company: string, resource = '') =>
  `/v1/companies/${company}/templates${resource}`;

const UUID = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;

/** Anything carrying an id and a company — a template, a version, an assignment, an asset. */
export type DesignRow = {
  id: string;
  company_id?: string;
  template_id?: string;
  [key: string]: unknown;
};

/**
 * That the response is about the company the screen is open on.
 *
 * Not a permission check — the service already made that, and repeating it here would be
 * security theatre. It is a **mismatch** check, and the mismatch it catches is real: the
 * company is switchable from the rail, so a reply can arrive for the company the reader just
 * left and paint one company's template under another's name. A tenant-wide house-style row
 * legitimately carries no company of its own, so `company_id` is only compared when present.
 */
export function assertDesignRow(row: DesignRow, company: string, id?: string): DesignRow {
  const mismatched =
    !row ||
    !UUID.test(row.id) ||
    (id !== undefined && row.id !== id) ||
    (typeof row.company_id === 'string' && row.company_id !== company && !isTenantWide(row));
  if (mismatched) {
    throw { status: 502, message: 'The design response did not match this company. Reload before continuing.' };
  }
  return row;
}

/**
 * The shared design every company inherits: owned by the tenant, scoped to no company.
 *
 * The **sentinel alone**, deliberately. This also accepted `is_system === true`, which was a
 * second way to skip the company comparison — and a broader one, since a row could carry
 * another company's id and still pass on a flag. `is_system` says a design is *shipped*;
 * `SCOPE_ALL` says it belongs to no company, which is the only thing that makes "this reply is
 * not for the open company" the wrong conclusion.
 */
function isTenantWide(row: DesignRow): boolean {
  return row.company_id === SCOPE_ALL;
}

/** The all-zero company id: tenant-wide, never a real company (billing_platform constants). */
const SCOPE_ALL = '00000000-0000-0000-0000-000000000000';

/**
 * That a saved version came back as a *new* revision.
 *
 * `version_number` is the service's own counter, so a reply without one, or with a zero, means
 * the save did not append what the editor thinks it did — and the editor is about to tell the
 * reader their work is safe.
 */
export function assertDesignVersion(row: DesignRow, templateId?: string): DesignRow {
  const count = row?.version_number;
  if (
    !row ||
    !UUID.test(row.id) ||
    typeof count !== 'number' ||
    !Number.isSafeInteger(count) ||
    count < 1 ||
    (templateId !== undefined && row.template_id !== templateId)
  ) {
    throw { status: 502, message: 'The saved version could not be verified. Retry the same request.' };
  }
  return row;
}
