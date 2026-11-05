import { createRequire } from 'node:module';
import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';
import { AppShell, Rail, Wordmark } from '@janso/ui';
import { AuthShell } from '../app/components/AuthShell';
import { renderScreen } from './helpers';

// Real shared wordmark, console rail and auth shell DOM/styles, without a live backend.
it.runIf(process.env.QA_BRANDING_BROWSER === '1').each(['auth', 'rail', 'collapsed'])('keeps the %s brand readable across themes and widths', async surface => {
  const root = resolve('../../..');
  const styles = resolve('../../packages/ui/src/styles');
  const css = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css', 'janso-ui.css', 'theme.css', 'shell.css']
    .map(name => readFileSync(resolve(styles, name), 'utf8')).join('\n')
    + readFileSync(resolve('app/auth.css'), 'utf8');
  const font = readFileSync(resolve(styles, '../assets/fonts/InterVariable.woff2')).toString('base64');
  const fontCss = `@font-face { font-family: Inter; font-weight: 100 900; src: url(data:font/woff2;base64,${font}) format('woff2'); }`;
  const view = renderScreen(surface === 'auth' ? <AuthShell><h1>Sign in</h1></AuthShell> : <AppShell collapsed={surface === 'collapsed'}
    rail={<Rail brand={<Wordmark size={28} nameSize="1.0625rem" strapline="Always balances" />}><span>Navigation</span></Rail>}
    topBar={<span>Business overview</span>}><main>Content</main></AppShell>);
  const html = view.container.innerHTML;
  const { chromium } = createRequire(resolve(root, '.tools/ui-review-runner/package.json'))('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const artifactRoot = resolve(root, '.test_artifacts/kiscobooks-branding');
  mkdirSync(artifactRoot, { recursive: true });
  try {
    const page = await browser.newPage();
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const width of [1440, 768, 390, 320]) for (const theme of ['light', 'dark', 'ledger']) {
      await page.setViewportSize({ width, height: 900 });
      await page.setContent(`<!doctype html><html data-theme="${theme}"><head><style>${fontCss}${css}</style></head><body class="janso-root">${html}</body></html>`);
      await page.evaluate(() => document.fonts.ready);
      if (surface === 'rail' && width <= 960) {
        // Review the drawer's open styling; browser tests here do not hydrate fixture DOM.
        await page.locator('.janso-shell').evaluate((el: HTMLElement) => el.setAttribute('data-drawer', 'open'));
      }
      const brands = page.locator('.janso-wordmark__name:visible');
      if (surface === 'collapsed') {
        expect(await brands.count()).toBe(0);
        if (width > 960) expect(await page.getByRole('img', { name: 'KiscoBooks' }).isVisible()).toBe(true);
      } else {
        expect(await brands.count()).toBe(1);
        const brand = brands.first();
        expect(await brand.textContent()).toBe('KiscoBooks');
        const parts = await brand.locator('span').evaluateAll((elements: Element[]) => elements.map(el => {
          const box = el.getBoundingClientRect();
          return { left: box.left, right: box.right, top: box.top, bottom: box.bottom, color: getComputedStyle(el).color };
        }));
        expect(parts[0]!.color).not.toBe(parts[1]!.color);
        expect(Math.abs(parts[0]!.right - parts[1]!.left)).toBeLessThan(1);
        expect(parts[0]!.top).toBe(parts[1]!.top);
        expect(parts[1]!.right).toBeLessThanOrEqual(width);
        const clipping = await brand.evaluate((el: HTMLElement) => {
          const r = el.getBoundingClientRect();
          let parent = el.parentElement;
          while (parent) {
            if (['hidden', 'clip'].includes(getComputedStyle(parent).overflowX)) {
              const p = parent.getBoundingClientRect();
              if (r.left < p.left - 1 || r.right > p.right + 1) return true;
            }
            parent = parent.parentElement;
          }
          return false;
        });
        expect(clipping, `${surface} ${width} ${theme} wordmark`).toBe(false);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
      await page.screenshot({ path: resolve(artifactRoot, `${surface}-${width}-${theme}.png`), fullPage: true });
    }
  } finally { await browser.close(); view.unmount(); }
}, 120_000);
