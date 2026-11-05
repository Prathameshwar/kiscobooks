import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { AccountingConfigurationEditor } from '../app/components/AccountingConfigurationEditor';
import { accountingResource } from '../app/lib/accounting-configuration-resources';
import { serviceCall } from '../app/lib/service-call';
import { capture } from './master-opening-fixture';
import { COMPANY, GROUP, response } from './accounting-configuration-fixtures';
import { consoleLayoutCss } from './console-layout-fixture';

vi.mock('../app/lib/service-call', async original => ({ ...await original<typeof import('../app/lib/service-call')>(), serviceCall: vi.fn() }));
const resources = ['parties', 'party-roles', 'accounts', 'party-addresses', 'party-address-uses', 'party-contacts', 'party-contact-uses', 'party-tax-registrations'];

it.each(['account', 'party', 'supplier'])('keeps %s creation and opening readable across widths and themes', async kind => {
  vi.mocked(serviceCall).mockReset();
  vi.mocked(serviceCall).mockImplementation(async (_, request) => request.path.endsWith('/master-balances/capture') ? { ...capture, company_id: COMPANY } as never : response(request.path, request.method, request.body) as never);
  const account = kind === 'account';
  const view = render(<AccountingConfigurationEditor company={COMPANY} config={accountingResource(account ? 'accounts' : 'parties')!} supplier={kind === 'supplier'} prefills={account ? { kind: 'GENERAL', group_id: GROUP } : undefined} availableResources={resources} manageableResources={resources} />);
  fireEvent.change(await screen.findByRole('textbox', { name: 'Code' }), { target: { value: 'CREATION-REVIEW' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Name' }), { target: { value: 'A long descriptive account or party name for layout review' } });
  if (kind === 'party') fireEvent.change(screen.getByRole('combobox', { name: 'Party role' }), { target: { value: 'CUSTOMER' } });
  const submitName = account ? 'Create account' : kind === 'supplier' ? 'Create supplier' : 'Create party';
  await waitFor(() => expect(screen.getByRole('button', { name: submitName })).toBeEnabled());
  if (account) expect(screen.getByText(/Opening balance is optional\. Enter it in the final step/)).toBeVisible();
  const css = consoleLayoutCss(), artifacts = resolve('../../../.tools/account-party-creation-ui-review'); mkdirSync(artifacts, { recursive: true });
  const { chromium } = createRequire(resolve('../../../.tools/ui-review-runner/package.json'))('playwright');
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage();
    const stages = account ? [0, 1] : [0, 1, 2, 3, 4];
    for (const stage of stages) {
      const step = account ? stage : Math.min(stage, 3);
      await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getAllByRole('button')[step]!);
      if (!account && stage === 1) for (const name of ['Add default address', 'Add default contact']) await userEvent.click(screen.getByRole('checkbox', { name }));
      if (!account && stage === 2) await userEvent.click(screen.getByRole('checkbox', { name: 'Add tax registration' }));
      if ((account && stage === 1) || (!account && stage >= 3)) {
        await waitFor(() => expect(screen.getByRole('textbox', { name: 'Opening balance' })).toBeEnabled());
        if (stage === 4) {
          await userEvent.click(screen.getByRole('radio', { name: 'Bill-wise' }));
          for (const [name, value] of [['Bill number', 'OPENING-2026-0001'], ['Bill amount', '2000'], ['Pending amount', '1000.0001'], ['Bill date', '2026-03-12'], ['Due date', '2026-04-10']]) fireEvent.change(screen.getByLabelText(name!), { target: { value } });
          await userEvent.click(screen.getByRole('button', { name: 'Add bill' }));
          await userEvent.click(screen.getByRole('button', { name: 'Add another bill' }));
        } else fireEvent.change(screen.getByRole('textbox', { name: 'Opening balance' }), { target: { value: '1000.0001' } });
      }
      // Serialize current native control values into the standalone browser snapshot.
      for (const select of view.container.querySelectorAll('select')) for (const option of select.options) option.toggleAttribute('selected', option.selected);
      for (const input of view.container.querySelectorAll('input')) { input.setAttribute('value', input.value); if (['checkbox', 'radio'].includes(input.type)) input.toggleAttribute('checked', input.checked); }
      await page.setContent('<!doctype html><html data-theme="light"><head><meta name="viewport" content="width=device-width"><style>' + css + '</style></head><body class="janso-root">' + view.container.innerHTML + '</body></html>');
      await page.evaluate(() => document.fonts.ready);
      for (const width of [1440, 768, 390, 320]) for (const theme of ['light', 'dark', 'ledger']) {
        await page.setViewportSize({ width, height: 1000 }); await page.evaluate((value: string) => { document.documentElement.dataset.theme = value; }, theme);
        await page.screenshot({ path: resolve(artifacts, kind + '-' + stage + '-' + width + '-' + theme + '.png'), fullPage: true, animations: 'disabled' });
        const size = await page.evaluate(() => ({ width: document.documentElement.clientWidth, content: document.documentElement.scrollWidth }));
        expect(size.content, kind + ' step ' + stage + ' width ' + width).toBeLessThanOrEqual(size.width + 1);
        const headerGap = await page.locator('.janso-page-header').evaluate((element: HTMLElement) => element.nextElementSibling!.getBoundingClientRect().top - element.getBoundingClientRect().bottom);
        expect(headerGap, 'Header spacing').toBeLessThanOrEqual(17);
        const submit = page.getByRole('button', { name: submitName, exact: true }); expect(await submit.isVisible()).toBe(true); await submit.focus();
        expect(await submit.evaluate((element: HTMLElement) => document.activeElement === element)).toBe(true);
        if (width <= 390) for (const label of await page.locator('.janso-stepper__text > span:first-child').all()) expect(await label.evaluate((element: HTMLElement) => element.getBoundingClientRect().height / parseFloat(getComputedStyle(element).lineHeight))).toBeLessThanOrEqual(2.1);
        if (width === 1440 && stage === 0) for (const grid of await page.locator('form .janso-form-grid').all()) expect(await grid.evaluate((element: HTMLElement) => getComputedStyle(element).gridTemplateColumns.split(' ').length)).toBeLessThanOrEqual(2);
        if (stage === 4) {
          const pending = page.locator('tbody td[data-label="Pending"]'); expect(await pending.isVisible()).toBe(true); expect((await pending.boundingBox())!.width).toBeGreaterThan(30);
        }
      }
      await page.setViewportSize({ width: 768, height: 1000 }); await page.evaluate(() => { document.documentElement.style.zoom = '2'; });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
    }
    await userEvent.click(within(screen.getByRole('navigation', { name: 'Setup progress' })).getAllByRole('button')[0]!);
    expect(screen.getByRole('textbox', { name: 'Code' })).toHaveValue('CREATION-REVIEW');
    expect(vi.mocked(serviceCall).mock.calls.some(([, request]) => request.method === 'POST')).toBe(false);
  } finally { await browser.close(); view.unmount(); }
}, 120_000);
