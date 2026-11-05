import { act, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useMediaQuery } from '../app/lib/use-media-query';

const original = window.matchMedia;
afterEach(() => { Object.defineProperty(window, 'matchMedia', { configurable: true, value: original }); });

function stubMedia(initial: boolean) {
  let listener: ((event: MediaQueryListEvent) => void) | null = null;
  const remove = vi.fn();
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string) => ({
      matches: initial, media: query,
      addEventListener: (_type: string, callback: (event: MediaQueryListEvent) => void) => { listener = callback; },
      removeEventListener: remove,
    }),
  });
  return { change: (matches: boolean) => listener?.({ matches } as MediaQueryListEvent), remove };
}

it('is false where matchMedia does not exist, so the first render is the wide layout', () => {
  Object.defineProperty(window, 'matchMedia', { configurable: true, value: undefined });
  const { result } = renderHook(() => useMediaQuery('(max-width: 680px)'));
  expect(result.current).toBe(false);
});

it('reads the query once mounted and follows later changes', () => {
  const media = stubMedia(true);
  const { result } = renderHook(() => useMediaQuery('(max-width: 680px)'));
  expect(result.current).toBe(true);
  act(() => media.change(false));
  expect(result.current).toBe(false);
});

it('stops listening when unmounted', () => {
  const media = stubMedia(false);
  const { unmount } = renderHook(() => useMediaQuery('(max-width: 680px)'));
  unmount();
  expect(media.remove).toHaveBeenCalledTimes(1);
});
