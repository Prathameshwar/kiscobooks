import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { FinancialOpeningAccounts } from '../app/components/FinancialOpeningAccounts';
import { serviceCall } from '../app/lib/service-call';
import { ACCOUNT, COMPANY, declaration, metadata, page } from './financial-opening-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const css = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css', 'janso-ui.css', 'controls.css', 'data.css', 'table.css', 'setup.css', 'financial-opening.css']
  .map(name => readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8')).join('\n');

it('keeps every opening input inside its mobile row, including long amounts and account names', async () => {
  const name = 'North Western Distribution and General Trading Company';
  vi.mocked(serviceCall).mockResolvedValue({ items: [{ id: ACCOUNT, company_id: COMPANY, name, code: 'NORTH_WESTERN_DISTRIBUTION', kind: 'PARTY', party_role: 'CUSTOMER', status: 'ACTIVE', currency_mode: 'BASE' }], page } as never);
  const value = declaration(); value.entries[0]!.amount = '999999999999999.9999';
  const view = render(<FinancialOpeningAccounts company={COMPANY} category="BUYER" group={null} value={value} metadata={metadata} disabled={false} onChange={vi.fn()} onDetails={vi.fn()} />);
  await screen.findByLabelText('Opening for ' + name);
  const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const browserPage = await browser.newPage();
    for (const theme of ['light', 'dark', 'ledger']) for (const width of [320, 390, 768, 1440]) {
      await browserPage.setViewportSize({ width, height: 1000 });
      await browserPage.setContent('<!doctype html><html data-theme="' + theme + '"><head><meta name="viewport" content="width=device-width"><style>' + css + '</style></head><body class="janso-root"><main class="janso-page janso-opening-page">' + view.container.innerHTML + '</main></body></html>');
      expect(await browserPage.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
      const grid = await browserPage.locator('.janso-opening-grid').boundingBox();
      if (width <= 768) expect((await browserPage.getByLabel('Quick account search').boundingBox())!.width).toBeGreaterThanOrEqual(grid!.width - 1);
      for (const input of await browserPage.locator('.janso-opening-grid input, .janso-opening-grid select, .janso-opening-grid button').all()) {
        const bounds = await input.boundingBox();
        expect(bounds, 'Opening control must be visible').not.toBeNull();
        expect(bounds!.x + bounds!.width, `Control must fit inside the ${width}px grid`).toBeLessThanOrEqual(grid!.x + grid!.width + 1);
      }
      const amount = browserPage.getByLabel('Opening for ' + name);
      await amount.focus();
      expect(await amount.evaluate((element: HTMLInputElement) => document.activeElement === element)).toBe(true);
      expect(await amount.evaluate((element: HTMLInputElement) => element.scrollWidth <= element.clientWidth + 1), 'The complete amount must fit without horizontal scrolling').toBe(true);
    }
    await browserPage.setViewportSize({ width: 768, height: 1000 });
    await browserPage.evaluate(() => { document.documentElement.style.zoom = '2'; });
    expect(await browserPage.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
  } finally { await browser.close(); view.unmount(); }
}, 120000);
