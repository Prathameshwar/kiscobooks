'use client';

import {
  memo,
  useCallback,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { IconButton } from './IconButton';
import { Select } from './Select';
import { CopyIcon, PlusIcon, TrashIcon } from './icons-table';
import { useNumericInput } from '../lib/numeric-input';
import type { SelectOption } from './Select';

/**
 * The document entry grid: a table of rows someone types into.
 *
 * `DataTable` is the *read* surface — a cursor page, a sort the server will honour, a verb set
 * per row. This is its opposite and deliberately a separate control: making one component do
 * both would mean a read list carrying edit machinery it never uses, and an entry grid
 * inheriting paging it must not have. A fifty-line invoice is one document, not a page of them.
 *
 * ## The keyboard model is the product
 *
 * A billing clerk raises dozens of these a day, and Tally's whole speed advantage is that the
 * mouse is never needed. Matching it costs one key-handler:
 *
 * | Key | Does |
 * |---|---|
 * | `Tab` / `Shift+Tab` | Next / previous cell, wrapping across rows |
 * | `Tab` on a row's last cell | The next row's first cell — the row's buttons are skipped going forward |
 * | `Tab` on the last cell | **Adds a row** and lands in its first cell — the flow that makes entry continuous |
 * | `Enter` / `Shift+Enter` | Next / previous row, *same column* — how a column is filled down |
 * | `Ctrl+Enter` | Add a row |
 * | `Alt+Enter` | Open this row's detail |
 * | `Ctrl+D` | Duplicate this row |
 * | `Alt+↑` / `Alt+↓` | Move this row |
 * | `Ctrl+Backspace` | Remove this row, with the caret at the start of the cell |
 * | `Escape` | Give the cell back its stored value |
 *
 * **`Ctrl+Backspace` is also "delete the previous word"** in every text box, and a grid that
 * took it over would delete a fifty-rupee line where the reader meant to delete a word. So it
 * removes the row only where the native action has nothing to do — the caret at the start of
 * the cell with nothing selected, or a control that is not a text box. Pressed twice in a
 * selected cell, it clears the cell and then removes the row.
 *
 * **Going forward, Tab skips a row's buttons; going back, it reaches them.** Three buttons per
 * row in the forward path is three extra presses per line, which on a fifty-line bill is a
 * hundred and fifty presses spent on controls with their own shortcuts. They stay in the native
 * order, so `Shift+Tab` from the next row lands on them — nothing becomes unreachable.
 *
 * **A blank last row ends the grid.** Tabbing or pressing Enter out of a row nobody has typed
 * into does not add another one: it is how a reader says "that was the last line", and the
 * focus moves on to whatever follows the grid, as Tally's end-of-list does.
 *
 * **The arrow keys are left alone.** Every cell is a live input, so `←`/`→` move the caret and
 * `↑`/`↓` are the reader's own. Stealing them for cell movement is the single most common way a
 * web grid becomes unusable for anyone who types.
 *
 * ## Why not `role="grid"`
 *
 * The WAI-ARIA grid pattern is one tab stop with arrow-key navigation over a roving index. That
 * contract cannot hold here: the cells are text inputs that need the arrows for the caret. A
 * `role="grid"` that does not implement arrow navigation is a promise to a screen-reader user
 * that is not kept — the same reason `Menu` drops `aria-haspopup` when it has nothing to open.
 * So this is a plain `<table>` with native tab order, column headers in `<th scope="col">`, and
 * every cell input named `"<column>, line <n>"`, because a visible label per cell is impossible
 * and an unlabelled input in a twelve-column row is unnavigable by voice or screen reader.
 */

export type EntryCellKind = 'text' | 'amount' | 'quantity' | 'select' | 'derived' | 'custom';

export type EntryColumn<Row> = {
  key: string;
  label: string;
  kind: EntryCellKind;
  /** A CSS width for the column. Numbers get a fixed one so a column of them cannot drift. */
  width?: string;
  align?: 'start' | 'end';
  /**
   * Keeps the column in view while the grid scrolls across: `start` beside the row number,
   * `end` beside the row controls. One of each at most — the offsets are the frame columns'
   * fixed widths, so a second pinned column would sit on top of the first.
   */
  pin?: 'start' | 'end';
  /** Marks the header. A required *entry* column is never hidden to save width. */
  required?: boolean;
  value: (row: Row) => string;
  /** Fixed choices, per row — a unit list depends on the item chosen. */
  options?: (row: Row) => readonly (SelectOption | { value: string; label: string })[];
  /** The unit or currency beside a numeric cell. Absent rather than guessed. */
  unit?: (row: Row) => string | undefined;
  /** Display precision override — a unit rate at four places where a total shows two. */
  precision?: number;
  /**
   * Show `unit` beside the figure, not only in its accessible name. For a column whose unit
   * changes what the number *means* — a discount that is `10` percent or `10` rupees — the
   * reader must see it. A quantity's unit is usually its own column and needs no repeat.
   */
  showUnit?: boolean;
  /** Something read beside a numeric cell — where its value came from, say. Never an input. */
  adornment?: (row: Row) => ReactNode;
  /**
   * Anything else a `custom` cell or an adornment renders from, as a string.
   *
   * Rows are memoised on what the column functions return for them (see `rowSignature`), so a
   * cell must render from its row and from `value`, `problem`, `readOnly` and `unit`. A cell
   * that reads something else too says what it is here, or it will not repaint when that
   * changes.
   */
  renderKey?: (row: Row) => string;
  /** Rejects zero as well as blank. A billed quantity needs it; a rate does not. */
  requirePositive?: boolean;
  placeholder?: string;
  /** This cell's own problem, so the row marks itself and the note says which field. */
  problem?: (row: Row) => string | undefined;
  /** Not editable on *this* row — a reward line's rate, a derived discount summary. */
  readOnly?: (row: Row) => boolean;
  /** `custom` cells render themselves: a lookup, a chip, anything with its own popover. */
  render?: (row: Row, context: EntryCellContext) => ReactNode;
  /**
   * Characters that change what a numeric cell's figure *means* rather than being part of it —
   * `%` and `₹` on a discount. Typed in the cell, the character is not inserted; `onUnitKey` is
   * told instead, so `10%` and `₹10` can be entered without leaving the keyboard row.
   */
  unitKeys?: readonly string[];
  onUnitKey?: (row: Row, key: string) => void;
};

export type EntryCellContext = {
  /** Put on the rendered control so the grid's key handling and focus registry find it. */
  readonly cellProps: {
    readonly 'data-entry-row': string;
    readonly 'data-entry-col': string;
    readonly 'aria-label': string;
  };
  readonly registerRef: (element: HTMLElement | null) => void;
  readonly disabled: boolean;
};

export type EntryRowState = 'invalid' | 'warn' | 'reward';

export type EntryGridProps<Row> = {
  /** Names the table. Required: a `<table>` with no caption is an unnamed region. */
  label: string;
  rows: readonly Row[];
  columns: readonly EntryColumn<Row>[];
  rowKey: (row: Row) => string;
  onCellChange: (rowKey: string, columnKey: string, value: string) => void;
  /** The settled canonical value after a numeric cell loses focus. */
  onCellCommit?: (rowKey: string, columnKey: string, value: string) => void;
  onAddRow: () => void;
  onRemoveRow: (rowKey: string) => void;
  onDuplicateRow?: (rowKey: string) => void;
  /** Ctrl+Shift+Enter: a new row directly below this one, rather than at the end. */
  onInsertRow?: (afterRowKey: string) => void;
  onMoveRow?: (rowKey: string, by: -1 | 1) => void;
  rowState?: (row: Row) => EntryRowState | undefined;
  /** One sentence under the row, about the row. Collected elsewhere it is unfindable. */
  rowNote?: (row: Row) => { message: string; tone: 'error' | 'warning' } | undefined;
  /** The row's own expander — the long tail of fields that do not fit a column. */
  onExpandRow?: (rowKey: string) => void;
  expandLabel?: string;
  disabled?: boolean;
  /** Shown instead of the add control when a reader may look but not change. */
  readOnlyNote?: string;
  /**
   * Whether a row is untouched. Leaving a blank last row by `Tab` or `Enter` ends the grid
   * instead of adding a second blank row. Absent, every row counts as entered.
   */
  isRowBlank?: (row: Row) => boolean;
  /**
   * Told when a numeric cell holds text that cannot be stored, and when it stops (`null`).
   * The cell keeps such text on screen while the row keeps its last storable value, so a
   * caller that saves must treat this as a problem — see `NumericInputOptions.onUnstorable`.
   */
  onCellUnstorable?: (rowKey: string, columnKey: string, problem: string | null) => void;
};

/**
 * What a row's cells will render, as one string.
 *
 * The grid re-renders on every keystroke — the caller's draft changed — and a 200-line bill is
 * some 2,400 controls. Re-rendering all of them to change one costs hundreds of milliseconds,
 * which is a lag a clerk feels on every key. So a row is memoised and repaints only when its
 * row object or this signature changes. The signature is cheap (a few string calls per cell)
 * and, unlike comparing column objects, survives a caller that rebuilds its columns per render —
 * which any caller whose derived cells read a live preview must.
 */
function rowSignature<Row>(row: Row, columns: readonly EntryColumn<Row>[]): string {
  let signature = '';
  for (const column of columns) {
    signature +=
      column.key + '\u0001' + column.label + '\u0001' + column.kind + '\u0001' +
      column.value(row) + '\u0001' + (column.problem?.(row) ?? '') + '\u0001' +
      (column.readOnly?.(row) ? '1' : '') + '\u0001' + (column.unit?.(row) ?? '') + '\u0001' +
      (column.placeholder ?? '') + '\u0001' + (column.renderKey?.(row) ?? '') + '\u0002';
  }
  return signature;
}

export function EntryGrid<Row>({
  label,
  rows,
  columns,
  rowKey,
  onCellChange,
  onCellCommit,
  onAddRow,
  onRemoveRow,
  onDuplicateRow,
  onInsertRow,
  onMoveRow,
  rowState,
  rowNote,
  onExpandRow,
  expandLabel = 'More',
  disabled = false,
  readOnlyNote,
  isRowBlank,
  onCellUnstorable,
}: EntryGridProps<Row>) {
  /** Prefixes each row note's id, so two grids on one page cannot collide. */
  const gridId = useId();
  /*
   * The row callbacks, held so the memoised rows can be handed stable functions. A caller
   * passing inline arrows — the ordinary way to write one — would otherwise defeat the memo
   * on every render, and a stale closure is impossible because the ref is read at call time.
   */
  const latest = useRef({ onCellChange, onCellCommit, onRemoveRow, onDuplicateRow, onExpandRow, onCellUnstorable });
  latest.current = { onCellChange, onCellCommit, onRemoveRow, onDuplicateRow, onExpandRow, onCellUnstorable };
  const stableCellChange = useCallback(
    (key: string, column: string, value: string) => latest.current.onCellChange(key, column, value),
    [],
  );
  const stableCellCommit = useCallback(
    (key: string, column: string, value: string) => latest.current.onCellCommit?.(key, column, value),
    [],
  );
  const stableRemove = useCallback((key: string) => latest.current.onRemoveRow(key), []);
  const stableDuplicate = useCallback((key: string) => latest.current.onDuplicateRow?.(key), []);
  const stableExpand = useCallback((key: string) => latest.current.onExpandRow?.(key), []);
  const stableUnstorable = useCallback(
    (key: string, column: string, problem: string | null) =>
      latest.current.onCellUnstorable?.(key, column, problem),
    [],
  );

  /**
   * Every focusable cell, by `row:column`.
   *
   * A registry rather than a `querySelector` sweep: a lookup cell renders a control this grid
   * did not build, and asking the DOM for "the next input" would find the popover's filter box
   * as readily as the next cell.
   */
  const cells = useRef(new Map<string, HTMLElement>());
  const register = useCallback((key: string) => (element: HTMLElement | null) => {
    if (element) cells.current.set(key, element);
    else cells.current.delete(key);
  }, []);

  /**
   * Where focus goes once the caller has re-rendered the rows: the last row (a row added at the
   * end), the row at an index (a copy or an insert, which land below the current one), or a
   * cell by key (a moved row, whose DOM node React relocated — and a browser blurs a node it
   * moves).
   */
  type ChaseTarget =
    | { readonly to: 'last' }
    | { readonly to: 'index'; readonly index: number; readonly column: string | null }
    | { readonly to: 'cell'; readonly key: string };
  type Chase = ChaseTarget & {
    /** The row keys when it was armed. Unchanged, the action changed nothing to chase. */
    readonly before: string;
  };
  const chase = useRef<Chase | null>(null);
  const rowKeys = rows.map(rowKey).join('');
  /*
   * Arm a chase for the render the caller's change produces. Kept with the row keys of the
   * moment: a move off the first line, or a refused duplicate, changes nothing and renders
   * nothing — and a chase left armed then fired on the *next* edit, anywhere, pulling focus
   * back to the cell the reader had already left.
   */
  const arm = (target: ChaseTarget) => {
    chase.current = { ...target, before: rowKeys };
  };

  const order = useMemo(() => {
    const keys: string[] = [];
    for (const row of rows) {
      for (const column of columns) {
        if (column.kind !== 'derived') keys.push(`${rowKey(row)}:${column.key}`);
      }
    }
    return keys;
  }, [columns, rowKey, rows]);

  const focusCell = useCallback((key: string) => {
    const registered = cells.current.get(key);
    if (!registered) return false;
    /*
     * A `custom` cell registers whatever it rendered — a lookup's wrapper, say — which may not
     * be focusable itself. So the focus target is the first thing inside it that is. Requiring
     * every custom cell to hand back a focusable element would make the slot much harder to
     * use than it needs to be.
     */
    const element = registered.matches('input, select, textarea, button, [tabindex]')
      ? registered
      : (registered.querySelector<HTMLElement>('input, select, textarea, button, [tabindex]') ??
        registered);
    element.focus();
    // A disabled control takes no focus. Reporting success anyway would let a caller swallow
    // the key — a read-only grid where Tab went nowhere.
    if (element.ownerDocument.activeElement !== element) return false;
    // Select on a programmatic move, so the next keystroke replaces rather than appends. This
    // is what makes filling a column down feel like a spreadsheet instead of like a form.
    if (element instanceof HTMLInputElement) element.select();
    return true;
  }, []);

  const moveRow = useCallback(
    (from: string, by: -1 | 1) => {
      const [currentRow, column] = from.split(':');
      const index = rows.findIndex((row) => rowKey(row) === currentRow);
      const target = rows[index + by];
      return target ? focusCell(`${rowKey(target)}:${column}`) : false;
    },
    [focusCell, rowKey, rows],
  );

  /**
   * Land in the row that tabbing just created.
   *
   * A layout effect, after render, because the caller owns the row's key and the registry only
   * holds it once the row is painted. Doing this inside the key handler would have meant
   * guessing a key from the registry's insertion order — which is fragile the moment a column
   * set changes.
   */
  useLayoutEffect(() => {
    const pending = chase.current;
    if (!pending) return;
    chase.current = null;
    if (pending.before === rows.map(rowKey).join('')) return;
    const first = columns.find((column) => column.kind !== 'derived');
    if (pending.to === 'cell') {
      focusCell(pending.key);
      return;
    }
    const target = pending.to === 'last' ? rows.at(-1) : rows[pending.index];
    const column = pending.to === 'index' && pending.column ? pending.column : first?.key;
    if (target && column) focusCell(`${rowKey(target)}:${column}`);
  }, [columns, focusCell, rowKey, rows]);

  const onKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLTableSectionElement>) => {
      /*
       * Walked up from the event's target rather than read off it. A `custom` cell renders a
       * control this grid did not build — a lookup with its own portalled list — and that
       * control cannot be expected to forward arbitrary data attributes onto whichever element
       * ends up focused. Asking the nearest ancestor that *is* a cell is the only version of
       * this that works for both kinds of cell.
       */
      // A cell's own control already answered this key — a lookup choosing its highlighted
      // option on Enter, say. Acting on it again would move a row as well as choosing.
      if (event.defaultPrevented) return;
      const target = event.target as HTMLElement;
      const host = target.closest<HTMLElement>('[data-entry-row][data-entry-col]');
      const row = host?.getAttribute('data-entry-row');
      const column = host?.getAttribute('data-entry-col');
      if (!row || !column) return;
      const here = `${row}:${column}`;

      const rowIndex = rows.findIndex((entry) => rowKey(entry) === row);
      const current = rows[rowIndex];
      const blank = current !== undefined && (isRowBlank?.(current) ?? false);

      if (event.key === 'Tab' && !event.shiftKey) {
        // A blank last row ends the grid: native Tab carries on past it.
        if (here === order.at(-1) && blank) return;
        if (here === order.at(-1) && !disabled) {
          /*
           * The flow that makes entry continuous, and the reason Tally and Zoho both do it:
           * tabbing out of the last cell adds a row rather than leaving the grid. Without it
           * every line costs a reach for "Add line".
           *
           * The new row's key belongs to the caller, so focus is *chased* in a layout effect
           * once the row exists rather than guessed at here.
           */
          event.preventDefault();
          arm({ to: 'last' });
          onAddRow();
          return;
        }
        const lastOfRow = columns.filter((entry) => entry.kind !== 'derived').at(-1)?.key;
        const next = rows[rowIndex + 1];
        const first = columns.find((entry) => entry.kind !== 'derived');
        // Past this row's buttons, to the next row: they are reachable going back. Only if that
        // cell took focus — otherwise the native order carries on, rather than Tab dying here.
        if (column === lastOfRow && next && first && focusCell(`${rowKey(next)}:${first.key}`)) {
          event.preventDefault();
        }
        return; // Native tab order handles every other case, which is what it is for.
      }
      if (event.key === 'Enter' && event.altKey && onExpandRow) {
        event.preventDefault();
        onExpandRow(row);
        return;
      }
      if (event.key === 'Enter' && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        // Same column, next row: filling a column down is the commonest entry shape. Off the
        // end of a blank row it adds nothing — a second empty line is not what was asked for.
        if (!moveRow(here, event.shiftKey ? -1 : 1) && !event.shiftKey && !disabled && !blank) {
          arm({ to: 'last' });
          onAddRow();
        }
        return;
      }
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && event.shiftKey && onInsertRow && !disabled) {
        event.preventDefault();
        // Below this line, not at the end: a forgotten item belongs next to the ones it goes with.
        arm({ to: 'index', index: rowIndex + 1, column: null });
        onInsertRow(row);
        return;
      }
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !disabled) {
        event.preventDefault();
        // Into the new row: adding a line and leaving the caret in the old one means the next
        // keystrokes land in the wrong line.
        arm({ to: 'last' });
        onAddRow();
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd' && onDuplicateRow && !disabled) {
        event.preventDefault();
        // Into the copy, same column: a duplicate is made to be changed, and leaving the caret
        // on the original means the change lands on the line that was meant to stay.
        arm({ to: 'index', index: rowIndex + 1, column });
        onDuplicateRow(row);
        return;
      }
      const wordDelete =
        target instanceof HTMLInputElement &&
        target.type === 'text' &&
        (target.selectionStart !== 0 || target.selectionEnd !== 0);
      if ((event.ctrlKey || event.metaKey) && event.key === 'Backspace' && !disabled && !wordDelete) {
        event.preventDefault();
        // Focus first, then remove: removing the row that owns the focused element would drop
        // focus to the body and lose the reader's place in a fifty-line document.
        if (!moveRow(here, 1)) moveRow(here, -1);
        onRemoveRow(row);
        return;
      }
      if (event.altKey && (event.key === 'ArrowUp' || event.key === 'ArrowDown') && onMoveRow && !disabled) {
        event.preventDefault();
        // The moved row's node is relocated by React, and a browser blurs a node it moves —
        // so focus is put back on the same cell once the move has rendered.
        const by = event.key === 'ArrowUp' ? -1 : 1;
        // Off either end there is nowhere to go: nothing to call and nothing to chase.
        if (rowIndex + by < 0 || rowIndex + by >= rows.length) return;
        arm({ to: 'cell', key: here });
        onMoveRow(row, by);
        return;
      }
      if (event.key === 'Escape') {
        // Handed to the cell, which knows its stored value. The grid does not hold drafts.
        (target as HTMLInputElement).blur?.();
        requestAnimationFrame(() => focusCell(here));
      }
      // `←`/`→`/`↑`/`↓` are deliberately untouched: every cell is a live input and the caret
      // is the reader's.
    },
    [
      columns,
      disabled,
      focusCell,
      isRowBlank,
      moveRow,
      onAddRow,
      onDuplicateRow,
      onExpandRow,
      onInsertRow,
      onMoveRow,
      onRemoveRow,
      order,
      rowKey,
      rows,
    ],
  );

  return (
    <div className="janso-entry-grid__scroll">
      <table className="janso-entry-grid">
        <caption className="janso-visually-hidden">
          {label}. Tab moves across, Enter moves down, Control and Enter adds a line.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="janso-entry-grid__ordinal">
              #
            </th>
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                style={column.width ? { width: column.width } : undefined}
                data-align={column.align === 'end' ? 'end' : undefined}
                data-pin={column.pin}
                data-required={column.required ? 'true' : undefined}
              >
                {column.label}
              </th>
            ))}
            <th scope="col" className="janso-entry-grid__controls">
              <span className="janso-visually-hidden">Line actions</span>
            </th>
          </tr>
        </thead>
        <tbody onKeyDown={onKeyDown}>
          {rows.map((row, index) => {
            const key = rowKey(row);
            const state = rowState?.(row);
            const note = rowNote?.(row);
            return (
              <MemoEntryRow
                key={key}
                row={row}
                rowKey={key}
                ordinal={index + 1}
                columns={columns}
                signature={rowSignature(row, columns)}
                state={state}
                noteMessage={note?.message}
                noteTone={note?.tone}
                register={register}
                noteId={note ? `${gridId}-note-${index + 1}` : undefined}
                onCellChange={stableCellChange}
                onCellCommit={stableCellCommit}
                onCellUnstorable={stableUnstorable}
                onRemoveRow={rows.length > 1 ? stableRemove : undefined}
                onDuplicateRow={onDuplicateRow ? stableDuplicate : undefined}
                onExpandRow={onExpandRow ? stableExpand : undefined}
                expandLabel={expandLabel}
                disabled={disabled}
              />
            );
          })}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={columns.length + 2}>
              {disabled ? (
                <p className="janso-entry__number-note">{readOnlyNote ?? 'Read only.'}</p>
              ) : (
                <button type="button" className="janso-entry-grid__add" onClick={onAddRow}>
                  <PlusIcon size={14} aria-hidden="true" />
                  Add line
                  {/* Shown, not announced: the caption already names the key, and a name of
                    * "Add line Ctrl ↵" reads the glyph aloud. */}
                  <kbd className="janso-command__kbd" aria-hidden="true">
                    Ctrl ↵
                  </kbd>
                </button>
              )}
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

