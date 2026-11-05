import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ActivityFeed } from '../app/components/ActivityFeed';
import { AuditApiError } from '../app/lib/audit-api';
import type { ActivityPage } from '../app/lib/activity-api';

const event = { id: 'event', occurred_at: '2026-10-29T00:00:00Z', action: 'catalog.item.create', entity_type: 'catalog.item', entity_id: 'item', actor_user_id: null, actor_type: null, on_behalf_of_user_id: null, source_service: 'catalog', category: 'admin', company_id: 'company' };
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

it('loads activity with audit navigation only for audit readers', async () => {
  const load = vi.fn().mockResolvedValue({ items: [event], page: { has_more: false, next_cursor: null } });
  const view = render(<ActivityFeed company="company" load={load} />);
  expect(await screen.findByText('catalog.item.create')).toBeVisible();
  expect(screen.queryByRole('link', { name: 'View audit history' })).not.toBeInTheDocument();
  view.rerender(<ActivityFeed company="company" load={load} canAudit />);
  fireEvent.click(screen.getByRole('button', { name: /actions/i }));
  expect(screen.getByRole('menuitem', { name: 'View audit history' })).toHaveAttribute('href', expect.stringContaining('company_id=company'));
});

it.each([401, 403, 422, 500, 503])('shows safe failure and recovery for %s', async status => {
  const load = vi.fn().mockRejectedValueOnce(new AuditApiError(status)).mockResolvedValue({ items: [], page: { has_more: false, next_cursor: null } });
  render(<ActivityFeed company="company" load={load} />);
  expect(await screen.findByText(new AuditApiError(status).message)).toBeVisible();
  expect(screen.queryByText('No events')).not.toBeInTheDocument();
  fireEvent.click(screen.getAllByRole('button', { name: status === 422 ? 'Return to recent activity' : 'Try again' })[0]!);
  expect(await screen.findByText('No recorded activity')).toBeVisible();
});

it('polls the first page, follows signed cursors and aborts on unmount', async () => {
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  vi.useFakeTimers();
  const load = vi.fn().mockResolvedValue({ items: [event], page: { has_more: true, next_cursor: 'signed' } });
  const view = render(<ActivityFeed company="company" load={load} />);
  await act(async () => {});
  expect(screen.getByText('catalog.item.create')).toBeVisible();
  await act(async () => { vi.advanceTimersByTime(30_000); });
  expect(load).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole('button', { name: /next/i }));
  await act(async () => {});
  expect(load).toHaveBeenLastCalledWith('signed', expect.any(AbortSignal));
  const calls = load.mock.calls.length;
  await act(async () => { vi.advanceTimersByTime(60_000); });
  expect(load).toHaveBeenCalledTimes(calls);
  const signal = load.mock.calls.at(-1)![1] as AbortSignal;
  view.unmount();
  expect(signal.aborted).toBe(true);
});

it('presents a rejected activity cursor as one validation failure', async () => {
  const load = vi.fn().mockRejectedValue(new AuditApiError(422));
  render(<ActivityFeed company="company" load={load} />);
  expect(await screen.findByText(new AuditApiError(422).message)).toBeVisible();
  expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
  expect(screen.getByText("We couldn't accept those details")).toBeVisible();
  expect(screen.getByRole('button', { name: 'Return to recent activity' })).toBeVisible();
});

it('keeps rows during refresh and clears them when refreshed access fails', async () => {
  let rejectRefresh!: (error: Error) => void;
  const load = vi.fn().mockResolvedValueOnce({ items: [event], page: { has_more: false, next_cursor: null } })
    .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectRefresh = reject; }));
  render(<ActivityFeed company="company" load={load} />);
  await screen.findByText(event.action);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh activity' }));
  expect(screen.getByText(event.action)).toBeVisible();
  expect(screen.getByRole('button', { name: 'Refresh activity' })).toBeDisabled();
  await act(async () => rejectRefresh(new AuditApiError(403)));
  expect(screen.queryByText(event.action)).not.toBeInTheDocument();
  expect(screen.getByText(new AuditApiError(403).message)).toBeVisible();
});

