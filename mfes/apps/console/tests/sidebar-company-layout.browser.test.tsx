import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { render } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { AppShell, CalendarIcon, ContextSwitcher, Rail, RailItem, RailSection, TopBar, DashboardIcon } from '@janso/ui';
import { consoleLayoutCss } from './console-layout-fixture';

it('contains long company names and codes inside expanded, collapsed and mobile rails', async () => {
  const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const page = await browser.newPage({ reducedMotion: 'reduce' });
  const artifacts = resolve('../../../.tools/sidebar-company-ui-review');
  mkdirSync(artifacts, { recursive: true });
  // Restore the shell's own scrolling after the standalone page fixture's override.
  const css = consoleLayoutCss() + '\nbody { overflow: hidden; }';
  const cases = [
    { name: 'Northwind Overseas Trading and Manufacturing Private Limited', code: 'NW-009' },
    { name: 'NorthwindOverseasTradingAndManufacturingPrivateLimited', code: 'NW-009' },
    { name: 'Northwind', code: 'NORTHWIND-OVERSEAS-MANUFACTURING-REGIONAL-OFFICE-009' },
  ];
  try {
    for (const [index, company] of cases.entries()) {
      const view = render(<AppShell
        rail={<Rail brand={<span>KiscoBooks</span>} switcher={<div className="janso-switcher">
          <ContextSwitcher label="Switch company" name={company.name} overline={company.code} options={[{ id: 'company', ...company }]} selectedId="company" onSelect={vi.fn()} />
          <ContextSwitcher label="Switch financial year" name="FY2026-2027" overline="Financial year" options={[{ id: 'year', name: 'FY2026-2027' }]} selectedId="year" onSelect={vi.fn()} icon={<CalendarIcon />} compact />
        </div>}>
          <RailSection label="Ledger"><RailItem icon={<DashboardIcon />} label="Dashboard" href="/" /></RailSection>
        </Rail>}
        topBar={<TopBar right={<span>Account</span>} />}
      ><h1>Overview</h1></AppShell>);
      await page.setContent('<!doctype html><html data-theme="light"><head><meta name="viewport" content="width=device-width"><style>' + css + '</style></head><body class="janso-root">' + view.container.innerHTML + '</body></html>');
      await page.evaluate(() => document.fonts.ready);
      for (const width of [1440, 1024, 961, 960, 390, 320]) for (const fontSize of [16, 32]) for (const theme of ['light', 'dark', 'ledger']) for (const collapsed of [false, true]) {
        await page.setViewportSize({ width, height: 900 });
        await page.evaluate(({ fontSize, theme, collapsed }: { fontSize: number; theme: string; collapsed: boolean }) => {
          document.documentElement.style.fontSize = fontSize + 'px';
          document.documentElement.dataset.theme = theme;
          const shell = document.querySelector<HTMLElement>('.janso-shell')!;
          shell.dataset.collapsed = String(collapsed);
          shell.dataset.drawer = 'open';
        }, { fontSize, theme, collapsed });
        const context = `case ${index}, ${width}px, font ${fontSize}, ${theme}, collapsed ${collapsed}`;
        const geometry = await page.getByRole('button', { name: /Switch company/ }).evaluate((button: HTMLElement) => {
          const rail = button.closest('.janso-shell__rail')!;
          const chevron = button.querySelector('.janso-org__chevron')!;
          return { rail: rail.getBoundingClientRect().right, button: button.getBoundingClientRect().right, chevron: chevron.getBoundingClientRect().right, scroll: button.scrollWidth, client: button.clientWidth };
        });
        expect(geometry.button, context + ' button stays inside rail').toBeLessThanOrEqual(geometry.rail);
        expect(geometry.scroll, context + ' text does not spill out').toBeLessThanOrEqual(geometry.client + 1);
        if (!collapsed || width <= 960) {
          expect(geometry.chevron, context + ' switch control stays inside button').toBeLessThanOrEqual(geometry.button);
          await page.getByRole('button', { name: /Switch company/ }).focus();
          expect(await page.getByRole('button', { name: /Switch company/ }).evaluate((button: HTMLElement) => document.activeElement === button)).toBe(true);
        }
        if (theme === 'light' && fontSize === 16 && !collapsed && [1440, 320].includes(width)) {
          await page.screenshot({ path: resolve(artifacts, `company-${index}-${width}.png`) });
        }
      }
      view.unmount();
    }
  } finally { await browser.close(); }
}, 120_000);
