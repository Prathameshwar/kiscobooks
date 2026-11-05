/**
 * The third review through the real page, on the route's own fixtures: a mixed bill, the payment
 * drawer, the line detail, billing and shipping, re-pricing, the confirmations and the preview.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisplayConfigProvider, PermissionProvider } from '@janso/ui';

vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

vi.setConfig({ testTimeout: 20_000 });

import { SalesEntryRoute } from '../app/components/SalesEntryRoute';

function mount() {
  return render(
    <DisplayConfigProvider config={{ amountPrecision: 2, digitGrouping: 'indian' }}>
      <PermissionProvider permissions={['vouchers.create', 'vouchers.edit']}>
        <SalesEntryRoute company="01990000-0000-7000-8000-000000000001" canCreate />
      </PermissionProvider>
    </DisplayConfigProvider>,
  );
}

type User = ReturnType<typeof userEvent.setup>;
const rail = () => screen.getByRole('complementary', { name: 'Invoice totals' });
const figure = (label: string) =>
  within(rail()).getByText(label).closest('p')!.querySelector('.janso-entry__total-value')!.textContent;

async function chooseCustomer(user: User, name: RegExp) {
  await user.type(screen.getByRole('combobox', { name: /Customer/ }), name.source.slice(0, 4));
  await user.click(await screen.findByRole('option', { name }));
}
async function chooseSubject(user: User, line: number, typed: string, name: RegExp) {
  const box = screen.getByRole('combobox', { name: new RegExp(`^(Item|Item or account|Account), line ${line}$`) });
  await user.type(box, typed);
  await user.click(await screen.findByRole('option', { name }));
}
async function quantity(user: User, line: number, value: string) {
  await user.type(screen.getByRole('textbox', { name: new RegExp(`^Actual, line ${line}`) }), value);
}

describe('B1 a mixed bill', () => {
  it('finds items and accounts in one lookup, and asks an account line for no quantity', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseCustomer(user, /Nandini Trading/);
    await user.click(screen.getByRole('radio', { name: 'Mixed' }));
    // No lines yet, so nothing to confirm.
    expect(screen.getByRole('columnheader', { name: /Item or account/ })).toBeInTheDocument();

    await chooseSubject(user, 1, 'rice 25', /Basmati rice 25kg/);
    await quantity(user, 1, '2');
    await user.keyboard('{Control>}{Enter}{/Control}');
    await chooseSubject(user, 2, 'services', /Sales — services/);
    await user.type(screen.getByRole('textbox', { name: /^Rate, line 2/ }), '1000');

    expect(screen.getByRole('textbox', { name: /^Billed, line 2/ })).toHaveAttribute('readonly');
    // 2 × 2,450 at 5% = 5,145.00, plus 1,000 at 18% = 1,180.00.
    expect(figure('Total')).toBe('₹6,325.00');
  });
});

describe('the fourth review on the page', () => {
  it('clears an item’s quantities when the line becomes an account', async () => {
    // Re-choosing an account over an item kept 11 and 10, and the row went on saying "1 free".
    const user = userEvent.setup({ delay: null });
    mount();
    await user.click(screen.getByRole('radio', { name: 'Mixed' }));
    await chooseSubject(user, 1, 'rice 25', /Basmati rice 25kg/);
    await quantity(user, 1, '10');
    const box = screen.getByRole('combobox', { name: /^Item or account, line 1$/ });
    await user.clear(box);
    await user.type(box, 'services');
    await user.click(await screen.findByRole('option', { name: /Sales — services/ }));
    expect(screen.getByRole('textbox', { name: /^Billed, line 1/ })).toHaveValue('');
    expect(screen.getAllByRole('row')[1]).not.toHaveAttribute('data-state', 'reward');
  });
});

describe('B6 and B7 in the line detail', () => {
  it('offers goods no "no stock effect", and clears the discount when its kind changes', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseSubject(user, 1, 'rice 25', /Basmati rice 25kg/);
    await quantity(user, 1, '2');
    await user.type(screen.getByRole('textbox', { name: /^Discount, line 1/ }), '10');

    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));
    const drawer = await screen.findByRole('dialog');
    const stock = within(drawer).getByRole('radiogroup', { name: 'What this line does to stock' });
    expect(within(stock).queryByRole('radio', { name: 'No stock effect' })).not.toBeInTheDocument();

    await user.click(within(drawer).getByRole('radio', { name: 'An amount' }));
    await user.keyboard('{Escape}');
    // 10% switched to an amount used to become ₹10 without a word.
    expect(screen.getByRole('textbox', { name: /^Discount, line 1/ })).toHaveValue('');
  });

  it('tells a service line it has no stock to move', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseSubject(user, 1, 'delivery', /Delivery and handling/);
    await user.click(screen.getByRole('button', { name: 'Line detail, line 1' }));
    const drawer = await screen.findByRole('dialog');
    expect(within(drawer).getByText(/A service moves no stock/)).toBeInTheDocument();
    expect(within(drawer).queryByRole('radiogroup', { name: 'What this line does to stock' })).not.toBeInTheDocument();
  });

  it('switches a discount cell to an amount with the currency key', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseSubject(user, 1, 'rice 25', /Basmati rice 25kg/);
    await quantity(user, 1, '1');
    const discount = screen.getByRole('textbox', { name: /^Discount, line 1/ });
    await user.type(discount, '50₹');
    expect(discount).toHaveValue('50');
    expect(discount.parentElement).toHaveTextContent('₹');
  });
});

describe('B4 the payment drawer', () => {
  it('says there when advances are more than the bill', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseCustomer(user, /Nandini Trading/);
    await chooseSubject(user, 1, 'turmeric', /Turmeric/);
    await quantity(user, 1, '1');
    await user.click(within(rail()).getByRole('button', { name: 'Payment' }));
    const drawer = await screen.findByRole('dialog', { name: 'Payment' });
    await user.click(await within(drawer).findByRole('button', { name: 'Apply' }));
    const applied = within(drawer).getByRole('textbox', { name: /Apply from Advance/ });
    // C4: prefilled with what it can settle — 96 at 5% is 100.80, rounded to 101.
    await user.tab();
    expect(applied).toHaveValue('101.00');
    await user.clear(applied);
    await user.type(applied, '2000');
    expect(within(drawer).getByRole('alert')).toHaveTextContent(/Advances of 2,000\.00 are more than the bill/);
  });
});

describe('C1 billing and shipping', () => {
  it('splits tax as IGST once the goods ship to another state', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseCustomer(user, /Nandini Trading/);
    await chooseSubject(user, 1, 'rice 25', /Basmati rice 25kg/);
    await quantity(user, 1, '1');
    expect(within(rail()).getByText('CGST')).toBeInTheDocument();

    await user.click(screen.getByRole('combobox', { name: /Ship to/ }));
    await user.click(await screen.findByRole('option', { name: /Warehouse, Hosur/ }));
    expect(within(rail()).getByText('IGST')).toBeInTheDocument();
    expect(screen.getByText('Place of supply: Tamil Nadu, from the ship-to address.')).toBeInTheDocument();
  });
});

describe('C2 changes that re-read the lines', () => {
  it('re-prices list-priced lines when the price level changes', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseSubject(user, 1, 'rice 25', /Basmati rice 25kg/);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Price level' }), 'Wholesale');
    // 5% under the retail 2,450 in the fixture's price book.
    expect(screen.getByRole('textbox', { name: /^Rate, line 1/ })).toHaveValue('2,327.5000');
  });

  it('asks before switching mode or tax-inclusive with lines entered', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseSubject(user, 1, 'rice 25', /Basmati rice 25kg/);
    await user.click(screen.getByRole('radio', { name: 'Accounts' }));
    const dialog = await screen.findByRole('dialog', { name: 'Switch this bill to accounts?' });
    expect(dialog).toHaveTextContent('Switch this bill to accounts?');
    await user.click(within(dialog).getByRole('button', { name: 'Keep as it is' }));
    expect(screen.getByRole('radio', { name: 'Items' })).toHaveAttribute('aria-checked', 'true');

    await user.click(screen.getByRole('checkbox', { name: 'Rates include tax' }));
    const second = await screen.findByRole('dialog', { name: 'Treat the rates as including tax?' });
    await user.click(within(second).getByRole('button', { name: 'Change it' }));
    expect(screen.getByRole('checkbox', { name: 'Rates include tax' })).toBeChecked();
  });
});

describe('C6 the preview', () => {
  it('lists the lines and flags an override', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseCustomer(user, /Nandini Trading/);
    await chooseSubject(user, 1, 'rice 25', /Basmati rice 25kg/);
    await quantity(user, 1, '1');
    const rate = screen.getByRole('textbox', { name: /^Rate, line 1/ });
    await user.clear(rate);
    await user.type(rate, '2400');
    await user.click(screen.getByRole('button', { name: 'Preview' }));
    const review = await screen.findByRole('dialog', { name: 'Check this bill before saving' });
    const lines = within(review).getByRole('table', { name: 'Lines on this bill' });
    expect(within(lines).getByText('Basmati rice 25kg')).toBeInTheDocument();
    expect(within(lines).getByText('Override of 2,450.00')).toBeInTheDocument();
    // The rail's rows, round-off included.
    expect(within(review).getByText('Round off')).toBeInTheDocument();
  });
});

describe('C7 the lookup in a cell', () => {
  it('does not open just because focus arrived', async () => {
    mount();
    const box = screen.getByRole('combobox', { name: /^Item, line 1/ });
    box.focus();
    await waitFor(() => expect(box).toHaveFocus());
    expect(box).toHaveAttribute('aria-expanded', 'false');
  });
});

describe('C8 credit', () => {
  it('warns under the bar when the bill takes the customer over the limit', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseCustomer(user, /Sharma Traders/);
    await chooseSubject(user, 1, 'rice 25', /Basmati rice 25kg/);
    await quantity(user, 1, '1');
    // Under the bar, by the customer, and in the rail's list of things to check.
    expect(screen.getAllByText(/over their credit limit of 50,000\.00/)).toHaveLength(2);
    expect(screen.getAllByText('Sharma Traders already has 6,500.00 overdue.')).toHaveLength(2);
  });
});
