import { NextResponse, type NextRequest } from 'next/server';
import { allowedPurchaseFileRequest } from '../../lib/purchase-file-policy';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';

export function POST(request: NextRequest) {
  return proxyServiceRequest(request, {
    allow: allowedPurchaseFileRequest, base: serviceOrigin, subject: 'Purchase supporting file',
    maximumBodyBytes: 14 * 1024 * 1024, upstreamTimeoutMs: 35000,
    passthrough: (response, input) => {
      if (!response.ok || !input.path.split('?')[0]!.endsWith('/download')) return null;
      const media = response.headers.get('content-type')?.split(';')[0] ?? '';
      if (!['application/pdf', 'image/png', 'image/jpeg', 'text/plain'].includes(media)) return null;
      return new NextResponse(response.body, { headers: {
        'Content-Type': media, 'Content-Disposition': 'attachment; filename="purchase-supporting-file"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "default-src 'none'; sandbox",
      } });
    },
  });
}
