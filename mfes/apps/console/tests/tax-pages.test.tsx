import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TaxPage } from '../app/components/TaxPage';
import { pageContext } from '../app/lib/page-context';
import { flattenNavigation, navigationFor } from '../app/nav';
import { companyMastersFor } from '../app/lib/company-masters';
import { companyContextFor, sessionFor } from './helpers';
import { COMPANY, RATE, RULE } from './tax-fixtures';

vi.mock('../app/lib/page-context', () => ({ pageContext: vi.fn() }));
vi.mock('../app/providers', () => ({ Providers: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/ConsoleShell', () => ({ ConsoleShell: ({ children }: { children: React.ReactNode }) => children }));
vi.mock('../app/components/NoCompany', () => ({ NoCompany: () => <p>Select a company</p> }));
vi.mock('../app/components/TaxDirectory', () => ({ TaxDirectory: () => <p>Tax directory</p>, TaxOverview: () => <p>Tax overview</p> }));
vi.mock('../app/components/TaxEditor', () => ({ TaxEditor: ({ superseding }: { superseding: boolean }) => <p>{superseding ? 'Tax replacement' : 'Tax editor'}</p> }));
vi.mock('../app/components/TaxDetail', () => ({ TaxDetail: () => <p>Tax detail</p> }));
vi.mock('../app/components/TaxSetup', () => ({ TaxSetup: ({ applicability }: { applicability: boolean }) => <p>{applicability ? 'Tax applicability' : 'Tax series'}</p> }));
vi.mock('../app/components/TaxReleaseEditor', () => ({ TaxReleaseEditor: () => <p>Tax release</p> }));
vi.mock('next/navigation', () => ({ notFound: () => { throw new Error('not found'); } }));

async function actor(permissions: string[], scope = COMPANY) {
  const session = await sessionFor(); session.company = { id: COMPANY, name: 'Acme' }; session.permissions = [];
  session.grants = [{ scope_type: 'company', scope_id: scope, valid_from: '2020-01-01', valid_to: null, permissions }];
  vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() }); return session;
}
beforeEach(async () => { vi.clearAllMocks(); await actor(['tax_rule.read', 'tax_rule.manage', 'tax_rule.publish']); });
describe('tax server routing and scoped menu access', () => {
  it.each([
    [[], 'Tax overview'], [['categories'], 'Tax directory'], [['classifications'], 'Tax directory'], [['rules'], 'Tax directory'], [['rates'], 'Tax directory'],
    [['categories', 'new'], 'Tax editor'], [['rules', RULE, 'edit'], 'Tax editor'], [['classifications', RATE], 'Tax detail'], [['rates', RATE, 'replace'], 'Tax replacement'],
    [['rates', 'release', 'new'], 'Tax release'], [['rates', 'series', 'new'], 'Tax series'], [['rules', RULE, 'applicability', 'new'], 'Tax applicability'],
  ])('opens supported path %s', async (segments, message) => { render(await TaxPage({ segments: segments as string[] })); expect(screen.getByText(message as string)).toBeVisible(); });
  it.each([['rates', RATE, 'edit'], ['classifications', RATE, 'edit'], ['unknown'], ['rules', 'bad-id'], ['rates', 'series', 'invalid'], ['rules', RULE, 'applicability', 'bad']])('rejects unsupported path %s', async (...segments) => expect(TaxPage({ segments })).rejects.toThrow('not found'));
  it('requires a company and does not use a foreign-company grant', async () => {
    const session = await actor(['tax_rule.read'], RULE);
    render(await TaxPage({ segments: ['categories'] })); expect(screen.getByText(/Tax read access/)).toBeVisible();
    expect(flattenNavigation(navigationFor(session).flatMap(section => section.items)).some(item => item.href === '/tax')).toBe(false);
  });
  it('keeps read-only directories available but denies editing', async () => {
    const session = await actor(['tax_rule.read']);
    render(await TaxPage({ segments: ['categories', 'new'] })); expect(screen.getByText(/Tax read access/)).toBeVisible();
    expect(flattenNavigation(navigationFor(session).flatMap(section => section.items)).some(item => item.href === '/masters')).toBe(true);
    expect(companyMastersFor(session).flatMap(section => section.items).filter(item => item.href.startsWith('/tax')).map(item => item.href)).toEqual(['/tax/categories', '/tax/classifications', '/tax/rules', '/tax/rates']);
  });
  it.each([['rates', 'new'], ['rates', 'release', 'new']])('requires publication permission for dated definitions %s', async (...segments) => {
    await actor(['tax_rule.read', 'tax_rule.manage']); render(await TaxPage({ segments })); expect(screen.getByText(/Tax read access/)).toBeVisible();
  });
  it('shows the company selection state without calling tax screens', async () => {
    const session = await actor(['tax_rule.read']); session.company = { name: 'Select a company' };
    vi.mocked(pageContext).mockResolvedValue({ session, context: companyContextFor() }); render(await TaxPage({ segments: ['categories'] })); expect(screen.getByText('Select a company')).toBeVisible();
  });
});
