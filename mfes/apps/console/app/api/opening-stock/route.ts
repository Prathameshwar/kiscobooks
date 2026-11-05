import { NextResponse, type NextRequest } from 'next/server';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';
import { allowedOpeningRequest } from '../../lib/opening-stock-policy';

export async function POST(request: NextRequest) {
  return proxyServiceRequest(request, {
    allow: allowedOpeningRequest,
    base: serviceOrigin,
    subject: 'opening stock',
    maximumBodyBytes: 3 * 1024 * 1024 + 4096,
    upstreamTimeoutMs: 30000,
    passthrough: (response) =>
      response.ok &&
      response.headers.get('content-type')?.startsWith('text/csv')
        ? new NextResponse(response.body, {
            headers: {
              'Content-Type': 'text/csv; charset=utf-8',
              'Content-Disposition': 'attachment; filename="opening-stock.csv"',
              'Cache-Control': 'no-store',
              'X-Content-Type-Options': 'nosniff',
            },
          })
        : null,
  });
}
