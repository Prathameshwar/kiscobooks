'use client';
import { useEffect, useState } from 'react';

/**
 * Whether a CSS media query currently matches. False until mounted and wherever `matchMedia` does
 * not exist, so the first render is always the wide layout and nothing here reads layout.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const list = window.matchMedia(query);
    setMatches(list.matches);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    list.addEventListener('change', onChange);
    return () => list.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}
