/**
 * S6 through the real page: paying, checking and saving a bill the way a clerk would.
 *
 * The money rules are proven without a DOM in `sales-entry-settlement.test.ts`. What is proven
 * here is what only the screen can show: that "receive the balance" is one press, that change to
 * hand back is the thing the rail shows, that advances belong to the chosen customer, that
 * Ctrl+S saves, that a disabled Save says why, and that leaving with unsaved work asks first.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisplayConfigProvider, PermissionProvider, type SearchSelectLoader } from '@janso/ui';

vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

// Whole-page tests that type a bill key by key take about two seconds alone and more when the
// suite runs files in parallel; the default five-second budget flaked under that load.
vi.setConfig({ testTimeout: 15_000 });

import { SalesEntryPage } from '../app/components/SalesEntryPage';
import { SAMPLE_SALES_POLICY } from '../app/lib/sales-entry-policy';

const RICE = { id: '01990000-0000-7000-8000-0000000000e1', label: 'Basmati rice 25kg', meta: 'RICE-25' };
const LOCAL = { id: '01990000-0000-7000-8000-0000000000c1', label: 'Nandini Trading Company', meta: 'Karnataka' };
const OTHER = { id: '01990000-0000-7000-8000-0000000000c3', label: 'Sharma Traders', meta: 'Delhi' };

const loadItems: SearchSelectLoader = async () => ({ items: [RICE], nextCursor: null });
const loadCustomers: SearchSelectLoader = async () => ({ items: [LOCAL, OTHER], nextCursor: null });
const loadAdvances = vi.fn(async (customerId: string) =>
  customerId === LOCAL.id
    ? [{ id: 'adv-42', label: 'Advance RC/26-27/0042', available: '500' }]
    : [],
);

function mount(extra: { onSaveDraft?: (draft: unknown) => void } = {}) {
  return render(
    <DisplayConfigProvider config={{ amountPrecision: 2, digitGrouping: 'indian' }}>
      <PermissionProvider permissions={['vouchers.create']}>
        <SalesEntryPage
          policy={SAMPLE_SALES_POLICY}
          today="2026-10-28"
          loadCustomers={loadCustomers}
          loadSubjects={() => loadItems}
          resolveSubject={(id) =>
            id === RICE.id
              ? { rate: '1000', unit: 'bag', hsnSac: '1006', taxRate: '5', stockIntent: 'EXECUTE' }
              : null
          }
          resolveCustomerState={(id) => (id === LOCAL.id ? 'Karnataka' : 'Delhi')}
          loadAdvances={loadAdvances}
          companyState="Karnataka"
          canCreate
          {...extra}
        />
      </PermissionProvider>
    </DisplayConfigProvider>,
  );
}

afterEach(() => loadAdvances.mockClear());

const rail = () => screen.getByRole('complementary', { name: 'Invoice totals' });
const owing = () =>
  within(rail()).getByText('Left owing').parentElement!.querySelector('.janso-entry__total-value')!
    .textContent;

type User = ReturnType<typeof userEvent.setup>;

async function chooseCustomer(user: User, who = LOCAL) {
  await user.type(screen.getByRole('combobox', { name: /Customer/ }), who.label.slice(0, 3));
  await user.click(await screen.findByRole('option', { name: new RegExp(who.label) }));
}

/** Two bags of rice at 1,000 and 5% — a total of 2,100. */
async function billTwoBags(user: User) {
  await chooseCustomer(user);
  await user.type(screen.getByRole('combobox', { name: /^Item/ }), 'bas');
  await user.click(await screen.findByRole('option', { name: /Basmati rice 25kg/ }));
  await user.type(screen.getByRole('textbox', { name: /^Actual, line 1/ }), '2');
  await user.tab();
}

async function openPayment(user: User) {
  await user.click(within(rail()).getByRole('button', { name: 'Payment' }));
  return screen.findByRole('dialog', { name: 'Payment' });
}

