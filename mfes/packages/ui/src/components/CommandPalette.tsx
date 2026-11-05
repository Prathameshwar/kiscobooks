'use client';

import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { useDialogA11y } from '../lib/dialog';
import { useGranted } from '../lib/permissions';
import { SearchIcon } from './icons-console';

export type CommandItem = {
  id: string;
  label: string;
  /** The heading the item is listed under — "Go to", "Create". Items keep their given order. */
  group?: string;
  icon?: ReactNode;
  /** Extra words the filter matches but the list does not show — "bills" for Invoices. */
  keywords?: readonly string[];
  /** A short trailing note — a section name, a shortcut. */
  hint?: string;
  /**
   * The permission the item needs. A denied item is **absent**, never greyed, exactly like a rail
   * link: the palette must not become a list of places the reader cannot go. Presentation only —
   * the destination still enforces it.
   */
  permission?: string;
};

export type CommandPaletteProps = {
  open: boolean;
  onClose: () => void;
  items: readonly CommandItem[];
  /** Called with the chosen item's id. The palette closes itself first. */
  onSelect: (id: string) => void;
  /** The dialog's accessible name. */
  label?: string;
  placeholder?: string;
};

type Entry = {
  item: CommandItem;
  /** Lower-cased once per item list, never per keystroke. */
  label: string;
  words: readonly string[];
  text: string;
  /** The caller's position, the tie-break that keeps a rank stable. */
  order: number;
};

type Group = { name: string; entries: Entry[] };

/** Items bucketed by group, buckets in the order the caller first names them. */
function bucket(items: readonly CommandItem[]): Group[] {
  const groups = new Map<string, Group>();
  items.forEach((item, order) => {
    const name = item.group ?? '';
    const label = item.label.toLowerCase();
    const entry: Entry = {
      item,
      label,
      words: label.split(/\s+/),
      text: [label, item.group ?? '', ...(item.keywords ?? [])].join(' ').toLowerCase(),
      order,
    };
    const group = groups.get(name);
    if (group) group.entries.push(entry);
    else groups.set(name, { name, entries: [entry] });
  });
  return [...groups.values()];
}

/**
 * Rank for a query: a label that starts with it beats a word in the label that starts with it,
 * which beats a match anywhere (a keyword, a group). Everything else is filtered out. Stable within
 * a rank, so the caller's order survives — a palette that reshuffles on every key cannot be learned.
 */
function rank(entry: Entry, query: string): number {
  if (entry.label.startsWith(query)) return 0;
  if (entry.words.some((word) => word.startsWith(query))) return 1;
  if (entry.text.includes(query)) return 2;
  return -1;
}

/**
 * The command palette: one keyboard path to every place and verb in the app (design-system §5.12).
 *
 * The keyboard contract is the WAI-ARIA combobox-with-listbox pattern inside a modal dialog:
 * focus stays in the input, the arrow keys move a highlighted option announced through
 * `aria-activedescendant`, Enter chooses it, Escape closes and returns focus to whatever opened
 * the palette. The focus trap, Escape and focus restore are `useDialogA11y`'s — the same hook
 * every other overlay uses, so this one cannot drift from them.
 *
 * The body mounts on open and unmounts on close, so every opening starts with an empty query and
 * the top option highlighted — no effect has to reset either.
 */
export function CommandPalette(props: CommandPaletteProps) {
  if (!props.open || typeof document === 'undefined') return null;
  return <PaletteBody {...props} />;
}

