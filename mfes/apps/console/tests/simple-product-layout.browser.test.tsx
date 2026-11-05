import { createRequire } from 'node:module';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { DisplayConfigProvider } from '@janso/ui';
import { SimpleProductCreate } from '../app/components/SimpleProductCreate';
import { serviceCall } from '../app/lib/service-call';
import { COMPANY, GROUP, simpleOptions, configuredSimpleOptions, multiPriceOptions, classificationOptions } from './simple-product-ready-fixtures';

vi.mock('../app/components/ProductModeProvider', () => ({ useProductMode: () => ({ data: { product_family_sku_enabled: false } }) }));
vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const css = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css', 'janso-ui.css', 'controls.css', 'search-select.css', 'data.css', 'table.css', 'overlay.css', 'setup.css'].map(name => readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8')).join('\n');
const fontCss = readFileSync(resolve('../../packages/ui/src/styles/fonts.css'), 'utf8').replace(
  '../assets/fonts/InterVariable.woff2',
  'data:font/woff2;base64,' + readFileSync(resolve('../../packages/ui/src/assets/fonts/InterVariable.woff2')).toString('base64'),
);
// Standalone page fixture uses the console palette; document scrolling replaces the shell.
const documentCss = readFileSync(resolve('app/globals.css'), 'utf8') + '\nbody { overflow: auto; }';
const artifacts = resolve('../../../.tools/simple-product-ui-review');

