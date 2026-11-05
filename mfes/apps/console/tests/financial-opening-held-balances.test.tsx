import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DEFAULT_DISPLAY_CONFIG, DisplayConfigProvider } from '@janso/ui';
import { FinancialOpeningHeldBalances } from '../app/components/FinancialOpeningHeldBalances';
import type { Entry } from '../app/lib/financial-opening';
import { heldEntry, withdrawLabel, type HeldBalance } from '../app/lib/party-opening';
import { serviceCall } from '../app/lib/service-call';
import { ACCOUNT, COMPANY, access } from './financial-opening-fixtures';
import { held, heldInvoice, heldPage } from './party-opening-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn() }));
const api = vi.mocked(serviceCall);
let listing: unknown, withdrawing: (() => unknown) | null = null;

beforeEach(() => {
  api.mockReset(); withdrawing = null; listing = heldPage([held(1), heldInvoice(2)]);
  api.mockImplementation(async (_endpoint, req) => {
    if (req.path.includes('/party-balances/') && req.path.endsWith('/withdraw')) { if (withdrawing) return withdrawing() as never; return { ...held(1), status: 'WITHDRAWN', row_version: 2 } as never; }
    if (req.path.includes('/party-balances')) { if (listing instanceof Error) throw listing; return listing as never; }
    if (req.path.includes('/accounts/')) return { id: ACCOUNT, company_id: COMPANY, name: 'Supplier ledger', kind: 'PARTY', status: 'ACTIVE' } as never;
    throw new Error('unexpected request ' + req.path);
  });
});

function panel(over: { rows?: Entry[]; editable?: boolean; manage?: boolean; onAdd?: (entries: Entry[]) => void; onDirty?: (dirty: boolean) => void; onLeave?: React.MouseEventHandler<HTMLAnchorElement> } = {}) {
  const onAdd = over.onAdd ?? vi.fn(), onDirty = over.onDirty ?? vi.fn();
  render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><FinancialOpeningHeldBalances company={COMPANY} rows={over.rows ?? []} access={{ ...access, manage: over.manage ?? true }} editable={over.editable ?? true} onAdd={onAdd} onDirty={onDirty} onLeave={over.onLeave} /></DisplayConfigProvider>);
  return { onAdd, onDirty };
}

it('asks for pending lines only and renders nothing when none are held', async () => {
  listing = heldPage([]);
  const { container } = render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><FinancialOpeningHeldBalances company={COMPANY} rows={[]} access={access} editable onAdd={vi.fn()} onDirty={vi.fn()} /></DisplayConfigProvider>);
  await waitFor(() => expect(api).toHaveBeenCalled());
  expect(api.mock.calls[0]![1].path).toBe(`/v1/companies/${COMPANY}/opening-batches/party-balances?status=PENDING&limit=200`);
  expect(container).toBeEmptyDOMElement();
});

it('lists what is held with exact totals and says nothing is posted', async () => {
  panel();
  expect(await screen.findByText('Balances held from party imports')).toBeVisible();
  expect(screen.getByText(/Nothing is posted/)).toBeVisible();
  const summary = screen.getByText('Held balances').closest('div')!.parentElement!;
  expect(within(summary).getByText('2')).toBeVisible();
  expect(within(summary).getByText('900.0000')).toBeVisible();
  expect(within(summary).getByText('100.2500')).toBeVisible();
  expect(screen.getByText('Credit · to pay')).toBeVisible();
  expect(screen.getByText('Debit · to receive')).toBeVisible();
  expect(screen.getByText('On account · dates unknown')).toBeVisible();
  expect(screen.getByText(/INV-77 · due/)).toBeVisible();
});

it('copies every held line into the worksheet exactly as imported', async () => {
  const { onAdd } = panel();
  await userEvent.click(await screen.findByRole('button', { name: 'Add 2 held balances to this worksheet' }));
  expect(onAdd).toHaveBeenCalledWith([heldEntry(held(1)), heldEntry(heldInvoice(2))]);
});

it('does not offer lines already in the worksheet, already included or withdrawn', async () => {
  listing = heldPage([held(1), held(2, { included: true }), held(3, { status: 'WITHDRAWN' }), heldInvoice(4)]);
  const { onAdd } = panel({ rows: [heldEntry(held(1))] });
  await userEvent.click(await screen.findByRole('button', { name: 'Add 1 held balance to this worksheet' }));
  expect(onAdd).toHaveBeenCalledWith([heldEntry(heldInvoice(4))]);
});

