'use client';

// `useId` is a client hook, and the rail is routinely composed in an app's root layout —
// which may be a server component — so the boundary is declared here rather than left to
// whichever consumer happens to import it first.

import { useEffect, useId, useState, type ReactNode } from 'react';
import { IconButton } from './IconButton';
import { ChevronDownIcon } from './icons-console';
import { ChevronUpIcon } from './icons-table';

/**
 * The left rail. Four bands on an inner grid — brand · organisation switcher ·
 * navigation · pinned footer — where only the navigation band scrolls, so the lockup and
 * the user card stay put however long the nav grows (design-system §4.1).
 *
 * Every band is placed explicitly rather than by auto-flow: an absent switcher must not
 * promote the nav into the switcher's row and hand the footer the flexible one.
 */
export function Rail({
  brand,
  switcher,
  children,
  footer,
}: {
  brand: ReactNode;
  switcher?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="janso-rail">
      <div className="janso-rail__brand">{brand}</div>
      {switcher ? <div className="janso-rail__switcher">{switcher}</div> : null}
      <div className="janso-rail__nav">{children}</div>
      {footer ? <div className="janso-rail__foot">{footer}</div> : null}
    </div>
  );
}

/**
 * A named group of rail items. The overline is a real label — it names the `<nav>` via
 * `aria-labelledby`, so "Ledger" is announced as the group rather than being decorative
 * text a screen reader reads and then forgets.
 */
export function RailSection({ label, children }: { label: string; children: ReactNode }) {
  const labelId = useId();

  return (
    <nav className="janso-rail-section" aria-labelledby={labelId}>
      <p className="janso-rail-section__label" id={labelId}>
        {label}
      </p>
      <ul className="janso-rail-section__list">{children}</ul>
    </nav>
  );
}

/**
 * One navigation destination. It knows nothing about permissions — gating happens at the
 * call site by wrapping the item, so the rail stays a layout component and permission
 * logic lives in exactly one place (design-system §5.2).
 *
 * The label is both visible text and `aria-label`: a collapsed rail hides the text with
 * CSS, and `display:none` would take the accessible name with it.
 */
export function RailItem({
  icon,
  label,
  href,
  active = false,
}: {
  icon: ReactNode;
  label: string;
  href: string;
  active?: boolean;
}) {
  return (
    <li className="janso-rail-item-slot">
      <RailLink icon={icon} label={label} href={href} active={active} />
    </li>
  );
}

function RailLink({ icon, label, href, active }: { icon: ReactNode; label: string; href: string; active: boolean }) {
  return <a
        className="janso-rail-item"
        href={href}
        aria-label={label}
        title={label}
        aria-current={active ? 'page' : undefined}
        data-active={active ? 'true' : undefined}
      >
        <span className="janso-rail-item__icon" aria-hidden="true">
          {icon}
        </span>
        <span className="janso-rail-item__label">{label}</span>
      </a>;
}

/** A working parent link and an independently keyboard-operated submenu disclosure. */
export function RailGroup({ icon, label, href, active = false, containsActive = false, children }: {
  icon: ReactNode; label: string; href: string; active?: boolean; containsActive?: boolean; children: ReactNode;
}) {
  const id = useId(), [open, setOpen] = useState(active || containsActive);
  useEffect(() => { if (active || containsActive) setOpen(true); }, [active, containsActive]);
  return <li className="janso-rail-group" data-open={open ? 'true' : 'false'}>
    <div className="janso-rail-group__heading"><RailLink icon={icon} label={label} href={href} active={active} />
      <IconButton className="janso-rail-group__toggle" size="sm" label={`${open ? 'Collapse' : 'Expand'} ${label} menu`} icon={open ? <ChevronUpIcon /> : <ChevronDownIcon />} aria-expanded={open} aria-controls={id} onClick={() => setOpen(value => !value)} />
    </div>
    <ul id={id} className="janso-rail-section__list janso-rail-group__items">{children}</ul>
  </li>;
}

/**
 * The rail's pinned base: help and settings, above a hairline rule.
 *
 * Its children are `RailItem`s, which render `<li>` — so this has to be a list, or they are
 * list items with no list parent (invalid HTML, and the marker is only suppressed by the
 * nav's list rule). It reuses `.janso-rail-section__list` for that suppression rather than
 * inventing a second class that would have to be kept in step with it.
 *
 * Anything that is *not* a `RailItem` — a user card, a version string — belongs beside this
 * element, not inside it, for the same reason.
 */
export function RailFooter({ children, label = 'Support' }: { children: ReactNode; label?: string }) {
  const labelId = useId();

  return (
    <nav className="janso-rail-footer" aria-labelledby={labelId}>
      <p className="janso-visually-hidden" id={labelId}>
        {label}
      </p>
      <ul className="janso-rail-section__list">{children}</ul>
    </nav>
  );
}
