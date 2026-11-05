/**
 * The sales line grid: the platform's rules, in the grid.
 *
 * `entry-grid.test.tsx` already proves the keyboard and the cell types. What is tested here is
 * only what is *about a sales bill* — the rules the form is not allowed to re-decide:
 *
 *  - the column set is the mode's and the policy's, not the component's;
 *  - every figure the service owns is read-only and shown as an em dash until it answers;
 *  - a reward line (actual above billed) is marked as deliberate and demands a reason;
 *  - a rate override is visible, and is only an override once a price was resolved;
 *  - duplicating a line does **not** carry its approved reasons across.
 */
import { describe, expect, it, vi } from 'vitest';
import { useReducer } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisplayConfigProvider, PermissionProvider, type SearchSelectLoader } from '@janso/ui';

vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

import { SalesLineGrid } from '../app/components/SalesLineGrid';
import {
  draftProblems,
  initialDraft,
  reduceDraft,
  type DraftLine,
} from '../app/lib/sales-entry-draft';
import { freeQuantity, isRewardLine, rateProvenance } from '../app/lib/sales-entry-columns';
import { SAMPLE_SALES_POLICY, type SalesEntryPolicy } from '../app/lib/sales-entry-policy';

const TODAY = '2026-10-28';

const loadSubjects: SearchSelectLoader = async () => ({
  items: [
    { id: '01990000-0000-7000-8000-0000000000e1', label: 'Basmati rice 25kg', meta: 'RICE-25' },
    { id: '01990000-0000-7000-8000-0000000000e3', label: 'Sunflower oil 1L', meta: 'OIL-1L' },
  ],
  nextCursor: null,
});

function Host({
  policy = SAMPLE_SALES_POLICY,
  seed,
  canEdit = true,
}: {
  policy?: SalesEntryPolicy;
  seed?: (draft: ReturnType<typeof initialDraft>) => ReturnType<typeof initialDraft>;
  canEdit?: boolean;
}) {
  const [draft, dispatch] = useReducer(reduceDraft, undefined, () => {
    const start = initialDraft(policy, TODAY);
    return seed ? seed(start) : start;
  });
  return (
    <DisplayConfigProvider>
      <PermissionProvider permissions={['vouchers.create']}>
        <SalesLineGrid
          draft={draft}
          policy={policy}
          problems={draftProblems(draft, policy)}
          dispatch={dispatch}
          loadSubjects={loadSubjects}
          canEdit={canEdit}
        />
      </PermissionProvider>
    </DisplayConfigProvider>
  );
}

/** A line with enough on it to be real. */
const patch = (over: Partial<DraftLine> = {}) => ({
  subjectId: '01990000-0000-7000-8000-0000000000e1',
  subjectLabel: 'Basmati rice 25kg',
  actualQuantity: '10',
  billedQuantity: '10',
  unit: 'nos',
  rate: '100',
  ...over,
});

const seedLine = (over: Partial<DraftLine> = {}) =>
  (draft: ReturnType<typeof initialDraft>) =>
    reduceDraft(draft, { type: 'line', key: draft.lines[0]!.key, patch: patch(over) });

const cell = (column: string, line: number) =>
  screen.getByRole('textbox', { name: new RegExp(`^${column}, line ${line}`) });

describe('the columns are the mode’s and the policy’s', () => {
  it('shows an item lookup, two quantities and the derived money columns', () => {
    render(<Host />);

    expect(screen.getByRole('columnheader', { name: 'Item' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Actual' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Billed' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Taxable value' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Tax' })).toBeInTheDocument();
  });

  it('gives the subject a lookup, not a text box', async () => {
    const user = userEvent.setup();
    render(<Host />);

    const lookup = screen.getByRole('combobox', { name: /Item/ });
    await user.type(lookup, 'bas');

    expect(await screen.findByRole('option', { name: /Basmati rice 25kg/ })).toBeInTheDocument();
  });

  it('records the chosen master on the line', async () => {
    const user = userEvent.setup();
    render(<Host />);

    await user.type(screen.getByRole('combobox', { name: /Item/ }), 'oil');
    await user.click(await screen.findByRole('option', { name: /Sunflower oil 1L/ }));

    expect(screen.getByRole('combobox', { name: /Item/ })).toHaveValue('Sunflower oil 1L');
  });

  it('never offers an input for a figure the service owns', () => {
    // Tax is resolved, not entered, and a display preference cannot disable it. So there is no
    // box to wonder about — the cells are read-only text.
    render(<Host seed={seedLine()} />);

    for (const column of ['Taxable value', 'Tax %', 'Tax', 'Amount']) {
      expect(screen.queryByRole('textbox', { name: new RegExp(`^${column},`) })).not.toBeInTheDocument();
    }
  });

  it('shows an unanswered figure as an em dash, never as zero', () => {
    render(<Host seed={seedLine()} />);
    const line = screen.getAllByRole('row')[1]!;

    expect(within(line).getAllByText('—').length).toBeGreaterThan(2);
    expect(within(line).queryByText('0.00')).not.toBeInTheDocument();
  });

  it('drops the quantity columns and swaps the lookup in accounts mode', () => {
    render(<Host seed={(draft) => reduceDraft(draft, { type: 'mode', mode: 'ACCOUNTS' })} />);

    expect(screen.getByRole('columnheader', { name: 'Account' })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Actual' })).not.toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Unit' })).not.toBeInTheDocument();
    // The money columns stay: an accounts-only bill still has a rate and a tax treatment.
    expect(screen.getByRole('columnheader', { name: 'Rate' })).toBeInTheDocument();
  });

  it('omits the discount column when the policy forbids a line discount', () => {
    render(
      <Host
        policy={{
          ...SAMPLE_SALES_POLICY,
          components: {
            ...SAMPLE_SALES_POLICY.components,
            lineDiscount: { available: false, reason: 'Off for this company.' },
          },
        }}
      />,
    );
    expect(screen.queryByRole('columnheader', { name: 'Discount' })).not.toBeInTheDocument();
  });
});

