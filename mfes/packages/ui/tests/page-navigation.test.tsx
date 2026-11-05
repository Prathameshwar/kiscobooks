import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { PageNavigation } from '../src/components/PageNavigation';

it('renders a named back link, ordered breadcrumbs and an unlinked current page', () => {
  render(<PageNavigation back={{ href: '/platform', label: 'platform administration' }} breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Tenants', href: '/platform/tenants' }]} />);
  const back = screen.getByRole('link', { name: 'Back to platform administration' });
  expect(back).toHaveAttribute('href', '/platform'); expect(back.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  const crumbs = screen.getByRole('navigation', { name: 'Breadcrumb' });
  expect(within(crumbs).getAllByRole('listitem')).toHaveLength(2);
  expect(within(crumbs).getByRole('link', { name: 'Platform administration' })).toHaveAttribute('href', '/platform');
  expect(within(crumbs).getByText('Tenants')).toHaveAttribute('aria-current', 'page');
  expect(within(crumbs).queryByRole('link', { name: 'Tenants' })).not.toBeInTheDocument();
});

it('supports breadcrumbs alone and degrades unsafe destinations to text', () => {
  render(<PageNavigation back={{ href: 'javascript:alert(1)', label: 'unsafe destination' }} breadcrumbs={[{ label: 'Unsafe', href: 'javascript:alert(1)' }, { label: 'Current' }]} />);
  expect(screen.queryByRole('link')).not.toBeInTheDocument(); expect(screen.getByText('Unsafe')).toBeInTheDocument();
  expect(screen.getByText('Current')).toHaveAttribute('aria-current', 'page');
});

it('reports every departure to onNavigate, so an unsaved draft is guarded once', async () => {
  const onNavigate = vi.fn();
  render(<PageNavigation back={{ href: '/platform/tenants', label: 'tenants' }} onNavigate={onNavigate}
    breadcrumbs={[{ label: 'Platform administration', href: '/platform' }, { label: 'Tenants', href: '/platform/tenants' }, { label: 'Edit tenant' }]} />);
  await userEvent.click(screen.getByRole('link', { name: 'Back to tenants' }));
  await userEvent.click(screen.getByRole('link', { name: 'Platform administration' }));
  await userEvent.click(screen.getByRole('link', { name: 'Tenants' }));
  expect(onNavigate).toHaveBeenCalledTimes(3);
});

it('supports back navigation alone and renders nothing without destinations', () => {
  const { rerender, container } = render(<PageNavigation back={{ href: '/settings', label: 'settings' }} />);
  expect(screen.getByRole('link', { name: 'Back to settings' })).toHaveAttribute('href', '/settings');
  expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  rerender(<PageNavigation />); expect(container).toBeEmptyDOMElement();
});
