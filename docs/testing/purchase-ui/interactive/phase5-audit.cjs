const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '../../../..');
const { chromium } = require(path.join(root, '.tools/ui-review-runner/node_modules/playwright'));
const axePath = path.join(root, '.tools/purchase-ui-audit/axe-4.10.3.min.js');
assert.equal(crypto.createHash('sha256').update(fs.readFileSync(axePath)).digest('hex'), '880970c081707360e64f34cea25ff91892f5bc95675b0776925b9709dd8a68bb');
const output = path.join(__dirname, '../phase5');
fs.mkdirSync(output, { recursive: true });
const base = process.env.PURCHASE_REVIEW_URL || 'http://127.0.0.1:4417';
(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const results = [];
  try {
    for (const [name, theme, width, height, query, panel] of [
      ['desktop-light', 'light', 1440, 1000, 'workflow=NEW'],
      ['desktop-dark', 'dark', 1440, 1000, 'workflow=NEW'],
      ['desktop-ledger', 'ledger', 1440, 1000, 'workflow=NEW'],
      ['tablet-light', 'light', 1024, 900, 'workflow=NEW'],
      ['tablet-dark', 'dark', 1024, 900, 'workflow=NEW'],
      ['tablet-ledger', 'ledger', 1024, 900, 'workflow=NEW'],
      ['mobile-light', 'light', 390, 844, 'workflow=NEW'],
      ['mobile-dark', 'dark', 390, 844, 'workflow=NEW'],
      ['mobile-ledger', 'ledger', 390, 844, 'workflow=NEW'],
      ['narrow-320', 'light', 320, 740, 'workflow=NEW'],
      ['landscape-dark', 'dark', 844, 390, 'workflow=DRAFT'],
      ['reflow-200-light', 'light', 720, 500, 'workflow=NEW'],
      ['reflow-200-dark', 'dark', 720, 500, 'workflow=NEW'],
      ['reflow-200-ledger', 'ledger', 720, 500, 'workflow=NEW'],
      ['locale-long-desktop', 'light', 1440, 1000, 'workflow=NEW&long&locale'],
      ['locale-long-mobile', 'ledger', 390, 844, 'workflow=NEW&long&locale'],
      ['empty-validation', 'light', 390, 844, 'workflow=NEW&blank', 'validate'],
      ['components-mobile', 'dark', 390, 844, 'workflow=NEW', 'Discounts & charges'],
      ['receipt-mobile', 'light', 390, 844, 'workflow=NEW&scenario=receipt', 'Goods receipt'],
      ['tracking-mobile', 'ledger', 390, 844, 'workflow=NEW&scenario=tracking', 'Line tracking'],
      ['settlement-mobile', 'light', 390, 844, 'workflow=NEW', 'Payment & terms'],
      ['evidence-mobile', 'dark', 390, 844, 'workflow=NEW', 'Supplier bill & attachments'],
      ['tax-recipient', 'light', 720, 500, 'workflow=NEW&scenario=recipient', 'Tax details'],
      ['submission-mobile', 'light', 390, 844, 'workflow=DRAFT', 'submit'],
      ['correction-mobile', 'ledger', 390, 844, 'workflow=REJECTED', 'correct'],
      ['approved-mobile', 'dark', 390, 844, 'workflow=APPROVED'],
      ['line-editor-mobile', 'light', 390, 844, 'workflow=NEW', 'line'],
      ['line-editor-dark', 'dark', 390, 844, 'workflow=NEW', 'line'],
      ['line-editor-long-locale', 'ledger', 320, 740, 'workflow=NEW&long&locale', 'line'],
      ['mixed-mobile', 'light', 390, 844, 'workflow=NEW&scenario=mixed'],
      ['bundle-ledger', 'ledger', 1440, 1000, 'workflow=NEW&scenario=bundle'],
      ['supplier-mismatch', 'light', 390, 844, 'workflow=NEW&scenario=mismatch', 'validate'],
      ['suspected-duplicate', 'dark', 390, 844, 'workflow=NEW&scenario=duplicate', 'validate'],
      ['restricted-cost', 'light', 390, 844, 'workflow=APPROVED&restricted'],
    ]) {
      const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: name.startsWith('reflow-200') ? 2 : 1 });
      const runtimeErrors = [];
      page.on('pageerror', error => runtimeErrors.push(error.message));
      await page.goto(`${base}/?theme=${theme}&${query}`);
      if (query.includes('restricted')) await page.getByText('Purchase costs are restricted').waitFor();
      else await page.getByRole('heading', { level: 1 }).waitFor(); await page.evaluate(() => document.fonts.ready);
      if (panel === 'validate') await page.getByRole('button', { name: 'Save demo draft', exact: true }).click();
      else if (panel === 'line') await page.getByRole('button', { name: 'Edit line 1', exact: true }).click();
      else if (panel === 'submit') await page.getByRole('button', { name: 'Review & submit demo', exact: true }).click();
      else if (panel === 'correct') await page.getByRole('button', { name: 'Correct purchase', exact: true }).click();
      else if (panel) await page.getByRole('button', { name: new RegExp('^' + panel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).click();
      await page.locator('[role="dialog"]').evaluateAll(async elements => { await Promise.all(elements.flatMap(element => element.getAnimations()).map(animation => animation.finished)); });
      await page.addScriptTag({ path: axePath });
      const audit = await page.evaluate(async () => {
        const result = await window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa', 'best-practice'] } });
        return { violations: result.violations.map(item => ({ id: item.id, impact: item.impact, help: item.help, nodes: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) })), incomplete: result.incomplete.map(item => ({ id: item.id, nodes: item.nodes.length, details: item.nodes.map(node => ({ target: node.target, summary: node.failureSummary })) })), passes: result.passes.length };
      });
      const geometry = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth,
        dialogs: [...document.querySelectorAll('[role="dialog"]')].map(element => ({ width: element.clientWidth, scroll: element.scrollWidth, height: element.getBoundingClientRect().height })),
        footerHeight: document.querySelector('.janso-entry-workspace__actions')?.getBoundingClientRect().height,
        actionPositions: [...document.querySelectorAll('.janso-entry-workspace__actions > button')].map(element => ({ y: element.getBoundingClientRect().y, height: element.getBoundingClientRect().height })),
        actionHeights: [...document.querySelectorAll('.janso-entry-workspace__actions button, [role="dialog"] .janso-overlay-foot button')].map(element => element.getBoundingClientRect().height),
      }));
      // Viewport captures avoid putting a fixed footer across rows in a stitched full-page image.
      await page.screenshot({ path: path.join(output, name + '.png'), fullPage: false, animations: 'disabled', scale: 'css' });
      if (!panel && !query.includes('restricted')) {
        await page.getByRole('region', { name: 'Purchase line entry' }).scrollIntoViewIfNeeded();
        await page.screenshot({ path: path.join(output, name + '-lines.png'), animations: 'disabled', scale: 'css' });
      }
      results.push({ name, theme, width, height, query, panel, runtimeErrors, geometry, audit });
      console.log(`${name}: ${audit.violations.length} accessibility findings; document ${geometry.document}/${width}`);
      await page.close();
    }
    fs.writeFileSync(path.join(output, 'audit.json'), JSON.stringify({ browser: browser.version(), axe: '4.10.3', checkedAt: new Date().toISOString(), surface: base, zoom: '200% layout equivalent: 720x500 CSS pixels at DPR 2, corresponding to a 1440x1000 display; not browser-toolbar automation.', results }, null, 2) + '\n');
    fs.writeFileSync(path.join(output, 'incomplete-review.json'), JSON.stringify({ reviewedAt: new Date().toISOString(), review: 'Remaining gradient backgrounds are checked against both theme-token stops by the 308-test shared contrast suite. Disclosure glyphs are decorative and their enclosing buttons have explicit accessible names. Unsupported generic ARIA labels were fixed, not waived. This review is not a human screen-reader or WCAG certification.', cases: results.filter(row => row.audit.incomplete.length).map(row => ({ name: row.name, incomplete: row.audit.incomplete })) }, null, 2) + '\n');
    assert(results.filter(row => row.width <= 720 && row.geometry.actionPositions.length === 2).every(row => Math.abs(row.geometry.actionPositions[0].y - row.geometry.actionPositions[1].y) < 1), 'Compact review/save actions should share a row');
    assert(results.every(row => row.geometry.document <= row.width && row.geometry.dialogs.every(dialog => dialog.scroll <= dialog.width) && !row.runtimeErrors.length && !row.audit.violations.length && row.audit.incomplete.every(item => item.id === 'color-contrast') && (row.width > 720 || row.geometry.actionHeights.every(height => height >= 44))), 'Quality findings need review; see phase5/audit.json');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
