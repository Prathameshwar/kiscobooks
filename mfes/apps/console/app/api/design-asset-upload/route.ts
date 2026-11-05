import { NextRequest } from 'next/server';
import { allowedDesignAssetUpload } from '../../lib/design-asset-upload-policy';
import { proxyServiceRequest } from '../../lib/service-proxy';
import { serviceOrigin } from '../../lib/services';

/**
 * Uploading a brand asset's bytes (plan P4, 2026-11-03): the one `POST /assets` body, which
 * carries the file base64 and is far larger than the console's ordinary JSON envelope. Its
 * own route for the same reason `purchase-files` has one — a boundary with a wider body
 * ceiling needs to be the narrow one, not the shared product-fields proxy everything else
 * writes through.
 */
export async function POST(request: NextRequest) {
  return proxyServiceRequest(request, {
    allow: allowedDesignAssetUpload,
    subject: 'brand asset',
    // Design's own ceiling is 7,340,032 bytes (`max_asset_body_bytes`); comfortably above it,
    // the same margin `purchase-files` keeps over its own 10 MiB limit.
    maximumBodyBytes: 8 * 1024 * 1024,
    upstreamTimeoutMs: 20000,
    base: serviceOrigin,
  });
}
