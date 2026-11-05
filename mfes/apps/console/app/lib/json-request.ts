import { NextResponse, type NextRequest } from 'next/server';
import { strictJson } from './strict-json';

const reply = (message: string, status: number) =>
  NextResponse.json({ error: { message } }, { status, headers: { 'Cache-Control': 'no-store' } });

/**
 * One bounded JSON read for every browser-facing route handler.
 *
 * A handler that calls `request.json()` has no size bound, no read deadline and no defence
 * against duplicate object members — where two parsers disagree about which value wins, and a
 * validated field can be smuggled past the one that checked it. The bounds live here rather
 * than per route so a new route cannot quietly be the lenient one (CLAUDE.md §3).
 *
 * The body is read as text and parsed by `strictJson`, so the duplicate-member rejection sees
 * the original bytes. Returns a ready error response rather than throwing: these are 4xx client
 * mistakes, not exceptions, and each carries the status the caller should hand back untouched.
 */
export async function readJsonBody(
  request: NextRequest,
  limit = 16384,
  timeout = 10000,
): Promise<{ value: Record<string, unknown> } | { error: NextResponse }> {
  if (!request.headers.get('content-type')?.startsWith('application/json')) return { error: reply('JSON required', 415) };
  const reader = request.body?.getReader();
  if (!reader) return { error: reply('Request required', 422) };
  const chunks: Uint8Array[] = [];
  let size = 0;
  let timedOut = false;
  const deadline = setTimeout(() => {
    timedOut = true;
    void reader.cancel();
  }, timeout);
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel();
        return { error: reply('Request is too large', 413) };
      }
      chunks.push(value);
    }
    if (timedOut) return { error: reply('Request timed out', 408) };
  } catch {
    return { error: reply('Invalid request', 422) };
  } finally {
    clearTimeout(deadline);
    reader.releaseLock();
  }
  try {
    const value: unknown = strictJson(Buffer.concat(chunks).toString('utf8'));
    // An array or a bare literal is not a request envelope; every caller reads named fields.
    if (!value || typeof value !== 'object' || Array.isArray(value)) return { error: reply('Invalid JSON or duplicate fields', 422) };
    return { value: value as Record<string, unknown> };
  } catch {
    return { error: reply('Invalid JSON or duplicate fields', 422) };
  }
}
