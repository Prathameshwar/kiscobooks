'use client';

import { useLayoutEffect, useRef } from 'react';
import { useUnsavedChanges } from './use-unsaved-changes';
import { goTo } from './navigate';

type NavigateEvent = Event & { navigationType: string; hashChange?: boolean; destination: { url: string; key?: string } };
type BrowserNavigation = EventTarget & { traverseTo?: (key: string) => { finished: Promise<unknown> } };

/** Same-tab links plus cancellable browser navigation. Native unload remains the fallback.
 * Does not write synthetic history entries or modify Next's history state. */
export function useDraftNavigation({ atRisk, blocked, requestLeave, onBlocked }: {
  atRisk: boolean; blocked: boolean; requestLeave: (proceed: () => void) => void; onBlocked: () => void;
}) {
  const allowed = useRef(false);
  const current = useRef({ atRisk, blocked, requestLeave, onBlocked });
  useLayoutEffect(() => { current.current = { atRisk, blocked, requestLeave, onBlocked }; }, [atRisk, blocked, requestLeave, onBlocked]);
  useUnsavedChanges(() => !allowed.current && (current.current.atRisk || current.current.blocked));
  useLayoutEffect(() => {
    const ask = (proceed: () => void) => {
      if (current.current.blocked) current.current.onBlocked();
      else current.current.requestLeave(() => { allowed.current = true; proceed(); });
    };
    const click = (event: MouseEvent) => {
      if (allowed.current || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[href]') : null;
      if (!anchor || anchor.hasAttribute('download') || anchor.target && anchor.target !== '_self') return;
      const destination = new URL(anchor.href, location.href);
      if (!['http:', 'https:'].includes(destination.protocol) || destination.origin === location.origin && destination.pathname === location.pathname && destination.search === location.search && destination.hash) return;
      if (!current.current.atRisk && !current.current.blocked) return;
      event.preventDefault(); event.stopImmediatePropagation();
      ask(() => goTo(destination.href));
    };
    const navigation = (window as Window & { navigation?: BrowserNavigation }).navigation;
    // The page rewriting its own address (history.replaceState with another query, as a saved bill does with its id)
    // replaces the entry it is on; nothing is left behind, so it is not something to ask about.
    const samePage = (next: NavigateEvent) => {
      if (next.navigationType !== 'replace') return false;
      const destination = new URL(next.destination.url, location.href);
      return destination.origin === location.origin && destination.pathname === location.pathname;
    };
    const navigate = (event: Event) => {
      const next = event as NavigateEvent;
      if (allowed.current || next.defaultPrevented || !next.cancelable || next.hashChange || next.navigationType === 'reload' || samePage(next) || !current.current.atRisk && !current.current.blocked) return;
      next.preventDefault();
      ask(() => {
        if (next.navigationType === 'traverse' && next.destination.key && navigation?.traverseTo) void navigation.traverseTo(next.destination.key).finished.catch(() => goTo(next.destination.url));
        else goTo(next.destination.url);
      });
    };
    document.addEventListener('click', click, true); navigation?.addEventListener('navigate', navigate);
    return () => { document.removeEventListener('click', click, true); navigation?.removeEventListener('navigate', navigate); };
  }, []);
}
