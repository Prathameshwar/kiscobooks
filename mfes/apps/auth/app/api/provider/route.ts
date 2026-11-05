import { NextResponse } from 'next/server';
import { authProvider } from '../../lib/provider';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

// Public intentionally: it tells the sign-in screens which provider id to hand to NextAuth and
// which copy to show. It reveals nothing about accounts, endpoints or secrets.
export async function GET() {
  const headers = { 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff' };
  try { return NextResponse.json({ provider: authProvider() }, { headers }); }
  catch { return NextResponse.json({ error: 'Authentication unavailable' }, { status: 503, headers }); }
}