it('discards old company rows and cursors immediately when the company changes', async () => {
  let resolveNext!: (page: ActivityPage) => void;
  const load = vi.fn().mockResolvedValue({ items: [event], page: { has_more: true, next_cursor: 'company-signed' } });
  const nextLoad = vi.fn().mockImplementation(() => new Promise<ActivityPage>(resolve => { resolveNext = resolve; }));
  const view = render(<ActivityFeed company="company" load={load} canAudit />);
  await screen.findByText(event.action);
  fireEvent.click(screen.getByRole('button', { name: /next/i }));
  await act(async () => {});
  view.rerender(<ActivityFeed company="other" load={nextLoad} canAudit />);
  expect(screen.queryByText(event.action)).not.toBeInTheDocument();
  expect(nextLoad).toHaveBeenLastCalledWith(null, expect.any(AbortSignal));
  expect(load.mock.calls.at(-1)![1].aborted).toBe(true);
  await act(async () => resolveNext({ items: [], page: { has_more: false, next_cursor: null } }));
  expect(screen.getByText('No recorded activity')).toBeVisible();
  expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
});

it('shows readable subject and actor references with the full IDs available', async () => {
  const row = { ...event, entity_id: '0192f480-2a10-7f01-8c22-91ab55c30011', actor_user_id: '0192f001-9d10-7a41-b001-7c2d90ae0001' };
  render(<ActivityFeed company="company" load={async () => ({ items: [row], page: { has_more: false, next_cursor: null } })} />);
  expect(await screen.findByText('catalog.item ·c30011')).toHaveAttribute('title', row.entity_id);
  expect(screen.getByText('user ·ae0001')).toHaveAttribute('title', row.actor_user_id);
});

it('distinguishes system work from missing attribution and retains represented users', async () => {
  const load = vi.fn().mockResolvedValue({ items: [
    { ...event, id: 'system', action: 'system work', actor_type: 'system' },
    { ...event, id: 'missing', action: 'old event' },
    { ...event, id: 'support', action: 'represented action', actor_user_id: 'support-123456', actor_type: 'user', on_behalf_of_user_id: 'tenant-654321' },
  ], page: { has_more: false, next_cursor: null } });
  render(<ActivityFeed company="company" load={load} />);
  await screen.findByText('system work');
  expect(screen.getByText('system')).toBeVisible();
  expect(screen.getByText('Not recorded')).toBeVisible();
  expect(screen.getByText('user ·654321')).toHaveAttribute('title', 'tenant-654321');
});

it('shows organisation scope links only when authorized and uses each event scope in history links', async () => {
  const load = vi.fn().mockResolvedValue({ items: [{ ...event, company_id: null }], page: { has_more: false, next_cursor: null } });
  const view = render(<ActivityFeed company="company" load={load} canAudit />);
  await screen.findByText(event.action);
  expect(screen.queryByRole('navigation', { name: 'Activity scope' })).not.toBeInTheDocument();
  view.rerender(<ActivityFeed company="company" organisation canOrganisation canAudit load={load} />);
  await screen.findByText(event.action);
  expect(screen.getByRole('link', { name: 'Organisation activity' })).toHaveAttribute('aria-current', 'page');
  fireEvent.click(screen.getByRole('button', { name: /actions/i }));
  expect(screen.getByRole('menuitem', { name: 'View audit history' })).toHaveAttribute('href', expect.stringContaining('scope=organisation'));
});

it('links cross-company organisation events to their recorded company', async () => {
  render(<ActivityFeed company="company" organisation canOrganisation canAudit load={async () => ({ items: [{ ...event, company_id: 'other' }], page: { has_more: false, next_cursor: null } })} />);
  await screen.findByText(event.action);
  fireEvent.click(screen.getByRole('button', { name: /actions/i }));
  expect(screen.getByRole('menuitem', { name: 'View audit history' })).toHaveAttribute('href', expect.stringContaining('company_id=other'));
});

it('clears old rows and paging when switching activity scope', async () => {
  let resolveOrganisation!: (page: ActivityPage) => void;
  const load = vi.fn().mockResolvedValueOnce({ items: [event], page: { has_more: true, next_cursor: 'company-cursor' } })
    .mockImplementation(() => new Promise<ActivityPage>(resolve => { resolveOrganisation = resolve; }));
  const view = render(<ActivityFeed company="company" canOrganisation load={load} />);
  await screen.findByText(event.action);
  const oldSignal = load.mock.calls[0]![1] as AbortSignal;
  view.rerender(<ActivityFeed company="company" organisation canOrganisation load={load} />);
  expect(screen.queryByText(event.action)).not.toBeInTheDocument();
  expect(oldSignal.aborted).toBe(true);
  expect(load).toHaveBeenLastCalledWith(null, expect.any(AbortSignal));
  await act(async () => resolveOrganisation({ items: [], page: { has_more: false, next_cursor: null } }));
  expect(screen.getByText('No recorded activity')).toBeVisible();
});
