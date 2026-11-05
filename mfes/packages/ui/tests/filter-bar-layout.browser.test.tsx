/** Actual browser geometry for the shared master-directory filter controls. */
import { createRequire } from 'node:module';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterAll, beforeAll, expect, it } from 'vitest';
import { FilterBar } from '../src/components/FilterBar';
import { TableSearch } from '../src/components/TableSearch';
import { SearchSelect } from '../src/components/SearchSelect';
import { Select } from '../src/components/Select';
import { TextField } from '../src/components/TextField';
import { Button } from '../src/components/Button';

const root = resolve(process.cwd(), '../../..');
const require = createRequire(resolve(process.cwd(), 'package.json'));
const { chromium } = require(resolve(root, '.tools/ui-review-runner/node_modules/playwright'));
const artifactRoot = resolve(root, '.test_artifacts/master-filter-layout');
let browser: Awaited<ReturnType<typeof chromium.launch>>;
const nothing = () => undefined;
const css = () => ['tokens.css', 'theme-light.css', 'janso-ui.css', 'search-select.css', 'table.css', 'data.css'].map(name => readFileSync(resolve(process.cwd(), 'src/styles', name), 'utf8')).join('\n');
beforeAll(async () => {
  mkdirSync(artifactRoot, { recursive: true });
  browser = await chromium.launch({ executablePath: process.env.QA_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
}, 30000);
afterAll(async () => { await browser?.close(); }, 30000);
it.each([1440, 768, 390])('keeps lookup, selected lookup, text, select and native date outer boxes aligned at %ipx', async width => {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  try {
    const html = renderToStaticMarkup(<main className="janso-page"><div className="janso-form-grid">
      <SearchSelect label="Supplier" value={null} options={[]} onChange={nothing} />
      <SearchSelect label="Payable" value="account" selected={{ id: 'account', label: 'Supplier payable account' }} options={[]} disabled onChange={nothing} />
      <TextField label="Reference" value="BILL-1" onChange={nothing} />
      <Select label="Purpose" value="GENERAL" options={[{ value: 'GENERAL', label: 'General' }]} onChange={nothing} />
      <TextField label="Due date" type="date" value="2026-10-30" onChange={nothing} />
    </div></main>);
    await page.setContent('<!doctype html><html data-theme="light"><head><style>' + css() + '</style></head><body class="janso-root">' + html + '</body></html>');
    const boxes: { top: number; height: number; right: number }[] = await page.locator('.janso-search-select__control,.janso-input').evaluateAll((elements: Element[]) => elements.map(el => {
      const box = el.getBoundingClientRect(); return { top: box.top, height: box.height, right: box.right };
    }));
    expect(boxes).toHaveLength(5);
    for (const box of boxes) { expect(box.height).toBeCloseTo(36, 0); expect(box.right).toBeLessThanOrEqual(width); }
    for (const box of boxes.filter(box => Math.abs(box.top - boxes[0]!.top) < 20)) expect(box.top).toBeCloseTo(boxes[0]!.top, 0);
    await page.getByLabel('Supplier', { exact: true }).focus();
    expect(await page.getByLabel('Supplier', { exact: true }).evaluate((el: Element) => el === document.activeElement)).toBe(true);
  } finally { await page.close(); }
}, 30000);
it.each([1440, 768, 390])('aligns query, native select, entity lookup and date controls at %ipx with hints below', async width => {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  try {
    const html = renderToStaticMarkup(<main className="janso-page"><FilterBar actions={<Button>Refresh</Button>}>
      <TableSearch value="" onChange={nothing} hint="Search by code or name." />
      <Select label="Status" value="" options={[{ value: '', label: 'All statuses' }]} onChange={nothing} hint="Available records" />
      <SearchSelect label="Filter by canonical unit" value={null} options={[]} onChange={nothing} hint="Select an active product." />
      <TextField label="Effective on" type="date" value="" onChange={nothing} />
    </FilterBar></main>);
    await page.setContent('<!doctype html><html data-theme="light"><head><style>' + css() + '</style></head><body class="janso-root">' + html + '</body></html>');
    const geometry = await page.evaluate(() => {
      const fields = [...document.querySelectorAll('.janso-filter-bar__controls .janso-field')];
      const box = (el: Element) => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, height: r.height }; };
      return { width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, fields: fields.map(field => ({ box: box(field), control: box(field.querySelector('.janso-input-wrap,.janso-select__wrap,.janso-search-select__control')!), hint: field.querySelector('.janso-hint') ? box(field.querySelector('.janso-hint')!) : null })) };
    });
    await page.screenshot({ path: resolve(artifactRoot, 'mixed-filters-' + width + '.png'), fullPage: true });
    expect(geometry.fields).toHaveLength(4);
    for (const field of geometry.fields) {
      expect(Math.abs(field.control.top - field.box.top)).toBeLessThanOrEqual(1);
      expect(field.control.height).toBe(36);
      expect(field.control.left).toBeGreaterThanOrEqual(0);
      expect(field.control.right).toBeLessThanOrEqual(width + 1);
      if (field.hint) expect(field.hint.top).toBeGreaterThanOrEqual(field.control.bottom);
    }
    expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.width + 1);
    for (const name of ['Status', 'Filter by canonical unit', 'Effective on']) {
      const control = page.getByLabel(name, { exact: true });
      await control.focus();
      expect(await control.evaluate((el: Element) => el === document.activeElement)).toBe(true);
    }
  } finally { await page.close(); }
}, 30000);
it('preserves ordinary stacked forms and an explicitly stacked dropdown', async () => {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  try {
    const html = renderToStaticMarkup(<main>
      <TextField label="Company name" value="" onChange={nothing} />
      <SearchSelect label="Account" value={null} options={[]} onChange={nothing} />
      <FilterBar><Select inline={false} label="Explicit stacked filter" value="" options={[]} onChange={nothing} /></FilterBar>
    </main>);
    await page.setContent('<!doctype html><html data-theme="light"><head><style>' + css() + '</style></head><body class="janso-root">' + html + '</body></html>');
    for (const name of ['Company name', 'Account', 'Explicit stacked filter']) {
      const offsets = await page.getByLabel(name, { exact: true }).evaluate((el: Element) => {
        const field = el.closest('.janso-field')!;
        const label = field.querySelector('.janso-field__row')!.getBoundingClientRect();
        const control = field.querySelector('.janso-input-wrap,.janso-select__wrap,.janso-search-select__control')!.getBoundingClientRect();
        return { labelBottom: label.bottom, controlTop: control.top };
      });
      expect(offsets.controlTop).toBeGreaterThan(offsets.labelBottom);
    }
  } finally { await page.close(); }
}, 30000);
it('allows multiple selected lookup chips to grow without clipping at phone width',async()=>{
  const page=await browser.newPage({viewport:{width:390,height:900}});
  try {
    const options=[1,2,3].map(n=>({id:String(n),label:'Selected company record '+n}));
    const html=renderToStaticMarkup(<main className="janso-page"><SearchSelect label="Multiple records" multiple value={options.map(row=>row.id)} options={options} selected={options} onChange={nothing}/></main>);
    await page.setContent('<!doctype html><html data-theme="light"><head><style>'+css()+'</style></head><body class="janso-root">'+html+'</body></html>');
    const bounds=await page.locator('.janso-search-select__control').boundingBox();
    expect(bounds!.height).toBeGreaterThan(36);
    expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(390);
    await page.getByRole('combobox',{name:'Multiple records'}).focus();
    expect(await page.getByRole('combobox',{name:'Multiple records'}).evaluate((el: Element)=>el===document.activeElement)).toBe(true);
  }finally{await page.close();}
},30000);