it('cannot add while the worksheet is not editable', async () => {
  panel({ editable: false });
  expect(await screen.findByRole('button', { name: /Add 2 held balances/ })).toBeDisabled();
  expect(screen.getByText(/worksheet is not editable now/)).toBeVisible();
});

it('shows the first twenty-five and says that adding takes them all', async () => {
  listing = heldPage(Array.from({ length: 30 }, (_, n) => held(n + 1)), true);
  panel();
  expect(await screen.findByText('Showing the first 25 of 30. Adding takes all 30.')).toBeVisible();
  expect(screen.getByText(/More held balances exist beyond this list/)).toBeVisible();
  expect(screen.getAllByRole('button', { name: /^Withdraw held supplier balance \d+: / })).toHaveLength(25);
});

it('withdraws one line after a reason, then refreshes and confirms', async () => {
  const { onDirty } = panel();
  await userEvent.click(await screen.findByRole('button', { name: withdrawLabel(held(1), 1) }));
  const dialog = await screen.findByRole('dialog');
  await waitFor(() => expect(onDirty).toHaveBeenLastCalledWith(true));
  await userEvent.type(within(dialog).getByLabelText('Withdrawal reason'), 'no');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Withdraw balance' }));
  expect(await within(dialog).findByRole('alert')).toHaveTextContent('between 3 and 500');
  expect(api.mock.calls.some(call => call[1].path.endsWith('/withdraw'))).toBe(false);
  listing = heldPage([heldInvoice(2)]);
  await userEvent.type(within(dialog).getByLabelText('Withdrawal reason'), 't wanted ');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Withdraw balance' }));
  expect(await screen.findByText('Held balance withdrawn. The party and its ledger account are unchanged.')).toBeVisible();
  const call = api.mock.calls.find(entry => entry[1].path.endsWith('/withdraw'))![1];
  expect(call.path).toBe(`/v1/companies/${COMPANY}/opening-batches/party-balances/${held(1).id}/withdraw`);
  expect(call.method).toBe('POST');
  expect(call.body).toEqual({ expected_version: 1, reason: 'not wanted' });
  expect(typeof call.key).toBe('string');
  await waitFor(() => expect(screen.queryByRole('button', { name: withdrawLabel(held(1), 1) })).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: withdrawLabel(heldInvoice(2), 1) })).toBeVisible();
  await waitFor(() => expect(onDirty).toHaveBeenLastCalledWith(false));
});

it('keeps the dialog and shows the reason when the service refuses the withdrawal', async () => {
  withdrawing = () => { throw { status: 409, message: 'this balance is in the opening declaration; change it there' }; };
  panel();
  await userEvent.click(await screen.findByRole('button', { name: withdrawLabel(held(1), 1) }));
  const dialog = await screen.findByRole('dialog');
  await userEvent.type(within(dialog).getByLabelText('Withdrawal reason'), 'Entered twice');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Withdraw balance' }));
  expect(await within(dialog).findByText(/in the opening declaration; change it there/)).toBeVisible();
  expect(screen.queryByText(/Held balance withdrawn/)).not.toBeInTheDocument();
});

it('retries the exact same request after an unconfirmed outcome', async () => {
  let attempts = 0;
  withdrawing = () => { attempts++; if (attempts === 1) throw { status: 503, message: 'Connection lost.' }; return { ...held(1), status: 'WITHDRAWN', row_version: 2 }; };
  panel();
  await userEvent.click(await screen.findByRole('button', { name: withdrawLabel(held(1), 1) }));
  const dialog = await screen.findByRole('dialog');
  await userEvent.type(within(dialog).getByLabelText('Withdrawal reason'), 'Entered twice');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Withdraw balance' }));
  await userEvent.click(await within(dialog).findByRole('button', { name: 'Retry the same request' }));
  expect(await screen.findByText(/Held balance withdrawn/)).toBeVisible();
  const sent = api.mock.calls.filter(entry => entry[1].path.endsWith('/withdraw')).map(entry => entry[1]);
  expect(sent).toHaveLength(2);
  expect(sent[1]!.key).toBe(sent[0]!.key);
  expect(sent[1]!.body).toEqual(sent[0]!.body);
});

it('does not let a reader withdraw', async () => {
  panel({ manage: false });
  expect(await screen.findByRole('button', { name: withdrawLabel(held(1), 1) })).toBeDisabled();
});

it('shows no panel to someone who cannot read opening evidence', async () => {
  listing = Object.assign(new Error('forbidden'), { status: 403, message: 'Not permitted.' });
  api.mockImplementation(async () => { throw { status: 403, message: 'Not permitted.' }; });
  const { container } = render(<DisplayConfigProvider config={DEFAULT_DISPLAY_CONFIG}><FinancialOpeningHeldBalances company={COMPANY} rows={[]} access={access} editable onAdd={vi.fn()} onDirty={vi.fn()} /></DisplayConfigProvider>);
  await waitFor(() => expect(api).toHaveBeenCalled());
  expect(container).toBeEmptyDOMElement();
});

