/**
 * The voucher type directory.
 *
 * A list this small has three ways to mislead: a filter that does not reach the service (so it
 * narrows only the page in hand), a row of another kind or company let through into a filtered
 * list, and an empty state that blames the filter when there is nothing at all — or the reverse.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, EXPORT, OTHER, RETAIL, item, lastRead, page, reads, service } from './voucher-type-fixtures';

vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/sign-in' }));

import { VoucherTypeDirectory } from '../app/components/VoucherTypeDirectory';

const mount = (canManage = true) => render(<VoucherTypeDirectory company={COMPANY} canManage={canManage} />);
const export_ = () => item({ id: EXPORT, code: 'EXPORT', name: 'Export sales', status: 'RETIRED', current_revision: 1 });

beforeEach(() => {
  // Braces matter: a function returned from a hook is run as its cleanup, and `mockReset()` returns the mock.
  vi.mocked(serviceCall).mockReset();
});

describe('the list', () => {
  it('shows each type with its code, kind, revision and status, linked to its page', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ list: [item(), export_()] }));
    mount();

    const row = await screen.findByRole('row', { name: /Retail sales/ });
    expect(within(row).getByRole('link', { name: 'Retail sales' })).toHaveAttribute('href', `/masters/voucher-types/${RETAIL}`);
    expect(within(row).getByText('RETAIL')).toBeInTheDocument();
    expect(within(row).getByText('Sales')).toBeInTheDocument();
    expect(within(row).getByText('standard')).toBeInTheDocument();
    expect(within(row).getByText('2')).toBeInTheDocument();
    expect(within(row).getByText('Active')).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /Export sales/ })).getByText('Retired')).toBeInTheDocument();
  });

  it('asks the service for a page, newest first, with no filter to begin with', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount();
    await screen.findByRole('row', { name: /Retail sales/ });

    const [[, request]] = reads('/voucher-types');
    expect(request.service).toBe('vouchers');
    const query = new URLSearchParams(request.path.split('?')[1]);
    expect(Object.fromEntries(query)).toEqual({ limit: '25', sort: '-id' });
  });

  it('puts the page in its place, with the way in to a new type', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount();
    await screen.findByRole('row', { name: /Retail sales/ });

    expect(screen.getByRole('heading', { level: 1, name: 'Voucher types' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'New voucher type' })).toHaveAttribute('href', '/masters/voucher-types/new');
    expect(screen.getByRole('link', { name: 'Back to masters' })).toHaveAttribute('href', '/masters');
  });

  it('offers a reader the list and nothing to change', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount(false);
    await screen.findByRole('row', { name: /Retail sales/ });

    expect(screen.queryByRole('link', { name: 'New voucher type' })).not.toBeInTheDocument();
    expect(screen.getByText(/Read-only access/)).toBeInTheDocument();
  });
});

describe('filtering', () => {
  it('sends the kind to the service', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    const user = userEvent.setup();
    mount();
    await screen.findByRole('row', { name: /Retail sales/ });

    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'SALES');

    await waitFor(() => expect(new URLSearchParams(lastRead('/voucher-types').split('?')[1]).get('kind')).toBe('SALES'));
  });

  it('sends the status to the service', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ list: [item({ status: 'RETIRED' })] }));
    const user = userEvent.setup();
    mount();
    await screen.findByRole('row', { name: /Retail sales/ });

    await user.selectOptions(screen.getByRole('combobox', { name: 'Status' }), 'RETIRED');

    await waitFor(() => expect(new URLSearchParams(lastRead('/voucher-types').split('?')[1]).get('status')).toBe('RETIRED'));
  });

  it('sends a code prefix as the service’s own search, never filtering the page in hand', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount();
    await screen.findByRole('row', { name: /Retail sales/ });

    fireEvent.change(screen.getByRole('searchbox', { name: 'Search voucher types' }), { target: { value: 'RET' } });

    await waitFor(() => expect(new URLSearchParams(lastRead('/voucher-types').split('?')[1]).get('q')).toBe('RET'));
  });

  it('offers every kind the platform defines, under its short name', async () => {
    vi.mocked(serviceCall).mockImplementation(service());
    mount();
    await screen.findByRole('row', { name: /Retail sales/ });

    const kinds = within(screen.getByRole('combobox', { name: 'Kind' })).getAllByRole('option');
    expect(kinds).toHaveLength(23); // "All kinds" and the 22
    expect(within(screen.getByRole('combobox', { name: 'Kind' })).getByRole('option', { name: 'Job-work order in' })).toBeInTheDocument();
  });

  it('says a filter matched nothing, and how to see more', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ list: [] }));
    const user = userEvent.setup();
    mount();
    await screen.findByText('No voucher types yet');

    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'RECEIPT');

    expect(await screen.findByText('No voucher type matches')).toBeInTheDocument();
    expect(screen.getByText(/Clear a filter or search a shorter code/)).toBeInTheDocument();
  });

  it('refuses a filtered list that carries another kind’s row', async () => {
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      const query = new URLSearchParams(request.path.split('?')[1]);
      return (await service({ list: query.get('kind') ? [item({ kind: 'PURCHASE' })] : [item()] })(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();
    await screen.findByRole('row', { name: /Retail sales/ });

    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'SALES');

    expect(await screen.findByText(/did not match this company/)).toBeInTheDocument();
    expect(screen.queryByRole('row', { name: /Retail sales/ })).not.toBeInTheDocument();
  });
});

describe('when there is nothing, or something goes wrong', () => {
  it('invites the first type to a manager, and only explains to a reader', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ list: [] }));
    mount();
    expect(await screen.findByText('No voucher types yet')).toBeInTheDocument();
    expect(screen.getByText(/Create the first one/)).toBeInTheDocument();
  });

  it('tells a reader nothing has been created, without telling them to create it', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ list: [] }));
    mount(false);
    expect(await screen.findByText('None has been created for this company.')).toBeInTheDocument();
    expect(screen.queryByText(/Create the first one/)).not.toBeInTheDocument();
  });

  it('shows a refusal as a refusal', async () => {
    vi.mocked(serviceCall).mockRejectedValue({ status: 403, message: 'You may not read voucher types here.' });
    mount();
    expect(await screen.findByText('You may not read voucher types here.')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('refuses a list carrying another company’s row', async () => {
    vi.mocked(serviceCall).mockImplementation(service({ list: [item({ company_id: OTHER })] }));
    mount();
    expect(await screen.findByText(/did not match this company/)).toBeInTheDocument();
  });

  it('keeps the filters on screen when a filtered read fails, and offers a retry', async () => {
    let failing = false;
    vi.mocked(serviceCall).mockImplementation(async (endpoint, request) => {
      if (failing) throw { status: 500, message: 'The voucher service is unavailable.' };
      return (await service()(endpoint, request)) as never;
    });
    const user = userEvent.setup();
    mount();
    await screen.findByRole('row', { name: /Retail sales/ });

    failing = true;
    await user.selectOptions(screen.getByRole('combobox', { name: 'Kind' }), 'SALES');

    expect(await screen.findByText('The voucher service is unavailable.')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Kind' })).toHaveValue('SALES');
    failing = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('row', { name: /Retail sales/ })).toBeInTheDocument();
  });

  it('pages with the service’s cursor', async () => {
    vi.mocked(serviceCall).mockImplementation(
      service({ list: [item()], listPage: { ...page, has_more: true, next_cursor: 'abc' } }),
    );
    const user = userEvent.setup();
    mount();
    await screen.findByRole('row', { name: /Retail sales/ });

    await user.click(screen.getByRole('button', { name: /next/i }));

    await waitFor(() => expect(new URLSearchParams(lastRead('/voucher-types').split('?')[1]).get('cursor')).toBe('abc'));
  });
});
