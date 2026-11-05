import { createRequire } from 'node:module';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { configure, fireEvent, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { CompanyConfiguration } from '../app/components/CompanyConfiguration';
import { CompanyGstSettings } from '../app/components/CompanyGstSettings';
import { companyCall } from '../app/lib/company-api';
import { renderWithProviders, sessionFor } from './helpers';

vi.mock('../app/lib/company-api', () => ({ companyCall: vi.fn(), companyFailure: (value: unknown) => value }));
const company = '01990000-0000-7000-8000-000000000001', registration = '01990000-0000-7000-8000-000000000002';
const stamp = '2026-11-02T10:00:00Z';
const css = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css', 'janso-ui.css', 'controls.css', 'data.css', 'table.css', 'overlay.css', 'setup.css']
  .map(name => readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8')).join('\n')
  + readFileSync(resolve('app/globals.css'), 'utf8').replace('overflow: hidden', 'overflow: auto');
const artifacts = resolve('../../../.tools/company-gst-settings-review');

async function markup(scenario: string, width: number) {
  Object.defineProperty(window, 'matchMedia', { configurable: true, value: (query: string) => ({ matches: width <= 680 && query.includes('max-width'), media: query, addEventListener() {}, removeEventListener() {} }) });
  const vat = scenario === 'vat', none = scenario === 'none', readOnly = scenario === 'gst-readonly';
  const profile = { id: company, display_name: 'Acme Manufacturing', legal_name: 'Acme Manufacturing Private Limited', trade_name: 'Acme', code: 'ACME', country_code: vat ? 'GB' : 'IN', state_code: vat ? 'ENG' : 'MH', status: 'active', updated_at: stamp, default_tax_system: vat ? 'vat_gb' : none ? 'none' : 'gst_in', base_currency: vat ? 'GBP' : 'INR', books_begin_date: '2026-04-01', timezone: vat ? 'Europe/London' : 'Asia/Kolkata' };
  const registrations = none || scenario === 'gst-empty' ? [] : [{ id: registration, tax_system: profile.default_tax_system, number: vat ? 'GB123456789' : '27ABCDE1234F1Z5', jurisdiction_code: vat ? 'GB' : 'MH', regime: vat ? 'standard' : 'regular', valid_from: '2026-04-01', valid_to: null }];
  vi.mocked(companyCall).mockImplementation(async (_service, path) => {
    if (path === '/v1/company-features') return { items: [{ key: 'inventory', label: 'Stock and inventory', description: 'Track stock and inventory', requires: [], tax_systems: [], locks: true }] } as never;
    if (path.endsWith('/setup-readiness')) return { company_id: company, company_status: 'active', company_updated_at: stamp, features: [{ feature_key: 'inventory', state: 'DISABLED', required_features: [], missing_prerequisites: [], tax_system_supported: true, locked_at: null }] } as never;
    if (path.endsWith('/gst-registration-setup')) return { country_code: 'IN', default_tax_system: 'gst_in', can_manage: !readOnly, regimes: { regular: 'Regular taxpayer', composition: 'Composition taxpayer' }, states: [{ code: 'MH', name: 'Maharashtra' }], create_schema: { properties: { number: { maxLength: 40 } } } } as never;
    if (path.endsWith('/gst-outward-profile-setup')) return { can_manage: !readOnly, create_schema: { properties: { reference: { maxLength: 120 } } } } as never;
    if (path.includes('/gst-outward-profiles?')) return { items: registrations.length ? [{ id: company, registration_id: registration, annual_turnover: '40000000.0000', rule_14a: false, valid_from: '2026-04-01', valid_to: null }] : [], page: { next_cursor: null } } as never;
    if (path.includes('/tax-registrations?')) return { items: registrations, page: { next_cursor: null } } as never;
    return profile as never;
  });
  const permissions = readOnly ? ['company.read'] : ['company.read', 'company.update', 'company.tax_registration.manage', 'report.read'];
  const session = await sessionFor({ permissions }); session.company = { id: company, name: profile.display_name };
  session.grants = [{ scope_type: 'company', scope_id: company, permissions, valid_from: '2020-01-01', valid_to: null }];
  const gstPage = scenario.startsWith('gst');
  const view = await renderWithProviders(gstPage ? <CompanyGstSettings session={session} companyId={company} returnTo={'/companies/' + company + '/configuration?returnTo=%2Fsettings'} /> : <CompanyConfiguration session={session} companyId={company} returnTo="/settings" />);
  await screen.findByRole('table', { name: gstPage ? 'Dated GST outward reporting profiles' : vat || none ? 'Company tax registrations' : 'Company features' });
  if (gstPage && registrations.length) await screen.findByText('40000000.0000');
  if (scenario === 'gst-registration-entry') {
    fireEvent.click(screen.getByRole('button', { name: 'Add GST registration' }));
  }
  if (scenario === 'gst-profile-entry') {
    fireEvent.click(screen.getByRole('button', { name: 'Add outward reporting profile' }));
  }
  const overlays = Array.from(document.body.querySelectorAll('.janso-drawer,.janso-dialog')).map(node => node.outerHTML).join('');
  const html = view.container.innerHTML + overlays; view.unmount(); return html;
}

it.runIf(process.env.QA_COMPANY_CONFIG_BROWSER === '1').each(['configuration', 'gst', 'gst-registration-entry', 'gst-profile-entry', 'gst-empty', 'gst-readonly', 'vat', 'none'])('keeps %s company settings readable across widths and themes', async scenario => {
  configure({ asyncUtilTimeout: 10000 });
  mkdirSync(artifacts, { recursive: true });
  const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    for (const width of [1440, 768, 390, 320]) {
      const html = await markup(scenario, width);
      for (const theme of ['light', 'dark', 'ledger']) {
        await page.setViewportSize({ width, height: 1000 });
        await page.setContent('<!doctype html><html data-theme="' + theme + '"><head><meta name="viewport" content="width=device-width"><style>' + css + '</style></head><body class="janso-root">' + html + '</body></html>');
        await page.screenshot({ path: resolve(artifacts, scenario + '-' + width + '-' + theme + '.png'), fullPage: true, animations: 'disabled' });
        if (scenario.startsWith('gst')) {
          for (const heading of ['GST registrations', 'GST outward reporting profiles']) {
            const card = page.locator('.janso-card').filter({ has: page.getByRole('heading', { name: heading, exact: true }) }).first();
            const spacing = await card.evaluate((node: HTMLElement) => {
              const header = node.querySelector(':scope > .janso-card__header')!;
              const blocks = Array.from(node.querySelectorAll(':scope > .janso-card__body > .janso-flow > *'));
              return {
                introduction: blocks[0].getBoundingClientRect().top - header.getBoundingClientRect().bottom,
                gaps: blocks.slice(1).map((block, index) => block.getBoundingClientRect().top - blocks[index].getBoundingClientRect().bottom),
              };
            });
            expect(spacing.introduction, heading + ' header to guidance').toBeLessThanOrEqual(12);
            for (const gap of spacing.gaps) {
              expect(gap, heading + ' related content must keep a compact gap').toBeGreaterThanOrEqual(0);
              expect(gap, heading + ' related content must keep a compact gap').toBeLessThanOrEqual(12);
            }
          }
        }
        expect(await page.evaluate(() => document.documentElement.scrollWidth), scenario + ' ' + theme + ' ' + width).toBeLessThanOrEqual(width);
        for (const control of await page.locator('input,select,button,a.janso-btn').all()) {
          if (!await control.isVisible()) continue;
          const bounds = (await control.boundingBox())!;
          expect(bounds.x).toBeGreaterThanOrEqual(0);
          expect(bounds.x + bounds.width).toBeLessThanOrEqual(width + 1);
        }
        expect((await page.getByRole('heading', { level: 1 }).boundingBox())!.width, 'Page heading must have readable space').toBeGreaterThanOrEqual(150);
        for (const title of await page.locator('.janso-card__title').all()) expect((await title.boundingBox())!.width, 'Card headings must retain readable space').toBeGreaterThanOrEqual(150);
        if (!scenario.startsWith('gst')) {
          const identity = (await page.getByRole('region', { name: 'Business identity', exact: true }).boundingBox())!;
          const regional = (await page.getByRole('region', { name: 'Regional and financial defaults' }).boundingBox())!;
          const companyHeading = (await page.getByRole('heading', { name: 'Acme Manufacturing', exact: true }).boundingBox())!;
          expect(companyHeading.width, 'Company name must have readable space').toBeGreaterThanOrEqual(150);
          if (width > 1100) expect(Math.abs(identity.y - regional.y)).toBeLessThanOrEqual(1);
          else expect(regional.y).toBeGreaterThanOrEqual(identity.y + identity.height);
          expect(await page.getByRole('table', { name: 'Company GST registrations' }).count()).toBe(0);
        }
        if (scenario === 'configuration') {
          const edit = (await page.getByRole('link', { name: 'Edit company settings' }).boundingBox())!;
          const gst = (await page.getByRole('link', { name: 'GST settings', exact: true }).boundingBox())!;
          expect(gst.y).toBeGreaterThanOrEqual(edit.y);
          if (Math.abs(gst.y - edit.y) < 1) expect(gst.x).toBeGreaterThan(edit.x);
        }
        if (scenario === 'gst-registration-entry' || scenario === 'gst-profile-entry') {
          const profileEntry = scenario === 'gst-profile-entry';
          const drawer = page.getByRole('dialog', { name: profileEntry ? 'Add outward reporting profile' : 'Add GST registration', exact: true });
          const bounds = (await drawer.boundingBox())!;
          expect(bounds.x + bounds.width).toBeCloseTo(width, 0);
          expect(bounds.height).toBe(1000);
          expect(await page.getByRole('dialog').count()).toBe(1);
          const save = (await drawer.getByRole('button', { name: profileEntry ? 'Save outward reporting profile' : 'Save GST registration' }).boundingBox())!;
          expect(save.y).toBeGreaterThan(0);
          expect(save.y + save.height).toBeLessThanOrEqual(1000);
          expect(await drawer.locator('.janso-card').count()).toBe(0);
          const body = drawer.locator('.janso-overlay-body');
          expect(await body.evaluate((node: HTMLElement) => getComputedStyle(node).overflowY)).toBe('auto');
          await body.evaluate((node: HTMLElement) => { node.scrollTop = node.scrollHeight; });
          const afterScroll = (await drawer.getByRole('button', { name: profileEntry ? 'Save outward reporting profile' : 'Save GST registration' }).boundingBox())!;
          expect(afterScroll.y).toBe(save.y);
          expect(await drawer.getByRole('group', { name: profileEntry ? 'Supporting evidence' : 'Registration details' }).count()).toBe(1);
        }
      }
    }
  } finally { await browser.close(); }
}, 120000);
