/** The New menu offers accessible links only to a currently authorized voucher creator. */
import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../app/lib/navigate', () => ({
  signInUrl: () => 'http://localhost:4310/login',
  authActionUrl: (path: string) => 'http://localhost:4310' + path,
  goTo: vi.fn(),
}));

import { ConsoleShell } from '../app/components/ConsoleShell';
import { newVoucherActions, showNewVoucher } from '../app/lib/new-voucher-actions';
import type { Session } from '../app/session';
import { companyContextFor, renderWithProviders } from './helpers';

const COMPANY = '01990000-0000-7000-8000-000000000001';

/** The shell as a page mounts it, with the company and the grants a test asks for. */
function shellFor({ noCompany = false, grantPermissions }: { noCompany?: boolean; grantPermissions?: string[] } = {}) {
  return (session: Session) => (
    <ConsoleShell
      session={{
        ...session,
        // Not `id: company` with an `undefined` default: a destructuring default fires on an
        // `undefined` property, so "no company" would silently become the open one.
        company: { ...session.company, id: noCompany ? undefined : COMPANY },
        grants: [
          {
            scope_type: 'tenant',
            scope_id: null,
            permissions: grantPermissions ?? session.permissions,
            valid_from: '2000-01-01',
            valid_to: null,
          },
        ],
      }}
      context={companyContextFor()}
      activeHref="/"
    >
      <p>Content</p>
    </ConsoleShell>
  );
}

/** Administration alone does not grant voucher creation. */
const ADMIN = ['company.read', 'vouchers.type.manage'];
const CREATOR = ['vouchers.read', 'vouchers.create'];

async function openNew(
  options: Parameters<typeof shellFor>[0] = {},
  permissions: string[] = CREATOR,
) {
  const view = await renderWithProviders(shellFor({ grantPermissions: permissions, ...options }), {
    permissions,
  });
  const trigger = screen.getByRole('button', { name: 'New' });
  await userEvent.click(trigger);
  return { ...view, trigger, menu: screen.getByRole('menu', { name: 'New voucher' }) };
}

describe('New voucher actions', () => {
  it('offers every kind as a link to its own page, in the agreed order', async () => {
    const { menu } = await openNew();

    expect(
      within(menu)
        .getAllByRole('menuitem')
        .map((item) => [item.textContent, item.getAttribute('href')]),
    ).toEqual([
      ['Sales', '/vouchers/new/sales'],
      ['Receipt', '/vouchers/new/receipt'],
      ['Purchase', '/vouchers/new/purchase'],
      ['Payment', '/vouchers/new/payment'],
      ['Stock adjustment', '/vouchers/new/stock-adjustment'],
    ]);
  });

  it('bands the verbs: sales pair, purchase pair, then the stock correction', async () => {
    const { menu } = await openNew();

    expect(within(menu).getAllByRole('separator')).toHaveLength(2);
    expect(
      [...menu.children].map((node) => node.getAttribute('role') === 'separator' ? '—' : node.textContent),
    ).toEqual(['Sales', 'Receipt', '—', 'Purchase', 'Payment', '—', 'Stock adjustment']);
  });

  it('is the bar’s primary action and advertises its menu', async () => {
    await renderWithProviders(shellFor({ grantPermissions: CREATOR }), { permissions: CREATOR });
    const trigger = screen.getByRole('button', { name: 'New' });

    expect(trigger).toHaveClass('janso-menu__trigger--primary');
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu');
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes on Escape and hands focus back, so the keyboard path is not a trap', async () => {
    const { trigger } = await openNew();

    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('menu', { name: 'New voucher' })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it.each([
    { role: 'a company administrator', permissions: ['company.read', 'vouchers.type.manage'] },
    { role: 'a reader with no voucher authority at all', permissions: ['company.read'] },
    { role: 'a reader with no permissions at all', permissions: [] },
    { role: 'a voucher reader', permissions: ['vouchers.read'] },
    { role: 'a creator without read access', permissions: ['vouchers.create'] },
  ])('hides New from $role', async ({ permissions }) => {
    await renderWithProviders(shellFor({ grantPermissions: permissions }), { permissions });
    expect(screen.queryByRole('button', { name: 'New' })).not.toBeInTheDocument();
  });

  it('is absent with no company open, because a voucher is raised into one', async () => {
    await renderWithProviders(shellFor({ noCompany: true }), { permissions: ADMIN });

    expect(screen.queryByRole('button', { name: 'New' })).not.toBeInTheDocument();
  });
});

describe('showNewVoucher', () => {
  const withCompany = (id: string | undefined) =>
    ({ company: { name: 'Janso Retail Pvt Ltd', id }, grants: [] }) as unknown as Session;

  it('denies an open company without grants', () => {
    expect(showNewVoucher(withCompany(COMPANY))).toBe(false);
  });

  it('hides it when no company is open', () => {
    expect(showNewVoucher(withCompany(undefined))).toBe(false);
  });

  it('denies missing grants', () => {
    const granted = { ...withCompany(COMPANY), grants: undefined } as unknown as Session;
    expect(showNewVoucher(granted)).toBe(false);
  });
});

describe('the action list itself', () => {
  it('gates the whole menu on combined read/create authority', () => {
    expect(newVoucherActions.every((item) => item.permission === undefined)).toBe(true);
  });

  it('keeps each id equal to its destination, which is what the keyboard path navigates to', () => {
    expect(newVoucherActions.every((item) => item.id === item.href)).toBe(true);
  });
});