function EntryRow<Row>({
  row,
  rowKey,
  ordinal,
  columns,
  state,
  noteMessage,
  noteTone,
  noteId,
  register,
  onCellChange,
  onCellCommit,
  onCellUnstorable,
  onRemoveRow,
  onDuplicateRow,
  onExpandRow,
  expandLabel,
  disabled,
}: {
  row: Row;
  rowKey: string;
  ordinal: number;
  columns: readonly EntryColumn<Row>[];
  /** Compared instead of `columns`; see `rowSignature`. */
  signature: string;
  state: EntryRowState | undefined;
  noteMessage: string | undefined;
  noteTone: 'error' | 'warning' | undefined;
  /** The note's id, so a cell with a problem can point its description at it. */
  noteId: string | undefined;
  register: (key: string) => (element: HTMLElement | null) => void;
  onCellChange: (rowKey: string, columnKey: string, value: string) => void;
  onCellCommit: (rowKey: string, columnKey: string, value: string) => void;
  onCellUnstorable: (rowKey: string, columnKey: string, problem: string | null) => void;
  onRemoveRow?: (rowKey: string) => void;
  onDuplicateRow?: (rowKey: string) => void;
  onExpandRow?: (rowKey: string) => void;
  expandLabel: string;
  disabled: boolean;
}) {
  return (
    <>
      <tr data-state={state}>
        <td className="janso-entry-grid__ordinal">{ordinal}</td>
        {columns.map((column) => (
          <td
            key={column.key}
            data-align={column.align === 'end' ? 'end' : undefined}
            data-pin={column.pin}
          >
            <EntryCell
              row={row}
              rowKey={rowKey}
              ordinal={ordinal}
              column={column}
              register={register}
              noteId={noteId}
              onCellChange={onCellChange}
              onCellCommit={onCellCommit}
              onCellUnstorable={onCellUnstorable}
              disabled={disabled}
            />
          </td>
        ))}
        <td className="janso-entry-grid__controls">
          {onExpandRow ? (
            <IconButton
              label={`${expandLabel}, line ${ordinal}`}
              icon={<span aria-hidden="true">⌄</span>}
              size="sm"
              onClick={() => onExpandRow(rowKey)}
            />
          ) : null}
          {onDuplicateRow && !disabled ? (
            <IconButton
              label={`Duplicate line ${ordinal}`}
              icon={<CopyIcon size={14} />}
              size="sm"
              onClick={() => onDuplicateRow(rowKey)}
            />
          ) : null}
          {onRemoveRow && !disabled ? (
            <IconButton
              label={`Remove line ${ordinal}`}
              icon={<TrashIcon size={14} />}
              size="sm"
              onClick={() => onRemoveRow(rowKey)}
            />
          ) : null}
        </td>
      </tr>
      {noteMessage ? (
        /* Under the row it is about. A problem list somewhere else makes a reader count rows
         * to find which line it means. */
        <tr className="janso-entry-grid__note">
          <td />
          <td colSpan={columns.length + 1}>
            <span className="janso-entry-grid__note-text" id={noteId} data-tone={noteTone}>
              {noteMessage}
            </span>
          </td>
        </tr>
      ) : null}
    </>
  );
}

