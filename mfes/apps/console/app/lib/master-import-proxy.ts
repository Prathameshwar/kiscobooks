import { NextResponse, type NextRequest } from 'next/server';
import { proxyServiceRequest } from './service-proxy';
import { serviceOrigin } from './services';

export async function masterImportProxy(
  request: NextRequest,
  allow: (service: string, method: string, path: string) => boolean,
  subject: string,
  upstreamTimeoutMs = 35000,
) {
  return proxyServiceRequest(request, {
    allow,
    base: serviceOrigin,
    subject,
    maximumBodyBytes: 13 * 1024 * 1024,
    upstreamTimeoutMs,
    passthrough: (response) => {
      const media = response.headers.get('content-type')?.split(';')[0] ?? '';
      if (
        !response.ok ||
        ![
          'text/csv',
          'text/tab-separated-values',
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          'application/octet-stream',
        ].includes(media)
      )
        return null;
      const offered = response.headers.get('content-disposition') ?? '';
      const filename =
        /^attachment; filename="([A-Za-z0-9][A-Za-z0-9_.-]{0,119})"$/.exec(
          offered,
        )?.[1] ?? 'master-import.csv';
      return new NextResponse(response.body, {
        headers: {
          'Content-Type': media,
          'Content-Disposition': `attachment; filename="${filename}"`,
          'Cache-Control': 'no-store',
          'X-Content-Type-Options': 'nosniff',
        },
      });
    },
  });
}
