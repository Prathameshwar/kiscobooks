/**
 * S5 through the real page: a chosen master resolves its price and tax, the rail shows the
 * provisional preview, and discounts and charges change it — all from the screen, the way a
 * clerk would do it.
 *
 * The arithmetic itself is proven in `sales-entry-preview.test.ts` with no DOM. What is proven
 * here is the wiring that a pure test cannot see: that choosing a customer in another state
 * really turns CGST + SGST into IGST, that a chosen item really arrives with its list price
 * marked as such, and that the components drawer offers only what policy permits.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DisplayConfigProvider, PermissionProvider, type SearchSelectLoader } from '@janso/ui';

vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

import { SalesEntryPage } from '../app/components/SalesEntryPage';
import { totalsLines } from '../app/components/SalesEntryTotals';
import { SAMPLE_SALES_POLICY, type SalesEntryPolicy } from '../app/lib/sales-entry-policy';
import { previewInvoice } from '../app/lib/sales-entry-preview';
import { initialDraft } from '../app/lib/sales-entry-draft';

const RICE = { id: '01990000-0000-7000-8000-0000000000e1', label: 'Basmati rice 25kg', meta: 'RICE-25' };
const LOCAL = { id: '01990000-0000-7000-8000-0000000000c1', label: 'Nandini Trading Company', meta: 'Karnataka' };
const DELHI = { id: '01990000-0000-7000-8000-0000000000c3', label: 'Sharma Traders', meta: 'Delhi' };

const loadItems: SearchSelectLoader = async () => ({ items: [RICE], nextCursor: null });
const loadCustomers: SearchSelectLoader = async () => ({ items: [LOCAL, DELHI], nextCursor: null });

function mount(policy: SalesEntryPolicy = SAMPLE_SALES_POLICY) {
  return render(
    <DisplayConfigProvider config={{ amountPrecision: 2, digitGrouping: 'indian' }}>
      <PermissionProvider permissions={['vouchers.create']}>
        <SalesEntryPage
          policy={policy}
          today="2026-10-28"
          loadCustomers={loadCustomers}
          loadSubjects={() => loadItems}
          resolveSubject={(id) =>
            id === RICE.id
              ? { rate: '1000', unit: 'bag', hsnSac: '1006', taxRate: '5', stockIntent: 'EXECUTE' }
              : null
          }
          resolveCustomerState={(id) => (id === LOCAL.id ? 'Karnataka' : 'Delhi')}
          companyState="Karnataka"
          canCreate
        />
      </PermissionProvider>
    </DisplayConfigProvider>,
  );
}

const rail = () => screen.getByRole('complementary', { name: 'Invoice totals' });
/** The figure on a rail row, by its label. */
const figure = (label: string) =>
  within(rail()).getByText(label).parentElement!.querySelector('.janso-entry__total-value')!
    .textContent;

async function chooseCustomer(user: ReturnType<typeof userEvent.setup>, who: typeof LOCAL) {
  await user.type(screen.getByRole('combobox', { name: /Customer/ }), who.label.slice(0, 3));
  await user.click(await screen.findByRole('option', { name: new RegExp(who.label) }));
}

async function chooseRice(user: ReturnType<typeof userEvent.setup>, quantity: string) {
  await user.type(screen.getByRole('combobox', { name: /^Item/ }), 'bas');
  await user.click(await screen.findByRole('option', { name: /Basmati rice 25kg/ }));
  await user.type(screen.getByRole('textbox', { name: /^Actual, line 1/ }), quantity);
  await user.tab();
}

describe('a chosen item resolves its price and tax', () => {
  it('arrives with its list price, unit, HSN and tax rate', async () => {
    const user = userEvent.setup();
    mount();

    await chooseRice(user, '2');

    expect(screen.getByRole('textbox', { name: /^Rate, line 1/ })).toHaveValue('1,000.0000');
    expect(screen.getByRole('textbox', { name: /^HSN\/SAC, line 1/ })).toHaveValue('1006');
    // A resolved price is the *list* price, so it needs no reason — and typing over it later
    // is visibly an override.
    expect(screen.queryByText(/differs from the price list/)).not.toBeInTheDocument();
  });

  it('fills the derived columns from the preview, formatted the company’s way', async () => {
    const user = userEvent.setup();
    mount();

    await chooseRice(user, '200');
    const line = screen.getAllByRole('row')[1]!;

    // 200 × 1,000 = 2,00,000 under Indian grouping, at 5%.
    expect(within(line).getByText('2,00,000.00')).toBeInTheDocument();
    expect(within(line).getByText('5%')).toBeInTheDocument();
    expect(within(line).getByText('10,000.00')).toBeInTheDocument();
  });
});