describe('a line that carries free units', () => {
  it('is marked as deliberate rather than as wrong', () => {
    // Free units are a recorded term. A row that looks like an error every time someone gives
    // a sample away trains people to ignore the marker that matters.
    render(<Host seed={seedLine({ actualQuantity: '11', billedQuantity: '10', quantityReason: 'Manual bonus quantity' })} />);

    expect(screen.getAllByRole('row')[1]).toHaveAttribute('data-state', 'reward');
  });

  it('is invalid until it says why the quantities differ', () => {
    // A bare difference between actual and billed is not evidence of an authorised bonus.
    render(<Host seed={seedLine({ actualQuantity: '11', billedQuantity: '10' })} />);

    expect(screen.getAllByRole('row')[1]).toHaveAttribute('data-state', 'invalid');
    expect(screen.getByText('Say why the actual and billed quantities differ.')).toBeInTheDocument();
  });

  it('derives the free quantity rather than holding a third one', () => {
    // 10+1 is actual 11, billed 10, free 1 — and "free" is never an editable third quantity or
    // a second stock movement.
    const line = { ...patch({ actualQuantity: '11', billedQuantity: '10' }) } as DraftLine;
    expect(isRewardLine(line)).toBe(true);
    expect(freeQuantity(line)).toBe('1');

    expect(isRewardLine({ ...line, actualQuantity: '10' } as DraftLine)).toBe(false);
    expect(freeQuantity({ ...line, actualQuantity: '10' } as DraftLine)).toBe('');
  });

  it('explains the arithmetic in the drawer, where it can be read', async () => {
    const user = userEvent.setup();
    render(<Host seed={seedLine({ actualQuantity: '11', billedQuantity: '10' })} />);

    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));

    // The rule the calculation contract spells out: the bonus must not deduct from the
    // already-normalised amount, and the cost covers all eleven.
    expect(await screen.findByText(/10 charged, 1 free/)).toBeInTheDocument();
    expect(screen.getByText(/do not deduct from it either/)).toBeInTheDocument();
  });

  it('offers only the reasons the policy allows', async () => {
    const user = userEvent.setup();
    render(<Host seed={seedLine({ actualQuantity: '11', billedQuantity: '10' })} />);

    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));
    const reason = await screen.findByRole('combobox', { name: /Why the quantities differ/ });

    expect(within(reason).getByRole('option', { name: 'Manual bonus quantity' })).toBeInTheDocument();
    expect(within(reason).queryByRole('option', { name: 'Automatic scheme' })).not.toBeInTheDocument();
  });
});

describe('where a rate came from', () => {
  it('says nothing when nothing resolved a price', () => {
    // "Override" would claim a departure from a figure that never existed.
    const line = { ...patch(), resolvedRate: '', rateSource: 'MANUAL' } as DraftLine;
    expect(rateProvenance(line)).toBeNull();
  });

  it('names the source, and warns once a rate departs from it', () => {
    const listed = { ...patch(), resolvedRate: '100', rateSource: 'PRICE_LEVEL' } as DraftLine;
    expect(rateProvenance(listed)).toEqual({ label: 'List', tone: 'neutral' });

    const cut = { ...patch({ rate: '85' }), resolvedRate: '100', rateSource: 'MANUAL' } as DraftLine;
    expect(rateProvenance(cut)).toEqual({ label: 'Override', tone: 'warn' });
  });

  it('asks for the reason in the drawer, not in a grid cell', async () => {
    // A reason typed into a narrow cell is a reason nobody reads.
    const user = userEvent.setup();
    render(<Host seed={seedLine({ rate: '85', resolvedRate: '100', rateSource: 'MANUAL' })} />);

    expect(screen.getAllByRole('row')[1]).toHaveAttribute('data-state', 'invalid');
    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));

    const reason = await screen.findByRole('textbox', {
      name: /Why this rate differs from the price list/,
    });
    expect(reason).toBeInTheDocument();

    // The list price is shown as the field's hint once the error it replaces is answered —
    // `TextField` shows one or the other, and the error is the more urgent of the two.
    await user.type(reason, 'Agreed volume price');
    expect(screen.getByText(/The list price is 100/)).toBeInTheDocument();
  });

  it('shows a rate at four places, where a total shows two', () => {
    // A unit rate routinely carries more precision than the figure it rolls up into.
    render(<Host seed={seedLine({ rate: '142.5' })} />);
    expect(cell('Rate', 1)).toHaveValue('142.5000');
  });
});

