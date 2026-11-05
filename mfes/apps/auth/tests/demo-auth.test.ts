import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  DEMO_EMAIL,
  DEMO_MOBILE,
  DEMO_PASSWORD,
  DEMO_SIGN_IN_ENABLED,
  checkDemoCredentials,
} from '../app/lib/demo-auth';

describe('demo sign-in', () => {
  it('is on under test, which is how the sign-in path is walkable at all', () => {
    expect(DEMO_SIGN_IN_ENABLED).toBe(true);
  });

  it('accepts the demo email and the demo mobile', () => {
    expect(checkDemoCredentials(DEMO_EMAIL, DEMO_PASSWORD)).toBe(true);
    expect(checkDemoCredentials(DEMO_MOBILE, DEMO_PASSWORD)).toBe(true);
  });

  it('accepts a mobile number written the way people write it', () => {
    for (const entered of ['98765 43210', '+91 98765 43210', '91 98765-43210', ' 9876543210 ']) {
      expect(checkDemoCredentials(entered, DEMO_PASSWORD)).toBe(true);
    }
  });

  it('ignores case and surrounding space on the email', () => {
    expect(checkDemoCredentials('  Owner@Janso.TEST ', DEMO_PASSWORD)).toBe(true);
  });

  it('rejects the wrong password, including a near miss', () => {
    expect(checkDemoCredentials(DEMO_EMAIL, 'janso-Demo')).toBe(false);
    expect(checkDemoCredentials(DEMO_EMAIL, `${DEMO_PASSWORD} `)).toBe(false);
    expect(checkDemoCredentials(DEMO_EMAIL, '')).toBe(false);
  });

  it('rejects any other identifier', () => {
    for (const entered of ['owner@janso.com', 'admin', '', '1234567890', '9876543211']) {
      expect(checkDemoCredentials(entered, DEMO_PASSWORD)).toBe(false);
    }
  });

  it('is not a substring match — a longer number must not pass', () => {
    // `includes`-style matching would let 19876543210 or 98765432109 through.
    expect(checkDemoCredentials('19876543210', DEMO_PASSWORD)).toBe(false);
    expect(checkDemoCredentials('98765432109', DEMO_PASSWORD)).toBe(false);
  });
});

/**
 * The gate is the whole safety argument, so it is tested rather than trusted. The flag is read
 * at module load, so each case re-imports the module with the environment already set.
 */
describe('the production gate', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  async function loadWith(env: Record<string, string | undefined>) {
    for (const [key, value] of Object.entries(env)) vi.stubEnv(key, value);
    vi.resetModules();
    return import('../app/lib/demo-auth');
  }

  it('is off in a production build, and refuses the credentials it published', async () => {
    const mod = await loadWith({ NODE_ENV: 'production', NEXT_PUBLIC_DEMO_SIGN_IN: undefined });

    expect(mod.DEMO_SIGN_IN_ENABLED).toBe(false);
    // The strings are still in the bundle — they are not a secret — but they open nothing.
    expect(mod.checkDemoCredentials(mod.DEMO_EMAIL, mod.DEMO_PASSWORD)).toBe(false);
    expect(mod.checkDemoCredentials(mod.DEMO_MOBILE, mod.DEMO_PASSWORD)).toBe(false);
  });

  it('can be turned on for a production demo, but only by name', async () => {
    const mod = await loadWith({ NODE_ENV: 'production', NEXT_PUBLIC_DEMO_SIGN_IN: 'true' });

    expect(mod.DEMO_SIGN_IN_ENABLED).toBe(true);
    expect(mod.checkDemoCredentials(mod.DEMO_EMAIL, mod.DEMO_PASSWORD)).toBe(true);
  });

  it('can be turned off in development too', async () => {
    const mod = await loadWith({ NODE_ENV: 'development', NEXT_PUBLIC_DEMO_SIGN_IN: 'false' });

    expect(mod.DEMO_SIGN_IN_ENABLED).toBe(false);
    expect(mod.checkDemoCredentials(mod.DEMO_EMAIL, mod.DEMO_PASSWORD)).toBe(false);
  });
});
