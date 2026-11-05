import { NextResponse, type NextRequest } from 'next/server';
import { allowedPurchasePrintRequest } from '../../lib/purchase-print-policy';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';

export function POST(request: NextRequest) {
  return proxyServiceRequest(request, {
    allow: allowedPurchasePrintRequest, base: serviceOrigin, subject: 'Purchase print',
    upstreamTimeoutMs: 45000,
    passthrough: (response, input) => {
      if (!response.ok || !input.path.split('?')[0]!.endsWith('/download')) return null;
      if (response.headers.get('content-type')?.split(';')[0] !== 'application/pdf') {
        return NextResponse.json({ error: { message: 'Unexpected Purchase print format' } }, { status: 502 });
      }
      return new NextResponse(response.body, { headers: {
        'Content-Type': 'application/pdf', 'Content-Disposition': 'inline; filename="purchase-voucher.pdf"',
        'Cache-Control': 'no-store, private', 'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "default-src 'none'; sandbox",
      } });
    },
  });
}