describe('row actions', () => {
  it('duplicates a line without carrying its approved reasons', async () => {
    /*
     * The one that matters: a quantity-difference reason and a rate-override reason justify
     * *that* line. Carrying them onto a copy would let an approved exception be multiplied by
     * pressing Ctrl+D.
     */
    const user = userEvent.setup();
    render(
      <Host
        seed={seedLine({
          actualQuantity: '11',
          billedQuantity: '10',
          quantityReason: 'Manual bonus quantity',
          // Within the 10% approval threshold, so the row's only mark is the reward.
          rate: '95',
          resolvedRate: '100',
          rateSource: 'MANUAL',
          rateReason: 'Agreed volume price',
        })}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Duplicate line 1' }));

    expect(screen.getAllByRole('row')[1]).toHaveAttribute('data-state', 'reward');
    // The copy is incomplete on purpose, and says which field it is missing.
    expect(screen.getAllByRole('row')[3]).toHaveAttribute('data-state', 'invalid');
    expect(screen.getByText('Say why the actual and billed quantities differ.')).toBeInTheDocument();
  });

  it('reorders without re-pricing, because row order is presentation', async () => {
    const user = userEvent.setup();
    render(
      <Host
        seed={(draft) => {
          const one = reduceDraft(draft, {
            type: 'line',
            key: draft.lines[0]!.key,
            patch: patch({ subjectLabel: 'First', rate: '100' }),
          });
          const two = reduceDraft(one, { type: 'addLine' });
          return reduceDraft(two, {
            type: 'line',
            key: two.lines[1]!.key,
            patch: patch({ subjectLabel: 'Second', rate: '200' }),
          });
        }}
      />,
    );

    expect(cell('Rate', 1)).toHaveValue('100.0000');
    await user.click(cell('Rate', 2));
    await user.keyboard('{Alt>}{ArrowUp}{/Alt}');

    /*
     * The calculation contract: document row order alone cannot change a result. The moved
     * cell is the focused one, so it shows canonical `200` rather than the grouped `200.0000`
     * — the display rule, not a lost figure.
     */
    expect(cell('Rate', 1)).toHaveValue('200');
    expect(cell('Rate', 2)).toHaveValue('100.0000');
  });

  it('opens the drawer for the long tail and closes again', async () => {
    const user = userEvent.setup();
    render(<Host seed={seedLine()} />);

    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));
    const drawer = await screen.findByRole('dialog', { name: /Basmati rice 25kg/ });

    // Scoped to the drawer: HSN/SAC is *both* a column and a drawer field, which is the point —
    // the column is for the lines that need it, the drawer for the ones that need more room.
    expect(within(drawer).getByRole('textbox', { name: /HSN\/SAC/ })).toBeInTheDocument();
    expect(
      within(drawer).getByRole('radiogroup', { name: /What this line does to stock/ }),
    ).toBeInTheDocument();

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('stock intent', () => {
  it('says what each choice means instead of leaving a reader to guess', async () => {
    const user = userEvent.setup();
    render(<Host seed={seedLine()} />);

    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));
    await user.click(await screen.findByRole('radio', { name: 'Already dispatched' }));

    // Goods billed against a delivery note must not move a second time.
    expect(screen.getByText(/does not dispatch anything again/)).toBeInTheDocument();

    await user.click(screen.getByRole('radio', { name: 'Dispatch later' }));
    expect(screen.getByText(/Nothing is dispatched by this bill/)).toBeInTheDocument();
  });

  it('is absent on an accounts-only line, which has no stock to affect', async () => {
    const user = userEvent.setup();
    render(
      <Host
        seed={(draft) =>
          reduceDraft(reduceDraft(draft, { type: 'mode', mode: 'ACCOUNTS' }), {
            type: 'line',
            key: draft.lines[0]!.key,
            patch: patch(),
          })
        }
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));
    await screen.findByRole('dialog');

    expect(screen.queryByRole('radiogroup', { name: /stock/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /Warehouse/ })).not.toBeInTheDocument();
  });
});

describe('read only', () => {
  it('takes the editing controls away and says why', () => {
    render(<Host seed={seedLine()} canEdit={false} />);

    expect(screen.queryByRole('button', { name: /Add line/ })).not.toBeInTheDocument();
    expect(screen.getByText('You can read this bill but not change it.')).toBeInTheDocument();
    // The drawer stays reachable: reading a line's detail is a legitimate thing to do.
    expect(screen.getByRole('button', { name: 'Line detail, line 1' })).toBeInTheDocument();
  });
});
