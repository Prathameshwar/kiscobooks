import { NextResponse, type NextRequest } from 'next/server';
import { allowedProductRequest } from '../../lib/product-request-policy';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/**
 * Product, voucher and money reads and writes, through the one proxy boundary
 * (`lib/service-proxy`). Only the allowlist and the service-to-origin map are this route's own.
 */
export async function POST(request: NextRequest) {
  return proxyServiceRequest(request, {
    allow: allowedProductRequest,
    subject: 'product field',
    // A voucher can carry 200 lines and the Vouchers service accepts up to 256 KiB of them; the default of
    // 16 KiB suits a catalog form and refused an ordinary Purchase of sixty lines before the service saw it.
    maximumBodyBytes: 320 * 1024,
    upstreamTimeoutMs: (input) => input.service === 'catalog' && input.method === 'POST'
      && /^\/v1\/companies\/[^/]+\/(products|product-families|simple-product-creations(?:\/[^/]+\/advance)?)$/.test(input.path) ? 45000 : 15000,
    // The allowlist decides which services this route serves; the table decides where they are.
    base: serviceOrigin,
    // Voucher import templates, result reports and report exports are files, not JSON envelopes.
    // A failure is still an envelope, so only a successful response is passed through.
    passthrough: (response, input) => {
      const media = response.headers.get('content-type') ?? '';
      if (!response.ok) return null;
      if (input.service === 'vouchers' && new RegExp(`^(?:text/csv|${XLSX})`).test(media)) {
        const csv = media.startsWith('text/csv');
        return new NextResponse(response.body, {
          headers: {
            'Content-Type': csv ? 'text/csv; charset=utf-8' : XLSX,
            'Content-Disposition': `attachment; filename="voucher-import.${csv ? 'csv' : 'xlsx'}"`,
            'Cache-Control': 'no-store',
          },
        });
      }
      if (input.service === 'reports' && media.startsWith('text/csv')) {
        return new NextResponse(response.body, {
          headers: {
            'Content-Type': 'text/csv; charset=utf-8',
            'Content-Disposition': 'attachment; filename="financial-report.csv"',
            'Cache-Control': 'no-store',
          },
        });
      }
      return null;
    },
  });
}
