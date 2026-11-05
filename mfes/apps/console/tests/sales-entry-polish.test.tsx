/**
 * S7 through the real page: arriving, being told what is wrong only once there is something to
 * be wrong about, getting from a problem to its fix, and finding the keys.
 */
import { describe, expect, it, vi } from 'vitest';
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

const OIL = { id: '01990000-0000-7000-8000-0000000000e3', label: 'Sunflower oil 1L', meta: 'OIL-1L' };
const loadItems: SearchSelectLoader = async ({ q }) => ({
  items: [RICE, OIL].filter((item) => item.label.toLowerCase().includes((q ?? '').toLowerCase())),
  nextCursor: null,
});
const loadCustomers: SearchSelectLoader = async () => ({ items: [LOCAL], nextCursor: null });

// Requires a UTR, so a UPI tender leaves a payment problem whose fix is the Payment drawer.
const STRICT = { ...SAMPLE_SALES_POLICY, settlement: { ...SAMPLE_SALES_POLICY.settlement, referenceRequired: ['UPI' as const] } };

function mount(canCreate = true, policy = SAMPLE_SALES_POLICY) {
  return render(
    <DisplayConfigProvider config={{ amountPrecision: 2, digitGrouping: 'indian' }}>
      <PermissionProvider permissions={['vouchers.create']}>
        <SalesEntryPage
          policy={policy}
          today="2026-10-28"
          loadCustomers={loadCustomers}
          loadSubjects={() => loadItems}
          resolveSubject={(id) =>
            id === RICE.id ? { rate: '1000', unit: 'bag', hsnSac: '1006', taxRate: '5' } : null
          }
          resolveCustomerState={() => 'Karnataka'}
          companyState="Karnataka"
          canCreate={canCreate}
        />
      </PermissionProvider>
    </DisplayConfigProvider>,
  );
}

type User = ReturnType<typeof userEvent.setup>;
const rail = () => screen.getByRole('complementary', { name: 'Invoice totals' });

async function chooseItem(user: User) {
  await user.type(screen.getByRole('combobox', { name: /^Item/ }), 'bas');
  await user.click(await screen.findByRole('option', { name: /Basmati rice 25kg/ }));
}

describe('arriving', () => {
  it('starts at the customer', async () => {
    mount();
    await waitFor(() => expect(screen.getByRole('combobox', { name: /Customer/ })).toHaveFocus());
  });

  it('says nothing is wrong before anything has been entered', () => {
    // A form that opens scolding someone for not having started is a form people resent.
    mount();
    expect(within(rail()).queryByText(/to fix/)).not.toBeInTheDocument();
    expect(screen.queryByText('Choose the customer this is billed to.')).not.toBeInTheDocument();
    // Save is still unavailable — only the shouting waits.
    expect(screen.getByRole('button', { name: /Save draft/ })).toBeDisabled();
  });

  it('says how entry works over the empty grid, and stops once a line exists', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    expect(screen.getByText(/Find an item to start/)).toBeInTheDocument();

    await chooseItem(user);
    expect(screen.queryByText(/Find an item to start/)).not.toBeInTheDocument();
  });
});

describe('from a problem to its fix', () => {
  it('takes "Before saving" to the field it is about', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseItem(user);
    await user.type(screen.getByRole('textbox', { name: /^Actual, line 1/ }), '2');

    const bar = screen.getByText(/Before saving:/);
    await user.click(within(bar).getByRole('button', { name: 'Customer' }));
    expect(screen.getByRole('combobox', { name: /Customer/ })).toHaveFocus();
  });

  it('opens the payment drawer for a payment problem', async () => {
    const user = userEvent.setup({ delay: null });
    mount(true, STRICT);
    await chooseItem(user);
    await user.click(within(rail()).getByRole('button', { name: 'Payment' }));
    const drawer = await screen.findByRole('dialog', { name: 'Payment' });
    await user.click(within(drawer).getByRole('button', { name: /UPI$/ }));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Payment' })).not.toBeInTheDocument());

    // The problem in the rail, not the rail's own Payment button: the one that names its fix.
    const problem = within(rail()).getByText('Enter the UTR.').closest('li')!;
    await user.click(within(problem as HTMLElement).getByRole('button', { name: 'Payment' }));
    expect(await screen.findByRole('dialog', { name: 'Payment' })).toBeInTheDocument();
  });

  it('marks credit days on the field itself', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await user.type(screen.getByRole('textbox', { name: /Credit days/ }), '1.5');
    expect(screen.getByRole('textbox', { name: /Credit days/ })).toHaveAccessibleDescription(
      /whole number of days/,
    );
  });
});

