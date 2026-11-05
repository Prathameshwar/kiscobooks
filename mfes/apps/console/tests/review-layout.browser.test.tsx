import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { FrameworkReports } from '../app/components/ReportWorkspace';
import { productFieldRequest } from '../app/lib/product-fields';
vi.mock('../app/lib/product-fields', () => ({ productFieldRequest: vi.fn() }));
const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
const css = ['tokens.css', 'theme-light.css', 'janso-ui.css', 'data.css', 'table.css', 'search-select.css', 'entry.css'].map(name => readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8')).join('\n');
it.each([1440,768,390])('keeps identifiable history buttons within the report page at %spx', async width => {
  const id = '10000000-0000-7000-8000-000000000001';
  vi.mocked(productFieldRequest).mockImplementation(async (_service, _method, path) => path.includes('/report-runs?') ? { items: [{ id, code: 'OUTSTANDING_BILLS', status: 'COMPLETE', created_at: '2026-10-30T01:00:00Z' }], page: { next_cursor: null } } : { items: [] });
  const view = render(<FrameworkReports company="company" permissions={['report.read']} />);
  await screen.findByRole('button', { name: new RegExp(id) });
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    await page.setContent('<!doctype html><html data-theme="light"><head><style>' + css + '</style></head><body class="janso-root"><main class="janso-page">' + view.container.innerHTML + '</main></body></html>');
    const bounds = await page.getByRole('button', { name: new RegExp(id) }).boundingBox();
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  } finally { await browser.close(); view.unmount(); }
}, 60000);
