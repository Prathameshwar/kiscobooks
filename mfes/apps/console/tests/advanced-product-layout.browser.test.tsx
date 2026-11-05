import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { AdvancedProductWizard } from '../app/components/AdvancedProductWizard';
import { masterRequest } from '../app/lib/catalog-master-api';
import { useProductMode } from '../app/components/ProductModeProvider';
import { COMPANY } from './product-classification-fixtures';

vi.mock('../app/lib/catalog-master-api', () => ({ masterRequest: vi.fn() }));
vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: vi.fn() }));
vi.mock('../app/components/ProductCatalogCustomFields', () => ({ ProductCatalogCustomFields: () => null }));
const mode = { company_id: COMPANY, row_version: 2, policy_generation: 4, product_family_sku_enabled: true };
const field = (key: string, label: string) => ({ key, label, source: 'native', visible: true, writable: true, conditional_access: false, required: true, order: 1 });
const options = { company_id: COMPANY, kind: 'GOODS', today: '2026-11-05', currency: 'INR', mode, default_group_id: null, selected_type: null, max_skus_per_draft: 64, defaults: { product_type_revision_id: null, configuration: { source_version: 9, options: { variants_mode: 'OPTIONAL' } } }, family_fields: { company_id: COMPANY, entity_type: 'catalog.product_family', source_version: 7, fields: [field('name', 'Profile name'), field('code', 'Profile code')] }, sku_fields: { company_id: COMPANY, entity_type: 'catalog.item', source_version: 8, fields: [] } };
const css = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css', 'janso-ui.css', 'controls.css', 'search-select.css', 'data.css', 'product-wizard.css'].map(name => readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8')).join('\n');

it.runIf(process.env.QA_PRODUCT_CONFIG_BROWSER === '1')('keeps Profile creation within desktop and phone widths in all themes', async () => {
  vi.mocked(useProductMode).mockReturnValue({ company: COMPANY, data: mode, loading: false, failure: null, refresh: vi.fn() });
  vi.mocked(masterRequest).mockImplementation(async request => request.path.includes('/options?') ? options as never : [] as never);
  const view = render(<AdvancedProductWizard company={COMPANY} mode={mode} />);
  await screen.findByRole('textbox', { name: 'Profile name' });
  const html = view.container.innerHTML; view.unmount();
  const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    for (const width of [1440, 768, 390, 320]) for (const theme of ['light', 'dark', 'ledger']) {
      await page.setViewportSize({ width, height: 1000 });
      await page.setContent(`<!doctype html><html data-theme="${theme}"><head><meta name="viewport" content="width=device-width"><style>${css} body{overflow:auto;margin:0;padding:0}</style></head><body class="janso-root">${html}</body></html>`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      for (const control of await page.locator('input,select,button,a').all()) {
        if (!await control.isVisible()) continue;
        const box = await control.boundingBox();
        if (box) { expect(box.x).toBeGreaterThanOrEqual(0); expect(box.x + box.width).toBeLessThanOrEqual(width + 1); }
      }
      expect(await page.getByRole('heading', { name: 'Product Profile', level: 2 }).count()).toBe(1);
    }
  } finally { await browser.close(); }
}, 30000);
