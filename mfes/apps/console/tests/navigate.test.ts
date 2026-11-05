import { afterEach, describe, expect, it, vi } from 'vitest';
import { goTo, signInUrl } from '../app/lib/navigate';

/**
 * Tested directly, without the mock the shell tests install. `goTo` is the one place this app
 * hands control to the browser, so if it silently stopped calling `assign` the sign-out button
 * would look like it worked and do nothing.
 */
const realLocation = window.location;

afterEach(() => {
  Object.defineProperty(window, 'location', { value: realLocation, writable: true });
  vi.unstubAllEnvs();
});

function stubLocation() {
  const assign = vi.fn();
  Object.defineProperty(window, 'location', {
    value: { ...realLocation, assign },
    writable: true,
  });
  return assign;
}

describe('navigate', () => {
  it('defaults sign-in to the local auth app', () => {
    expect(signInUrl()).toBe('http://localhost:4310/login');
  });

  it('takes the sign-in URL from configuration when one is set', () => {
    // Behind nginx both MFEs share an origin, so this becomes a same-origin path.
    vi.stubEnv('NEXT_PUBLIC_AUTH_URL', '/login');
    expect(signInUrl()).toBe('/login');
  });

  it('hands the URL to the browser', () => {
    const assign = stubLocation();
    goTo('http://localhost:4310/login');
    expect(assign).toHaveBeenCalledWith('http://localhost:4310/login');
  });
});
