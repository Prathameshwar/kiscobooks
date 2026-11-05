import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { PurchaseEntryConnected } from '../app/components/PurchaseEntryConnected';
import { serviceCall } from '../app/lib/service-call';
import { company, metadata as fixture } from './purchase-entry-fixtures';
import type { FieldSet } from '../app/lib/voucher-fields';

vi.mock('../app/lib/service-call', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/purchase-entry', async importOriginal => ({ ...await importOriginal<typeof import('../app/lib/purchase-entry')>(), purchaseLookup: vi.fn(() => vi.fn(async () => ({ items: [], nextCursor: null }))) }));
// The real workspace, header and cards are rendered here: this file is about how the page is put together.

const id = (n: number) => '10000000-0000-7000-8000-' + String(n).padStart(12, '0');
const props = { company, currency: 'INR', actor: id(12), year: id(13), canCreate: true, permissions: ['vouchers.read', 'vouchers.create', 'vouchers.edit'] };
let metadata: FieldSet;
let types: unknown[];
let drafts: () => unknown;
const requested: string[] = [];

beforeEach(() => {
  sessionStorage.clear(); requested.length = 0; vi.mocked(serviceCall).mockReset();
  metadata = structuredClone(fixture);
  Object.assign(metadata.native.properties!, Object.fromEntries(['document_date', 'currency', 'narration', 'mode', 'lines', 'attachments', 'links', 'custom_fields'].map(key => [key, {}])));
  types = [{ id: id(2), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', name: 'Account purchases' }];
  drafts = () => ({ items: [{ id: id(91), company_id: company, kind: 'PURCHASE', status: 'DRAFT', document_date: '2026-10-28' }, { id: id(92), company_id: company, kind: 'PURCHASE', status: 'DRAFT', document_date: null }], page: { next_cursor: 'more' } });
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    requested.push(request.path);
    if (request.path.includes('/voucher-types?')) return { items: types, page: { next_cursor: null } };
    if (request.path.endsWith('/voucher-capabilities')) return { financial_execution: false, invoice_execution: false, kinds: [{ kind: 'PURCHASE', execution_ready: false }] };
    if (request.path.includes('/field-set')) return metadata;
    if (request.path.includes('/vouchers?kind=PURCHASE&status=DRAFT')) return drafts();
    if (request.path.includes('/vouchers/')) throw { status: 404, message: 'That purchase was not found.' };
    throw Error('Unexpected test route ' + request.path);
  });
});

describe('the connected Purchase page', () => {
  it('is one page column with a header, the bill and an action bar, and none of the old clutter', async () => {
    const { container } = render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { level: 1, name: 'New purchase' });
    expect(container.querySelector('section.janso-page')).toBe(container.firstElementChild);
    for (const text of ['Connected to company APIs', 'Accounting totals', 'Save changes, then calculate the saved bill', 'Find saved purchases', 'Open saved purchase']) expect(screen.queryByText(text)).toBeNull();
    expect(screen.queryByRole('combobox', { name: 'Tax treatment' })).toBeNull();
    expect(container.querySelector('aside')).toBeNull();
    expect(screen.getByRole('button', { name: 'Saved drafts' })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Supplier and invoice details' })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Purchase line entry' })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Terms and tax' })).toBeVisible();
    expect(screen.getByRole('group', { name: 'Purchase actions' })).toBeVisible();
  });

  it('names the type and currency as chips, and the scope in plain words', async () => {
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    expect(screen.getByText('Account purchases')).toBeVisible();
    expect(screen.getByText('Amounts in INR')).toBeVisible();
    expect(screen.getByText('Not saved')).toBeVisible();
    expect(screen.getByText(/with or without GST\. Purchases of stock cannot be recorded on this screen yet/)).toBeVisible();
  });

  it('does not show a calculation card or a lifecycle card before there is a saved bill', async () => {
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    expect(screen.queryByRole('region', { name: 'Accounting calculation' })).toBeNull();
    expect(screen.queryByRole('region', { name: 'Purchase lifecycle' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'New purchase' })).toBeNull();
  });

  it('shows the total as lines entered until Accounting has calculated', async () => {
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    expect(within(screen.getByRole('group', { name: 'Purchase actions' })).getByText('Lines total')).toBeVisible();
    expect(screen.getByText('Not saved yet')).toBeVisible();
  });

  it('shows a skeleton and a status while the configuration loads', () => {
    vi.mocked(serviceCall).mockImplementation(() => new Promise(() => undefined));
    const { container } = render(<PurchaseEntryConnected {...props} />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading Purchase configuration and access…');
    expect(screen.getByRole('heading', { level: 1, name: 'New purchase' })).toBeVisible();
    expect(container.querySelector('.janso-skeleton')).not.toBeNull();
    expect(container.querySelector('section.janso-page')).toHaveAttribute('aria-busy', 'true');
  });
});

