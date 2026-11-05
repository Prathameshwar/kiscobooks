/**
 * `EntryGrid` — the keyboard model, which is the whole product.
 *
 * A billing clerk raises dozens of documents a day, and Tally's entire speed advantage is that
 * the mouse is never needed. So the tests here are about keys, in this order of importance:
 *
 *  - **Tab out of the last cell adds a line and lands in it.** Without this, every line costs a
 *    reach for "Add line", and that single behaviour is most of what makes Tally fast.
 *  - **Enter moves down the same column.** Filling a column down is the commonest entry shape.
 *  - **The arrow keys are left alone.** Every cell is a live input; stealing `←`/`→` for cell
 *    movement is the single most common way a web grid becomes unusable for anyone who types.
 *  - **Removing a row keeps the reader's place**, because losing focus to the body in a
 *    fifty-line document means finding your line again by eye.
 */
import { describe, expect, it, vi } from 'vitest';
import { useState } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { EntryGrid, type EntryColumn } from '../src/components/EntryGrid';
import { DisplayConfigProvider } from '../src/lib/display-config';

type Row = { key: string; item: string; qty: string; rate: string; unit: string; amount: string };

let counter = 0;
const row = (over: Partial<Row> = {}): Row => ({
  key: `r${++counter}`,
  item: '',
  qty: '',
  rate: '',
  unit: 'nos',
  amount: '',
  ...over,
});

const COLUMNS: EntryColumn<Row>[] = [
  { key: 'item', label: 'Item', kind: 'text', required: true, value: (r) => r.item },
  { key: 'qty', label: 'Billed', kind: 'quantity', align: 'end', value: (r) => r.qty, requirePositive: true },
  {
    key: 'unit',
    label: 'Unit',
    kind: 'select',
    value: (r) => r.unit,
    options: () => [
      { value: 'nos', label: 'nos' },
      { value: 'kg', label: 'kg' },
    ],
  },
  { key: 'rate', label: 'Rate', kind: 'amount', align: 'end', value: (r) => r.rate },
  { key: 'amount', label: 'Amount', kind: 'derived', align: 'end', value: (r) => r.amount },
];

/** A controlled host, so the grid is exercised the way a page actually drives it. */
function Host({
  initial,
  columns = COLUMNS,
  onChangeSpy,
  ...rest
}: {
  initial?: Row[];
  columns?: EntryColumn<Row>[];
  onChangeSpy?: (key: string, column: string, value: string) => void;
  [key: string]: unknown;
}) {
  const [rows, setRows] = useState<Row[]>(initial ?? [row(), row()]);
  return (
    <DisplayConfigProvider>
      <EntryGrid<Row>
        label="Invoice lines"
        rows={rows}
        columns={columns}
        rowKey={(entry) => entry.key}
        onCellChange={(key, column, value) => {
          onChangeSpy?.(key, column, value);
          setRows((current) =>
            current.map((entry) => (entry.key === key ? { ...entry, [column]: value } : entry)),
          );
        }}
        onAddRow={() => setRows((current) => [...current, row()])}
        onInsertRow={(after) =>
          setRows((current) => {
            const index = current.findIndex((entry) => entry.key === after);
            return [...current.slice(0, index + 1), row(), ...current.slice(index + 1)];
          })
        }
        onRemoveRow={(key) => setRows((current) => current.filter((entry) => entry.key !== key))}
        onDuplicateRow={(key) =>
          setRows((current) => {
            const index = current.findIndex((entry) => entry.key === key);
            const source = current[index]!;
            return [
              ...current.slice(0, index + 1),
              { ...source, key: `r${++counter}` },
              ...current.slice(index + 1),
            ];
          })
        }
        onMoveRow={(key, by) =>
          setRows((current) => {
            const index = current.findIndex((entry) => entry.key === key);
            const target = index + by;
            if (target < 0 || target >= current.length) return current;
            const next = [...current];
            const [moved] = next.splice(index, 1);
            next.splice(target, 0, moved!);
            return next;
          })
        }
        {...rest}
      />
    </DisplayConfigProvider>
  );
}

const cell = (column: string, line: number) =>
  screen.getByRole(column === 'Unit' ? 'combobox' : 'textbox', {
    name: new RegExp(`^${column}, line ${line}`),
  });

