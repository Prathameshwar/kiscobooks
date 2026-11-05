'use client';

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { useGranted } from '../lib/permissions';
import { usePlacement } from '../lib/placement';
import { Avatar } from './Avatar';
import { Badge } from './Badge';
import { CheckIcon } from './icons';
import { OrgSwitcher } from './OrgSwitcher';
import { TextField } from './TextField';

export type ContextOption = {
  id: string;
  /** The primary line — a company's display name, a year's code. */
  name: string;
  /** The overline above it: a company code, a year's date span. */
  code?: string;
  /** A quiet third line. Used for "Step-up required" and for a period's status. */
  note?: string;
  /** A right-hand chip: "Default", "Current". */
  badge?: string;
  /**
   * Why this option cannot be chosen *right now*. Required rather than a bare boolean, for
   * `Menu`'s reason: a greyed row with no explanation is a support ticket, and the reason is
   * always known at the call site.
   */
  disabledReason?: string;
};

export type ContextAction = {
  id: string;
  label: string;
  icon?: ReactNode;
  /**
   * Presentation gate. The action is **absent**, not disabled, when the actor lacks the key —
   * a disabled control still tells them the capability exists. The server enforces regardless.
   */
  permission?: string;
};

type ContextSwitcherProps = {
  /** Accessible name for both the trigger and the listbox it owns. */
  label: string;
  /** Trigger overline — the selected company's code, or "Financial year". */
  overline: string;
  /** Trigger primary text — the selected option's name, or a "nothing selected" phrase. */
  name: string;
  options: readonly ContextOption[];
  selectedId?: string;
  onSelect: (id: string) => void;
  icon?: ReactNode;
  compact?: boolean;
  /**
   * Shows a filter field above the list. **Controlled by the caller**, because the console's
   * company list is searched server-side (`?q=`) while a fiscal-year list is filtered in
   * memory — the component must not assume which, so it owns neither.
   */
  search?: { label: string; value: string; onChange: (value: string) => void; placeholder?: string };
  /** Mutually exclusive in practice; all three render in the panel in place of the list. */
  status?: { loading?: boolean; error?: string; empty?: string };
  actions?: readonly ContextAction[];
  onAction?: (id: string) => void;
  disabled?: boolean;
};

/**
 * The popup half of a context switcher: company in the rail's switcher band, financial year
 * stacked under it (design-system §5.2 — the rail owns the affordance, the caller owns the data).
 *
 * One component for both, deliberately. The expensive part of a switcher is not its rows, it is
 * the keyboard and dismissal contract, and two copies of that is how they drift (CLAUDE.md §3).
 * What differs between company and year is data and a glyph, which are props.
 *
 * It portals and places against the trigger for `lib/placement`'s reason: the rail is a scroll
 * container, and any ancestor with `overflow` clips an absolutely positioned descendant. The
 * rail also sits above the page on `--janso-z-rail`, so a panel left inside it would be trapped
 * under the rail's own stacking context on a narrow viewport.
 *
 * Deliberately no focus trap: like `Menu`, this is not a dialog, and Tab is expected to leave.
 */
