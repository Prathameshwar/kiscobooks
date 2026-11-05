import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

/*
 * `auth` is a different origin in development, so signing out leaves this app. `goTo` is
 * mocked rather than jsdom's `location`, which is read-only.
 */
vi.mock('../app/lib/navigate', () => ({
  signInUrl: () => 'http://localhost:4310/login',
  authActionUrl: (path: string) => 'http://localhost:4310' + path,
  goTo: vi.fn(),
}));

const { goTo } = await import('../app/lib/navigate');

beforeEach(() => {
  vi.mocked(goTo).mockClear();
});
import { ConsoleShell } from '../app/components/ConsoleShell';
import type { Session } from '../app/session';
import { companyContextFor, renderWithProviders, sessionFor } from './helpers';

/**
 * The shell takes the session as a prop — the page resolves it per request — so the test hands
 * it the same object the providers were given rather than importing a shared module constant.
 */
const shell = (session: Session) => (
  <ConsoleShell session={{ ...session, company: { ...session.company, id: session.company.id ?? '01990000-0000-7000-8000-000000000001' },
    grants: session.grants ?? [{ scope_type: 'tenant', scope_id: null, permissions: session.permissions, valid_from: '2000-01-01', valid_to: null }] }} context={companyContextFor()} activeHref="/">
    <p>Content</p>
  </ConsoleShell>
);

describe('ConsoleShell', () => {
  it('shows the new product and publisher while preserving the signed-in company', async () => {
    const { session } = await renderWithProviders(shell);
    expect(screen.getByRole('img', { name: 'KiscoBooks' })).toBeInTheDocument();
    expect(screen.getByText(`KiscoBooks · © ${new Date().getFullYear()} Khushiyan Enterprise. All rights reserved.`)).toBeInTheDocument();
    expect(screen.getAllByText(session.company.name).length).toBeGreaterThanOrEqual(1);
  });
  it('opens self access from the account menu without administrative permissions', async () => {
    const { session } = await renderWithProviders(shell, { permissions: [] });
    await userEvent.click(screen.getByRole('button', { name: new RegExp(session.user.name) }));
    await userEvent.click(screen.getByRole('menuitem', { name: 'My access' }));
    expect(goTo).toHaveBeenCalledWith('/my-access');
  });
  it('opens password change immediately above separated Sign out', async () => {
    const { session } = await renderWithProviders(shell);
    await userEvent.click(screen.getByRole('button', { name: new RegExp(session.user.name) }));
    const items = screen.getAllByRole('menuitem');
    expect(items.at(-2)).toHaveAccessibleName('Change password');
    expect(items.at(-1)).toHaveAccessibleName('Sign out');
    expect(screen.getByRole('separator')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('menuitem', { name:'Change password' }));
    expect(goTo).toHaveBeenCalledWith('http://localhost:4310/change-password');
  });
  it.each([{ permissions: [] }, { permissions: ['platform.tenant.read'] }])('keeps Settings only in the pinned menu for $permissions', async ({ permissions }) => {
    await renderWithProviders(session => <ConsoleShell session={session} context={companyContextFor()} activeHref="/settings"><p>Content</p></ConsoleShell>, { permissions });
    expect(screen.getAllByRole('link', { name: 'Company settings' })).toHaveLength(1);
    const settings = within(screen.getByRole('navigation', { name: 'Support' })).getByRole('link', { name: 'Company settings' });
    expect(settings).toHaveAttribute('href', '/settings');
    expect(settings).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('link', { name: 'Settings' })).not.toBeInTheDocument();
    if (permissions.length) expect(screen.getByRole('link', { name: 'Platform administration' })).toBeInTheDocument();
  });
  it('renders the rail, the top bar and the content region', async () => {
    const { session } = await renderWithProviders(shell);

    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByText('Content')).toBeInTheDocument();
    // The rail's switcher names the open **company** now, not the tenant; the tenant stays on
    // the user card and in the account menu.
    expect(screen.getAllByText(session.user.secondary).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Account: ' + session.role)).toBeInTheDocument();
    expect(screen.getAllByText(session.company.name).length).toBeGreaterThanOrEqual(1);
  });

  it('marks the current route and only the current route', async () => {
    await renderWithProviders(shell);

    const current = screen.getAllByRole('link', { current: 'page' });
    expect(current).toHaveLength(1);
    expect(current[0]).toHaveAccessibleName(/Business overview/);
  });

  it('shows a nav item the role can reach and hides one it cannot', async () => {
    await renderWithProviders(shell);

    // The session holds invoice.read but not ledger.read or role.read.
    expect(screen.getByRole('link', { name: /Reports/ })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Ledgers/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Roles & access/ })).not.toBeInTheDocument();
  });

  it('shows available destinations while keeping future pages hidden with broad permissions', async () => {
    const base = await sessionFor();
    await renderWithProviders(shell, {
      permissions: [...base.permissions, 'ledger.read', 'role.read', 'stock.read'],
    });

    expect(screen.queryByRole('link', { name: /Ledgers/ })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Roles & access/ })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Stock ledger' })).toHaveAttribute('href', '/books/stock-ledger');
  });

  it('makes scoped role review reachable in the rail and command palette', async () => {
    const session = await sessionFor();
    session.grants = [{ permissions: ['role.read', 'ledger.read'], scope_type: 'department', scope_id: 'department', valid_from: '2000-01-01', valid_to: null }];
    await renderWithProviders(shell(session), { permissions: session.permissions });
    expect(screen.getByRole('link', { name: /Roles & access/ })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Ledgers/ })).not.toBeInTheDocument();
    await userEvent.keyboard('{Control>}k{/Control}');
    expect(screen.getByRole('option', { name: /Roles & access/ })).toBeInTheDocument();
  });

  it('collapses and expands the rail, keeping each item named while collapsed', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);

    const toggle = screen.getByRole('button', { name: /Collapse sidebar/i });
    await user.click(toggle);

    expect(screen.getByRole('button', { name: /Expand sidebar/i })).toBeInTheDocument();
    // Collapsing is a visual affordance; losing the accessible name would make the whole
    // navigation unusable with a screen reader.
    expect(screen.getByRole('link', { name: /Reports/ })).toBeInTheDocument();
  });

  it('announces unread notifications by count, not by a coloured dot alone', async () => {
    await renderWithProviders(shell);

    expect(screen.getByRole('button', { name: /3 unread/i })).toBeInTheDocument();
  });

  it('offers the theme switcher as a labelled radio group of four options', async () => {
    await renderWithProviders(shell);

    const group = screen.getByRole('radiogroup', { name: /theme/i });
    expect(group).toBeInTheDocument();
    for (const name of ['Light', 'Dark', 'Ledger', 'System']) {
      expect(screen.getByRole('radio', { name })).toBeInTheDocument();
    }
  });

  it('sends sign out to Auth confirmation', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);

    await user.click(screen.getByRole('button', { name: /Prathameshwar Singh/i }));
    await user.click(screen.getByRole('menuitem', { name: 'Sign out' }));

    expect(goTo).toHaveBeenCalledWith('http://localhost:4310/logout');
  });

  it('offers working account actions and omits unimplemented entries', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);
    await user.click(screen.getByRole('button', { name: /Prathameshwar Singh/i }));
    expect(screen.queryByRole('menuitem', { name: 'Your profile' })).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Preferences' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('menuitem', { name: 'My access' }));
    expect(goTo).toHaveBeenCalledWith('/my-access');
  });

  it('retains the footer without links to missing pages', async () => {
    await renderWithProviders(shell);
    for (const name of ['API status', 'Documentation', 'Feedback', 'Help']) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument();
    }
    expect(screen.getByText(/All rights reserved/)).toBeInTheDocument();
  });

});

