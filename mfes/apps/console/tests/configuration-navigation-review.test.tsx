import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { configBack, configLink, configRoot } from '../app/lib/product-configuration';
import { accountingBack, accountingLink } from '../app/lib/accounting-configuration-resources';
import { ConfigurationNavigation } from '../app/components/ProductConfigurationCommon';
import { AccountingNavigation } from '../app/components/AccountingConfigurationCommon';

const ID = '01990000-0000-7000-8000-000000000001';
const url = (value: string) => new URL(value, 'https://console.invalid');
it('preserves a product scope, filtered directory and settings through deeper links', () => {
  const directory = configLink(configRoot + '?scope_kind=COMPANY', '/settings');
  const scope = configLink(configRoot + '/scopes/' + ID, directory);
  const draft = configLink(configRoot + '/drafts/' + ID, scope);
  expect(url(configBack(url(draft).searchParams.get('returnTo')!)).searchParams.get('returnTo')).toBe(directory);
});
it('preserves accounting filters and the settings origin through encoded return links', () => {
  const root = accountingLink('/accounting', '/settings');
  const directory = accountingLink('/accounting/parties?status=ACTIVE', root);
  const detail = accountingLink('/accounting/parties/' + ID, directory);
  expect(accountingBack(url(detail).searchParams.get('returnTo')!)).toBe(directory);
});
it.each([configLink, accountingLink])('returns to the original parent after saving on the same details page', link => {
  const root = link === configLink ? configRoot : '/accounting', page = root + (link === configLink ? '/drafts/' : '/parties/') + ID;
  const details = link(page, '/settings');
  expect(link(page, details)).toBe(details);
  expect(link(details, '/settings')).toBe(details);
});
it.each([configBack, accountingBack])('keeps company configuration as a safe return destination', back => {
  expect(back(`/companies/${ID}/configuration?returnTo=%2Fsettings`)).toBe(`/companies/${ID}/configuration?returnTo=%2Fsettings`);
});
it.each([configBack, accountingBack])('rejects unsafe destinations and removes unsafe nested returns', back => {
  for (const value of ['//evil.example', '/%2f%2fevil.example', '/accounting/%2e%2e/settings', '/settings#secret', 'https://evil.example']) expect(back(value, '/settings')).toBe('/settings');
  const root = back === configBack ? configRoot : '/accounting';
  expect(back(root + '?returnTo=' + encodeURIComponent('//evil.example'))).toBe(root);
  let nested = '/settings';
  for (let index = 0; index < 12; index++) nested = root + '?returnTo=' + encodeURIComponent(nested);
  expect(back(nested).length).toBeLessThan(4096);
});
it('labels a filtered product directory back link and keeps its settings breadcrumb', () => {
  const directory = configLink(configRoot + '?scope_kind=COMPANY', '/settings');
  render(<ConfigurationNavigation title="Configuration scope" back={directory} />);
  expect(screen.getByRole('link', { name: 'Back to product configuration' })).toHaveAttribute('href', directory);
  expect(screen.getByRole('link', { name: 'Company settings' })).toHaveAttribute('href', '/settings');
});
it.each([['effective', 'effective product settings'], ['adopt', 'product adoption']])('labels a return to the %s workflow', (path, label) => {
  const parent = configLink(configRoot + '/' + path, '/settings');
  render(<ConfigurationNavigation title="Published configuration" back={parent} />);
  expect(screen.getByRole('link', { name: 'Back to ' + label })).toHaveAttribute('href', parent);
});
it('labels accounting record back links and retains the settings breadcrumb', () => {
  const directory = accountingLink('/accounting/parties?status=ACTIVE', accountingLink('/accounting', '/settings'));
  render(<AccountingNavigation title="Party configuration" back={directory} />);
  expect(screen.getByRole('link', { name: 'Back to parties' })).toHaveAttribute('href', directory);
  expect(screen.getByRole('link', { name: 'Company settings' })).toHaveAttribute('href', '/settings');
});
