import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { PlatformDetailsForm } from '../app/platform/details/PlatformDetailsForm';
const { fetcher } = vi.hoisted(() => ({ fetcher: vi.fn() }));
vi.mock('../app/lib/session-fetch', () => ({ sessionFetch: fetcher }));
const details = { name: 'JANSO', public_url: 'http://localhost:4320' };
beforeEach(() => { fetcher.mockReset(); sessionStorage.clear(); fetcher.mockImplementation(async () => Response.json(details)); });
it('loads and saves platform metadata with a clear confirmation', async () => {
  render(<PlatformDetailsForm scope="operator" />);
  const name = await screen.findByRole('textbox', { name: 'Platform name' });
  expect(name).toHaveValue('JANSO'); fireEvent.change(name, { target: { value: 'JANSO Retail' } });
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByText('Platform details updated.')).toBeInTheDocument();
  expect(JSON.parse(fetcher.mock.lastCall![1].body)).toMatchObject({ method: 'PATCH', path: '/v1/platform/details', body: { name: 'JANSO Retail' } });
});
it('carries the shared back chevron and breadcrumb trail, not a bare text link', async () => {
  const { container } = render(<PlatformDetailsForm scope="operator" />);
  await screen.findByRole('textbox', { name: 'Platform name' });
  expect(screen.getByRole('link', { name: 'Back to platform administration' })).toHaveAttribute('href', '/platform');
  const crumbs = within(screen.getByRole('navigation', { name: 'Breadcrumb' }));
  expect(crumbs.getByRole('link', { name: 'Platform administration' })).toHaveAttribute('href', '/platform');
  expect(crumbs.getByText('Platform details')).toHaveAttribute('aria-current', 'page');
  expect(container.querySelector('.janso-grid--split')).toBeInTheDocument();
  const footer = container.querySelector('.janso-card__footer')!;
  expect(within(footer as HTMLElement).getByRole('link', { name: 'Cancel' })).toBeInTheDocument();
  expect(footer.querySelector('.janso-form-actions')).toContainElement(screen.getByRole('button', { name: 'Save changes' }));
});
it('confirms a discard before any route out of the editor', async () => {
  const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
  render(<PlatformDetailsForm scope="operator" />);
  fireEvent.change(await screen.findByRole('textbox', { name: 'Platform name' }), { target: { value: 'JANSO Retail' } });
  for (const name of ['Back to platform administration', 'Platform administration', 'Cancel']) {
    fireEvent.click(screen.getByRole('link', { name }));
  }
  expect(confirm).toHaveBeenCalledTimes(3);
  confirm.mockRestore();
});
it('validates names and origins and focuses the first invalid field', async () => {
  render(<PlatformDetailsForm scope="operator" />); const name = await screen.findByRole('textbox', { name: 'Platform name' });
  fireEvent.change(name, { target: { value: '  ' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Public application URL' }), { target: { value: 'http://remote.invalid/path' } });
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(name).toHaveFocus(); expect(name).toHaveAttribute('aria-invalid', 'true'); expect(fetcher).toHaveBeenCalledTimes(1);
});
it.each([401, 403, 404, 500])('provides a deliberate loading error for %i without editable fields', async status => {
  fetcher.mockResolvedValue(Response.json({ error: { message: 'Cannot load details' } }, { status }));
  render(<PlatformDetailsForm scope="operator" />); expect(await screen.findByRole('alert')).toHaveTextContent('Cannot load details');
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  expect(!!screen.queryByRole('link', { name: 'Sign in again' })).toBe(status === 401);
});
it('preserves the draft only for explicit fresh sign-in and restores it without submitting', async () => {
  const view = render(<PlatformDetailsForm scope="operator" />);
  fireEvent.change(await screen.findByRole('textbox', { name: 'Platform name' }), { target: { value: 'Recovered draft' } });
  fetcher.mockResolvedValue(Response.json({ error: { code: 'platform_reauthentication_required', message: 'Confirm this change' } }, { status: 403 }));
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));
  const link = await screen.findByRole('link', { name: 'Sign in again' });
  expect(link).toHaveAttribute('href', expect.stringContaining('returnTo=%2Fplatform%2Fdetails'));
  link.addEventListener('click', event => event.preventDefault());
  fireEvent.click(link); view.unmount(); fetcher.mockImplementation(async () => Response.json(details));
  render(<PlatformDetailsForm scope="operator" />);
  await waitFor(() => expect(screen.getByRole('textbox', { name: 'Platform name' })).toHaveValue('Recovered draft'));
  expect(sessionStorage.length).toBe(0);
});
it('disables submission while saving and surfaces server validation', async () => {
  render(<PlatformDetailsForm scope="operator" />); await screen.findByRole('textbox', { name: 'Platform name' });
  let finish!: (value: Response) => void; fetcher.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  await userEvent.click(screen.getByRole('button', { name: 'Save changes' })); expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
  finish(Response.json({ error: { message: 'Check platform name', fields: { name: 'invalid' } } }, { status: 422 }));
  expect(await screen.findByText('Check platform name')).toBeInTheDocument();
  expect(screen.getByRole('textbox', { name: 'Platform name' })).toHaveAttribute('aria-invalid', 'true');
});