/** Rows minus the header and the footer, which holds the add control. */
const lineCount = () => screen.getAllByRole('row').length - 2;

describe('the keyboard model', () => {
  it('adds a line when tab leaves the last cell, and lands in it', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row()]} />);
    expect(lineCount()).toBe(1);

    // The last editable cell: the amount column is derived and takes no focus.
    await user.click(cell('Rate', 1));
    await user.tab();

    expect(lineCount()).toBe(2);
    // And the caret is already where the next line starts, so entry never stops.
    expect(cell('Item', 2)).toHaveFocus();
  });

  it('moves down the same column on Enter', async () => {
    const user = userEvent.setup();
    render(<Host />);

    await user.click(cell('Billed', 1));
    await user.keyboard('{Enter}');

    expect(cell('Billed', 2)).toHaveFocus();
  });

  it('moves up the same column on Shift+Enter, and does not add a line at the top', async () => {
    const user = userEvent.setup();
    render(<Host />);

    await user.click(cell('Billed', 2));
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    expect(cell('Billed', 1)).toHaveFocus();

    await user.keyboard('{Shift>}{Enter}{/Shift}');
    expect(lineCount()).toBe(2);
    expect(cell('Billed', 1)).toHaveFocus();
  });

  it('adds a line on Enter from the last row, because that is where entry continues', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row()]} />);

    await user.click(cell('Item', 1));
    await user.keyboard('{Enter}');

    expect(lineCount()).toBe(2);
  });

  it('adds a line on Ctrl+Enter from anywhere', async () => {
    const user = userEvent.setup();
    render(<Host />);

    await user.click(cell('Item', 1));
    await user.keyboard('{Control>}{Enter}{/Control}');

    expect(lineCount()).toBe(3);
  });

  it('duplicates a line on Ctrl+D', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'Basmati rice' })]} />);

    await user.click(cell('Item', 1));
    await user.keyboard('{Control>}d{/Control}');

    expect(lineCount()).toBe(2);
    expect(cell('Item', 2)).toHaveValue('Basmati rice');
  });

  it('moves a line with Alt and the arrows', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'First' }), row({ item: 'Second' })]} />);

    await user.click(cell('Item', 2));
    await user.keyboard('{Alt>}{ArrowUp}{/Alt}');

    expect(cell('Item', 1)).toHaveValue('Second');
    expect(cell('Item', 2)).toHaveValue('First');
  });

  it('removes a line on Ctrl+Backspace and keeps the reader’s place', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'First' }), row({ item: 'Second' })]} />);

    await user.click(cell('Item', 1));
    // From the start of the cell, where "delete the previous word" has nothing to delete.
    await user.keyboard('{Home}{Control>}{Backspace}{/Control}');

    expect(lineCount()).toBe(1);
    // Focus moved *before* the row went, so it did not fall to the body — which in a fifty-line
    // document means finding your place again by eye.
    expect(cell('Item', 1)).toHaveFocus();
    expect(cell('Item', 1)).toHaveValue('Second');
  });

  it('leaves the arrow keys to the caret', async () => {
    // The single most common way a web grid becomes unusable: every cell here is a live input,
    // so `←`/`→` belong to the text and `↑`/`↓` to the reader.
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'abc' }), row()]} />);

    const input = cell('Item', 1) as HTMLInputElement;
    await user.click(input);
    input.setSelectionRange(3, 3);
    await user.keyboard('{ArrowLeft}');

    expect(input).toHaveFocus();
    expect(input.selectionStart).toBe(2);

    await user.keyboard('{ArrowDown}');
    expect(cell('Item', 1)).toHaveFocus();
  });

  it('selects on a programmatic move, so the next keystroke replaces', async () => {
    // What makes filling a column down feel like a spreadsheet rather than like a form.
    const user = userEvent.setup();
    render(<Host initial={[row({ qty: '5' }), row({ qty: '7' })]} />);

    await user.click(cell('Billed', 1));
    await user.keyboard('{Enter}');
    await user.keyboard('9');

    expect(cell('Billed', 2)).toHaveValue('9');
  });
});

