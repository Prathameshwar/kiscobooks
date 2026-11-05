import type { NextRequest } from 'next/server';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';
import { allowedSalesEntryRequest } from '../../lib/sales-entry-request-policy';

/**
 * The sales bill page's calls to Vouchers, Accounting and Catalog, through the one proxy
 * boundary (`lib/service-proxy`): the browser names a service, a method and a path, the
 * allowlist decides whether that triple exists, and the session's token is attached here.
 */
export async function POST(request: NextRequest) {
  return proxyServiceRequest(request, {
    allow: allowedSalesEntryRequest,
    base: serviceOrigin,
    subject: 'sales bill',
  });
}
