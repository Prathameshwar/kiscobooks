import { NextRequest, NextResponse } from 'next/server';
import { refreshSession } from '../../../lib/session-response';

function allowedOrigin(request: NextRequest): string | null {
  try {
    const origin = request.headers.get('origin');
    return origin && [new URL(process.env.NEXTAUTH_URL!).origin, new URL(process.env.CONSOLE_URL!).origin]
      .includes(origin) ? origin : null;
  } catch { return null; }
}
function cors(response: Response, origin: string): Response {
  response.headers.set('Access-Control-Allow-Origin', origin);
  response.headers.set('Access-Control-Allow-Credentials', 'true');
  response.headers.set('Vary', 'Origin');
  response.headers.set('Cache-Control', 'no-store');
  return response;
}
// The encrypted session authenticates this endpoint; exact Origin validation protects the POST.
export async function POST(request: NextRequest) {
  const origin = allowedOrigin(request);
  if (!origin) return new NextResponse(null, { status: 403, headers: { 'Cache-Control': 'no-store' } });
  return cors(await refreshSession(request), origin);
}
export async function OPTIONS(request: NextRequest) {
  const origin = allowedOrigin(request);
  if (!origin) return new NextResponse(null, { status: 403 });
  const response = cors(new NextResponse(null, { status: 204 }), origin);
  response.headers.set('Access-Control-Allow-Methods', 'POST');
  response.headers.set('Access-Control-Allow-Headers', 'Content-Type');
  return response;
}
