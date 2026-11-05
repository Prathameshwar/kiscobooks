import { describe, expect, it } from 'vitest';
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConsoleShell } from '../app/components/ConsoleShell';
import type { Session } from '../app/session';
import { companyContextFor, renderWithProviders } from './helpers';

declare const __emitPrefersDark: (value: boolean) => void;

const shell = (session: Session) => (
  <ConsoleShell session={session} context={companyContextFor()} activeHref="/">
    <p>Content</p>
  </ConsoleShell>
);

/**
 * The theme system is unit-tested inside @janso/ui. These are the integration facts: that the
 * console's real `<Providers>` actually mounts it, that a switch repaints the whole document,
 * and that the choice survives — the parts a component test cannot prove.
 */
describe('theming, end to end in the console', () => {
  it('applies each of the three palettes from the switcher', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);

    expect(document.documentElement).toHaveAttribute('data-theme', 'light');

    await user.click(screen.getByRole('radio', { name: 'Dark' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(document.documentElement.style.colorScheme).toBe('dark');

    await user.click(screen.getByRole('radio', { name: 'Ledger' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'ledger');
    // Ledger is warm paper, so native controls and scrollbars must stay in the light scheme.
    expect(document.documentElement.style.colorScheme).toBe('light');

    await user.click(screen.getByRole('radio', { name: 'Light' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');
  });

  it('follows the operating system while the preference is System', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);

    await user.click(screen.getByRole('radio', { name: 'System' }));
    expect(document.documentElement).toHaveAttribute('data-theme', 'light');

    // The OS change fires outside React's event system, so flush it explicitly.
    await act(async () => __emitPrefersDark(true));
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
  });

  it('stops following the operating system once an explicit palette is chosen', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);

    await user.click(screen.getByRole('radio', { name: 'System' }));
    await user.click(screen.getByRole('radio', { name: 'Ledger' }));

    await act(async () => __emitPrefersDark(true));
    expect(document.documentElement).toHaveAttribute('data-theme', 'ledger');
  });

  it('persists the preference so a reload does not flash the wrong palette', async () => {
    const user = userEvent.setup();
    const { unmount } = await renderWithProviders(shell);

    await user.click(screen.getByRole('radio', { name: 'Dark' }));
    unmount();

    // Remount with no stored session preference, as a fresh page load would: the client
    // stores win, which is also what the pre-paint script already painted.
    await renderWithProviders(shell, { theme: null });
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
    expect(screen.getByRole('radio', { name: 'Dark' })).toHaveAttribute('aria-checked', 'true');
  });

  it("takes the session's stored preference over the client stores", async () => {
    // `user.theme` outranks the cookie and localStorage (design-system §2.2), and the real
    // `<Providers>` is the component that has to pass it through.
    await renderWithProviders(shell, { theme: 'ledger' });

    expect(document.documentElement).toHaveAttribute('data-theme', 'ledger');
  });

  it('keeps the dashboard readable in every palette', async () => {
    const user = userEvent.setup();
    await renderWithProviders(shell);

    for (const theme of ['Dark', 'Ledger', 'Light']) {
      await user.click(screen.getByRole('radio', { name: theme }));
      // Nothing should unmount or blank out on a palette change — colour is CSS-only.
      expect(screen.getByRole('main')).toBeInTheDocument();
      expect(screen.getByText('Content')).toBeInTheDocument();
    }
  });
});
