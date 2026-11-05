import { afterEach, describe, expect, it, vi } from 'vitest';
import { consoleUrl, goTo } from '../app/lib/navigate';

/**
 * Tested directly, without the mock the login test installs. `goTo` is the one place this app
 * hands control to the browser, so if it silently stopped calling `assign`, sign-in would sit
 * on its pending state forever and look like a hang.
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
  it('defaults the console to the local dev port', () => {
    expect(consoleUrl()).toBe('http://localhost:4320');
  });

  it('takes the console URL from configuration when one is set', () => {
    // Behind nginx both MFEs share an origin, so this becomes a same-origin path.
    vi.stubEnv('NEXT_PUBLIC_CONSOLE_URL', '/console');
    expect(consoleUrl()).toBe('/console');
  });

  it('hands the URL to the browser', () => {
    const assign = stubLocation();
    goTo('http://localhost:4320');
    expect(assign).toHaveBeenCalledWith('http://localhost:4320');
  });
});