/**
 * A row repaints when its row, its signature or its chrome changes — never because a sibling
 * did. `columns` is deliberately not compared: callers rebuild it per render, and what it would
 * render differently is already in the signature.
 */
const MemoEntryRow = memo(EntryRow, (before, after) =>
  before.row === after.row &&
  before.signature === after.signature &&
  before.rowKey === after.rowKey &&
  before.ordinal === after.ordinal &&
  before.state === after.state &&
  before.noteMessage === after.noteMessage &&
  before.noteTone === after.noteTone &&
  before.noteId === after.noteId &&
  before.disabled === after.disabled &&
  before.expandLabel === after.expandLabel &&
  before.register === after.register &&
  before.onCellChange === after.onCellChange &&
  before.onCellCommit === after.onCellCommit &&
  before.onCellUnstorable === after.onCellUnstorable &&
  before.onRemoveRow === after.onRemoveRow &&
  before.onDuplicateRow === after.onDuplicateRow &&
  before.onExpandRow === after.onExpandRow,
) as typeof EntryRow;

function EntryCell<Row>({
  row,
  rowKey,
  ordinal,
  column,
  register,
  noteId,
  onCellChange,
  onCellCommit,
  onCellUnstorable,
  disabled,
}: {
  row: Row;
  rowKey: string;
  ordinal: number;
  column: EntryColumn<Row>;
  register: (key: string) => (element: HTMLElement | null) => void;
  noteId: string | undefined;
  onCellChange: (rowKey: string, columnKey: string, value: string) => void;
  onCellCommit: (rowKey: string, columnKey: string, value: string) => void;
  onCellUnstorable: (rowKey: string, columnKey: string, problem: string | null) => void;
  disabled: boolean;
}) {
  const key = `${rowKey}:${column.key}`;
  // A visible label per cell is impossible in a twelve-column row, and an unlabelled input is
  // unnavigable by voice or screen reader. So the column and the line number are the name.
  const name = `${column.label}, line ${ordinal}`;
  const value = column.value(row);
  const problem = column.problem?.(row);
  const readOnly = disabled || (column.readOnly?.(row) ?? false);
  // A cell with a problem points at the note under its row, which is where the problem is said.
  const describedBy = problem && noteId ? noteId : undefined;

  const cellProps = {
    'data-entry-row': rowKey,
    'data-entry-col': column.key,
    'aria-label': name,
  } as const;

  if (column.kind === 'derived') {
    return (
      /*
       * Not a disabled input — *not an input*. A disabled box invites "why can I not type
       * here", and the answer ("the service resolves this") is not a permission problem.
       */
      <span className="janso-entry-cell--derived" data-unresolved={value === '' ? 'true' : undefined}>
        <span className="janso-visually-hidden">{name}: </span>
        {value === '' ? '—' : value}
      </span>
    );
  }

  if (column.kind === 'custom' && column.render) {
    return <>{column.render(row, { cellProps, registerRef: register(key), disabled: readOnly })}</>;
  }

  if (column.kind === 'select') {
    return (
      <select
        ref={register(key) as never}
        className="janso-entry-cell"
        value={value}
        disabled={readOnly}
        aria-invalid={problem ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => onCellChange(rowKey, column.key, event.target.value)}
        {...cellProps}
      >
        {(column.options?.(row) ?? []).map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (column.kind === 'amount' || column.kind === 'quantity') {
    return (
      <NumericCell
        cellKey={key}
        name={name}
        kind={column.kind === 'amount' ? 'money' : 'quantity'}
        value={value}
        unit={column.unit?.(row)}
        showUnit={column.showUnit ?? false}
        adornment={column.adornment?.(row)}
        precision={column.precision}
        requirePositive={column.requirePositive ?? false}
        problem={problem}
        readOnly={readOnly}
        placeholder={column.placeholder}
        cellProps={cellProps}
        describedBy={describedBy}
        register={register}
        onChange={(next) => onCellChange(rowKey, column.key, next)}
        onCommit={(next) => onCellCommit(rowKey, column.key, next)}
        onUnstorable={(message) => onCellUnstorable(rowKey, column.key, message)}
        unitKeys={column.unitKeys}
        onUnitKey={column.onUnitKey ? (typed) => column.onUnitKey?.(row, typed) : undefined}
      />
    );
  }

  return (
    <input
      ref={register(key)}
      className="janso-entry-cell"
      type="text"
      value={value}
      placeholder={column.placeholder}
      readOnly={readOnly}
      autoComplete="off"
      aria-invalid={problem ? true : undefined}
      aria-describedby={describedBy}
      onChange={(event) => onCellChange(rowKey, column.key, event.target.value)}
      {...cellProps}
    />
  );
}

/**
 * A money or quantity cell, on the same hook the form fields use.
 *
 * Identical parsing, separators, storage scale and focused-versus-blurred display — because a
 * figure typed in the grid and read on a form that disagreed would make both worthless. The
 * chrome differs (no label row, no floating label, right-aligned); the mechanism does not.
 */
function NumericCell({
  cellKey,
  name,
  kind,
  value,
  unit,
  showUnit,
  adornment,
  precision,
  requirePositive,
  problem,
  readOnly,
  placeholder,
  cellProps,
  describedBy,
  register,
  onChange,
  onCommit,
  onUnstorable,
  unitKeys,
  onUnitKey,
}: {
  cellKey: string;
  name: string;
  kind: 'money' | 'quantity';
  value: string;
  unit: string | undefined;
  showUnit: boolean;
  adornment: ReactNode;
  precision: number | undefined;
  requirePositive: boolean;
  problem: string | undefined;
  readOnly: boolean;
  placeholder: string | undefined;
  cellProps: Record<string, string>;
  describedBy: string | undefined;
  register: (key: string) => (element: HTMLElement | null) => void;
  onChange: (value: string) => void;
  onCommit: (value: string) => void;
  onUnstorable: (problem: string | null) => void;
  unitKeys?: readonly string[] | undefined;
  onUnitKey?: ((key: string) => void) | undefined;
}) {
  const numeric = useNumericInput({
    value,
    onChange,
    onUnstorable,
    kind,
    requirePositive,
    ...(precision !== undefined ? { precision } : {}),
  });
  const input = useRef<HTMLInputElement | null>(null);
  /**
   * Select-all on focus, applied after the paint rather than inside the handler.
   *
   * A numeric cell swaps its text on focus — grouped `1,234.50` becomes canonical `1234.5` —
   * and selecting before that swap is pointless, because the re-render puts the caret at the
   * end again. A layout effect runs after the new value is in the DOM and before the browser
   * paints, so the selection survives. Without it, moving down a column *appends* to whatever
   * was there, which is the opposite of what a spreadsheet does.
   */
  const selectOnPaint = useRef(false);
  useLayoutEffect(() => {
    if (!selectOnPaint.current) return;
    selectOnPaint.current = false;
    input.current?.select();
  });

  return (
    <span className="janso-entry-cell__numeric-wrap">
      <input
        ref={(element) => {
          input.current = element;
          register(cellKey)(element);
        }}
        className="janso-entry-cell janso-entry-cell--numeric"
        {...numeric.inputProps}
        value={numeric.text}
        placeholder={placeholder}
        readOnly={readOnly}
        aria-invalid={problem || numeric.invalid ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => numeric.onChange(event.target.value)}
        onKeyDown={(event) => {
          // Escape gives the cell back its stored value — including over text that could not
          // be stored, which blur deliberately keeps.
          if (event.key === 'Escape') numeric.revert();
          if (onUnitKey && !readOnly && unitKeys?.includes(event.key)) {
            event.preventDefault();
            onUnitKey(event.key);
          }
        }}
        onFocus={() => {
          selectOnPaint.current = true;
          numeric.onFocus();
        }}
        onBlur={() => { const settled = numeric.onBlur(); if (settled !== null) onCommit(settled); }}
        {...cellProps}
        aria-label={unit ? `${name} in ${unit}` : name}
      />
      {showUnit && unit ? (
        <span className="janso-entry-cell__unit" aria-hidden="true">
          {unit}
        </span>
      ) : null}
      {adornment}
    </span>
  );
}