describe('what a cell is', () => {
  it('renders a derived column as read-only text, not a disabled input', () => {
    // A disabled box invites "why can I not type here", and the answer — the service resolves
    // this — is not a permission problem.
    render(<Host initial={[row({ amount: '1,000.00' })]} />);

    expect(screen.queryByRole('textbox', { name: /^Amount/ })).not.toBeInTheDocument();
    expect(screen.getByText('1,000.00')).toBeInTheDocument();
  });

  it('shows an unresolved derived figure as an em dash, never as zero', () => {
    render(<Host initial={[row()]} />);
    const line = screen.getAllByRole('row')[1]!;

    expect(within(line).getByText('—')).toBeInTheDocument();
    expect(within(line).queryByText('0.00')).not.toBeInTheDocument();
  });

  it('formats a numeric cell on blur and emits canonical text', async () => {
    const onChangeSpy = vi.fn();
    const user = userEvent.setup();
    render(<Host initial={[row()]} onChangeSpy={onChangeSpy} />);

    await user.type(cell('Rate', 1), '1234.5');
    await user.tab();

    // Canonical on the wire, grouped on the screen — the same hook the form fields use.
    expect(onChangeSpy).toHaveBeenCalledWith(expect.any(String), 'rate', '1234.5');
    expect(cell('Rate', 1)).toHaveValue('1,234.50');
  });

  it('marks a numeric cell invalid without discarding what was typed', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row()]} />);

    await user.type(cell('Rate', 1), '1.23456');

    expect(cell('Rate', 1)).toHaveAttribute('aria-invalid', 'true');
    expect(cell('Rate', 1)).toHaveValue('1.23456');
  });

  it('refuses a zero quantity where the column needs a positive one', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row()]} />);

    await user.type(cell('Billed', 1), '0');
    expect(cell('Billed', 1)).toHaveAttribute('aria-invalid', 'true');
  });

  it('offers a select cell the row’s own choices', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row()]} />);

    await user.selectOptions(cell('Unit', 1), 'kg');
    expect(cell('Unit', 1)).toHaveValue('kg');
  });
});