describe('ConsoleShell command palette', () => {
  it('keeps Settings available through the command palette', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);
    await user.keyboard('{Control>}k{/Control}');
    await user.keyboard('settings');
    const option = screen.getByRole('option', { name: /^Company settings/ });
    await user.click(option);
    expect(goTo).toHaveBeenCalledWith('/settings');
  });
  it('opens from the top-bar trigger and from Ctrl+K', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);

    await user.click(screen.getByRole('button', { name: /Search or jump to/ }));
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.keyboard('{Control>}k{/Control}');
    expect(screen.getByRole('dialog', { name: 'Command palette' })).toBeInTheDocument();
  });

  it('offers exactly the destinations the rail shows — a denied page is absent from both', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);
    await user.keyboard('{Control>}k{/Control}');

    const offered = screen.getAllByRole('option').map((option) => option.textContent ?? '');
    expect(offered.some((label) => label.startsWith('Reports'))).toBe(true);
    // The session holds neither ledger.read nor role.read, so neither the rail nor the palette has them.
    expect(offered.some((label) => label.startsWith('Ledgers'))).toBe(false);
    expect(offered.some((label) => label.startsWith('Roles & access'))).toBe(false);
  });

  it('navigates to the chosen destination', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);
    await user.keyboard('{Control>}k{/Control}');
    await user.keyboard('reports{Enter}');
    expect(goTo).toHaveBeenCalledWith('/reports');
  });
});
