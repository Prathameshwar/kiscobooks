'use client';

import { serviceCall, type ServiceRequest } from './service-call';

/** The services the sales bill page talks to. */
export type SalesService = 'identity' | 'vouchers' | 'accounting' | 'catalog';

/**
 * One call from the sales bill page, through its own route.
 *
 * The replay rule, the error envelope and the idempotency key travel exactly as every other
 * console call's do (`service-call`); only the endpoint and the allowlist behind it are this
 * page's own.
 */
export function salesCall<T>(service: SalesService, request: Omit<ServiceRequest, 'service'>): Promise<T> {
  return serviceCall<T>('/api/sales-entry', { ...request, service }, 'sales bill');
}

/** A company-scoped path. Every call this page makes is one. */
export const companyPath = (company: string, rest: string) => `/v1/companies/${company}${rest}`;
