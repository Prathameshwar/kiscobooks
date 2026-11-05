import { vi } from 'vitest';
import { NextRequest } from 'next/server';

/** Shared fixtures for the local sign-in provider's server tests. No real secret appears here. */
export const BFF_SECRET = 'test-bff-secret-0123456789-abcdefghijklmnop';
export const AUTH_URL = 'https://auth.test';
export const IDENTITY = 'https://identity.test';
export const ISSUER = 'https://bill.test/identity/oidc';
export const REQUEST_ID = 'rq_9f8e7d6c5b4a39281706f5e4d3c2b1a0';
export const TOKEN = 'tk_0a1b2c3d4e5f60718293a4b5c6d7e8f9';
export const LEAK = 'SECRET-UPSTREAM-TEXT';

/** Local provider configuration. `AUTH_PROVIDER` is deliberately left unset: local is the default. */
export function localEnv(extra: Record<string, string> = {}) {
  for (const [key, value] of Object.entries({ NEXTAUTH_URL: AUTH_URL, IDENTITY_URL: IDENTITY,
    AUTH_LOCAL_BFF_SECRET: BFF_SECRET, AUTH_LOCAL_ISSUER: ISSUER, AUTH_LOCAL_CLIENT_ID: 'auth-app',
    AUTH_LOCAL_CLIENT_SECRET: 'client-secret-for-tests', NEXTAUTH_SECRET: 'nextauth-secret-for-tests-0123456789',
    CONSOLE_URL: 'https://console.test', ...extra })) vi.stubEnv(key, value);
  delete process.env.AUTH_PROVIDER;
}

export function post(path: string, body: unknown, headers: Record<string, string> = {}, url = AUTH_URL) {
  return new NextRequest(`${url}${path}`, { method: 'POST',
    headers: { origin: AUTH_URL, 'content-type': 'application/json', ...headers },
    body: typeof body === 'string' ? body : JSON.stringify(body) });
}

/** An Identity platform error envelope that carries text the Auth app must never show. */
export function envelope(status: number, code: string, extra: Record<string, unknown> = {}, headers: Record<string, string> = {}) {
  return Response.json({ error: { code, message: LEAK }, ...extra }, { status, headers });
}

/** Spies on every console method; the Auth app logs nothing, and certainly no credentials. */
export function consoleSpies() {
  return (['log', 'info', 'warn', 'error', 'debug'] as const).map(name => vi.spyOn(console, name).mockImplementation(() => undefined));
}