it.runIf(process.env.QA_PRODUCT_CONFIG_BROWSER === '1').each(['GOODS', 'SERVICE', 'CONFIGURED', 'ERROR', 'UNAVAILABLE', 'MULTI', 'CLASSIFICATION', 'BATCH', 'SERIAL', 'BATCH_SERIAL', 'SAVING', 'SAVED'])('keeps the %s creation form usable across widths and themes', async scenario => {
  const kind = ['SERVICE', 'UNAVAILABLE'].includes(scenario) ? 'SERVICE' : 'GOODS';
  sessionStorage.clear();
  vi.mocked(serviceCall).mockImplementation(async (_endpoint, request) => {
    if (request.path.includes('/options?')) {
      if (scenario === 'SAVING' || scenario === 'SAVED') return simpleOptions() as never;
      if (scenario === 'SERIAL' || scenario === 'BATCH_SERIAL') {
        const value = simpleOptions();
        return { ...value, serial: { enabled: true, requirements: [{ identifier_type: 'SERIAL', namespace_rule: 'COMPANY', min_count: 1, max_count: 1, requires_slot: false }, { identifier_type: 'IMEI', namespace_rule: 'COMPANY', min_count: 1, max_count: 2, requires_slot: true }] }, batch: { available: scenario === 'BATCH_SERIAL', required: scenario === 'BATCH_SERIAL', expiry_enabled: false, expiry_required: false, manufacture_date_required: false }, fields: [...value.fields, ...['serial_identifiers', 'batch_enabled', 'batch_code'].map(key => ({ ...value.fields[0], key, visible: true, writable: true }))] } as never;
      }
      if (scenario === 'BATCH') {
        const value = multiPriceOptions();
        return { ...value, batch: { available: true, required: false, expiry_enabled: true, expiry_required: true, manufacture_date_required: false }, fields: [...value.fields, ...['batch_enabled', 'batch_code', 'batch_expires_on'].map(key => ({ ...value.fields[0], key, visible: true, writable: true }))] } as never;
      }
      if (scenario === 'MULTI') return multiPriceOptions() as never;
      if (scenario === 'CLASSIFICATION') return classificationOptions('REQUIRED') as never;
      const options = scenario === 'CONFIGURED' ? configuredSimpleOptions() : simpleOptions(new URL(request.path, 'http://test').searchParams.get('kind')!, true);
      if (scenario === 'UNAVAILABLE' && options.kind === 'SERVICE') options.fields = options.fields.filter(field => field.key !== 'purchase_price');
      return (scenario !== 'CONFIGURED' ? options : { ...options,
        configuration: { ...options.configuration, options: { ...options.configuration.options, barcode_mode: 'OPTIONAL', barcode_default: true } },
        fields: [...options.fields, { ...options.fields[0], key: 'barcode_value', label: 'Barcode value' },
          { ...options.fields[0], key: 'barcode_symbology', label: 'Barcode format', control: { kind: 'select', choices: [{ value: 'CODE128', label: 'Code 128' }, { value: 'GTIN', label: 'GTIN' }, { value: 'QR', label: 'QR' }] } }],
      }) as never;
    }
    if (request.path.endsWith('/simple-product-creations')) return scenario === 'SAVING' ? new Promise<never>(() => undefined) : { id: GROUP, company_id: COMPANY, code: 'PRODUCT123', status: 'COMPLETE', step: 'COMPLETE', opening_posted: true } as never;
    if (request.path.endsWith('/item-groups/' + GROUP)) return { id: GROUP, name: 'Default' } as never;
    const choice = request.path.includes('/tax-classifications?') ? { description: 'Tea classification', code: '0902' }
      : request.path.includes('/tax-rules?') ? { name: 'GST 18 percent', code: 'GST18' }
      : request.path.includes('catalog.brand_series?') ? { label: 'Tea series' }
      : request.path.includes('catalog.brands?') ? { label: 'Tea brand' }
      : request.path.includes('catalog.manufacturers?') ? { label: 'Tea maker' }
      : request.path.includes('catalog.manufacturer_sites?') ? { label: 'Main plant' }
      : request.path.includes('catalog.item_categories?') ? { label: 'Tea' }
      : request.path.includes('catalog.units?') ? { label: 'Numbers' } : null;
    if (choice) return { items: [{ id: GROUP, ...choice }], page: { has_more: false } } as never;
    throw new Error('Unexpected layout request');
  });
  const view = render(<DisplayConfigProvider config={{ currency: 'INR', timezone: 'Asia/Kolkata', dateFormat: 'dd/MM/yyyy' }}><SimpleProductCreate company={COMPANY} /></DisplayConfigProvider>);
  await screen.findByRole('textbox', { name: 'Product name' });
  if (scenario === 'UNAVAILABLE') await userEvent.type(screen.getByRole('textbox', { name: 'Purchase price' }), '12.50');
  if (kind === 'SERVICE') {
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Type' }), 'SERVICE');
    await screen.findByRole('combobox', { name: /SAC/ });
  }
  await screen.findByDisplayValue('Default');
  if (scenario === 'SAVING' || scenario === 'SAVED') {
    await userEvent.type(screen.getByRole('textbox', { name: 'Product name' }), 'Ready product');
    await userEvent.click(screen.getByRole('combobox', { name: 'Base unit' }));
    await userEvent.click(await screen.findByRole('option', { name: 'Numbers' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save product' }));
    if (scenario === 'SAVED') await screen.findByRole('region', { name: 'Product saved' });
    else expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
  }
  if (scenario === 'BATCH') {
    await userEvent.click(screen.getByRole('button', { name: '2. Stock and prices' }));
    await userEvent.click(screen.getByRole('switch', { name: 'Allow batch' }));
    await userEvent.click(screen.getByRole('button', { name: 'Add batch' }));
  }
  if (scenario === 'SERIAL' || scenario === 'BATCH_SERIAL') {
    await userEvent.click(screen.getByRole('button', { name: '2. Stock and prices' }));
    if (scenario === 'BATCH_SERIAL') await userEvent.click(screen.getByRole('button', { name: 'Add batch' }));
    await userEvent.click(screen.getByRole('button', { name: 'Add serial unit' }));
    await userEvent.click(screen.getByRole('button', { name: 'Add serial unit' }));
  }
  if (scenario === 'CONFIGURED') {
    const user = userEvent.setup({ delay: null });
    for (const [label, option] of [['Base unit', 'Numbers'], ['Brand', 'Tea brand'], ['Brand series', 'Tea series'], ['HSN', 'Tea classification'], ['GST treatment / rate', 'GST 18 percent']] as const) {
      await user.click(screen.getByRole('combobox', { name: label }));
      await user.click(await screen.findByRole('option', { name: new RegExp(option) }));
    }
    for (const [label, value] of [['Product name', 'Darjeeling tea'], ['Product code', 'TEA00101'], ['Model', 'Classic'], ['Purchase price', '12.50'], ['Selling price', '20.00'], ['MRP', '25.00'], ['Opening quantity', '3']] as const) {
      await user.clear(screen.getByRole('textbox', { name: label }));
      await user.type(screen.getByRole('textbox', { name: label }), value);
    }
    await user.type(screen.getByRole('textbox', { name: 'Barcode value' }), '0012345678905');
  }
  if (scenario === 'ERROR') {
    await userEvent.click(screen.getByRole('button', { name: 'Save product' }));
    await screen.findByText('Enter the product name.');
  }
  if (scenario === 'CLASSIFICATION') {
    const user = userEvent.setup({ delay: null });
    for (const [label, option] of [['Manufacturer', 'Tea maker'], ['Manufacturer site', 'Main plant'], ['Category 1', 'Tea']] as const) {
      await user.click(screen.getByRole('combobox', { name: label }));
      await user.click(await screen.findByRole('option', { name: option }));
    }
    await user.click(screen.getByRole('button', { name: 'Add category' }));
  }
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
      await page.setContent('<!doctype html><html data-theme="' + theme + '"><head><meta name="viewport" content="width=device-width"><style>' + fontCss + css + documentCss + '</style></head><body class="janso-root">' + html + '</body></html>');
      await page.evaluate(() => document.fonts.ready);
      expect(await page.evaluate(() => document.documentElement.scrollWidth), JSON.stringify(await page.evaluate(() => [...document.querySelectorAll('div,fieldset,table')].filter(el => el.getBoundingClientRect().right > innerWidth).slice(0, 15).map(el => ({ tag: el.tagName, class: el.className, width: el.getBoundingClientRect().width, min: getComputedStyle(el).minWidth, display: getComputedStyle(el).display }))))).toBeLessThanOrEqual(width);
      const formBox = (await page.locator('.janso-simple-product').boundingBox())!;
      if (width === 1440) {
        expect(formBox.width).toBeLessThanOrEqual(scenario.startsWith('BATCH') ? 1440 : 832);
        if (scenario.startsWith('BATCH')) expect(formBox.width).toBeGreaterThan(832);
        expect(Math.abs(formBox.x - (width - formBox.width) / 2)).toBeLessThanOrEqual(1);
      }
      const nameBox = ['BATCH', 'SERIAL', 'BATCH_SERIAL', 'SAVED'].includes(scenario) ? null : (await page.getByRole('textbox', { name: 'Product name', exact: true }).boundingBox())!;
      if (nameBox) {
      const typeBox = (await page.getByRole('combobox', { name: 'Type', exact: true }).boundingBox())!;
      expect(Math.abs(typeBox.x - nameBox.x)).toBeLessThanOrEqual(1);
      expect(Math.abs(typeBox.width - nameBox.width)).toBeLessThanOrEqual(1);
      if (width <= 390) {
        // Keep useful input space after both the page and card gutters.
        expect(nameBox.width).toBeGreaterThanOrEqual(width - 68);
      }
      if (scenario === 'CONFIGURED') {
        for (const label of ['Model', 'MRP']) {
          const box = (await page.getByRole('textbox', { name: label, exact: true }).boundingBox())!;
          expect(Math.abs(box.width - nameBox!.width)).toBeLessThanOrEqual(1);
          expect(Math.abs(box.x - nameBox.x)).toBeLessThanOrEqual(1);
        }
      }
      // Hints and errors must not shift the neighbouring input off its row.
      }
      for (const pair of await page.locator('.janso-fieldpair').all()) {
        if (!await pair.isVisible()) continue;
        const controls = await pair.locator('input, select').all();
        if (controls.length !== 2) continue;
        const [first, second] = await Promise.all(controls.map((control: { boundingBox: () => Promise<{ x: number; y: number; height: number } | null> }) => control.boundingBox()));
        if (width > 640) expect(Math.abs(first!.y - second!.y)).toBeLessThanOrEqual(1);
        else {
          expect(Math.abs(first!.x - second!.x)).toBeLessThanOrEqual(1);
          expect(second!.y).toBeGreaterThan(first!.y + first!.height);
        }
      }
      for (const control of await page.locator('input,select,button,a').all()) {
        if (!await control.isVisible()) continue;
        if (['BATCH', 'SERIAL', 'BATCH_SERIAL'].includes(scenario) && await control.evaluate((element: HTMLElement) => !!element.closest('.janso-product-batch-scroll'))) continue;
        const box = (await control.boundingBox())!;
        expect(box.x).toBeGreaterThanOrEqual(0);
        expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
      }
      expect(await page.getByLabel(kind === 'GOODS' ? 'HSN' : 'SAC', { exact: true }).count()).toBe(['MULTI', 'CLASSIFICATION', 'BATCH', 'SERIAL', 'BATCH_SERIAL', 'SAVING', 'SAVED'].includes(scenario) ? 0 : 1);
      if (scenario === 'MULTI') {
        for (const name of ['Retail', 'Wholesale', 'Distributor']) {
          const box = (await page.getByRole('textbox', { name, exact: true }).boundingBox())!;
          expect(Math.abs(box.width - nameBox!.width)).toBeLessThanOrEqual(1);
        }
      }
      expect(await page.getByLabel('Opening quantity', { exact: true }).count()).toBe(kind === 'GOODS' && !scenario.startsWith('BATCH') && scenario !== 'SAVED' ? 1 : 0);
      expect(await page.getByLabel('MRP', { exact: true }).count()).toBe(scenario === 'CONFIGURED' ? 1 : 0);
      if (scenario === 'CONFIGURED') {
        expect(await page.getByRole('switch').count()).toBe(3);
        for (const control of await page.getByRole('switch').all()) {
          const box = (await control.boundingBox())!;
          expect(box.width).toBeGreaterThan(20); expect(box.height).toBeGreaterThan(16);
          // The complete visible label activates the compact shared switch.
          const target = await control.evaluate((node: HTMLElement) => node.closest('label')!.getBoundingClientRect().height);
          expect(target).toBeGreaterThanOrEqual(44);
        }
      }
      if (scenario === 'ERROR') expect(await page.locator('[aria-invalid="true"]').count()).toBeGreaterThan(0);
      if (scenario !== 'SAVING' && scenario !== 'SAVED') expect(await page.getByRole('link', { name: 'Cancel', exact: true }).evaluate((node: HTMLElement) => getComputedStyle(node).color))
        .toBe(await page.locator('body').evaluate((node: HTMLElement) => getComputedStyle(node).color));
      const save = page.getByRole('button', { name: 'Save product' });
      const action = scenario === 'SAVED' ? page.getByRole('link', { name: 'Create another product' }) : scenario === 'UNAVAILABLE' ? page.getByRole('button', { name: 'Clear unavailable details' }) : save;
      if (scenario === 'UNAVAILABLE') expect(await save.isDisabled()).toBe(true);
      if (scenario === 'SAVING') {
        expect(await page.getByRole('button', { name: 'Saving…' }).isDisabled()).toBe(true);
        expect(await page.getByRole('textbox', { name: 'Product name', exact: true }).isDisabled()).toBe(true);
      } else {
        await action.scrollIntoViewIfNeeded(); await action.focus();
        expect(await action.evaluate((node: HTMLElement) => node === document.activeElement)).toBe(true);
      }
      await page.screenshot({ path: resolve(artifacts, scenario + '-' + width + '-' + theme + '.png'), fullPage: true, animations: 'disabled' });
    }
  } finally { await browser.close(); }
}, 120000);