describe('paying a bill', () => {
  it('owes the whole total until something is paid', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await billTwoBags(user);

    expect(owing()).toMatch(/2,100\.00/);
  });

  it('receives the balance in one press', async () => {
    // The commonest case at a counter. It is still a visible, editable amount — not a hidden
    // "paid in full" flag.
    const user = userEvent.setup({ delay: null });
    mount();
    await billTwoBags(user);

    const drawer = await openPayment(user);
    await user.click(within(drawer).getByRole('button', { name: /Receive ₹2,100\.00 by cash/ }));

    expect(within(drawer).getByRole('textbox', { name: /Cash amount/ })).toHaveValue('2,100.00');
    expect(owing()).toMatch(/0\.00/);
  });

  it('tells the counter how much change to hand back', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await billTwoBags(user);

    const drawer = await openPayment(user);
    await user.click(within(drawer).getByRole('button', { name: /by cash/ }));
    const cash = within(drawer).getByRole('textbox', { name: /Cash amount/ });
    await user.clear(cash);
    await user.type(cash, '2500');

    expect(within(rail()).getByText(/Return ₹400\.00 in change/)).toBeInTheDocument();
  });

  it('refuses to save more received by UPI than the bill, because UPI gives no change', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await billTwoBags(user);

    const drawer = await openPayment(user);
    await user.click(within(drawer).getByRole('button', { name: /by upi/i }));
    const upi = within(drawer).getByRole('textbox', { name: /UPI amount/ });
    await user.clear(upi);
    await user.type(upi, '2500');
    await user.type(within(drawer).getByRole('textbox', { name: /UTR/ }), 'UTR998877');

    expect(screen.getByRole('button', { name: /Save draft/ })).toBeDisabled();
    expect(screen.getAllByText(/only cash can be handed back as change/).length).toBeGreaterThan(0);
  });

  it('asks a card tender for its approval code and refuses a card number', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await billTwoBags(user);

    const drawer = await openPayment(user);
    await user.click(within(drawer).getByRole('button', { name: /by card/i }));
    const code = within(drawer).getByRole('textbox', { name: /Approval code/ });

    expect(within(drawer).getByText(/Card numbers are never stored/)).toBeInTheDocument();
    await user.type(code, '4111111111111111');
    expect(within(drawer).getByText(/That looks like a card number/)).toBeInTheDocument();
  });
});

describe('advances belong to the customer', () => {
  it('asks for a customer before offering any', async () => {
    const user = userEvent.setup({ delay: null });
    mount();

    const drawer = await openPayment(user);
    expect(within(drawer).getByText(/an advance belongs to the party who paid it/)).toBeInTheDocument();
    expect(loadAdvances).not.toHaveBeenCalled();
  });

  it('offers the chosen customer’s open advances and applies one', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await billTwoBags(user);

    const drawer = await openPayment(user);
    expect(loadAdvances).toHaveBeenCalledWith(LOCAL.id);
    await user.click(await within(drawer).findByRole('button', { name: 'Apply' }));
    // Apply prefills what it can settle; these tests then type their own figure.
    await user.clear(within(drawer).getByRole('textbox', { name: /Apply from Advance/ }));
    await user.type(within(drawer).getByRole('textbox', { name: /Apply from Advance/ }), '500');

    expect(owing()).toMatch(/1,600\.00/);
    expect(within(rail()).getByText('Advances applied')).toBeInTheDocument();
  });

  it('caps an advance at what it has unallocated', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await billTwoBags(user);

    const drawer = await openPayment(user);
    await user.click(await within(drawer).findByRole('button', { name: 'Apply' }));
    // Apply prefills what it can settle; these tests then type their own figure.
    await user.clear(within(drawer).getByRole('textbox', { name: /Apply from Advance/ }));
    await user.type(within(drawer).getByRole('textbox', { name: /Apply from Advance/ }), '900');

    expect(within(drawer).getByText('Only 500.00 of Advance RC/26-27/0042 is unallocated.')).toBeInTheDocument();
  });
});

