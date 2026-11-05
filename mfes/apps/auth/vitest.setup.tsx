import '@testing-library/jest-dom/vitest';
import React from 'react';
import { vi } from 'vitest';

// next/link needs an app-router context we don't mount in unit tests; render a plain
// anchor so href and children assertions work.
vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...rest }: { href: unknown; children: React.ReactNode }) =>
    React.createElement('a', { href: typeof href === 'string' ? href : '#', ...rest }, children),
}));

/**
 * jsdom has no `matchMedia`, and the auth shell now carries a `ThemeSwitcher` whose `system`
 * option resolves through it. Controllable so a test can flip the OS preference.
 */
type Listener = (event: MediaQueryListEvent) => void;

let prefersDark = false;
const listeners = new Set<Listener>();

Object.defineProperty(globalThis, '__emitPrefersDark', {
  writable: true,
  value: (value: boolean) => {
    prefersDark = value;
    for (const listener of listeners) listener({ matches: value } as MediaQueryListEvent);
  },
});

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    media: query,
    get matches() {
      return query.includes('dark') ? prefersDark : false;
    },
    onchange: null,
    addEventListener: (_: string, listener: Listener) => listeners.add(listener),
    removeEventListener: (_: string, listener: Listener) => listeners.delete(listener),
    addListener: (listener: Listener) => listeners.add(listener),
    removeListener: (listener: Listener) => listeners.delete(listener),
    dispatchEvent: () => false,
  })),
});

beforeEach(() => {
  prefersDark = false;
  listeners.clear();
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
  document.documentElement.style.removeProperty('color-scheme');
  document.cookie = 'janso-theme=; max-age=0; path=/';
});