describe('accessibility', () => {
  it('names every cell by its column and line number', () => {
    // A visible label per cell is impossible in a twelve-column row, and an unlabelled input is
    // unnavigable by voice or screen reader.
    render(<Host initial={[row(), row()]} />);

    expect(screen.getByRole('textbox', { name: 'Item, line 1' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Item, line 2' })).toBeInTheDocument();
  });

  it('is a plain table, not a role="grid" it does not implement', () => {
    /*
     * The WAI-ARIA grid pattern is one tab stop with arrow-key navigation over a roving index,
     * and that contract cannot hold when every cell is a text input that needs the arrows for
     * the caret. Claiming the role anyway is a promise to a screen-reader user that is not
     * kept — the same reason `Menu` drops `aria-haspopup` when it has nothing to open.
     */
    render(<Host />);

    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.queryByRole('grid')).not.toBeInTheDocument();
  });

  it('names the table and says how to move around it', () => {
    render(<Host />);
    expect(screen.getByRole('table', { name: /Invoice lines/ })).toBeInTheDocument();
    expect(screen.getByText(/Tab moves across, Enter moves down/)).toBeInTheDocument();
  });

  it('marks a required entry column in its header', () => {
    render(<Host />);
    expect(screen.getByRole('columnheader', { name: 'Item' })).toHaveAttribute(
      'data-required',
      'true',
    );
  });

  it('names each row action with the line it acts on', () => {
    render(<Host />);
    expect(screen.getByRole('button', { name: 'Remove line 1' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Duplicate line 2' })).toBeInTheDocument();
  });
});

describe('rows, states and notes', () => {
  it('withholds remove when one line is all there is', () => {
    // An empty grid has nothing to type into, and "add a line" as the only thing on screen is
    // a worse empty state than one blank row.
    render(<Host initial={[row()]} />);
    expect(screen.queryByRole('button', { name: /Remove line/ })).not.toBeInTheDocument();
  });

  it('marks a row state and puts its note under the row it is about', () => {
    render(
      <Host
        initial={[row({ item: 'Bad' }), row()]}
        rowState={(entry: Row) => (entry.item === 'Bad' ? 'invalid' : undefined)}
        rowNote={(entry: Row) =>
          entry.item === 'Bad' ? { message: 'Enter a rate.', tone: 'error' } : undefined
        }
      />,
    );

    expect(screen.getAllByRole('row')[1]).toHaveAttribute('data-state', 'invalid');
    // A problem list somewhere else makes a reader count rows to find which line it means.
    expect(screen.getByText('Enter a rate.')).toBeInTheDocument();
  });

  it('offers a row expander only when the caller has somewhere to expand to', () => {
    const onExpandRow = vi.fn();
    render(<Host initial={[row()]} onExpandRow={onExpandRow} expandLabel="Line detail" />);

    expect(screen.getByRole('button', { name: 'Line detail, line 1' })).toBeInTheDocument();
  });

  it('advertises the add shortcut on the control, at the foot of the rows', () => {
    // Where the next line will appear. A button at the top adds a row the reader then has to
    // scroll to find, and an unadvertised shortcut is one nobody uses.
    render(<Host />);
    const add = screen.getByRole('button', { name: /Add line/ });

    expect(add).toBeInTheDocument();
    expect(within(add).getByText('Ctrl ↵')).toBeInTheDocument();
  });
});

describe('read only', () => {
  it('takes away the add and remove controls and says why', () => {
    render(<Host disabled readOnlyNote="This bill has been issued." />);

    expect(screen.queryByRole('button', { name: /Add line/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Remove line/ })).not.toBeInTheDocument();
    expect(screen.getByText('This bill has been issued.')).toBeInTheDocument();
  });

  it('does not add a line when tab leaves the last cell', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row()]} disabled />);

    await user.click(cell('Rate', 1));
    await user.tab();

    expect(lineCount()).toBe(1);
  });
});

describe('the keyboard pass (S7)', () => {
  const blank = (entry: Row) => !entry.item && !entry.qty && !entry.rate;

  it('tabs from a row’s last cell to the next row, past its buttons', async () => {
    // Three buttons per row in the forward path is three extra presses per line.
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'Rice' }), row()]} onExpandRow={() => {}} />);

    await user.click(cell('Rate', 1));
    await user.tab();
    expect(cell('Item', 2)).toHaveFocus();
  });

  it('still reaches a row’s buttons going back', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'Rice' }), row()]} />);

    await user.click(cell('Item', 2));
    await user.tab({ shift: true });
    expect(screen.getByRole('button', { name: 'Remove line 1' })).toHaveFocus();
  });

  it('ends the grid when tab leaves a blank last row, rather than adding another', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'Rice' }), row()]} isRowBlank={blank} />);

    await user.click(cell('Rate', 2));
    await user.tab();
    expect(lineCount()).toBe(2);
    expect(cell('Rate', 2)).not.toHaveFocus();
  });

  it('still adds a line when tab leaves an entered last row', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'Rice' })]} isRowBlank={blank} />);

    await user.click(cell('Rate', 1));
    await user.tab();
    expect(lineCount()).toBe(2);
    expect(cell('Item', 2)).toHaveFocus();
  });

  it('adds no line on Enter from a blank last row', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row()]} isRowBlank={blank} />);

    await user.click(cell('Item', 1));
    await user.keyboard('{Enter}');
    expect(lineCount()).toBe(1);
  });

  it('opens a row’s detail on Alt+Enter', async () => {
    const user = userEvent.setup();
    const expand = vi.fn();
    render(<Host onExpandRow={expand} />);

    await user.click(cell('Billed', 2));
    await user.keyboard('{Alt>}{Enter}{/Alt}');
    expect(expand).toHaveBeenCalledTimes(1);
    expect(lineCount()).toBe(2);
  });
});

describe('what a numeric cell shows beside itself', () => {
  it('shows a unit that changes what the figure means', () => {
    const columns: EntryColumn<Row>[] = [
      ...COLUMNS.slice(0, 3),
      { ...COLUMNS[3]!, label: 'Discount', unit: () => '%', showUnit: true },
    ];
    render(<Host initial={[row({ rate: '10' })]} columns={columns} />);

    const box = screen.getByRole('textbox', { name: 'Discount, line 1 in %' });
    expect(box.parentElement).toHaveTextContent('%');
  });

  it('keeps an unshown unit in the name only', () => {
    const columns: EntryColumn<Row>[] = [{ ...COLUMNS[1]!, unit: () => 'kg' }];
    render(<Host initial={[row({ qty: '2' })]} columns={columns} />);

    const box = screen.getByRole('textbox', { name: 'Billed, line 1 in kg' });
    expect(box.parentElement).not.toHaveTextContent('kg');
  });

  it('renders an adornment after the figure', () => {
    const columns: EntryColumn<Row>[] = [{ ...COLUMNS[3]!, adornment: () => <span>List</span> }];
    render(<Host initial={[row({ rate: '10' })]} columns={columns} />);

    expect(cell('Rate', 1).parentElement).toHaveTextContent('List');
  });
});