describe('the setup-needed page', () => {
  it('asks for a voucher type when there are several, with links to review them', async () => {
    types = [...types, { id: id(22), company_id: company, kind: 'PURCHASE', profile: 'STANDARD', name: 'Branch purchases' }];
    const { container } = render(<PurchaseEntryConnected {...props} permissions={[...props.permissions, 'vouchers.type.manage']} />);
    const select = await screen.findByRole('combobox', { name: 'Purchase voucher type' });
    expect(screen.getByRole('heading', { level: 1, name: 'New purchase' })).toBeVisible();
    expect(container.querySelector('.janso-purchase-setup')).not.toBeNull();
    expect(screen.getByRole('link', { name: 'Open voucher types' })).toBeVisible();
    fireEvent.change(select, { target: { value: id(22) } });
    expect(await screen.findByText('Branch purchases')).toBeVisible();
    expect(screen.queryByRole('combobox', { name: 'Purchase voucher type' })).toBeNull();
  });

  it('says there is no active type, and lets the person look again', async () => {
    types = [];
    render(<PurchaseEntryConnected {...props} />);
    expect(await screen.findByText('No active Purchase type')).toBeVisible();
    expect(screen.queryByRole('combobox', { name: 'Purchase voucher type' })).toBeNull();
    expect(screen.getByRole('link', { name: 'Open voucher types' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Refresh Purchase setup' })).toBeEnabled();
  });
});

describe('saved drafts', () => {
  it('lists them in a drawer, read when it is first opened and not before', async () => {
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    expect(requested.some(path => path.includes('status=DRAFT'))).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    const list = await screen.findByRole('list', { name: 'Saved purchase drafts' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(list).getByText('Saved draft')).toBeVisible();
    expect(screen.getByRole('button', { name: 'More saved purchases' })).toBeVisible();
    expect(requested.filter(path => path.includes('status=DRAFT'))).toHaveLength(1);
  });

  it('reads them again each time the drawer is opened, so a bill saved in between is there', async () => {
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    await screen.findByRole('list', { name: 'Saved purchase drafts' });
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Saved purchase drafts' })).getAllByRole('button', { name: 'Close' }).at(-1)!);
    await waitFor(() => expect(screen.queryByRole('list', { name: 'Saved purchase drafts' })).toBeNull());
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    await screen.findByRole('list', { name: 'Saved purchase drafts' });
    await waitFor(() => expect(requested.filter(path => path.includes('status=DRAFT'))).toHaveLength(2));
  });

  it('shows the new list, not the old one, when a bill has been saved since the drawer was last open', async () => {
    drafts = () => ({ items: [], page: { next_cursor: null } });
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    expect(await screen.findByText('No saved drafts')).toBeVisible();
    fireEvent.click(within(screen.getByRole('dialog', { name: 'Saved purchase drafts' })).getAllByRole('button', { name: 'Close' }).at(-1)!);
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Saved purchase drafts' })).toBeNull());
    drafts = () => ({ items: [{ id: id(93), company_id: company, kind: 'PURCHASE', status: 'DRAFT', document_date: '2026-10-30' }], page: { next_cursor: null } });
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    expect(await screen.findByRole('button', { name: new RegExp('Open draft 30 Oct 2026, ' + id(93)) })).toBeVisible();
    expect(screen.queryByText('No saved drafts')).toBeNull();
  });

  it('closes the drawer and opens the draft chosen', async () => {
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    fireEvent.click(await screen.findByRole('button', { name: new RegExp('Open draft 28 Oct 2026, ' + id(91)) }));
    await waitFor(() => expect(requested).toContain(`/v1/companies/${company}/vouchers/${id(91)}`));
    await waitFor(() => expect(screen.queryByRole('list', { name: 'Saved purchase drafts' })).toBeNull());
    expect(await screen.findByText('That purchase was not found.')).toBeVisible();
  });

  it('shows a failed read inside the drawer, not an empty list', async () => {
    drafts = () => { throw { status: 503, message: 'Saved purchases are unavailable.' }; };
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    const drawer = await screen.findByRole('dialog', { name: 'Saved purchase drafts' });
    expect(await within(drawer).findByText('Saved purchases are unavailable.')).toBeVisible();
    expect(within(drawer).queryByText('No saved drafts')).toBeNull();
  });

  it('can be tried again after a failed read, and the failure stays in the drawer', async () => {
    let calls = 0;
    drafts = () => { if (++calls === 1) throw { status: 503, message: 'Saved purchases are unavailable.' }; return { items: [{ id: id(91), company_id: company, kind: 'PURCHASE', status: 'DRAFT', document_date: '2026-10-28' }], page: { next_cursor: null } }; };
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    const drawer = await screen.findByRole('dialog', { name: 'Saved purchase drafts' });
    fireEvent.click(await within(drawer).findByRole('button', { name: 'Try again' }));
    expect(await within(drawer).findByRole('button', { name: new RegExp('Open draft 28 Oct 2026') })).toBeVisible();
    expect(within(drawer).queryByText('Saved purchases are unavailable.')).toBeNull();
    expect(screen.queryByText('Purchase needs attention')).toBeNull();
  });

  it('does not put a drafts failure on the page behind the drawer', async () => {
    drafts = () => { throw { status: 503, message: 'Saved purchases are unavailable.' }; };
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    const drawer = await screen.findByRole('dialog', { name: 'Saved purchase drafts' });
    await within(drawer).findByText('Saved purchases are unavailable.');
    expect(screen.queryByText('Purchase needs attention')).toBeNull();
  });

  it('puts keyboard focus back on the Saved drafts button after a draft has been chosen', async () => {
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    fireEvent.click(await screen.findByRole('button', { name: new RegExp('Open draft 28 Oct 2026, ' + id(91)) }));
    await screen.findByText('That purchase was not found.');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Saved drafts' })).toHaveFocus());
  });

  it('says there are none when there are none', async () => {
    drafts = () => ({ items: [], page: { next_cursor: null } });
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    expect(await screen.findByText('No saved drafts')).toBeVisible();
  });

  it('still opens a saved purchase by its ID', async () => {
    render(<PurchaseEntryConnected {...props} />);
    await screen.findByRole('heading', { name: 'New purchase' });
    fireEvent.click(screen.getByRole('button', { name: 'Saved drafts' }));
    const open = await screen.findByRole('button', { name: 'Open saved purchase' });
    expect(open).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Saved Purchase ID'), { target: { value: id(95) } });
    fireEvent.click(open);
    await waitFor(() => expect(requested).toContain(`/v1/companies/${company}/vouchers/${id(95)}`));
  });
});