describe('checking and saving', () => {
  it('previews the bill as a summary to check, and saves from there', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await billTwoBags(user);

    await user.click(screen.getByRole('button', { name: 'Preview' }));
    const review = await screen.findByRole('dialog', { name: 'Check this bill before saving' });

    expect(within(review).getByText('Nandini Trading Company')).toBeInTheDocument();
    // The same rows as the rail, and the lines themselves.
    expect(within(review).getByText('CGST')).toBeInTheDocument();
    expect(within(review).getAllByText('₹50.00')).toHaveLength(2);
    expect(within(review).getByRole('table', { name: 'Lines on this bill' })).toBeInTheDocument();
    // Not a printout: there is no renderer, and it says the figures are provisional.
    expect(within(review).getByText(/Provisional figures/)).toBeInTheDocument();

    await user.click(within(review).getByRole('button', { name: 'Save draft' }));
    expect(screen.queryByRole('dialog', { name: /Check this bill/ })).not.toBeInTheDocument();
    expect(screen.getByText(/nothing was stored/)).toBeInTheDocument();
  });

  it('saves on Ctrl+S, where a clerk’s hand already is', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await billTwoBags(user);

    await user.keyboard('{Control>}s{/Control}');
    // Not connected yet, so "saved" would be a lie: it says what happened.
    expect(screen.getByText(/nothing was stored/)).toBeInTheDocument();
    expect(screen.getByText(/1 line · checked, not stored/)).toBeInTheDocument();
  });

  it('hands the checked draft to the write path when there is one', async () => {
    const user = userEvent.setup({ delay: null });
    const save = vi.fn();
    mount({ onSaveDraft: save });
    await billTwoBags(user);

    await user.keyboard('{Control>}s{/Control}');
    expect(save).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/1 line · saved/)).toBeInTheDocument();
  });

  it('says why Save is disabled instead of only greying it', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseCustomer(user);

    expect(screen.getByRole('button', { name: /Save draft/ })).toBeDisabled();
    expect(screen.getByText(/Before saving: Add at least one line\./)).toBeInTheDocument();
  });

  it('keeps asking before leaving after a check that stored nothing', async () => {
    // The review found the guard dropped on a "save" that kept nothing — closing the tab then
    // lost the bill without a word.
    const user = userEvent.setup({ delay: null });
    mount();
    await billTwoBags(user);

    await user.keyboard('{Control>}s{/Control}');
    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
  });

  it('asks before following an in-app link away from unsaved work', async () => {
    const user = userEvent.setup({ delay: null });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    mount();
    await billTwoBags(user);

    const back = screen.getAllByRole('link').find((link) => link.getAttribute('href') === '/vouchers')!;
    const click = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
    back.dispatchEvent(click);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(click.defaultPrevented).toBe(true);
    confirm.mockRestore();
    void user;
  });

  it('asks before leaving with unsaved work, and stops asking once stored', async () => {
    const user = userEvent.setup({ delay: null });
    const listen = vi.spyOn(window, 'addEventListener');
    mount({ onSaveDraft: () => {} });

    await billTwoBags(user);
    expect(listen).toHaveBeenCalledWith('beforeunload', expect.any(Function));

    const unload = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);

    await user.keyboard('{Control>}s{/Control}');
    const after = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(after);
    expect(after.defaultPrevented).toBe(false);
    listen.mockRestore();
  });

  it('takes the reader from a problem to the line it is about', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseCustomer(user);
    // A line with an item but no quantity: its problem names "Line 1".
    await user.type(screen.getByRole('combobox', { name: /^Item/ }), 'bas');
    await user.click(await screen.findByRole('option', { name: /Basmati rice 25kg/ }));
    await user.clear(screen.getByRole('textbox', { name: /^Billed, line 1/ }));

    const goto = await within(rail()).findAllByRole('button', { name: 'Line 1' });
    await user.click(goto[0]!);

    await waitFor(() => {
      const focused = document.activeElement as HTMLElement | null;
      expect(focused?.closest('[data-entry-row]')).not.toBeNull();
    });
  });
});
