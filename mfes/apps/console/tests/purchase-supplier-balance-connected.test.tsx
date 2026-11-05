import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseEntryConnected } from '../app/components/PurchaseEntryConnected';
import { COMPANY, SUPPLIERS, id, installFakeServices, payableOf, type FakeServices } from './purchase-fake-service';

/**
 * The supplier's balance on the real Purchase page, against stand-ins for the services reached through
 * the Console's real proxy allowlist. What matters here is how it behaves around the entry: it is read
 * once when a supplier is chosen, it never holds the bill back, and it says "not available" rather than
 * guess.
 */
// Each test drives the whole page with real typing; under a loaded full run that outlasts the default five seconds.
vi.setConfig({ testTimeout: 60_000 });
const SHARMA = SUPPLIERS[0]!, BRIGHT = SUPPLIERS[1]!;
const permissions = ['vouchers.read', 'vouchers.create', 'vouchers.edit', 'vouchers.submit', 'vouchers.approve', 'vouchers.reject', 'vouchers.cancel',
  'vouchers.history.read', 'vouchers.post', 'vouchers.operation.read', 'vouchers.operation.recover'];
const props = { company: COMPANY, currency: 'INR', actor: id(12), year: id(13), canCreate: true, permissions: [...permissions, 'ledger.read'] };
const SEARCH = 'Search a supplier by name or code';
let services: FakeServices;
const owed = { [SHARMA.id]: { debit: '25000.0000', credit: '150000.0000' }, [BRIGHT.id]: { debit: '9000.0000', credit: '0.0000' } };
beforeEach(() => { sessionStorage.clear(); services = installFakeServices({ balances: owed }); });
afterEach(() => vi.unstubAllGlobals());

const reads = () => services.requests.filter(row => row.path.split('?')[0]!.endsWith('/ledger/balance'));
const strip = () => document.querySelector<HTMLElement>('[data-purchase-balance]');
async function open() {
  render(<PurchaseEntryConnected {...props} />);
  await screen.findByRole('heading', { level: 1, name: 'New purchase' });
}
// The supplier shows in its field only once it, and its payable account, have been read and verified.
const chosen = (name: string) => waitFor(() => expect(screen.getByPlaceholderText(SEARCH)).toHaveValue(name));
async function choose(user: ReturnType<typeof userEvent.setup>, query: string, name: RegExp) {
  const box = await screen.findByPlaceholderText(SEARCH);
  await user.click(box); await user.type(box, query);
  await user.click(await screen.findByRole('option', { name }));
}

