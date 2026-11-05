import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it } from 'vitest';
import { PageNavigation } from '@janso/ui';
import { LogsAndActivities } from '../app/components/LogsAndActivities';
import { ActivityFeed } from '../app/components/ActivityFeed';
import { AuditEvents } from '../app/components/AuditEvents';
import { createAuditLoader, createAuditDetailLoader } from '../app/lib/audit-events';
import { getAuditTrail } from '../app/lib/audit-trail';
import { renderWithProviders } from './helpers';

// Real component DOM and shared CSS; transports remain deterministic fixtures.
const css = ['tokens.css', 'theme-light.css', 'theme-dark.css', 'theme-ledger.css', 'janso-ui.css', 'data.css', 'table.css', 'overlay.css'].map(name => readFileSync(resolve('../../packages/ui/src/styles', name), 'utf8')).join('\n')
  // The fixture reviews the content region without the viewport-owning AppShell.
  + readFileSync(resolve('app/globals.css'), 'utf8').replace('overflow: hidden', 'overflow: auto');

it.runIf(process.env.QA_LOGS_BROWSER === '1').each(['hub', 'audit', 'activity', 'organisation'])('keeps %s cards, controls and evidence readable at four widths in every theme', async surface => {
  localStorage.clear();
  const trail = await getAuditTrail(Date.parse('2026-10-30T12:00:00Z'));
  const event = trail.events[0]!;
  event.action = 'catalog.product_configuration.company_policy_revision.publish_with_validation';
  const detail = trail.details[event.id]!;
  detail.changes = { very_long_configuration_field_name_with_no_breaks: { from: '123456789012345678901234567890.0000', to: '123456789012345678901234567891.0000' } };
  let view;
  if (surface === 'hub') view = render(<LogsAndActivities canAudit canActivity />);
  else if (surface === 'activity' || surface === 'organisation') {
    view = await renderWithProviders(<ActivityFeed company="company" organisation={surface === 'organisation'} canOrganisation canAudit load={async () => ({ items: [event], page: { has_more: false, next_cursor: null } })} />);
    await screen.findByText(event.action);
  } else {
    view = await renderWithProviders(<AuditEvents navigation={<PageNavigation back={{ href: '/logs-and-activities', label: 'logs and activities' }} breadcrumbs={[{ label: 'Logs and activities', href: '/logs-and-activities' }, { label: 'Audit logs' }]} />} trail={trail} load={createAuditLoader([event], 0)} loadDetail={createAuditDetailLoader(trail.details, 0)} />);
    await waitFor(() => expect(screen.getByRole('table')).not.toHaveAttribute('aria-busy'));
    await userEvent.click(screen.getByRole('button', { name: /details/i }));
    await screen.findByText('very_long_configuration_field_name_with_no_breaks');
  }
  const html = view.container.innerHTML;
  const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    for (const width of [1440, 768, 390, 320]) for (const theme of ['light', 'dark', 'ledger']) {
      await page.setViewportSize({ width, height: 1000 });
      await page.setContent(`<!doctype html><html data-theme="${theme}"><head><style>${css}</style></head><body class="janso-root"><main>${html}</main></body></html>`);
      await page.screenshot({ path: resolve(`../../../.test_artifacts/logs-${surface}-${width}-${theme}.png`), fullPage: true, animations: 'disabled' });
      expect(await page.evaluate(() => document.documentElement.scrollWidth), `${surface} ${theme} ${width} document`).toBeLessThanOrEqual(width);
      if (surface === 'hub') {
        const cards = await page.locator('.janso-action-card').all();
        expect(cards).toHaveLength(2);
        const first = (await cards[0].boundingBox())!, second = (await cards[1].boundingBox())!;
        expect(Math.abs(first.width - second.width)).toBeLessThanOrEqual(1);
        if (width <= 390) expect(second.y).toBeGreaterThanOrEqual(first.y + first.height);
        else expect(Math.abs(first.y - second.y)).toBeLessThanOrEqual(1);
        await cards[0].focus();
        expect(await cards[0].evaluate((node: HTMLElement) => node.matches(':focus-visible'))).toBe(true);
      } else {
        if (surface === 'audit' && width <= 390) {
          expect(await page.locator('.console-audit-changes thead th').first().evaluate((node: HTMLElement) => node.getBoundingClientRect().width), 'visible Field/Before/After headings').toBeGreaterThan(20);
          expect(await page.locator('.console-audit-changes thead th').first().evaluate((node: HTMLElement) => node.getBoundingClientRect().height), 'readable evidence column headings').toBeGreaterThan(15);
          expect(await page.locator('.janso-table > thead > tr > th').first().evaluate((node: HTMLElement) => getComputedStyle(node).position), 'stacked list headings remain visually clipped').toBe('absolute');
        }
        const overflow = await page.locator('.janso-event-log__toolbar').evaluate((node: HTMLElement) => node.scrollWidth - node.clientWidth);
        expect(overflow, `${surface} toolbar ${width}`).toBeLessThanOrEqual(1);
        if (width <= 390) {
          expect(await page.locator('.janso-table-shell').evaluate((node: HTMLElement) => node.scrollWidth - node.clientWidth), `${surface} stacked rows`).toBeLessThanOrEqual(1);
        }
        if (surface === 'audit') {
          const controls = await page.locator('.janso-filter-bar__controls select').all();
          expect(controls).toHaveLength(3);
          const tops: number[] = [];
          for (const control of controls) tops.push((await control.boundingBox())!.y);
          if (width === 1440) expect(Math.max(...tops) - Math.min(...tops)).toBeLessThanOrEqual(1);
          expect(await page.locator('.console-audit-detail').evaluate((node: HTMLElement) => node.scrollWidth - node.clientWidth), 'expanded evidence').toBeLessThanOrEqual(1);
        }
      }
    }
  } finally { await browser.close(); view.unmount(); }
}, 120_000);
