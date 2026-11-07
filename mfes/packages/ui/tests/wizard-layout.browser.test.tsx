import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';
import { Button } from '../src/components/Button';
import { TextField } from '../src/components/TextField';
import { WizardLayout } from '../src/components/WizardLayout';

it.runIf(process.env.QA_WIZARD_BROWSER === '1')('keeps wizard actions visible and fields reachable on short and narrow screens', async () => {
  const require = createRequire(resolve(__dirname, '../package.json'));
  const { chromium } = require(process.env.QA_PLAYWRIGHT_MODULE || resolve(__dirname, '../../../../.tools/ui-review-runner/node_modules/playwright'));
  const browser = await chromium.launch({ executablePath: process.env.QA_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const css = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css', 'janso-ui.css', 'data.css', 'setup.css']
    .map(name => readFileSync(resolve(__dirname, '../src/styles', name), 'utf8')).join('\n');
  const markup = renderToStaticMarkup(<WizardLayout brand="JANSO" steps={['Business', 'Location and tax', 'Money and calendar', 'What you track', 'Presentation', 'Review and create']}
    current={4} reached={5} title="Presentation" subtitle="Choose how dates, amounts and quantities appear." onSubmit={event => event.preventDefault()}
    actions={<><Button type="button">Leave for now</Button><Button type="submit">Retry the remaining steps</Button></>}>
    {Array.from({ length: 12 }, (_, index) => <TextField key={index} label={'Setting ' + index} hint="A setting with guidance." />)}
    <figure className="janso-preview"><dl className="janso-preview__grid"><div className="janso-preview__row">
      <dt className="janso-preview__key">A date and time</dt><dd className="janso-preview__value">06-11-2026 20:00</dd>
    </div></dl></figure>
  </WizardLayout>);
  try {
    const page = await browser.newPage();
    for (const width of [320, 390, 768, 1440]) for (const height of [390, 844]) for (const font of [16, 20]) for (const theme of ['light', 'dark', 'ledger']) {
      await page.setViewportSize({ width, height });
      await page.setContent('<!doctype html><html data-theme="' + theme + '"><head><meta name="viewport" content="width=device-width"><style>' + css
        + 'html{font-size:' + font + 'px}body{margin:0;overflow:hidden}</style></head><body class="janso-root">' + markup + '</body></html>');
      const action = page.getByRole('button', { name: 'Retry the remaining steps' });
      await page.locator('form').evaluate((form: HTMLFormElement) => { form.addEventListener('submit', event => event.preventDefault()); });
      const initial = (await action.boundingBox())!;
      expect(initial.y).toBeGreaterThanOrEqual(0);
      expect(initial.y + initial.height).toBeLessThanOrEqual(height);
      await action.click();
      await page.locator('.janso-setup__scroll').evaluate((node: HTMLElement) => { node.scrollTop = node.scrollHeight; });
      expect((await action.boundingBox())!.y).toBe(initial.y);
      for (const control of await page.locator('button,input,.janso-preview__row').all()) {
        const bounds = (await control.boundingBox())!;
        expect(bounds.x).toBeGreaterThanOrEqual(0);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(width + 1);
      }
      expect(await page.locator('.janso-setup__scroll').evaluate((node: HTMLElement) => node.scrollTop)).toBeGreaterThan(0);
      const preview = (await page.locator('.janso-preview').boundingBox())!;
      expect(preview.y + preview.height).toBeLessThanOrEqual((await page.locator('footer').boundingBox())!.y);
    }
  } finally { await browser.close(); }
}, 60000);
