import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { ProductCatalogReference } from '../app/components/ProductCatalogCommon';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, access, resetFixtures } from './product-classification-fixtures';
import { drawerResponse } from './product-reference-fixtures';

vi.mock('../app/lib/service-call', async original => ({ ...(await original<typeof import('../app/lib/service-call')>()), serviceCall: vi.fn() }));
const css = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css', 'janso-ui.css', 'data.css', 'table.css', 'search-select.css', 'entry.css', 'overlay.css'].map(name => readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8')).join('\n') + readFileSync(resolve('app/console.css'), 'utf8');

it.runIf(process.env.QA_PRODUCT_REFERENCE_BROWSER === '1').each(['item-groups', 'product-type-revisions'])('aligns %s creation controls and right drawer at three widths in every theme', async source => {
  const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  resetFixtures(); vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => drawerResponse(request) as never);
  const title = source === 'item-groups' ? 'New product group' : 'New product type';
  const view = render(<ProductCatalogReference company={COMPANY} source={source} label="Product reference with a long label to check wrapping" values={{ kind: 'GOODS' }} value={null} access={{ ...access, manageGroups: true, manageTypes: true }} onChange={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: title }));
  const panel = await screen.findByRole('dialog', { name: title });
  await within(panel).findByRole('textbox', { name: 'Code' }, { timeout: 10_000 });
  const html = view.container.innerHTML + panel.closest('.janso-drawer')!.outerHTML;
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    for (const width of [1440, 768, 390]) for (const theme of ['light', 'dark', 'ledger']) {
      await page.setViewportSize({ width, height: 900 });
      await page.setContent(`<!doctype html><html data-theme="${theme}"><head><style>${css}</style></head><body class="janso-root"><main class="janso-page">${html}</main></body></html>`);
      await page.locator('.janso-drawer__panel').waitFor({ state: 'visible' });
      await page.waitForTimeout(250);
      const control = await page.locator('.console-reference-create .janso-search-select__control').boundingBox();
      const action = await page.locator('.console-reference-create__action').boundingBox();
      const drawer = await page.locator('.janso-drawer__panel').boundingBox();
      expect(control).not.toBeNull(); expect(action).not.toBeNull(); expect(drawer).not.toBeNull();
      expect(Math.abs(control!.y + control!.height / 2 - action!.y - action!.height / 2)).toBeLessThanOrEqual(1);
      expect(action!.x).toBeGreaterThanOrEqual(control!.x + control!.width);
      expect(action!.width).toBe(action!.height);
      expect(action!.height).toBeLessThanOrEqual(control!.height);
      expect(Math.abs(drawer!.x + drawer!.width - width)).toBeLessThanOrEqual(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      const overflow = await page.locator('.janso-drawer__panel').evaluate((node: HTMLElement) => node.scrollWidth - node.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);
      if (width === 390 && theme === 'light') await page.screenshot({ path: resolve(`../../../.test_artifacts/product-reference-${source}-390.png`), fullPage: true });
    }
  } finally { await browser.close(); view.unmount(); }
}, 60_000);
