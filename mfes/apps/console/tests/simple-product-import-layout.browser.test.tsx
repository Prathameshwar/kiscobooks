import { createRequire } from 'node:module';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { ProductImport } from '../app/components/ProductImport';
import { serviceCall } from '../app/lib/service-call';
import {
  COMPANY,
  JOB,
  ROW,
  importResponse,
  job,
  page,
} from './product-import-fixtures';

vi.mock('../app/components/ProductModeProvider', () => ({
  useProductMode: () => ({ data: { product_family_sku_enabled: false } }),
}));
vi.mock('../app/lib/service-call', async (original) => ({
  ...(await original<typeof import('../app/lib/service-call')>()),
  serviceCall: vi.fn(),
}));
const css = [
  'tokens.css',
  'theme-light.css',
  'theme-dark.css',
  'theme-ledger.css',
  'janso-ui.css',
  'controls.css',
  'search-select.css',
  'file-upload.css',
  'data.css',
  'table.css',
  'overlay.css',
  'setup.css',
]
  .map((name) =>
    readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8'),
  )
  .join('\n');
const documentCss =
  readFileSync(resolve('app/globals.css'), 'utf8') +
  '\nbody { overflow: auto; }';
const artifacts = resolve('../../../.tools/simple-product-import-review');

it
  .runIf(process.env.QA_SIMPLE_IMPORT_BROWSER === '1')
  .each(['NEW', 'INVALID', 'PARTIAL', 'SUCCEEDED'])(
  'keeps Simple import %s usable across widths and themes',
  async (state) => {
    const current = {
      ...job(state === 'NEW' ? 'STAGED' : state, 3),
      definition: 'simple_products',
    };
    vi.mocked(serviceCall).mockImplementation(async (_, request) => {
      if (request.path.includes('/import-definitions'))
        return {
          items: [{ key: 'simple_products' }],
          formats: ['CSV', 'TSV', 'XLSX'],
          maximum_commands: 200,
        } as never;
      if (request.path.includes('/simple-product-imports/')) {
        if (request.path.includes('/rows'))
          return {
            items: [
              {
                id: ROW,
                source_file: '1-products.csv',
                source_row: 3,
                code: state === 'SUCCEEDED' ? 'TEA0000123' : null,
                name: 'Darjeeling tea premium pack',
                state:
                  state === 'SUCCEEDED'
                    ? 'APPLIED'
                    : state === 'PARTIAL'
                      ? 'PENDING'
                      : 'INVALID',
                opening_posted: state === 'SUCCEEDED',
                messages:
                  state === 'INVALID'
                    ? [
                        {
                          field: 'base_unit',
                          message:
                            "Choose an active code from this company's template options.",
                        },
                      ]
                    : [],
              },
            ],
            page,
          } as never;
        return {
          job: current,
          pending_count: state === 'PARTIAL' ? 1 : 0,
          failed_count: 0,
          can_resume: state === 'PARTIAL',
        } as never;
      }
      return importResponse(request.path, current) as never;
    });
    const view = render(
      <DisplayConfigProvider
        config={{
          currency: 'INR',
          timezone: 'Asia/Kolkata',
          dateFormat: 'dd/MM/yyyy',
        }}
      >
        <ProductImport
          company={COMPANY}
          canManage
          initialJob={state === 'NEW' ? undefined : JOB}
        />
      </DisplayConfigProvider>,
    );
    if (state === 'NEW')
      await screen.findByRole('button', { name: 'Download template' });
    else await screen.findByText('Darjeeling tea premium pack');
    if (state === 'PARTIAL')
      await screen.findByRole('button', { name: 'Resume import' });
    for (const select of view.container.querySelectorAll('select'))
      for (const option of select.options)
        option.toggleAttribute('selected', option.value === select.value);
    const html = view.container.innerHTML;
    view.unmount();
    mkdirSync(artifacts, { recursive: true });
    const { chromium } = createRequire(
      resolve('../../../.tools/ui-review-runner/package.json'),
    )('playwright');
    const browser = await chromium.launch({
      channel: 'msedge',
      headless: true,
    });
    try {
      const browserPage = await browser.newPage();
      for (const width of [1440, 768, 390, 320])
        for (const theme of ['light', 'dark', 'ledger']) {
          await browserPage.setViewportSize({ width, height: 1000 });
          await browserPage.setContent(
            '<!doctype html><html data-theme="' +
              theme +
              '"><head><meta name="viewport" content="width=device-width"><style>' +
              css +
              documentCss +
              '</style></head><body class="janso-root">' +
              html +
              '</body></html>',
          );
          expect(
            await browserPage.evaluate(
              () => document.documentElement.scrollWidth,
            ),
          ).toBeLessThanOrEqual(width);
          for (const control of await browserPage
            .locator('input,select,button,a')
            .all()) {
            if (!(await control.isVisible())) continue;
            const box = await control.boundingBox();
            expect(box!.x).toBeGreaterThanOrEqual(0);
            expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1);
          }
          if (state === 'NEW') {
            expect(
              await browserPage.getByLabel('Type', { exact: true }).count(),
            ).toBe(1);
            expect(
              await browserPage.getByLabel('Import operation').count(),
            ).toBe(0);
          }
          const action = browserPage.getByRole('button', {
            name:
              state === 'NEW'
                ? 'Download template'
                : state === 'PARTIAL'
                  ? 'Resume import'
                  : 'Download results',
            exact: true,
          });
          await action.scrollIntoViewIfNeeded();
          await action.focus();
          expect(
            await action.evaluate(
              (node: HTMLElement) => node === document.activeElement,
            ),
          ).toBe(true);
          await browserPage.screenshot({
            path: resolve(
              artifacts,
              state + '-' + width + '-' + theme + '.png',
            ),
            fullPage: true,
            animations: 'disabled',
          });
        }
    } finally {
      await browser.close();
    }
  },
  120000,
);
