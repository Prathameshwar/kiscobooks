'use client';

import {
  Fragment,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';

import { Avatar } from './Avatar';
import { ChevronDownIcon } from './icons-console';

export type UserMenuItem = { id: string; label: string; icon?: ReactNode; separatorBefore?: boolean };

/**
 * The account menu. Hand-rolled rather than a popover library because the keyboard
 * contract *is* the component: a `role="menu"` that does not cycle with the arrow keys and
 * return focus on Escape is a worse control than a plain list of links.
 *
 * There is deliberately no focus trap — a menu is not a dialog, and Tab is expected to
 * leave it (and therefore to close it).
 */
export function UserMenu({
  name,
  secondary,
  items,
  onSelect,
}: {
  name: string;
  secondary?: string;
  items: UserMenuItem[];
  onSelect?: (id: string) => void;
}) {
  // An items array can arrive empty — every entry permission-filtered out at the call site,
  // say. `items.length - 1` is then -1, which left `activeIndex` outside the list and opened an
  // empty `role="menu"` with nothing focusable in it. A menu with no items simply does not open.
  const hasItems = items.length > 0;
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const menuId = useId();

  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false);
    // Escape and selection put focus back where the user left it; an outside click does
    // not, because the click has already chosen the next focus target.
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    itemRefs.current[activeIndex]?.focus();
  }, [open, activeIndex]);

  useEffect(() => {
    if (!open) return;
    // `mousedown`, not `click`: dismiss before the press lands, so the click's real target
    // still receives it.
    const onPointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  function onTriggerKeyDown(event: ReactKeyboardEvent<HTMLButtonElement>): void {
    if (!hasItems) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex(0);
      setOpen(true);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex(items.length - 1);
      setOpen(true);
    }
    // Enter and Space are left to the button's native activation, which fires `onClick`.
  }

  function onMenuKeyDown(event: ReactKeyboardEvent<HTMLDivElement>): void {
    const last = items.length - 1;
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setActiveIndex((index) => (index >= last ? 0 : index + 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setActiveIndex((index) => (index <= 0 ? last : index - 1));
        break;
      case 'Home':
        event.preventDefault();
        setActiveIndex(0);
        break;
      case 'End':
        event.preventDefault();
        setActiveIndex(last);
        break;
      case 'Escape':
        event.preventDefault();
        close(true);
        break;
      case 'Tab':
        close(false);
        break;
      default:
        break;
    }
  }

  return (
    <div className="janso-usermenu" ref={rootRef}>
      <button
        type="button"
        ref={triggerRef}
        className="janso-usermenu__trigger"
        /*
         * Named explicitly rather than by its visible text, because that text is hidden in two
         * places — a collapsed rail and a narrow top bar — and a trigger whose accessible name
         * disappears with its label is an unlabelled button. `secondary` is deliberately left
         * out of the name: it is context, not identity.
         */
        aria-label={name}
        // With nothing to show, the trigger stops claiming to have a popup: `aria-haspopup`
        // on a control that never opens is a promise to a screen-reader user that is not kept.
        aria-haspopup={hasItems ? 'menu' : undefined}
        aria-expanded={hasItems ? open : undefined}
        aria-controls={open ? menuId : undefined}
        onClick={() => {
          if (!hasItems) return;
          setActiveIndex(0);
          setOpen((wasOpen) => !wasOpen);
        }}
        onKeyDown={onTriggerKeyDown}
      >
        <Avatar name={name} shape="round" size="sm" />
        <span className="janso-usermenu__text">
          <span className="janso-usermenu__name">{name}</span>
          {secondary ? <span className="janso-usermenu__secondary">{secondary}</span> : null}
        </span>
        <ChevronDownIcon className="janso-usermenu__chevron" size={16} />
      </button>

      {open && hasItems ? (
        <div
          className="janso-usermenu__menu"
          id={menuId}
          role="menu"
          aria-label={`${name} account menu`}
          onKeyDown={onMenuKeyDown}
        >
          {items.map((item, index) => (
            <Fragment key={item.id}>
            {item.separatorBefore && index > 0 ? <div role="separator" className="janso-usermenu__separator" /> : null}
            <button
              key={item.id}
              type="button"
              role="menuitem"
              className="janso-usermenu__item"
              // One tab stop for the whole menu; the arrow keys move within it.
              tabIndex={index === activeIndex ? 0 : -1}
              ref={(element) => {
                itemRefs.current[index] = element;
              }}
              onClick={() => {
                onSelect?.(item.id);
                close(true);
              }}
            >
              {item.icon ? (
                <span className="janso-usermenu__item-icon" aria-hidden="true">
                  {item.icon}
                </span>
              ) : null}
              <span>{item.label}</span>
            </button>
            </Fragment>
          ))}
        </div>
      ) : null}
    </div>
  );
}