describe('the grid says what its figures are', () => {
  it('shows the percent sign on a percentage discount', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseItem(user);
    const discount = screen.getByRole('textbox', { name: 'Discount, line 1 in %' });
    expect(discount.parentElement).toHaveTextContent('%');
  });

  it('marks a rate typed over the list price as an override', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseItem(user);
    const rate = screen.getByRole('textbox', { name: /^Rate, line 1/ });
    expect(rate.parentElement).toHaveTextContent('List');

    await user.clear(rate);
    await user.type(rate, '950');
    expect(rate.parentElement).toHaveTextContent('Override');
  });
});

describe('keys', () => {
  it('lists every key on Ctrl+/', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await user.keyboard('{Control>}/{/Control}');

    const dialog = await screen.findByRole('dialog', { name: 'Keyboard shortcuts' });
    expect(within(dialog).getByText('Ctrl S')).toBeInTheDocument();
    expect(within(dialog).getByText('Alt Enter')).toBeInTheDocument();
  });

  it('lists them from a button too, for a reader who does not know the key', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await user.click(screen.getByRole('button', { name: /^Keys/ }));
    expect(await screen.findByRole('dialog', { name: 'Keyboard shortcuts' })).toBeInTheDocument();
  });

  it('announces checking without claiming storage when no writer is connected', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await user.type(screen.getByRole('combobox', { name: /Customer/ }), 'Nan');
    await user.click(await screen.findByRole('option', { name: /Nandini/ }));
    await chooseItem(user);
    await user.type(screen.getByRole('textbox', { name: /^Actual, line 1/ }), '2');
    await user.keyboard('{Control>}s{/Control}');

    expect(await screen.findByText('Checked. Nothing was stored; this form is not connected yet.')).toHaveAttribute('role', 'status');
  });
});

describe('review fixes on the page', () => {
  it('refuses to save while a cell shows a figure the bill does not hold', async () => {
    // `2450.12345` stayed in the cell while the draft kept 2,450, and Ctrl+S saved 2,450.
    const user = userEvent.setup({ delay: null });
    mount();
    await user.type(screen.getByRole('combobox', { name: /Customer/ }), 'Nan');
    await user.click(await screen.findByRole('option', { name: /Nandini/ }));
    await chooseItem(user);
    await user.type(screen.getByRole('textbox', { name: /^Actual, line 1/ }), '2');
    const rate = screen.getByRole('textbox', { name: /^Rate, line 1/ });
    await user.click(rate);
    await user.keyboard('{End}.12345');
    await user.tab();

    expect(screen.getByRole('button', { name: /Save draft/ })).toBeDisabled();
    expect(screen.getAllByText('Up to 4 decimal places.').length).toBeGreaterThan(0);
  });

  it('opens the line’s detail from a missing-reason problem', async () => {
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseItem(user);
    await user.type(screen.getByRole('textbox', { name: /^Actual, line 1/ }), '11');
    const billed = screen.getByRole('textbox', { name: /^Billed, line 1/ });
    await user.clear(billed);
    await user.type(billed, '10');

    const problem = within(rail()).getByText('Say why the actual and billed quantities differ.').closest('li')!;
    await user.click(within(problem as HTMLElement).getByRole('button', { name: 'Line 1' }));
    const drawer = await screen.findByRole('dialog', { name: /Line 1/ });
    expect(within(drawer).getByRole('combobox', { name: /Why the quantities differ/ })).toBeInTheDocument();
  });

  it('names each row’s item lookup by its line', async () => {
    mount();
    expect(screen.getByRole('combobox', { name: 'Item, line 1' })).toBeInTheDocument();
  });

  it('makes the document bar read-only for a reader who may not raise a bill', () => {
    mount(false);
    expect(screen.getByLabelText(/Invoice date/)).toBeDisabled();
    expect(screen.getByRole('combobox', { name: /Customer/ })).toBeDisabled();
  });
});

describe('changing a line’s item', () => {
  it('drops what the previous item supplied', async () => {
    // Rice's list price, "List" badge and HSN stayed on a line re-pointed at an unpriced item.
    const user = userEvent.setup({ delay: null });
    mount();
    await chooseItem(user);
    const rate = () => screen.getByRole('textbox', { name: /^Rate, line 1/ });
    expect(rate().parentElement).toHaveTextContent('List');

    const lookup = screen.getByRole('combobox', { name: 'Item, line 1' });
    await user.clear(lookup);
    await user.type(lookup, 'sun');
    await user.click(await screen.findByRole('option', { name: /Sunflower oil/ }));

    expect(rate()).toHaveValue('');
    expect(rate().parentElement).not.toHaveTextContent('List');
  });
});