it('reports a failed or unverifiable read with a way to retry', async () => {
  api.mockImplementationOnce(async () => { throw { status: 500, message: 'Accounting is unavailable.' }; });
  panel();
  expect(await screen.findByText(/Accounting is unavailable/)).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Reload configuration' }));
  expect(await screen.findByText('Balances held from party imports')).toBeVisible();
});

it('refuses a malformed payload instead of offering unverified amounts', async () => {
  listing = heldPage([held(1, { amount: '1e5' } as Partial<HeldBalance>)]);
  panel();
  expect(await screen.findByText(/could not be verified/)).toBeVisible();
  expect(screen.queryByRole('button', { name: /Add \d+ held/ })).not.toBeInTheDocument();
});

it('names each withdraw button by what it withdraws and which one it is', async () => {
  panel();
  expect(await screen.findByRole('button', { name: 'Withdraw held supplier balance 1: 100.2500 INR' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Withdraw held customer balance 2: 900.0000 INR' })).toBeVisible();
});

it('says which balance is being withdrawn before asking for a reason', async () => {
  panel();
  await userEvent.click(await screen.findByRole('button', { name: withdrawLabel(heldInvoice(2), 2) }));
  const dialog = await screen.findByRole('dialog');
  expect(await within(dialog).findByText('Supplier ledger')).toBeVisible();
  expect(within(dialog).getByText(/Debit · to receive/)).toBeVisible();
  expect(within(dialog).getByText(/900\.00/)).toBeVisible();
  expect(within(dialog).getByText(/INV-77 · due/)).toBeVisible();
  expect(within(dialog).getByText(/can still be entered in the worksheet by hand/)).toBeVisible();
  expect(within(dialog).queryByText(/import the party again/)).not.toBeInTheDocument();
});

it('reloads the list after a definite refusal so the next attempt carries the current version', async () => {
  let attempts = 0;
  withdrawing = () => { attempts++; if (attempts === 1) throw { status: 409, message: 'the held balance changed; reload it' }; return { ...held(1), status: 'WITHDRAWN', row_version: 4 }; };
  panel();
  await userEvent.click(await screen.findByRole('button', { name: withdrawLabel(held(1), 1) }));
  const dialog = await screen.findByRole('dialog');
  await userEvent.type(within(dialog).getByLabelText('Withdrawal reason'), 'Entered twice');
  listing = heldPage([held(1, { row_version: 3 }), heldInvoice(2)]);
  await userEvent.click(within(dialog).getByRole('button', { name: 'Withdraw balance' }));
  expect(await within(dialog).findByText(/the held balance changed/)).toBeVisible();
  await waitFor(() => expect(api.mock.calls.filter(call => call[1].path.includes('party-balances?')).length).toBeGreaterThan(1));
  await userEvent.click(within(dialog).getByRole('button', { name: 'Withdraw balance' }));
  await screen.findByText(/Held balance withdrawn/);
  const bodies = api.mock.calls.filter(call => call[1].path.endsWith('/withdraw')).map(call => (call[1].body as { expected_version: number }).expected_version);
  expect(bodies).toEqual([1, 3]);
});

it('closes the dialog and frees the buttons when the line leaves the list', async () => {
  const { onDirty } = panel();
  await userEvent.click(await screen.findByRole('button', { name: withdrawLabel(held(1), 1) }));
  await screen.findByRole('dialog');
  withdrawing = () => { throw { status: 409, message: 'this balance was already withdrawn' }; };
  listing = heldPage([heldInvoice(2)]);
  await userEvent.type(screen.getByLabelText('Withdrawal reason'), 'Entered twice');
  await userEvent.click(screen.getByRole('button', { name: 'Withdraw balance' }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  await waitFor(() => expect(onDirty).toHaveBeenLastCalledWith(false));
  expect(screen.getByRole('button', { name: withdrawLabel(heldInvoice(2), 1) })).toBeEnabled();
});

it('guards the ledger link so an unsaved worksheet is not lost silently', async () => {
  const onLeave = vi.fn((event: React.MouseEvent<HTMLAnchorElement>) => event.preventDefault());
  panel({ onLeave });
  const links = await screen.findAllByRole('link', { name: 'Supplier ledger' });
  await userEvent.click(links[0]!);
  expect(onLeave).toHaveBeenCalledTimes(1);
});
