import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import { OverviewView } from '../app/components/OverviewView';
import { anchorOf } from '../app/lib/overview-periods';
import { renderWithProviders } from './helpers';
import { overviewFixture, type Daily } from './overview-fixture';

/*
 * The overview as a reader sees it: real component DOM and the shared stylesheets, rendered in a
 * browser at four widths in every theme. The data is a fixture that exists only under `tests/` —
 * the application itself never carries sample figures. Opt in with QA_OVERVIEW_BROWSER=1; the
 * screenshots land in `.test_artifacts/` for review.
 */
const css = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css', 'janso-ui.css', 'controls.css', 'data.css', 'chart.css', 'table.css', 'search-select.css', 'overlay.css', 'setup.css']
  .map(name => readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8')).join('\n')
  + readFileSync(resolve('app/globals.css'), 'utf8').replace('overflow: hidden', 'overflow: auto');

const company = '01234567-89ab-4cde-8fab-0123456789ab';
/** Weekday trading with a slow wave and a quiet Sunday: tens of thousands of rupees a day. */
const trading: Daily = (date, index) => {
  if (new Date(date + 'T00:00:00Z').getUTCDay() === 0) return { income: 0, expenses: 0 };
  const wave = 1 + Math.sin(index / 6);
  return { income: Math.round(wave * 4_100_000) + 1_200_000, expenses: Math.round((2 - wave) * 1_450_000) + 300_000 };
};

const scenarios = {
  populated: overviewFixture({ company, from: '2026-04-01', to: '2026-11-01', daily: trading, scale: 500, change: { coverage_start: '2026-04-01', earlier_history_unavailable: false } }),
  month: overviewFixture({ company, from: '2026-10-03', to: '2026-11-01', daily: trading, scale: 500 }),
  quiet: overviewFixture({ company, quiet: true }),
} as const;

function matchMedia(narrow: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string) => ({ matches: narrow && query.includes('max-width'), media: query, addEventListener: () => undefined, removeEventListener: () => undefined }),
  });
}

it.runIf(process.env.QA_OVERVIEW_BROWSER === '1')('keeps figure details concise and readable on desktop and mobile', async () => {
  const html = await markup('populated', false);
  const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  mkdirSync(resolve('../../../.test_artifacts'), { recursive: true });
  try {
    const page = await browser.newPage();
    for (const width of [1440, 390]) for (const theme of ['light', 'dark', 'ledger']) {
      await page.setViewportSize({ width, height: 1000 });
      await page.setContent('<!doctype html><html data-theme="' + theme + '"><head><style>' + css + '</style></head><body class="janso-root">' + html + '</body></html>');
      await page.getByText('About these figures', { exact: true }).click();
      const details = page.locator('details').filter({ hasText: 'About these figures' });
      expect(await details.locator('dt').count()).toBe(3);
      expect((await details.innerText()).trim().split(/\s+/).length).toBeLessThan(80);
      const bounds = (await details.boundingBox())!;
      expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
      expect(bounds.height).toBeLessThan(500);
      await details.screenshot({ path: resolve('../../../.test_artifacts/overview-copy-' + width + '-' + theme + '.png') });
    }
  } finally { await browser.close(); }
}, 60000);

async function markup(scenario: keyof typeof scenarios, narrow: boolean) {
  matchMedia(narrow);
  const data = scenarios[scenario];
  const view = await renderWithProviders(<OverviewView data={data} anchor={anchorOf(data)} period="ytd" onPeriod={() => undefined} refreshing={false} onRefresh={() => undefined}
    companyName="Janso Retail Pvt Ltd" yearLabel="FY 2026-27" company={company} canReadCustomers links={{ voucher: '/vouchers/new/sales', opening: '/accounting/opening' }} />);
  await screen.findByText('Cash and bank');
  const html = view.container.innerHTML;
  view.unmount();
  return html;
}

