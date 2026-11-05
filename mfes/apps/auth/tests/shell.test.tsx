import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { AuthShell } from '../app/components/AuthShell';
import { renderScreen } from './helpers';

/** The shell contains a `ThemeSwitcher`, which needs the provider the layout mounts. */
function renderShell(children: React.ReactNode = <span />) {
  return renderScreen(<AuthShell>{children}</AuthShell>);
}

describe('AuthShell + BrandPanel', () => {
  it('uses the wider registration form without changing the default shell', () => {
    const result = renderScreen(<AuthShell registration><span>registration</span></AuthShell>);
    expect(result.container.querySelector('.auth')).toHaveClass('janso-registration');
  });
  it('renders the value panel beside the form', () => {
    renderShell(<p>form goes here</p>);

    expect(screen.getByText('form goes here')).toBeInTheDocument();
    // meaningful-before-login value rows, not a fake balance
    expect(screen.getByText('Invoice in seconds')).toBeInTheDocument();
    expect(screen.getByText('Books that always balance')).toBeInTheDocument();
    expect(screen.getByText('Stock you can trust')).toBeInTheDocument();
    expect(screen.getByText('Billing, accounting and inventory.')).toBeInTheDocument();
  });

  it('keeps the drawing on the panel out of the accessibility tree, and the lockup the only logo', () => {
    const { container } = renderShell();

    const sheet = container.querySelector('.auth__sheet');
    expect(sheet).toHaveAttribute('aria-hidden', 'true');
    // Decoration only: it holds no text and nothing focusable, and is not a second "KiscoBooks" image.
    expect(sheet?.textContent).toBe('');
    expect(sheet?.querySelector('a, button, input, [tabindex]')).toBeNull();
    expect(screen.getAllByRole('img', { name: 'KiscoBooks' })).toHaveLength(2); // panel + phone header
    expect(container.querySelectorAll('.auth__balance')).toHaveLength(1);
  });

  it('states the privacy reassurance and the brand lockup', () => {
    renderShell();

    expect(screen.getByText(/only people you invite can open your workspace/i)).toBeInTheDocument();
    expect(screen.getAllByRole('img', { name: 'KiscoBooks' }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('always balances')).toBeInTheDocument();
  });

  it('lets a returning user pick a palette before signing in', () => {
    renderShell();

    expect(screen.getByRole('radiogroup', { name: /theme/i })).toBeInTheDocument();
    for (const name of ['Light', 'Dark', 'Ledger', 'System']) {
      expect(screen.getByRole('radio', { name })).toBeInTheDocument();
    }
  });

  it('applies a chosen palette to the document', async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(screen.getByRole('radio', { name: 'Ledger' }));

    expect(document.documentElement).toHaveAttribute('data-theme', 'ledger');
    // Warm paper is a light scheme, so native controls must not flip to dark.
    expect(document.documentElement.style.colorScheme).toBe('light');
  });

  it('carries a quiet legal footer', () => {
    renderShell();

    const legal = screen.getByRole('navigation', { name: 'Legal' });
    expect(legal).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Terms' })).toHaveAttribute('href', '/terms');
    expect(screen.getByRole('link', { name: 'Privacy' })).toHaveAttribute('href', '/privacy');
    expect(screen.getByRole('link', { name: 'Help' })).toHaveAttribute('href', '/help');
  });

  it('takes the copyright year from the clock, not a hardcoded value', () => {
    renderShell();

    const year = new Date().getFullYear();
    expect(screen.getByText(`© ${year} Khushiyan Enterprise`)).toBeInTheDocument();
  });
});