export function ContextSwitcher({
  label,
  overline,
  name,
  options,
  selectedId,
  onSelect,
  icon,
  compact = false,
  search,
  status,
  actions,
  onAction,
  disabled = false,
}: ContextSwitcherProps) {
  const granted = useGranted();
  /*
   * Permission-filtered before anything measures the list, so the roving index and the
   * "is there anything here" test both speak about what is actually rendered (`Menu`'s lesson).
   */
  const visibleActions = (actions ?? []).filter((action) => granted(action.permission));

  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const panelId = useId();

  const statusText = status?.error
    ? status.error
    : status?.loading
      ? 'Loading…'
      : options.length === 0
        ? status?.empty ?? null
        : null;
  /*
   * The panel opens even with no options: an empty switcher has something to say — "no company
   * has been assigned to you", or the footer's "Create company". A trigger that silently does
   * nothing is the worse failure. It only stops claiming a popup when there is genuinely
   * nothing at all to show, because `aria-haspopup` on a control that never opens is a promise
   * to a screen-reader user that is not kept.
   */
  const usable = !disabled && (options.length > 0 || visibleActions.length > 0 || statusText !== null);
  const placement = usePlacement(triggerRef, open, { align: 'start', minHeight: 120, maxHeight: 420 });
  /*
   * Placement is measured in a layout effect, so the first render after `open` has none and the
   * panel is not in the DOM yet. Anything touching an option — focus above all — waits for this
   * rather than for `open`, or it runs against refs that are still null.
   */
  const mounted = open && usable && placement !== null;

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false);
    // Escape and selection put focus back where the user left it; an outside click does not,
    // because the click has already chosen the next focus target.
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  /*
   * Focus moves **on open only**, and `move()` owns every step after that. Keying this on
   * `activeIndex` instead would drag focus back into the filter field on each arrow press,
   * because the field is where an open panel starts when one exists.
   *
   * With a filter the first stop is that field — the common act is typing a few letters of a
   * company name. Without one, focus lands on the selected row, so the arrow keys start from
   * where the user already is.
   */
  useEffect(() => {
    if (!mounted) return;
    if (search) searchRef.current?.focus();
    else optionRefs.current[activeIndex]?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- open-time only; see above
  }, [mounted]);

  // The list shrinks while open — a server-side search returning fewer rows. Clamping keeps the
  // roving index inside the list rather than focusing nothing.
  useEffect(() => {
    setActiveIndex((index) => (index > options.length - 1 ? Math.max(0, options.length - 1) : index));
  }, [options.length]);

  useEffect(() => {
    if (!open) return;
    // `mousedown`, not `click`: dismiss before the press lands, so the click's real target still
    // receives it. Both the trigger and the portalled panel count as inside — the panel is not a
    // DOM descendant of the trigger, so testing one element would close the panel on its own rows.
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target)) return;
      if (panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  function openAt(index: number): void {
    if (!usable) return;
    setActiveIndex(index);
    setOpen(true);
  }

  function selectedIndex(): number {
    const found = options.findIndex((option) => option.id === selectedId);
    return found < 0 ? 0 : found;
  }

  function onTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>): void {
    if (!usable) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      openAt(selectedIndex());
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      openAt(Math.max(0, options.length - 1));
    }
    // Enter and Space are left to the button's native activation, which fires `onClick`.
  }

  function move(next: (index: number, last: number) => number): void {
    const last = options.length - 1;
    if (last < 0) return;
    const target = next(activeIndex, last);
    setActiveIndex(target);
    // Focus is moved here rather than by an effect, so arrowing out of the filter field lands on
    // a row — the open-time effect deliberately does not re-run on `activeIndex`.
    optionRefs.current[target]?.focus();
  }

  function onPanelKeyDown(event: ReactKeyboardEvent<HTMLDivElement>): void {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        move((index, last) => (index >= last ? 0 : index + 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        move((index, last) => (index <= 0 ? last : index - 1));
        break;
      case 'Home':
        event.preventDefault();
        move(() => 0);
        break;
      case 'End':
        event.preventDefault();
        move((_index, last) => last);
        break;
      case 'Escape':
        event.preventDefault();
        close(true);
        break;
      case 'Tab':
        /*
         * Not prevented. The panel is portalled to the end of the body, so letting Tab run from a
         * row would jump to the end of the document. Moving focus back to the trigger
         * *synchronously*, before the default action, makes the browser compute the next tab stop
         * from the trigger — which is where the user expects to continue.
         */
        close(true);
        break;
      default:
        break;
    }
  }

  function choose(option: ContextOption): void {
    // `aria-disabled` rather than `disabled`, so the row keeps its tab stop and its reason stays
    // readable — which means activation has to be refused here.
    if (option.disabledReason) return;
    onSelect(option.id);
    close(true);
  }

  const panel =
    mounted && placement ? (
      <div
        ref={panelRef}
        id={panelId}
        className="janso-switcher__panel"
        data-flipped={placement.flipped ? 'true' : undefined}
        style={placement.style}
        onKeyDown={onPanelKeyDown}
      >
        {search ? (
          <div className="janso-switcher__search">
            <TextField
              ref={searchRef}
              label={search.label}
              hideLabel
              type="search"
              autoComplete="off"
              placeholder={search.placeholder ?? 'Search'}
              value={search.value}
              maxLength={100}
              onChange={(event) => search.onChange(event.target.value)}
            />
          </div>
        ) : null}
        {statusText ? (
          <p className="janso-switcher__status" role={status?.error ? 'alert' : 'status'}>
            {statusText}
          </p>
        ) : null}
        {options.length > 0 ? (
          <div className="janso-switcher__list" role="listbox" aria-label={label}>
            {options.map((option, index) => {
              const selected = option.id === selectedId;
              return (
                <button
                  key={option.id}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  aria-disabled={option.disabledReason ? true : undefined}
                  className="janso-switcher__option"
                  data-selected={selected ? 'true' : undefined}
                  // One tab stop for the whole list; the arrow keys move within it.
                  tabIndex={index === activeIndex ? 0 : -1}
                  ref={(element) => {
                    optionRefs.current[index] = element;
                  }}
                  onClick={() => choose(option)}
                >
                  {icon ? null : <Avatar name={option.name} shape="square" size="sm" />}
                  <span className="janso-switcher__option-text">
                    {option.code ? <span className="janso-switcher__option-code" title={option.code}>{option.code}</span> : null}
                    <span className="janso-switcher__option-name" title={option.name}>{option.name}</span>
                    {(option.disabledReason ?? option.note) ? (
                      <span className="janso-switcher__option-note">{option.disabledReason ?? option.note}</span>
                    ) : null}
                  </span>
                  {option.badge ? <Badge tone="brand" variant="outline">{option.badge}</Badge> : null}
                  {/* The checkmark slot is kept when unselected, so the badges of every row stay in one column. */}
                  <span className="janso-switcher__check" aria-hidden="true">
                    {selected ? <CheckIcon size={14} /> : null}
                  </span>
                </button>
              );
            })}
          </div>
        ) : null}
        {visibleActions.length > 0 ? (
          <div className="janso-switcher__actions">
            {visibleActions.map((action) => (
              <button
                key={action.id}
                type="button"
                className="janso-switcher__action"
                onClick={() => {
                  onAction?.(action.id);
                  close(false);
                }}
              >
                {action.icon ? (
                  <span className="janso-switcher__action-icon" aria-hidden="true">
                    {action.icon}
                  </span>
                ) : null}
                <span>{action.label}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    ) : null;

  return (
    <div className="janso-switcher">
      <OrgSwitcher
        ref={triggerRef}
        label={label}
        name={name}
        code={overline}
        icon={icon}
        compact={compact}
        open={open && usable}
        controls={panelId}
        disabled={disabled || !usable}
        onOpen={() => (open ? close(false) : openAt(selectedIndex()))}
        onKeyDown={onTriggerKeyDown}
      />
      {panel && typeof document !== 'undefined' ? createPortal(panel, document.body) : null}
    </div>
  );
}