it.runIf(process.env.QA_OVERVIEW_BROWSER === '1').each(Object.keys(scenarios) as (keyof typeof scenarios)[])('keeps the %s overview readable at four widths in every theme', async scenario => {
  localStorage.clear();
  const wide = await markup(scenario, false), narrow = await markup(scenario, true);
  const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    for (const width of [1440, 1024, 768, 390]) for (const theme of ['light', 'dark', 'ledger']) {
      await page.setViewportSize({ width, height: 1000 });
      const html = width <= 680 ? narrow : wide;
      await page.setContent(`<!doctype html><html data-theme="${theme}"><head><meta name="viewport" content="width=device-width"><style>${css}</style></head><body class="janso-root"><main>${html}</main></body></html>`);
      await page.screenshot({ path: resolve(`../../../.test_artifacts/overview-${scenario}-${width}-${theme}.png`), fullPage: true, animations: 'disabled' });
      const overflowing = await page.evaluate((limit: number) => [...document.querySelectorAll('main *')]
        .filter(node => node.getBoundingClientRect().right > limit + 1)
        .slice(0, 6).map(node => node.tagName.toLowerCase() + '.' + String(node.getAttribute('class')).split(' ')[0]), width);
      expect(await page.evaluate(() => document.documentElement.scrollWidth), `${scenario} ${theme} ${width} document, wider: ${overflowing.join(', ')}`).toBeLessThanOrEqual(width);
      const tiles = await page.locator('.janso-stat').all();
      expect(tiles).toHaveLength(4);
      const tops = new Set<number>();
      for (const tile of tiles) tops.add(Math.round((await tile.boundingBox())!.y));
      // 4-up above 1100px, 2-up to 680px, a single column below
      expect(tops.size, `${scenario} ${theme} ${width} KPI rows`).toBe(width > 1100 ? 1 : width > 680 ? 2 : 4);
      // the two card bands stack below 1100px and sit side by side above it
      const cards = await page.locator('.janso-grid > .janso-card').all();
      expect(cards).toHaveLength(4);
      const first = (await cards[0]!.boundingBox())!, second = (await cards[1]!.boundingBox())!;
      if (width > 1100) expect(Math.abs(first.y - second.y), `${scenario} ${theme} ${width} band`).toBeLessThanOrEqual(1);
      else expect(second.y, `${scenario} ${theme} ${width} stacked`).toBeGreaterThanOrEqual(first.y + first.height);
      for (const card of cards) expect((await card.boundingBox())!.x + (await card.boundingBox())!.width, `${scenario} ${theme} ${width} card edge`).toBeLessThanOrEqual(width);
      if (scenario !== 'quiet') {
        expect(await page.locator('.janso-chart__legend-item').count()).toBe(2);
        // tick text must stay readable: the drawing is no more than ~1.4x down-scaled on a phone
        const scale = await page.locator('.janso-chart__svg').evaluate((node: SVGSVGElement) => node.getBoundingClientRect().width / node.viewBox.baseVal.width);
        if (width <= 680) expect(scale, `${scenario} ${theme} ${width} chart scale`).toBeGreaterThan(0.7);
      }
    }
  } finally { await browser.close(); }
}, 240_000);

/*
 * `apps/console/preview.html`: the same real component markup and shared stylesheets as a
 * dependency-free static page (double-click it, no build step), with a theme switch. It is
 * generated, so it cannot drift from the screen: regenerate with QA_OVERVIEW_PREVIEW=1. The
 * figures are the fixture's — they exist only here and in that file.
 */
it.runIf(process.env.QA_OVERVIEW_PREVIEW === '1')('writes the static design preview from the real components', async () => {
  localStorage.clear();
  const html = await markup('populated', false);
  const page = `<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KiscoBooks console — Business overview (static preview)</title>
<!--
  GENERATED by apps/console/tests/overview-layout.browser.test.tsx — do not edit by hand.
  Regenerate: QA_OVERVIEW_PREVIEW=1 pnpm --filter @janso/console exec vitest run tests/overview-layout.browser.test.tsx
  Real component markup and the shared stylesheets; sample figures live only in tests/overview-fixture.ts.
-->
<style>${css}
.preview-themes { display: flex; gap: .5rem; padding: .75rem 1.5rem 0; font: 13px system-ui, sans-serif; }
.preview-themes button { font: inherit; padding: .25rem .75rem; border: 1px solid var(--janso-control-line); border-radius: 6px; background: var(--janso-surface); color: var(--janso-ink); cursor: pointer; }
.preview-themes button[aria-pressed='true'] { border-color: var(--janso-brand); color: var(--janso-brand); }
</style>
</head>
<body class="janso-root">
<div class="preview-themes" role="group" aria-label="Theme">
<button type="button" aria-pressed="true" data-theme-choice="light">Light</button>
<button type="button" aria-pressed="false" data-theme-choice="dark">Dark</button>
<button type="button" aria-pressed="false" data-theme-choice="ledger">Ledger</button>
</div>
<main>${html}</main>
<script>
document.querySelectorAll('[data-theme-choice]').forEach(function (button) {
  button.addEventListener('click', function () {
    document.documentElement.setAttribute('data-theme', button.dataset.themeChoice);
    document.querySelectorAll('[data-theme-choice]').forEach(function (other) { other.setAttribute('aria-pressed', String(other === button)); });
  });
});
</script>
</body>
</html>
`;
  writeFileSync(resolve('preview.html'), page);
  expect(page).toContain('Business overview');
}, 60_000);
