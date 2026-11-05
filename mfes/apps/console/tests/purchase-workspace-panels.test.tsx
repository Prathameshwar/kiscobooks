import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { PurchaseWorkspace } from '../app/components/PurchaseWorkspace';
import { PurchaseDetailsPanel } from '../app/components/PurchaseDetailsPanel';
import { PURCHASE_DEMO_POLICY as policy, purchaseExample } from '../app/lib/purchase-workspace';
import { purchaseScenario } from '../app/lib/purchase-workspace-scenarios';
import { BEFORE_COMPANY_CHANGE } from '../app/lib/use-unsaved-changes';
import { checkPurchaseAttachment } from '../app/lib/purchase-workspace-attachments';

vi.mock('../app/lib/purchase-workspace-attachments', async importOriginal => {
  const actual = await importOriginal<typeof import('../app/lib/purchase-workspace-attachments')>();
  return { ...actual, checkPurchaseAttachment: vi.fn(actual.checkPurchaseAttachment) };
});
const today = '2026-10-31';
vi.setConfig({ testTimeout: 25_000 });
beforeEach(() => {
  URL.createObjectURL = vi.fn(() => 'blob:purchase-test');
  URL.revokeObjectURL = vi.fn();
});
function mount(scenario = 'goods', canCreate = true) {
  return render(<DisplayConfigProvider config={{ currency: 'INR', currencySymbol: '₹' }}><PurchaseWorkspace today={today} canCreate={canCreate} initialDraft={purchaseScenario(scenario, today)} /></DisplayConfigProvider>);
}
const panel = (name: string) => screen.getByRole('dialog', { name });
async function open(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(screen.getByRole('button', { name: new RegExp('^' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }));
  return panel(name);
}

describe('Purchase progressive detail panels', () => {
  it('applies a charge edit once, updates its bounded tax example and returns focus', async () => {
    const user = userEvent.setup(); mount();
    const dialog = await open(user, 'Discounts & charges');
    const amount = within(dialog).getByLabelText('Component 1 value');
    await user.clear(amount); await user.type(amount, '200');
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getAllByText('₹5,841.00')).toHaveLength(2);
    expect(screen.getByRole('button', { name: /^Discounts & charges/ })).toHaveFocus();
    expect(screen.getByText('₹4,841.00')).toBeVisible();
  });
  it('keeps bill state intact on dirty cancel, restores panel input and blocks company change while dirty', async () => {
    const user = userEvent.setup(); mount();
    let dialog = await open(user, 'Discounts & charges');
    const amount = within(dialog).getByLabelText('Component 1 value');
    await user.clear(amount); await user.type(amount, '200');
    const change = new Event(BEFORE_COMPANY_CHANGE, { cancelable: true }); window.dispatchEvent(change);
    expect(change.defaultPrevented).toBe(true);
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.getByRole('dialog', { name: 'Discard panel changes?' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Keep editing' }));
    dialog = panel('Discounts & charges'); expect(within(dialog).getByLabelText('Component 1 value')).toHaveValue('200.00');
    await user.keyboard('{Escape}');
    await user.click(screen.getByRole('button', { name: 'Discard panel changes' }));
    expect(screen.getAllByText('₹5,723.00')).toHaveLength(2);
    dialog = await open(user, 'Discounts & charges');
    expect(within(dialog).getByLabelText('Component 1 value')).toHaveValue('100.00');
  });
  it('adds and validates a document component without guessing a tax treatment', async () => {
    const user = userEvent.setup(); mount(); const dialog = await open(user, 'Discounts & charges');
    await user.click(within(dialog).getByRole('button', { name: 'Add charge' }));
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(within(dialog).getByText('Check these details')).toBeVisible();
    await user.type(within(dialog).getByLabelText('Component 2 name'), 'Packing');
    const amount = within(dialog).getByLabelText('Component 2 value');
    await user.clear(amount); await user.type(amount, '50');
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByText('₹5,723.00')).not.toBeInTheDocument();
    const tax = await open(user, 'Tax details');
    expect(within(tax).getByText('Calculation evidence unavailable')).toBeVisible();
  });
  it('allows removing a component whose numeric text cannot be stored', async () => {
    const user = userEvent.setup(); mount(); const dialog = await open(user, 'Discounts & charges');
    const amount = within(dialog).getByLabelText('Component 1 value');
    await user.clear(amount); await user.type(amount, '999999999999999999999');
    await user.click(within(dialog).getByRole('button', { name: 'Remove component 1' }));
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it('keeps an added discount where it was added: the order is the calculation order and can be moved', async () => {
    const user = userEvent.setup(); mount(); const dialog = await open(user, 'Discounts & charges');
    await user.click(within(dialog).getByRole('button', { name: 'Add document discount' }));
    const legends = () => [...dialog.querySelectorAll('legend')].map(element => element.textContent);
    expect(legends()).toEqual(['Charge 1', 'Discount 2']);
    expect(within(dialog).getByLabelText('Component 1 name')).toHaveValue('Freight');
    await user.click(within(dialog).getByRole('button', { name: 'Move component 2 up' }));
    expect(legends()).toEqual(['Discount 1', 'Charge 2']);
    expect(within(dialog).getByLabelText('Component 2 name')).toHaveValue('Freight');
  });
  it('renders read-only tax rates and separates recipient liability', async () => {
    const user = userEvent.setup(); mount('recipient');
    expect(screen.getByText('Recipient tax liability')).toBeVisible();
    const dialog = await open(user, 'Tax details');
    expect(within(dialog).getByText(/Recipient liability · excluded/)).toBeVisible();
    expect(within(dialog).queryByRole('textbox')).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Done' }));
    expect(screen.getByRole('cell', { name: 'Net amount, line 1: ₹1,000.00' })).toBeVisible();
    expect(within(screen.getByRole('group', { name: 'Purchase actions' })).getByText('₹1,000.00')).toBeVisible();
  });
  it('shows a partial receipt residual and refuses an over-claim before Apply', async () => {
    const user = userEvent.setup(); mount('receipt'); const dialog = await open(user, 'Goods receipt');
    expect(within(dialog).getByText(/Existing receipts will not be received again/)).toBeVisible();
    expect(within(dialog).getByText(/Remaining after all selected slices: 4.0000/)).toBeVisible();
    const quantity = within(dialog).getByLabelText('Matched quantity for line 1');
    await user.clear(quantity); await user.type(quantity, '11');
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(within(dialog).getAllByText(/exceed the remaining quantity/).length).toBeGreaterThan(0);
    expect(screen.getByRole('dialog', { name: 'Goods receipt' })).toBeVisible();
  });
  it('preserves inactive receipt references when deferring receipt', async () => {
    const user = userEvent.setup(); mount('receipt'); let dialog = await open(user, 'Goods receipt');
    await user.selectOptions(within(dialog).getByLabelText('Goods receipt intent'), 'DEFERRED');
    expect(within(dialog).getByText(/Previous receipt selections are retained/)).toBeVisible();
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    dialog = await open(user, 'Goods receipt');
    await user.selectOptions(within(dialog).getByLabelText('Goods receipt intent'), 'REFERENCE');
    expect(within(dialog).getByLabelText('Matched quantity for line 1')).toHaveValue('6.0000');
  });
  it('validates required tracking and applies batches, expiry and unique serials', async () => {
    const user = userEvent.setup(); mount('tracking'); const dialog = await open(user, 'Line tracking');
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(within(dialog).getByLabelText('Receipt location for line 1')).toHaveFocus();
    await user.selectOptions(within(dialog).getByLabelText('Receipt location for line 1'), 'demo-store');
    await user.type(within(dialog).getByLabelText('Batch number for line 1'), 'INK-26');
    fireEvent.change(within(dialog).getByLabelText('Expiry date for line 1'), { target: { value: '2027-10-31' } });
    await user.selectOptions(within(dialog).getByLabelText('Receipt location for line 2'), 'demo-office');
    await user.type(within(dialog).getByLabelText('Serial numbers for line 2'), 'SCAN-1\nSCAN-2');
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Save demo draft' }));
    expect(screen.getByText('Demo draft only')).toBeVisible();
  });
  it('plans advances/payment without reducing the bill total or allowing overpayment', async () => {
    const user = userEvent.setup(); mount(); let dialog = await open(user, 'Payment & terms');
    let amount = within(dialog).getByLabelText('Payment to record');
    await user.clear(amount); await user.type(amount, '5000');
    await user.selectOptions(within(dialog).getByLabelText('Payment account'), 'demo-bank');
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(within(dialog).getAllByText(/cannot exceed the full bill total/)).toHaveLength(2);
    await user.clear(amount); await user.type(amount, '2000');
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(screen.getAllByText('₹5,723.00')).toHaveLength(2);
    expect(screen.getByText('₹2,723.00')).toBeVisible();
    dialog = await open(user, 'Payment & terms');
    expect(within(dialog).getByLabelText('Payment to record')).toHaveValue('2,000.00');
  });
  it('keeps supplier originals while requiring a matching revised total and reason', async () => {
    const user = userEvent.setup(); mount(); let dialog = await open(user, 'Supplier bill & attachments');
    await user.type(within(dialog).getByLabelText('Supplier-declared bill total'), '5750');
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    await user.click(screen.getByRole('button', { name: 'Review bill' }));
    dialog = panel('Supplier bill & attachments');
    expect(within(dialog).getByLabelText('Supplier-declared bill total')).toHaveFocus();
    await user.selectOptions(within(dialog).getByLabelText('Difference resolution'), 'SUPPLIER_REVISED');
    await user.type(within(dialog).getByLabelText('Supplier revised total'), '5723');
    await user.type(within(dialog).getByLabelText('Supplier revision reason or reference'), 'Supplier correction EX-42');
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(screen.getByText('Original supplier total')).toBeVisible();
    expect(screen.getByText('₹5,750.00')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Review bill' }));
    expect(screen.getByRole('dialog', { name: 'Review purchase bill' })).toBeVisible();
  });
  it('checks local attachments, previews safely, removes files and never claims upload', async () => {
    const user = userEvent.setup(); mount(); const dialog = await open(user, 'Supplier bill & attachments');
    const input = within(dialog).getByLabelText('Supplier bill attachments');
    const png = new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], 'bill.png', { type: 'image/png' });
    await user.upload(input, png);
    await waitFor(() => expect(within(dialog).getByText(/Selected locally/)).toBeVisible());
    expect(within(dialog).queryByText(/Uploaded/)).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Preview attachment 1' }));
    expect(screen.getByRole('img', { name: 'Selected purchase attachment' })).toHaveAttribute('src', 'blob:purchase-test');
    fireEvent.error(screen.getByRole('img', { name: 'Selected purchase attachment' }));
    expect(screen.getByText('Image preview unavailable')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Close preview' }));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:purchase-test');
    await user.click(within(dialog).getByRole('button', { name: /Remove bill.png/ }));
    expect(within(dialog).queryByText('bill.png')).not.toBeInTheDocument();
    await user.upload(input, new File(['<script>bad</script>'], 'bad.png', { type: 'image/png' }));
    await waitFor(() => expect(within(dialog).getByText(/content does not match/)).toBeVisible());
    await user.click(within(dialog).getByRole('button', { name: 'Apply details' }));
    expect(within(dialog).getByText('Check these details')).toBeVisible();
  });
  it('renders PDF metadata without embedding active content', async () => {
    const user = userEvent.setup(); mount(); const dialog = await open(user, 'Supplier bill & attachments');
    await user.upload(within(dialog).getByLabelText('Supplier bill attachments'), new File(['%PDF-1.7'], 'bill.pdf', { type: 'application/pdf' }));
    await waitFor(() => expect(within(dialog).getByText(/Selected locally/)).toBeVisible());
    await user.click(within(dialog).getByRole('button', { name: 'Preview attachment 1' }));
    expect(screen.getByText(/trusted PDF reader/)).toBeVisible();
    expect(document.querySelector('iframe,object,embed')).toBeNull();
  });
  it('blocks Apply during local file checks and ignores a result after discarding the panel', async () => {
    let finish!: (value: string | null) => void;
    vi.mocked(checkPurchaseAttachment).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const user = userEvent.setup(); mount(); const dialog = await open(user, 'Supplier bill & attachments');
    await user.upload(within(dialog).getByLabelText('Supplier bill attachments'), new File(['%PDF-1.7'], 'pending.pdf', { type: 'application/pdf' }));
    expect(within(dialog).getByRole('button', { name: 'Checking files…' })).toBeDisabled();
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByRole('button', { name: 'Discard panel changes' }));
    await act(async () => finish(null));
    const reopened = await open(user, 'Supplier bill & attachments');
    expect(within(reopened).queryByText('pending.pdf')).not.toBeInTheDocument();
    expect(within(reopened).getByRole('button', { name: 'Apply details' })).toBeEnabled();
  });
  it('validates typed custom fields and normalizes them only on Apply', async () => {
    const user = userEvent.setup(), onApply = vi.fn();
    render(<PurchaseDetailsPanel panel="evidence" draft={purchaseExample(today)} policy={policy} canEdit onApply={onApply} onClose={vi.fn()} />);
    await user.type(screen.getByLabelText('Number of parcels'), '1.5');
    await user.click(screen.getByRole('button', { name: 'Apply details' }));
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Number of parcels')).toHaveFocus();
    await user.clear(screen.getByLabelText('Number of parcels')); await user.type(screen.getByLabelText('Number of parcels'), '2');
    await user.click(screen.getByRole('button', { name: 'Apply details' }));
    expect(onApply).toHaveBeenCalledWith(expect.objectContaining({ custom: expect.objectContaining({ cf_purchase_parcels: 2 }) }));
  });
  it('keeps all detail editors read only without create permission', async () => {
    const user = userEvent.setup(); mount('goods', false); const dialog = await open(user, 'Payment & terms');
    expect(within(dialog).getByLabelText('Payment to record')).toBeDisabled();
    expect(within(dialog).getByLabelText('Credit days')).toBeDisabled();
    expect(within(dialog).queryByRole('button', { name: 'Apply details' })).not.toBeInTheDocument();
  });
  it('omits unavailable sections and respects fixture write restrictions', async () => {
    const user = userEvent.setup(), restricted = { ...policy, details: { ...policy.details, panels: { ...policy.details.panels, evidence: { available: false, writable: false }, components: { available: true, writable: false } } } };
    render(<PurchaseWorkspace today={today} canCreate initialDraft={purchaseExample(today)} policy={restricted} />);
    expect(screen.queryByRole('button', { name: /^Supplier bill & attachments/ })).not.toBeInTheDocument();
    const dialog = await open(user, 'Discounts & charges');
    expect(within(dialog).getByLabelText('Component 1 value')).toBeDisabled();
    expect(within(dialog).queryByRole('button', { name: 'Apply details' })).not.toBeInTheDocument();
  });
});