describe('at scale', () => {
  /*
   * A 200-line bill is some 2,400 controls. Re-rendering all of them to change one is a lag
   * a clerk feels on every key, so a row repaints only when its own row or signature changes.
   * Counted rather than timed: a render count is deterministic where a stopwatch is not.
   */
  it('repaints only the row that changed', async () => {
    const user = userEvent.setup();
    const painted = vi.fn();
    const columns: EntryColumn<Row>[] = [
      {
        key: 'item',
        label: 'Item',
        kind: 'custom',
        value: (r) => r.item,
        render: (r, context) => {
          painted(r.key);
          return <input {...context.cellProps} ref={context.registerRef} value={r.item} readOnly />;
        },
      },
      COLUMNS[1]!,
    ];
    const rows = Array.from({ length: 200 }, () => row());
    render(<Host initial={rows} columns={columns} />);
    painted.mockClear();

    await user.type(screen.getByRole('textbox', { name: 'Billed, line 3' }), '5');
    const keys = new Set(painted.mock.calls.map(([key]) => key));
    expect([...keys]).toEqual([rows[2]!.key]);
  });

  it('repaints a row whose derived figure changed though the row did not', () => {
    // The memo compares what the row will show, not the row object alone — a document
    // discount changes every line's amount without touching a single line.
    const rows = [row({ item: 'Rice' })];
    const columns = (amount: string): EntryColumn<Row>[] => [
      COLUMNS[0]!,
      { key: 'amount', label: 'Amount', kind: 'derived', value: () => amount },
    ];
    const grid = (amount: string) => (
      <DisplayConfigProvider>
        <EntryGrid<Row>
          label="Invoice lines"
          rows={rows}
          columns={columns(amount)}
          rowKey={(entry) => entry.key}
          onCellChange={() => {}}
          onAddRow={() => {}}
          onRemoveRow={() => {}}
        />
      </DisplayConfigProvider>
    );
    const { rerender } = render(grid('100.00'));
    rerender(grid('90.00'));
    expect(screen.getByText('90.00')).toBeInTheDocument();
  });

  it('calls the latest callback, not the one a memoised row was painted with', async () => {
    const user = userEvent.setup();
    const first = vi.fn();
    const second = vi.fn();
    const rows = [row({ item: 'Rice' })];
    const grid = (spy: () => void) => (
      <DisplayConfigProvider>
        <EntryGrid<Row>
          label="Invoice lines"
          rows={rows}
          columns={COLUMNS}
          rowKey={(entry) => entry.key}
          onCellChange={spy}
          onAddRow={() => {}}
          onRemoveRow={() => {}}
        />
      </DisplayConfigProvider>
    );
    const { rerender } = render(grid(first));
    rerender(grid(second));
    await user.type(cell('Item', 1), 'x');
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalled();
  });
});

describe('Ctrl+Backspace inside text', () => {
  it('deletes a word rather than the line when there is text before the caret', async () => {
    // The native "delete the previous word" must survive: a grid that took the chord over would
    // remove a whole line where the reader meant to remove a word.
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'Basmati rice' }), row({ item: 'Oil' })]} />);

    await user.click(cell('Item', 1));
    await user.keyboard('{End}{Control>}{Backspace}{/Control}');
    expect(lineCount()).toBe(2);
  });

  it('removes the line from an empty cell', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'Rice' }), row()]} />);

    await user.click(cell('Item', 2));
    await user.keyboard('{Control>}{Backspace}{/Control}');
    expect(lineCount()).toBe(1);
  });
});

