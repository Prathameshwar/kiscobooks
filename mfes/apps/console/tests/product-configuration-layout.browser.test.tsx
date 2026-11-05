import { createRequire } from 'node:module';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { ProductConfigurationEditor } from '../app/components/ProductConfigurationEditor';
import { ProductConfigurationDetail } from '../app/components/ProductConfigurationDetail';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, DRAFT } from './product-configuration-fixtures';
import { completeResponse } from './product-configuration-layout-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
vi.mock('../app/lib/navigate', () => ({ goTo: vi.fn(), signInUrl: () => '/signin' }));
const css = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css', 'janso-ui.css', 'controls.css', 'search-select.css', 'data.css', 'table.css', 'overlay.css', 'setup.css'].map(name => readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8')).join('\n');
// Standalone page fixture uses the console palette; document scrolling replaces the shell.
const documentCss = readFileSync(resolve('app/globals.css'), 'utf8') + '\nbody { overflow: auto; }';
const artifacts = resolve('../../../.tools/product-config-ui-review');

it.runIf(process.env.QA_PRODUCT_CONFIG_BROWSER === '1').each(['editor', 'review'])('keeps the full %s configuration usable across widths and themes', async scenario => {
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => completeResponse(request.path, request.method) as never);
  const view = render(<DisplayConfigProvider config={{ timezone: 'Asia/Kolkata', currency: 'INR' }}>{scenario === 'editor' ? <ProductConfigurationEditor company={COMPANY} id={DRAFT} timezone="Asia/Kolkata" returnTo="/settings" /> : <ProductConfigurationDetail company={COMPANY} id={DRAFT} canManage={false} canPublish={false} timezone="Asia/Kolkata" returnTo="/settings" />}</DisplayConfigProvider>);
  await screen.findByRole('navigation', { name: 'Configuration sections' });
  for (const select of view.container.querySelectorAll('select')) for (const option of select.options) option.toggleAttribute('selected', option.value === select.value);
  for (const input of view.container.querySelectorAll('input')) input.setAttribute('value', input.value);
  const html = view.container.innerHTML; view.unmount();
  mkdirSync(artifacts, { recursive: true });
  const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    for (const width of [1440, 768, 390, 320]) for (const theme of ['light', 'dark', 'ledger']) {
      await page.setViewportSize({ width, height: 1000 });
      await page.setContent('<!doctype html><html data-theme="' + theme + '"><head><meta name="viewport" content="width=device-width"><style>' + css + documentCss + '</style></head><body class="janso-root">' + html + '</body></html>');
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      for (const control of await page.locator('input,select,button,a').all()) {
        if (!await control.isVisible()) continue;
        const box = (await control.boundingBox())!;
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
      }
      await page.getByRole('navigation', { name: 'Configuration sections' }).getByRole('link', { name: 'Unit conversion' }).click();
      expect(await page.evaluate(() => window.location.hash)).toBe('#configuration-unit-conversion');
      expect((await page.locator('#configuration-unit-conversion').boundingBox())!.y).toBeLessThan(1000);
      if (scenario === 'editor') {
        const model = page.getByRole('combobox', { name: 'Model', exact: true });
        await model.focus();
        expect(await model.evaluate((node: HTMLElement) => node === document.activeElement)).toBe(true);
        await page.getByRole('button', { name: 'Save draft changes' }).scrollIntoViewIfNeeded();
        const box = (await page.getByRole('button', { name: 'Save draft changes' }).boundingBox())!;
        expect(box.y + box.height).toBeLessThanOrEqual(1000);
      }
      await page.screenshot({ path: resolve(artifacts, scenario + '-' + width + '-' + theme + '.png'), fullPage: true, animations: 'disabled' });
    }
  } finally { await browser.close(); }
}, 120000);
