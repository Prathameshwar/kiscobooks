'use client';

import { forwardRef, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { Avatar } from './Avatar';
import { ChevronUpDownIcon } from './icons-console';

/**
 * The organisation (company) switcher at the head of the rail.
 *
 * A button opening a listbox rather than a native `<select>`: the option rows carry an
 * avatar, a code and a name, which a `<select>` cannot render, and the list is often
 * fetched. The popup itself is the caller's — the rail owns the affordance, not the data
 * (design-system §5.2). `ContextSwitcher` is that caller for both the company and the
 * financial year; this stays usable on its own as a static label-and-chevron trigger.
 *
 * The ref and the ARIA/keyboard pass-throughs exist so the popup's owner can anchor its
 * panel here and wire the listbox relationship without a second trigger implementation.
 */
export const OrgSwitcher = forwardRef<
  HTMLButtonElement,
  {
    name: string;
    code: string;
    onOpen?: () => void;
    open?: boolean;
    /**
     * The trigger's accessible name. Defaults to "Switch organisation" — the financial-year
     * variant needs its own, and a trigger whose name is wrong is worse than an unnamed one.
     */
    label?: string;
    /**
     * Replaces the square avatar. The company variant is identified by its initials; the
     * year variant has no entity to initial, so it carries a calendar glyph instead.
     */
    icon?: ReactNode;
    /** Denser padding and a smaller name, for a second switcher stacked under the first. */
    compact?: boolean;
    controls?: string;
    disabled?: boolean;
    onKeyDown?: (event: ReactKeyboardEvent<HTMLButtonElement>) => void;
  }
>(function OrgSwitcher(
  { name, code, onOpen, open = false, label = 'Switch organisation', icon, compact = false, controls, disabled = false, onKeyDown },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      className="janso-org"
      title={`${name} (${code})`}
      data-compact={compact ? 'true' : undefined}
      aria-haspopup="listbox"
      aria-expanded={open}
      aria-controls={open ? controls : undefined}
      disabled={disabled}
      onClick={onOpen}
      onKeyDown={onKeyDown}
    >
      <span className="janso-visually-hidden">{label}</span>
      {icon ? (
        <span className="janso-org__icon" aria-hidden="true">
          {icon}
        </span>
      ) : (
        <Avatar name={name} shape="square" size="md" />
      )}
      <span className="janso-org__text">
        <span className="janso-org__code" title={code}>{code}</span>
        <span className="janso-org__name" title={name}>{name}</span>
      </span>
      <ChevronUpDownIcon className="janso-org__chevron" />
    </button>
  );
});