describe('the fourth review', () => {
  it('does not chase focus after a move that changed nothing', async () => {
    // Alt+Up on the first line armed a focus jump that fired on the next edit anywhere.
    const user = userEvent.setup();
    render(<Host initial={[{ ...row(), item: 'Rice' }, { ...row(), item: 'Oil' }]} />);
    await user.click(cell('Rate', 1));
    await user.keyboard('{Alt>}{ArrowUp}{/Alt}');
    await user.click(cell('Item', 2));
    await user.keyboard('x');
    expect(cell('Item', 2)).toHaveFocus();
    expect(cell('Item', 2)).toHaveValue('Oilx');
  });

  it('does not chase focus after a duplicate that was refused', async () => {
    const user = userEvent.setup();
    render(<Host initial={[{ ...row(), item: 'Rice' }, { ...row(), item: 'Oil' }]} onDuplicateRow={() => undefined} />);
    await user.click(cell('Item', 1));
    await user.keyboard('{Control>}d{/Control}');
    await user.click(cell('Item', 2));
    await user.keyboard('y');
    expect(cell('Item', 2)).toHaveFocus();
  });
});

describe('the third review', () => {
  it('puts the caret in the copy after Ctrl+D, in the same column', async () => {
    const user = userEvent.setup();
    render(<Host initial={[{ ...row(), item: 'Rice', qty: '2' }]} />);
    await user.click(cell('Billed', 1));
    await user.keyboard('{Control>}d{/Control}');
    expect(lineCount()).toBe(2);
    await waitFor(() => expect(cell('Billed', 2)).toHaveFocus());
  });

  it('inserts a line below with Ctrl+Shift+Enter and lands in it', async () => {
    const user = userEvent.setup();
    render(<Host initial={[{ ...row(), item: 'Rice' }, { ...row(), item: 'Oil' }]} />);
    await user.click(cell('Item', 1));
    await user.keyboard('{Control>}{Shift>}{Enter}{/Shift}{/Control}');
    expect(lineCount()).toBe(3);
    // Between the two, not at the end.
    expect(cell('Item', 2)).toHaveValue('');
    expect(cell('Item', 3)).toHaveValue('Oil');
    await waitFor(() => expect(cell('Item', 2)).toHaveFocus());
  });

  it('keeps focus on the moved line after Alt+Down', async () => {
    const user = userEvent.setup();
    render(<Host initial={[{ ...row(), item: 'Rice' }, { ...row(), item: 'Oil' }]} />);
    await user.click(cell('Item', 1));
    await user.keyboard('{Alt>}{ArrowDown}{/Alt}');
    expect(cell('Item', 2)).toHaveValue('Rice');
    await waitFor(() => expect(cell('Item', 2)).toHaveFocus());
  });

  it('hands a unit key to the column instead of typing it', async () => {
    const onUnitKey = vi.fn();
    const columns: EntryColumn<Row>[] = [
      COLUMNS[0]!,
      { ...COLUMNS[3]!, unitKeys: ['%', '₹'], onUnitKey },
    ];
    const user = userEvent.setup();
    render(<Host columns={columns} initial={[{ ...row(), item: 'Rice' }]} />);
    await user.click(cell('Rate', 1));
    await user.keyboard('10%');
    expect(onUnitKey).toHaveBeenCalledWith(expect.objectContaining({ item: 'Rice' }), '%');
    expect(cell('Rate', 1)).toHaveValue('10');
  });
});

describe('the second review', () => {
  it('pins the columns a reader orients by, header and cells alike', () => {
    const columns: EntryColumn<Row>[] = [
      { ...COLUMNS[0]!, pin: 'start' },
      ...COLUMNS.slice(1, 4),
      { ...COLUMNS[4]!, pin: 'end' },
    ];
    render(<Host columns={columns} />);
    expect(screen.getByRole('columnheader', { name: /Item/ })).toHaveAttribute('data-pin', 'start');
    expect(screen.getByRole('columnheader', { name: 'Amount' })).toHaveAttribute('data-pin', 'end');
    expect(cell('Item', 1).closest('td')).toHaveAttribute('data-pin', 'start');
    expect(screen.getByRole('columnheader', { name: 'Rate' })).not.toHaveAttribute('data-pin');
  });

  it('names the add control without reading its keycap aloud', () => {
    render(<Host />);
    // The caption names the key already; "Add line Ctrl ↵" read the glyph.
    expect(screen.getByRole('button', { name: 'Add line' })).toBeInTheDocument();
  });
});

