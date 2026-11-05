'use client';

import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent, type RefObject } from 'react';

/**
 * The accessibility mechanism shared by every modal surface — `ConfirmDialog`, `Modal`, `Drawer`.
 * Written once here rather than per component (CLAUDE.md §3): a focus trap that lets Tab wander out
 * of one dialog but not another is exactly the kind of drift that a second copy invites.
 *
 * It owns four things and no markup: where focus goes on open, where it returns on close, the Tab
 * cycle inside the panel, and the body scroll lock. The scrim, the panel and its contents belong to
 * the caller — this only needs a ref to the panel and a keydown handler to put on it.
 */

/** Tab order within a panel. Excludes anything the browser has taken out of it. */
export const FOCUSABLE_SELECTOR =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export type UseDialogA11yOptions = {
  open: boolean;
  /** Called on Escape, and by the caller's scrim — only fires when `dismissible`. */
  onClose: () => void;
  /**
   * Escape (and the caller's scrim, which checks the same flag) are ignored when false: an action
   * in flight cannot be recalled, so dismissing here would leave the user believing nothing happened.
   */
  dismissible?: boolean;
  /**
   * The element to focus on open, given the panel. Return `null` to fall back to the first focusable
   * child, and then to the panel itself. A destructive dialog focuses Cancel; a form focuses its
   * first field.
   */
  initialFocus?: (panel: HTMLElement | null) => HTMLElement | null;
  /** Lock body scroll while open, restoring whatever was set before. Default `true`. */
  lockScroll?: boolean;
};

export type DialogA11y = {
  panelRef: RefObject<HTMLDivElement | null>;
  onKeyDown: (event: ReactKeyboardEvent<HTMLElement>) => void;
};

export function useDialogA11y({
  open,
  onClose,
  dismissible = true,
  initialFocus,
  lockScroll = true,
}: UseDialogA11yOptions): DialogA11y {
  const panelRef = useRef<HTMLDivElement | null>(null);
  // The callbacks live in a ref so the focus and scroll effects depend only on `open`: a caller that
  // passes a fresh `onClose` closure every render must not tear the trap down and rebuild it.
  const latest = useRef({ onClose, dismissible, initialFocus });
  latest.current = { onClose, dismissible, initialFocus };

  // Focus in on open; back out to whatever opened it on close — a kebab item, usually, which has
  // itself unmounted by then, so the fallback is to leave focus alone.
  useEffect(() => {
    if (!open) return;
    const opener = document.activeElement as HTMLElement | null;
    const target =
      latest.current.initialFocus?.(panelRef.current) ??
      panelRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ??
      panelRef.current;
    target?.focus();

    return () => {
      if (opener && document.contains(opener)) opener.focus();
    };
  }, [open]);

  // Body scroll lock. Restores the previous inline value rather than clearing it, so a stacked
  // overlay or an app that set its own overflow both survive the close.
  useEffect(() => {
    if (!open || !lockScroll || typeof document === 'undefined') return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open, lockScroll]);

  function onKeyDown(event: ReactKeyboardEvent<HTMLElement>): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      if (latest.current.dismissible) latest.current.onClose();
      return;
    }
    if (event.key !== 'Tab') return;

    const focusable = [...(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR) ?? [])];
    if (focusable.length === 0) return;
    const first = focusable[0] as HTMLElement;
    const last = focusable[focusable.length - 1] as HTMLElement;
    const active = document.activeElement;

    // Only the two edges are handled; in between, the browser's own order is the right one.
    if (event.shiftKey && (active === first || !panelRef.current?.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  return { panelRef, onKeyDown };
}
