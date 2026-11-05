/**
 * The chrome every notification area shares: the routed area strip, the grouped landing cards, the
 * cursor pager, the filter strip and what a list says when it holds nothing. These are one
 * implementation in `notifications/common.tsx`, so they are tested once here rather than being
 * re-asserted in each area's own file.
 */
import { beforeEach, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import { ID, VARIANT, VERSION, baseResponse, mountNotification, page, readPermissions, template } from './notification-fixtures';
const { call } = vi.hoisted(() => ({ call: vi.fn() }));
vi.mock('../app/lib/notification-api', async original => ({ ...await original<object>(), notificationCall: call }));
vi.mock('../app/components/PlatformHistory', () => ({ PlatformHistory: () => <p>Administrative history</p> }));
beforeEach(() => { call.mockReset(); call.mockImplementation(baseResponse); });

it('marks the open area in the area strip and leaves the others unmarked', async () => {
  await mountNotification(['templates']);
  const nav = screen.getByRole('navigation', { name: 'Notification areas' });
  expect(within(nav).getByRole('link', { name: 'Templates' })).toHaveAttribute('aria-current', 'page');
  expect(within(nav).getByRole('link', { name: 'Routing' })).not.toHaveAttribute('aria-current');
  expect(within(nav).getByRole('link', { name: 'Overview' })).toHaveAttribute('href', '/platform/notifications');
});
it('hides areas the actor cannot read from the strip as well as from the landing page', async () => {
  await mountNotification(['providers'], { permissions: ['platform.notification_provider.read'] });
  const nav = screen.getByRole('navigation', { name: 'Notification areas' });
  expect(within(nav).getByRole('link', { name: 'Providers and senders' })).toBeVisible();
  expect(within(nav).queryByRole('link', { name: 'Suppressions' })).not.toBeInTheDocument();
});
it('groups the landing cards in the order the work is done and describes each area', async () => {
  await mountNotification([]);
  for (const heading of ['Transport', 'Message content', 'Recipients and policy', 'What happened']) {
    expect(screen.getByRole('heading', { name: heading })).toBeVisible();
  }
  expect(screen.getByText('The verified provider, sender and retry policy a purpose sends through.')).toBeVisible();
  expect(screen.getByText('Deliveries with no settled outcome. A blind retry can send the message twice.')).toBeVisible();
});
it('reports each channel’s admission and readiness separately on the landing page', async () => {
  await mountNotification([]);
  // Two badges per channel, and they are different questions: enabled is a switch, ready is config.
  expect(screen.getAllByText('active').length).toBeGreaterThan(0);
  expect(screen.getAllByText('ready').length).toBeGreaterThan(0);
  expect(screen.getByText('no verified sender')).toBeVisible();
});
it('explains what a channel is still missing and withholds a switch that would not help', async () => {
  await mountNotification(['channels']);
  expect(within(screen.getByText('Outstanding for this channel').closest('.janso-notice')!).getByText('no verified sender')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Enable sms' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Disable email' })).toBeEnabled();
});
it('states the range it is showing and offers a step back to the first page', async () => {
  call.mockImplementation(async (owner, path, method, body) => path.startsWith('templates?') ? page([template], 'opaque cursor') : baseResponse(owner, path, method, body));
  await mountNotification(['templates'], { query: { cursor: 'held' } });
  const pager = screen.getByRole('navigation', { name: 'template pages' });
  expect(within(pager).getByText('Showing 1 template')).toBeVisible();
  expect(within(pager).getByRole('link', { name: 'First page' })).toHaveAttribute('href', '/platform/notifications/templates');
  expect(within(pager).getByRole('link', { name: 'Next page' })).toHaveAttribute('href', '/platform/notifications/templates?cursor=opaque+cursor');
});
it('does not state a range before the page it describes has arrived', async () => {
  // A page opened at a cursor has `back` true and no rows yet, which used to print "No templates"
  // over a table of loading skeletons that was about to fill.
  call.mockImplementation(async (owner, path, method, body) => path.startsWith('templates?') ? new Promise(() => {}) : baseResponse(owner, path, method, body));
  await mountNotification(['templates'], { query: { cursor: 'held' } });
  const pager = screen.getByRole('navigation', { name: 'template pages' });
  expect(within(pager).getByText('Loading…')).toBeVisible();
  expect(within(pager).queryByText('No templates')).not.toBeInTheDocument();
});
it('accounts for a predicate no form on the screen offers', async () => {
  // Arriving from a delivery's "View masked recipient" pins the list to one endpoint, and the
  // recipients form only offers a subject reference — so this is the chip that has to come from
  // the query rather than from the declared fields.
  await mountNotification(['recipients'], { query: { recipient_endpoint_id: ID } });
  const chips = screen.getByRole('group', { name: 'Filters in force' });
  expect(within(chips).getByText('Recipient endpoint')).toBeVisible();
  expect(within(chips).getByText(ID)).toBeVisible();
});
it('accounts for a filter that arrived in the address and offers to lift it', async () => {
  await mountNotification(['templates'], { query: { event_key: 'platform.staff.alert' } });
  const chips = screen.getByRole('group', { name: 'Filters in force' });
  expect(within(chips).getByText('platform / staff / alert')).toBeVisible();
  expect(screen.getByRole('link', { name: 'Clear filters' })).toHaveAttribute('href', '/platform/notifications/templates');
});
it('does not offer to clear filters when none are in force', async () => {
  await mountNotification(['templates']);
  expect(screen.queryByRole('group', { name: 'Filters in force' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Clear filters' })).not.toBeInTheDocument();
  expect(screen.getByRole('form', { name: 'Filter list' })).toHaveAttribute('method', 'get');
});
it('says what an empty list is for instead of leaving a blank table', async () => {
  call.mockImplementation(async (owner, path, method, body) => path.startsWith('templates?') ? page([]) : baseResponse(owner, path, method, body));
  await mountNotification(['templates']);
  expect(screen.getByText('No templates found')).toBeVisible();
  expect(screen.getByText('A template is created against a registered purpose, which fixes its required variables.')).toBeVisible();
});
it('keeps record references out of the way until they are asked for', async () => {
  await mountNotification(['providers', ID], { permissions: readPermissions });
  const disclosure = screen.getByText('Reference details').closest('details')!;
  expect(disclosure.open).toBe(false);
  expect(within(disclosure).getByText(ID)).toBeInTheDocument();
});
it('renders a failed load as the console’s own error state, not a bare message', async () => {
  call.mockImplementation(async (owner, path, method, body) => path.startsWith('templates?') ? Promise.reject({ status: 403, message: 'Template read access is required.' }) : baseResponse(owner, path, method, body));
  await mountNotification(['templates']);
  expect(screen.getByText("You don't have access to this")).toBeVisible();
  expect(screen.getByText('Template read access is required.')).toBeVisible();
});
it('reports a denied area as a denied area rather than a page-level notice', async () => {
  await mountNotification(['templates'], { permissions: ['platform.notification_provider.read'] });
  expect(screen.getByText('Notification access is required for this area.')).toBeVisible();
  expect(screen.queryByRole('navigation', { name: 'Notification areas' })).not.toBeInTheDocument();
});
it('names the area a record returns to instead of calling it a parent record', async () => {
  await mountNotification(['providers', ID]);
  const back = screen.getByRole('link', { name: 'Back to providers and senders' });
  expect(back).toHaveAttribute('href', '/platform/notifications/providers');
});
// On a nested record the chip's words and its href must agree: the destination is the record one
// level up, not the top-level area, and "Back to templates" beside a link to a variant is a lie.
it.each([
  [['templates', ID, 'variants', VARIANT], 'Back to the template', `/platform/notifications/templates/${ID}`],
  [['templates', ID, 'variants', VARIANT, 'versions', VERSION], 'Back to this channel and language', `/platform/notifications/templates/${ID}/variants/${VARIANT}`],
  [['providers', ID, 'senders'], 'Back to the provider account', `/platform/notifications/providers/${ID}`],
  [['providers', ID, 'senders', VARIANT], 'Back to sender identities', `/platform/notifications/providers/${ID}/senders`],
])('names the record a nested page returns to (%j)', async (route, label, destination) => {
  await mountNotification(route as string[]);
  expect(screen.getByRole('link', { name: label as string })).toHaveAttribute('href', destination);
});