describe('the supplier balance on the Purchase page', () => {
  it('shows one figure, marked Cr and To pay, when a supplier is chosen', async () => {
    const user = userEvent.setup();
    await open();
    expect(strip()).toBeNull();
    await choose(user, 'Sharma', /Sharma Office Supplies/);
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'ready'));
    expect(strip()!.querySelector('.janso-purchase-balance__amount')).toHaveTextContent('₹1,25,000.00 Cr');
    expect(within(strip()!).getByText('To pay')).toBeInTheDocument();
    expect(screen.queryByText('Purchase needs attention')).toBeNull();
  });

  it('reads it once, as of the posting date, for that supplier and its payable account, in the base currency', async () => {
    const user = userEvent.setup();
    await open();
    await choose(user, 'Sharma', /Sharma Office Supplies/);
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'ready'));
    expect(reads()).toHaveLength(1);
    const [request] = reads();
    expect(request!.service).toBe('accounting');
    expect(request!.method).toBe('GET');
    expect(Object.fromEntries(new URLSearchParams(request!.path.split('?')[1]))).toEqual({
      as_of: (screen.getByLabelText(/Posting date/) as HTMLInputElement).value, basis: 'BASE', currency: 'INR', party_id: SHARMA.id, account_id: payableOf(SHARMA.id),
    });
  });

  it('is not read again when the bill is edited afterwards', async () => {
    const user = userEvent.setup();
    await open();
    await choose(user, 'Sharma', /Sharma Office Supplies/);
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'ready'));
    await user.type(screen.getByLabelText(/Supplier invoice number/), 'SOS/26-27/0418');
    const posting = screen.getByLabelText(/Posting date/);
    await user.clear(posting); await user.type(posting, '2026-10-15');
    await user.click(screen.getByRole('checkbox', { name: 'This bill carries no tax' }));
    expect(reads()).toHaveLength(1);
    expect(strip()).toHaveAttribute('data-purchase-balance', 'ready');
  });

  it('shows an amount the supplier holds for the company as Dr and To receive', async () => {
    const user = userEvent.setup();
    await open();
    await choose(user, 'Bright', /Bright Lights Electricals/);
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'ready'));
    expect(strip()!.querySelector('.janso-purchase-balance__amount')).toHaveTextContent('₹9,000.00 Dr');
    expect(within(strip()!).getByText('To receive')).toBeInTheDocument();
  });

  it('never holds the bill back: the entry is open while the balance is still being read', async () => {
    const user = userEvent.setup();
    const release = services.holdBalances();
    await open();
    await choose(user, 'Sharma', /Sharma Office Supplies/);
    await chosen(SHARMA.name);
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'loading'));
    expect(strip()).toHaveTextContent('Checking the balance…');
    // Nothing is locked: the fields take input and no pending state is announced for the page.
    const invoice = screen.getByLabelText(/Supplier invoice number/);
    expect(invoice).toBeEnabled();
    await user.type(invoice, 'SOS/26-27/0418');
    expect(invoice).toHaveValue('SOS/26-27/0418');
    expect(screen.getByPlaceholderText(SEARCH)).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();
    release();
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'ready'));
    expect(invoice).toHaveValue('SOS/26-27/0418');
  });

  it('drops a read the person has moved on from, and never shows one supplier’s figure for another', async () => {
    const user = userEvent.setup();
    const release = services.holdBalances();
    await open();
    await choose(user, 'Sharma', /Sharma Office Supplies/);
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'loading'));
    const first = reads()[0]!.path;
    await user.clear(screen.getByPlaceholderText(SEARCH));
    await choose(user, 'Bright', /Bright Lights Electricals/);
    await waitFor(() => expect(services.cancelled).toEqual([first]));
    release();
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'ready'));
    expect(strip()!.querySelector('.janso-purchase-balance__amount')).toHaveTextContent('₹9,000.00 Dr');
    expect(strip()).not.toHaveTextContent('Cr');
    expect(reads()).toHaveLength(2);
  });

  it('removes the balance when the supplier is cleared', async () => {
    const user = userEvent.setup();
    await open();
    await choose(user, 'Sharma', /Sharma Office Supplies/);
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'ready'));
    await user.click(screen.getByRole('button', { name: 'Clear Supplier' }));
    await waitFor(() => expect(strip()).toBeNull());
  });

  it('says it is not available, and carries on, when Accounting refuses the read', async () => {
    const user = userEvent.setup();
    services.failNext((method, path) => path.endsWith('/ledger/balance'), 403, 'ledger fields are not readable');
    await open();
    await choose(user, 'Sharma', /Sharma Office Supplies/);
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'unavailable'));
    expect(strip()).toHaveTextContent('Not available right now. You can carry on with the bill.');
    expect(strip()).not.toHaveTextContent('₹');
    // The supplier was still chosen and verified, with no error for the page.
    expect(screen.getByPlaceholderText(SEARCH)).toHaveValue(SHARMA.name);
    expect(screen.queryByText('Purchase needs attention')).toBeNull();
    expect(screen.queryByText(/ledger fields are not readable/)).toBeNull();
    expect(screen.getByLabelText(/Supplier invoice number/)).toBeEnabled();
  });

  it('says it is not available when the answer cannot be proved', async () => {
    const user = userEvent.setup();
    const real = globalThis.fetch;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const response = await real(input, init);
      const body = JSON.parse(String(init?.body ?? '{}'));
      if (!String(body.path).split('?')[0]!.endsWith('/ledger/balance')) return response;
      return new Response(JSON.stringify({ ...(await response.json()), balance: '1.0000' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));
    await open();
    await choose(user, 'Sharma', /Sharma Office Supplies/);
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'unavailable'));
    expect(strip()).not.toHaveTextContent('₹');
  });

  it('asks for nothing and shows nothing without the ledger read permission', async () => {
    const user = userEvent.setup();
    render(<PurchaseEntryConnected {...props} permissions={permissions} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    await choose(user, 'Sharma', /Sharma Office Supplies/);
    await chosen(SHARMA.name);
    expect(reads()).toHaveLength(0);
    expect(strip()).toBeNull();
  });

  it('stays after a draft is saved, and is gone once the bill is posted, since the ledger then includes it', { timeout: 90000 }, async () => {
    const user = userEvent.setup();
    await open();
    await choose(user, 'Sharma', /Sharma Office Supplies/);
    await waitFor(() => expect(strip()).toHaveAttribute('data-purchase-balance', 'ready'));
    await user.type(screen.getByLabelText(/Supplier invoice number/), 'SOS/26-27/0418');
    await user.click(screen.getByPlaceholderText('Find an expense account'));
    await user.type(screen.getByPlaceholderText('Find an expense account'), 'Office');
    await user.click(await screen.findByRole('option', { name: /Office expenses/ }));
    await waitFor(() => expect(services.requests.some(row => row.path.includes('/account-heads/'))).toBe(true));
    await user.type(await screen.findByRole('textbox', { name: 'Amount, line 1' }), '18450');
    await user.click(screen.getByRole('checkbox', { name: 'This bill carries no tax' }));
    await user.click(screen.getByRole('button', { name: 'Save draft' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 1' });
    expect(strip()).toHaveAttribute('data-purchase-balance', 'ready');

    await user.click(screen.getByRole('button', { name: 'Calculate saved bill' }));
    await user.click(await screen.findByRole('button', { name: 'Accept Accounting calculation' }));
    await screen.findByRole('heading', { name: 'Purchase bill · revision 2' });
    await user.click(screen.getByRole('button', { name: 'Submit' }));
    await user.click(await screen.findByRole('button', { name: 'Approve' }));
    expect(strip()).toHaveAttribute('data-purchase-balance', 'ready');
    await user.click(await screen.findByRole('button', { name: 'Post approved Purchase' }));
    await screen.findByText('PENDING');
    expect(strip()).toBeNull();
    services.completeExecution();
    await user.click(screen.getByRole('button', { name: 'Refresh Purchase execution' }));
    await screen.findByText(/Posted Purchase is immutable/);
    expect(strip()).toBeNull();
    // Saving, accepting, submitting and posting never asked for the balance again.
    expect(reads()).toHaveLength(1);
  });
});