function PaletteBody({
  onClose,
  items,
  onSelect,
  label = 'Command palette',
  placeholder = 'Search or jump to…',
}: CommandPaletteProps) {
  const granted = useGranted();
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const baseId = useId();
  const listId = `${baseId}-list`;
  const optionId = (index: number) => `${baseId}-option-${index}`;

  const { panelRef, onKeyDown: dialogKeys } = useDialogA11y({
    open: true,
    onClose,
    initialFocus: () => inputRef.current,
  });

  const groups = useMemo(
    () => bucket(items.filter((item) => granted(item.permission))),
    [items, granted],
  );

  /*
   * Ranked within each group, groups in the caller's order — ranking across groups would split one
   * group around another and print its heading twice. Each entry carries its flat index, so the
   * arrows walk straight through the groups.
   */
  const { shown, results } = useMemo(() => {
    const q = query.trim().toLowerCase();
    const flat: CommandItem[] = [];
    const visible = groups
      .map((group) => {
        const entries =
          q === ''
            ? group.entries
            : group.entries
                .map((entry) => ({ entry, score: rank(entry, q) }))
                .filter(({ score }) => score >= 0)
                .sort((x, y) => x.score - y.score || x.entry.order - y.entry.order)
                .map(({ entry }) => entry);
        return {
          name: group.name,
          entries: entries.map((entry) => ({ item: entry.item, index: flat.push(entry.item) - 1 })),
        };
      })
      .filter((group) => group.entries.length > 0);
    return { shown: visible, results: flat };
  }, [groups, query]);

  /* Keep the highlighted option in view as the arrows walk past the panel's edge. */
  useEffect(() => {
    document.getElementById(optionId(active))?.scrollIntoView?.({ block: 'nearest' });
    // `optionId` is derived from a stable `useId`; only the highlighted index moves the view.
  }, [active]);

  function choose(index: number): void {
    const item = results[index];
    if (!item) return;
    onClose();
    onSelect(item.id);
  }

  function onInputKeyDown(event: ReactKeyboardEvent<HTMLInputElement>): void {
    const last = results.length - 1;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActive((current) => (current >= last ? 0 : current + 1));
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActive((current) => (current <= 0 ? Math.max(last, 0) : current - 1));
    } else if (event.key === 'Home' && results.length > 0) {
      event.preventDefault();
      setActive(0);
    } else if (event.key === 'End' && results.length > 0) {
      event.preventDefault();
      setActive(last);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      choose(active);
    }
  }

  const hasResults = results.length > 0;

  return createPortal(
    <div className="janso-command">
      {/* Presentational, like every overlay scrim: the input owns Escape. */}
      <div className="janso-command__scrim" aria-hidden="true" onMouseDown={onClose} />
      <div
        ref={panelRef}
        className="janso-command__panel"
        role="dialog"
        aria-modal="true"
        aria-label={label}
        onKeyDown={dialogKeys}
      >
        <div className="janso-command__search">
          <span className="janso-command__search-icon" aria-hidden="true">
            <SearchIcon size={16} />
          </span>
          <input
            ref={inputRef}
            className="janso-command__input"
            type="text"
            role="combobox"
            aria-label={label}
            aria-expanded={hasResults}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={hasResults ? optionId(active) : undefined}
            placeholder={placeholder}
            value={query}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            onKeyDown={onInputKeyDown}
          />
          <kbd className="janso-command__kbd" aria-hidden="true">
            Esc
          </kbd>
        </div>

        <ul id={listId} className="janso-command__list" role="listbox" aria-label={label}>
          {shown.map((group) => (
            <li key={`${group.name}-${group.entries[0]?.index ?? 0}`} role="presentation">
              {group.name ? (
                <p className="janso-command__group" aria-hidden="true">
                  {group.name}
                </p>
              ) : null}
              <ul role="group" aria-label={group.name || undefined} className="janso-command__options">
                {group.entries.map(({ item, index }) => (
                  <li
                    key={item.id}
                    id={optionId(index)}
                    role="option"
                    aria-selected={index === active}
                    className="janso-command__option"
                    onMouseMove={() => {
                      if (index !== active) setActive(index);
                    }}
                    /* `mousedown` + preventDefault keeps focus in the input, which owns the contract. */
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => choose(index)}
                  >
                    {item.icon ? (
                      <span className="janso-command__option-icon" aria-hidden="true">
                        {item.icon}
                      </span>
                    ) : null}
                    <span className="janso-command__option-label">{item.label}</span>
                    {item.hint ? <span className="janso-command__option-hint">{item.hint}</span> : null}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>

        {hasResults ? null : (
          <p className="janso-command__empty" role="status">
            Nothing matches “{query.trim()}”.
          </p>
        )}

        <div className="janso-command__foot" aria-hidden="true">
          <span>
            <kbd className="janso-command__kbd">↑</kbd>
            <kbd className="janso-command__kbd">↓</kbd> to move
          </span>
          <span>
            <kbd className="janso-command__kbd">↵</kbd> to open
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}

/**
 * ⌘K on Apple platforms, Ctrl+K elsewhere — both are accepted everywhere, because a reader on a
 * Windows keyboard attached to a Mac still reaches for the key their hands know. Ignored while an
 * IME composition is in progress, so a Japanese or Hindi reader typing "k" is not interrupted.
 */
export function useCommandPaletteShortcut(onOpen: () => void): void {
  const latest = useRef(onOpen);
  latest.current = onOpen;
  useEffect(() => {
    function onKey(event: KeyboardEvent): void {
      if (event.isComposing) return;
      if ((event.metaKey || event.ctrlKey) && !event.altKey && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        latest.current();
      }
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);
}

/**
 * The visible way in: a search-shaped button in the top bar. It is a button, not an input — typing
 * happens in the palette — and it names its shortcut so the keyboard path is discoverable.
 *
 * The key cap follows the platform: `⌘ K` on Apple devices, `Ctrl K` elsewhere. It is resolved
 * after mount, so the server render and the first client render agree; the shortcut hook accepts
 * both keys everywhere regardless. `shortcut` overrides the resolved cap.
 */
export function CommandTrigger({
  onOpen,
  label = 'Search or jump to…',
  shortcut,
}: {
  onOpen: () => void;
  label?: string;
  shortcut?: string;
}) {
  const [platformCap, setPlatformCap] = useState('Ctrl K');
  useEffect(() => {
    if (/Mac|iPhone|iPad/.test(navigator.platform)) setPlatformCap('⌘ K');
  }, []);

  return (
    <button
      type="button"
      className="janso-command-trigger"
      onClick={onOpen}
      aria-haspopup="dialog"
      aria-keyshortcuts="Control+K Meta+K"
    >
      <span className="janso-command-trigger__icon" aria-hidden="true">
        <SearchIcon size={15} />
      </span>
      <span className="janso-command-trigger__label">{label}</span>
      <kbd className="janso-command__kbd" aria-hidden="true">
        {shortcut ?? platformCap}
      </kbd>
    </button>
  );
}
