import { NextResponse, type NextRequest } from 'next/server';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';
import { allowedFinancialOpeningRequest } from '../../lib/financial-opening-policy';

export async function POST(request: NextRequest) {
  return proxyServiceRequest(request, {
    allow: allowedFinancialOpeningRequest,
    base: serviceOrigin,
    subject: 'account and party opening',
    maximumBodyBytes: 3 * 1024 * 1024 + 4096,
    upstreamTimeoutMs: 35000,
    passthrough: response => response.ok && response.headers.get('content-type')?.startsWith('text/csv')
      ? new NextResponse(response.body, { headers: {
        'Content-Type': 'text/csv; charset=utf-8',
        'Content-Disposition': 'attachment; filename="account-party-opening.csv"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
      } }) : null,
  });
}