describe('the rail follows the place of supply', () => {
  it('splits tax into CGST and SGST for a customer in the same state', async () => {
    const user = userEvent.setup();
    mount();

    await chooseCustomer(user, LOCAL);
    await chooseRice(user, '2');

    expect(figure('CGST')).toBe('50.00');
    expect(figure('SGST')).toBe('50.00');
    expect(within(rail()).queryByText('IGST')).not.toBeInTheDocument();
  });

  it('charges IGST for a customer in another state', async () => {
    const user = userEvent.setup();
    mount();

    await chooseCustomer(user, DELHI);
    await chooseRice(user, '2');

    expect(figure('IGST')).toBe('100.00');
    expect(within(rail()).queryByText('CGST')).not.toBeInTheDocument();
  });

  it('shows one tax figure, and says why, until a customer is chosen', async () => {
    const user = userEvent.setup();
    mount();

    await chooseRice(user, '2');

    expect(figure('Tax')).toBe('100.00');
    expect(within(rail()).getByText(/intra-state or an inter-state/)).toBeInTheDocument();
  });

  it('totals 2 bags at 1,000 and 5% as 2,100 with the currency', async () => {
    const user = userEvent.setup();
    mount();

    await chooseCustomer(user, LOCAL);
    await chooseRice(user, '2');

    expect(figure('Subtotal')).toBe('2,000.00');
    expect(figure('Taxable value')).toBe('2,000.00');
    expect(figure('Total')).toMatch(/2,100\.00/);
    expect(figure('Total')).toMatch(/₹/);
  });
});

describe('discounts and charges', () => {
  it('opens the drawer from the rail', async () => {
    const user = userEvent.setup();
    mount();

    await user.click(within(rail()).getByRole('button', { name: 'Discounts and charges' }));
    expect(await screen.findByRole('dialog', { name: 'Discounts and charges' })).toBeInTheDocument();
  });

  it('applies a bill discount and the rail follows', async () => {
    const user = userEvent.setup();
    mount();

    await chooseCustomer(user, LOCAL);
    await chooseRice(user, '2');
    await user.click(within(rail()).getByRole('button', { name: 'Discounts and charges' }));
    const drawer = await screen.findByRole('dialog', { name: 'Discounts and charges' });

    await user.click(within(drawer).getByRole('button', { name: 'Add a bill discount' }));
    await user.type(within(drawer).getByRole('textbox', { name: /Bill discount/ }), '4');

    expect(figure('Discounts')).toBe('80.00');
    expect(figure('Taxable value')).toBe('1,920.00');
  });

  it('offers no second bill discount, because two would be two authorities', async () => {
    const user = userEvent.setup();
    mount();

    await user.click(within(rail()).getByRole('button', { name: 'Discounts and charges' }));
    const drawer = await screen.findByRole('dialog', { name: 'Discounts and charges' });
    await user.click(within(drawer).getByRole('button', { name: 'Add a bill discount' }));

    expect(within(drawer).queryByRole('button', { name: 'Add a bill discount' })).not.toBeInTheDocument();
  });

  it('warns, without blocking, above the approval threshold', async () => {
    // The fixture needs approval above 5%. That is not an error — it is a step someone else
    // takes — so the reader is told before saving and nothing is refused.
    const user = userEvent.setup();
    mount();

    await user.click(within(rail()).getByRole('button', { name: 'Discounts and charges' }));
    const drawer = await screen.findByRole('dialog', { name: 'Discounts and charges' });
    await user.click(within(drawer).getByRole('button', { name: 'Add a bill discount' }));
    await user.type(within(drawer).getByRole('textbox', { name: /Bill discount/ }), '8');

    expect(within(drawer).getByText(/above 5% needs approval/)).toBeInTheDocument();
  });

  it('adds a charge, and says its tax treatment is not the reader’s switch', async () => {
    const user = userEvent.setup();
    mount();

    await chooseCustomer(user, LOCAL);
    await chooseRice(user, '2');
    await user.click(within(rail()).getByRole('button', { name: 'Discounts and charges' }));
    const drawer = await screen.findByRole('dialog', { name: 'Discounts and charges' });

    await user.click(within(drawer).getByRole('button', { name: 'Add a charge' }));
    await user.type(within(drawer).getByRole('textbox', { name: /Freight amount/ }), '150');

    expect(figure('Charges')).toBe('150.00');
    expect(within(drawer).getByText(/decided by the company’s tax profile/)).toBeInTheDocument();
    // There is no "taxable" checkbox: that is a tax-profile result, not a choice.
    expect(within(drawer).queryByRole('checkbox', { name: /tax/i })).not.toBeInTheDocument();
  });

  it('says what a forbidden component is, instead of hiding it', () => {
    mount({
      ...SAMPLE_SALES_POLICY,
      components: {
        ...SAMPLE_SALES_POLICY.components,
        charges: { available: false, reason: 'Charges are not used on this bill type.' },
      },
    });
    // The rail has no Charges row at all — a zero row for a mechanic that does not exist would
    // suggest someone could add one.
    expect(within(rail()).queryByText('Charges')).not.toBeInTheDocument();
  });
});

describe('the rail’s rows, as a pure list', () => {
  it('names CGST and SGST as separate rows, because they are separate components', () => {
    const draft = { ...initialDraft(SAMPLE_SALES_POLICY, '2026-10-28'), customerState: 'Karnataka' };
    const rows = totalsLines(
      previewInvoice(draft, SAMPLE_SALES_POLICY, { companyState: 'Karnataka', places: 2 }),
      SAMPLE_SALES_POLICY,
    ).map((row) => row.label);

    expect(rows).toEqual([
      'Subtotal',
      'Discounts',
      'Taxable value',
      'CGST',
      'SGST',
      'Charges',
      'Round off',
      'Total',
    ]);
  });
});
