import { expect, it } from 'vitest';
import { navigationFor, sidebarCurrentHref } from '../app/nav';
import { sessionFor } from './helpers';

it.each(['audit.read', 'activity.read'])('offers a single Logs and activities destination for %s', async permission => {
  const session = await sessionFor({ permissions: [permission] });
  session.company.id = 'company';
  session.grants = [{ scope_type: 'company', scope_id: 'company', permissions: [permission], valid_from: '2000-01-01', valid_to: null }];
  const items = navigationFor(session).flatMap(section => section.items);
  expect(items.find(item => item.label === 'Logs and activities')?.href).toBe('/logs-and-activities');
  expect(items.some(item => ['/audit', '/activity'].includes(item.href))).toBe(false);
  expect(sidebarCurrentHref(items, '/audit')).toBe('/logs-and-activities');
  expect(sidebarCurrentHref(items, '/activity')).toBe('/logs-and-activities');
});

it('does not expose the hub using another company grant', async () => {
  const session = await sessionFor({ permissions: ['audit.read', 'activity.read'] });
  session.company.id = 'company';
  session.grants = [{ scope_type: 'company', scope_id: 'other', permissions: session.permissions, valid_from: '2000-01-01', valid_to: null }];
  expect(navigationFor(session).flatMap(section => section.items).some(item => item.href === '/logs-and-activities')).toBe(false);
});
