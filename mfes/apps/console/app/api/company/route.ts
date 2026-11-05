import type { NextRequest } from 'next/server';
import { allowedCompanyRequest } from '../../lib/company-request-policy';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';

/**
 * Company context and company setup, through the one proxy boundary (`lib/service-proxy`).
 * Identity owns the company, Accounting the chart/calendar, Catalog its default masters,
 * and Vouchers its company voucher types and rules.
 */
export async function POST(request: NextRequest) {
  return proxyServiceRequest(request, {
    allow: allowedCompanyRequest,
    subject: 'company setup',
    upstreamTimeoutMs: input => input.service === 'accounting' && input.method === 'POST'
      && /^\/v1\/companies\/[^/]+\/(?:accounting|financial)-setup\/initialize$/.test(input.path) ? 45000 : 15000,
    base: serviceOrigin,
  });
}
