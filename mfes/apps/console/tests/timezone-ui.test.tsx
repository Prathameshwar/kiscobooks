import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { TimezoneDirectory } from '../app/platform/references/timezones/TimezoneDirectory';
import TimezonePage from '../app/platform/references/timezones/page';
import { allowedPlatformRequest } from '../app/lib/platform-request';
const { fetcher, context } = vi.hoisted(() => ({ fetcher: vi.fn(), context: vi.fn() }));
vi.mock('../app/lib/session-fetch', () => ({ sessionFetch: fetcher }));
vi.mock('../app/lib/page-context', () => ({ pageContext: context }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
const data = { items: [{ code: 'Asia/Kolkata', name: 'Kolkata', is_active: true }, { code: 'UTC', name: 'UTC', is_active: false }], page: { next_cursor: null, has_more: false } };
beforeEach(() => { vi.clearAllMocks(); window.history.replaceState({}, '', '/platform/references/timezones'); fetcher.mockResolvedValue(Response.json(data)); context.mockResolvedValue({ session: { permissions: ['platform.config.manage'] }, context: {} }); });
const show = () => render(<DisplayConfigProvider><TimezoneDirectory /></DisplayConfigProvider>);
it('provides a read-only searchable IANA directory with availability and navigation', async () => {
  show(); await screen.findByText('Asia/Kolkata'); expect(screen.getAllByText('Archived').length).toBeGreaterThan(0);
  expect(screen.getByRole('link', { name: 'Back to reference data' })).toHaveAttribute('href', '/platform/references');
  expect(screen.queryByRole('button', { name: /Edit|Delete|Create/ })).not.toBeInTheDocument();
  expect(screen.getByText(/UTC offsets depend on the date/)).toBeInTheDocument();
});
it('gates the server page before loading reference data', async () => {
  const view = render(await TimezonePage()); await screen.findByText('Asia/Kolkata'); view.unmount(); context.mockResolvedValue({ session: { permissions: [] }, context: {} });
  render(await TimezonePage()); expect(screen.getByRole('alert')).toHaveTextContent('Platform configuration permission');
});
it.each([401, 403, 422, 500])('shows a meaningful %s failure and clears old rows', async status => {
  fetcher.mockResolvedValue(Response.json({ error: { message: 'Timezone request failed' } }, { status })); show(); await screen.findByText('Timezone request failed'); expect(screen.queryByText('Asia/Kolkata')).not.toBeInTheDocument();
  if (status === 401) expect(screen.getByRole('link', { name: /sign in/i })).toBeInTheDocument();
});
it('recovers from a failed read and exposes no create action in the empty state', async () => {
  fetcher.mockRejectedValueOnce(new Error('network')).mockImplementation(async () => Response.json({ ...data, items: [] })); show(); await screen.findByText(/unavailable/i);
  await userEvent.click(screen.getByRole('button', { name: 'Refresh' })); await screen.findByText('No timezones available');
});
it('binds search and availability to bounded directory queries', async () => {
  fetcher.mockImplementation(async () => Response.json(data)); show(); await screen.findByText('Asia/Kolkata');
  fireEvent.change(screen.getByRole('searchbox', { name: 'Search timezones' }), { target: { value: 'Asia' } });
  await waitFor(() => expect(fetcher.mock.calls.some(([, init]) => JSON.parse(init.body).path.includes('q=Asia'))).toBe(true));
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Availability' }), 'archived');
  await waitFor(() => expect(fetcher.mock.calls.some(([, init]) => JSON.parse(init.body).path.includes('status=archived'))).toBe(true));
});
it.each(['?limit=0', '?limit=201', '?limit=1&limit=2', '?sort=offset', '?q=A', '?status=bad', '?country_code=IN', '/UTC', '/UTC/archive'])('rejects unsupported timezone proxy input %s', suffix => {
  expect(allowedPlatformRequest('GET', '/v1/platform/references/timezones' + suffix)).toBe(false);
});
it('allows signed paging inputs and rejects all timezone writes', () => {
  const path = '/v1/platform/references/timezones?q=Asia&status=active&sort=-code&limit=50&cursor=signed'; expect(allowedPlatformRequest('GET', path)).toBe(true);
  expect(allowedPlatformRequest('POST', '/v1/platform/references/timezones')).toBe(false);
});
