/**
 * Regression tests for the second review: the page in a real browser, and an independent read of
 * the code. Each states what used to happen.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisplayConfigProvider, PermissionProvider, type SearchSelectLoader } from '@janso/ui';

vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

vi.setConfig({ testTimeout: 15_000 });

import { SalesEntryPage } from '../app/components/SalesEntryPage';
import { SalesEntryRoute } from '../app/components/SalesEntryRoute';
import { FIRST_LINE_KEY, initialDraft } from '../app/lib/sales-entry-draft';
import { SAMPLE_SALES_POLICY } from '../app/lib/sales-entry-policy';
import type { AdvanceLoader } from '../app/components/SalesSettlementDrawer';

const RICE = { id: '01990000-0000-7000-8000-0000000000e1', label: 'Basmati rice 25kg', meta: 'RICE-25' };
const LOCAL = { id: '01990000-0000-7000-8000-0000000000c1', label: 'Nandini Trading Company', meta: 'Karnataka' };
const loadItems: SearchSelectLoader = async () => ({ items: [RICE], nextCursor: null });
const loadCustomers: SearchSelectLoader = async () => ({ items: [LOCAL], nextCursor: null });

function mount({ canCreate = true, loadAdvances }: { canCreate?: boolean; loadAdvances?: AdvanceLoader } = {}) {
  return render(
    <DisplayConfigProvider config={{ amountPrecision: 2, digitGrouping: 'indian' }}>
      <PermissionProvider permissions={['vouchers.create']}>
        <SalesEntryPage
          policy={SAMPLE_SALES_POLICY}
          today="2026-10-28"
          loadCustomers={loadCustomers}
          loadSubjects={() => loadItems}
          resolveSubject={(id) =>
            id === RICE.id ? { rate: '1000', unit: 'bag', hsnSac: '1006', taxRate: '5' } : null
          }
          resolveCustomerState={() => 'Karnataka'}
          companyState="Karnataka"
          canCreate={canCreate}
          {...(loadAdvances ? { loadAdvances } : {})}
        />
      </PermissionProvider>
    </DisplayConfigProvider>,
  );
}

type User = ReturnType<typeof userEvent.setup>;
const rail = () => screen.getByRole('complementary', { name: 'Invoice totals' });

async function chooseCustomer(user: User) {
  await user.type(screen.getByRole('combobox', { name: /Customer/ }), 'nan');
  await user.click(await screen.findByRole('option', { name: /Nandini/ }));
}
async function chooseItem(user: User) {
  await user.type(screen.getByRole('combobox', { name: /^Item/ }), 'bas');
  await user.click(await screen.findByRole('option', { name: /Basmati rice 25kg/ }));
}

afterEach(() => {
  vi.useRealTimers();
});

describe('controls that were styled only inside the designer', () => {
  it('asks whether rates include tax with a labelled checkbox, not a bare switch', () => {
    mount();
    // The switch had an accessible name and nothing visible; on a form it was an empty pill.
    expect(screen.getByRole('checkbox', { name: 'Rates include tax' })).not.toBeChecked();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
  });

  it('prints the question above a choice in the line detail', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));
    const drawer = await screen.findByRole('dialog');
    // Visible text, and the group's name comes from it.
    expect(within(drawer).getByText('Discount is')).toBeVisible();
    expect(within(drawer).getByRole('radiogroup', { name: 'Discount is' })).toBeInTheDocument();
    expect(within(drawer).getByRole('radiogroup', { name: 'What this line does to stock' })).toBeInTheDocument();
  });
});

describe('a reader without create access', () => {
  it('can open a line’s detail but not change anything in it', async () => {
    const user = userEvent.setup({ delay: null });
    mount({ canCreate: false });
    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));
    const drawer = await screen.findByRole('dialog');

    // Typing a description used to change the draft, raise the revision and arm the leave guard.
    const description = within(drawer).getByRole('textbox', { name: /Description/ });
    expect(description).toBeDisabled();
    await user.type(description, 'changed');
    expect(description).toHaveValue('');
    for (const radio of within(drawer).getAllByRole('radio')) expect(radio).toBeDisabled();
    expect(screen.getByText('Nothing entered yet.')).toBeInTheDocument();
  });

  it('cannot change whether rates include tax', () => {
    mount({ canCreate: false });
    expect(screen.getByRole('checkbox', { name: 'Rates include tax' })).toBeDisabled();
  });
});

describe('a drawer holding a figure that cannot be stored', () => {
  it('stays open, and says why, rather than keeping a different figure behind the reader’s back', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseCustomer(user);
    await chooseItem(user);
    await user.click(within(rail()).getByRole('button', { name: 'Discounts and charges' }));
    const drawer = await screen.findByRole('dialog', { name: 'Discounts and charges' });
    await user.click(within(drawer).getByRole('button', { name: 'Add a charge' }));
    const amount = within(drawer).getByRole('textbox', { name: /Freight amount/ });
    // `12..5` keeps `12` in the bill. Closing used to drop the problem and keep the 12.
    await user.type(amount, '12..5');

    await user.keyboard('{Escape}');
    expect(screen.getByRole('dialog', { name: 'Discounts and charges' })).toBeInTheDocument();
    expect(
      await screen.findByText('A figure in this panel cannot be stored. Correct or clear it before closing.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save draft/ })).toBeDisabled();

    // Corrected, it closes.
    await user.clear(amount);
    await user.type(amount, '12.5');
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });
});

describe('getting from a problem to its fix', () => {
  it('lands on the cell the problem is in, not on the item', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseCustomer(user);
    await chooseItem(user);
    // Rice is chosen and its rate resolved; only the billed quantity is missing.
    await user.click(within(rail()).getByRole('button', { name: 'Line 1' }));
    await waitFor(() =>
      expect(screen.getByRole('textbox', { name: /^Billed, line 1/ })).toHaveFocus(),
    );
  });
});

describe('the shortcuts list', () => {
  it('does not open over a drawer', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));
    await screen.findByRole('dialog');
    await user.keyboard('{Control>}/{/Control}');
    expect(screen.queryByRole('dialog', { name: 'Keyboard shortcuts' })).not.toBeInTheDocument();
  });
});

describe('the totals', () => {
  it('does not sign a discount of nothing', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseCustomer(user);
    const row = within(rail()).getByText('Discounts').closest('p')!;
    // `− 0.00` reads as something taken off.
    expect(row).not.toHaveClass('janso-entry__total--deduct');
  });
});

describe('open advances that fail to load', () => {
  it('offers the retry the message asks for', async () => {
    const user = userEvent.setup({ delay: null });
    const loadAdvances = vi
      .fn<AdvanceLoader>()
      .mockRejectedValueOnce(new Error('down'))
      .mockResolvedValue([{ id: 'a1', label: 'Advance RC/26-27/0042', available: '5000' }]);
    mount({ loadAdvances });
    await chooseCustomer(user);
    await chooseItem(user);
    await user.click(within(rail()).getByRole('button', { name: 'Payment' }));
    const drawer = await screen.findByRole('dialog', { name: 'Payment' });

    await user.click(await within(drawer).findByRole('button', { name: 'Try again' }));
    expect(await within(drawer).findByText('Advance RC/26-27/0042')).toBeInTheDocument();
    expect(loadAdvances).toHaveBeenCalledTimes(2);
  });
});

describe('the first line', () => {
  it('has the same key on every render, so a server-rendered grid hydrates with its own rows', () => {
    // A module counter gave the server `line-7` and the client `line-1`.
    expect(initialDraft(SAMPLE_SALES_POLICY, '2026-10-28').lines[0]!.key).toBe(FIRST_LINE_KEY);
    expect(initialDraft(SAMPLE_SALES_POLICY, '2026-10-28').lines[0]!.key).toBe(FIRST_LINE_KEY);
  });
});

describe('the default dates', () => {
  it('are the company’s day, not the UTC one', () => {
    // 01:30 on 1 April in India is still 31 March in UTC — the previous financial year.
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-03-31T20:00:00Z'));
    render(
      <DisplayConfigProvider config={{ timezone: 'Asia/Kolkata' }}>
        <PermissionProvider permissions={['vouchers.create']}>
          <SalesEntryRoute company="01990000-0000-7000-8000-000000000001" canCreate />
        </PermissionProvider>
      </DisplayConfigProvider>,
    );
    expect(screen.getByLabelText('Invoice date')).toHaveValue('2026-04-01');
  });
});