describe('review fixes', () => {
  it('leaves Enter alone when the cell’s own control already used it', async () => {
    // A lookup choosing its highlighted option on Enter must not also move down a row.
    const user = userEvent.setup();
    const columns: EntryColumn<Row>[] = [
      {
        key: 'item',
        label: 'Item',
        kind: 'custom',
        value: (r) => r.item,
        render: (r, context) => (
          <input
            {...context.cellProps}
            ref={context.registerRef}
            value={r.item}
            readOnly
            onKeyDown={(event) => {
              if (event.key === 'Enter') event.preventDefault();
            }}
          />
        ),
      },
      COLUMNS[1]!,
    ];
    render(<Host columns={columns} />);

    await user.click(screen.getByRole('textbox', { name: 'Item, line 1' }));
    await user.keyboard('{Enter}');
    expect(screen.getByRole('textbox', { name: 'Item, line 1' })).toHaveFocus();
    expect(lineCount()).toBe(2);
  });

  it('lands in the new line after Ctrl+Enter', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row({ item: 'Rice' })]} />);

    await user.click(cell('Billed', 1));
    await user.keyboard('{Control>}{Enter}{/Control}');
    expect(cell('Item', 2)).toHaveFocus();
  });

  it('does not trap Tab in a read-only grid whose next cell cannot take focus', async () => {
    const user = userEvent.setup();
    const columns: EntryColumn<Row>[] = [
      {
        key: 'item',
        label: 'Item',
        kind: 'custom',
        value: (r) => r.item,
        render: (r, context) => (
          <input {...context.cellProps} ref={context.registerRef} value={r.item} readOnly disabled />
        ),
      },
      COLUMNS[3]!,
    ];
    render(
      <>
        <Host initial={[row({ rate: '1' }), row({ rate: '2' })]} columns={columns} disabled />
        <button type="button">After</button>
      </>,
    );

    await user.click(screen.getByRole('textbox', { name: /^Rate, line 1/ }));
    await user.tab();
    // Native order moved on instead of the key dying on a disabled cell.
    expect(screen.getByRole('textbox', { name: /^Rate, line 1/ })).not.toHaveFocus();
  });

  it('gives a numeric cell back its stored value on Escape', async () => {
    const user = userEvent.setup();
    render(<Host initial={[row({ rate: '2450' })]} />);

    const rate = cell('Rate', 1);
    await user.click(rate);
    // `2450..5` was never storable, so the row still holds 2450.
    await user.keyboard('{End}..5');
    expect(rate).toHaveValue('2450..5');
    await user.keyboard('{Escape}');
    // The grid hands focus back on the next frame, so the canonical text returns with it.
    await waitFor(() => expect(rate).toHaveValue('2450'));
    expect(rate).not.toHaveAttribute('aria-invalid');
  });

  it('tells the caller when a cell holds text that cannot be stored, and when it stops', async () => {
    const user = userEvent.setup();
    const report = vi.fn();
    render(<Host initial={[row({ rate: '2450' })]} onCellUnstorable={report} />);

    const rate = cell('Rate', 1);
    await user.click(rate);
    await user.clear(rate);
    await user.type(rate, '2450.12345');
    expect(report).toHaveBeenLastCalledWith(expect.any(String), 'rate', 'Up to 4 decimal places.');

    await user.clear(rate);
    await user.type(rate, '2450.5');
    expect(report).toHaveBeenLastCalledWith(expect.any(String), 'rate', null);
  });

  it('does not report a decimal point typed on the way to a number', async () => {
    const user = userEvent.setup();
    const report = vi.fn();
    render(<Host initial={[row()]} onCellUnstorable={report} />);

    await user.type(cell('Rate', 1), '12.');
    expect(report).not.toHaveBeenCalled();
  });

  it('points a cell with a problem at the note under its row', () => {
    const columns: EntryColumn<Row>[] = [{ ...COLUMNS[0]!, problem: () => 'Choose an item.' }];
    render(
      <Host
        initial={[row()]}
        columns={columns}
        rowNote={() => ({ message: 'Choose an item.', tone: 'error' as const })}
      />,
    );
    expect(cell('Item', 1)).toHaveAccessibleDescription('Choose an item.');
  });
});

